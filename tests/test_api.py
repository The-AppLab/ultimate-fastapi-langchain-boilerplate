"""No API keys needed: the model is a fake, and tokens are signed with a test secret."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate

from app.agent import get_chain
from app.config import Settings
from app.main import create_app

SECRET = "test-secret-at-least-32-bytes-long!!"


def settings(**overrides) -> Settings:
    base = dict(
        openai_api_key="", openai_model="gpt-4o-mini", supabase_url="",
        supabase_jwt_secret=SECRET, jwt_audience="authenticated",
    )
    return Settings(**{**base, **overrides})


def fake_chain(text: str = "Hello there, agent here."):
    model = GenericFakeChatModel(messages=iter([AIMessage(content=text)]))
    return ChatPromptTemplate.from_messages([("system", "{system}"), ("user", "{input}")]) | model


def client(s: Settings | None = None, text: str = "Hello there, agent here.") -> TestClient:
    app = create_app(s or settings())
    app.dependency_overrides[get_chain] = lambda: fake_chain(text)
    return TestClient(app)


def token(**claims) -> str:
    base = {"sub": "user-123", "email": "a@example.com", "role": "authenticated",
            "aud": "authenticated", "exp": int(time.time()) + 300}
    return jwt.encode({**base, **claims}, SECRET, algorithm="HS256")


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines() if not line.startswith(":"))
        if "event" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_health_is_public():
    r = client().get("/")
    assert r.status_code == 200 and r.json()["auth"] is True


def test_missing_token_is_rejected():
    r = client().post("/api/v1/agent/run", json={"user_input": "hi"})
    assert r.status_code == 401


@pytest.mark.parametrize("bad", [
    {"exp": int(time.time()) - 10},          # expired
    {"aud": "someone-else"},                 # wrong audience
    {"role": "anon"},                        # the anon key's token, not a user
])
def test_bad_tokens_are_rejected(bad):
    r = client().post("/api/v1/agent/run", json={"user_input": "hi"}, headers=auth(token(**bad)))
    assert r.status_code == 401


def test_token_signed_with_wrong_secret_is_rejected():
    forged = jwt.encode({"sub": "x", "role": "authenticated", "aud": "authenticated",
                         "exp": int(time.time()) + 60}, "a-different-secret-32-bytes-long!!", algorithm="HS256")
    assert client().get("/api/v1/me", headers=auth(forged)).status_code == 401


def test_me_returns_the_signed_in_user():
    r = client().get("/api/v1/me", headers=auth(token()))
    assert r.json() == {"id": "user-123", "email": "a@example.com"}


def test_run_returns_the_answer():
    r = client().post("/api/v1/agent/run", json={"user_input": "hi"}, headers=auth(token()))
    assert r.status_code == 200
    assert r.json() == {"success": True, "agent_response": "Hello there, agent here."}


def test_stream_sends_tokens_then_done():
    with client().stream("POST", "/api/v1/agent/stream", json={"user_input": "hi"}, headers=auth(token())) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["x-accel-buffering"] == "no"
        events = parse_sse(r.read().decode())
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done" and kinds.count("token") > 1
    streamed = "".join(d["text"] for k, d in events if k == "token")
    assert streamed == events[-1][1]["text"] == "Hello there, agent here."


def test_stream_reports_model_errors_as_an_event():
    app = create_app(settings())

    class Broken:
        async def astream(self, _inputs):
            raise RuntimeError("rate limited")
            yield  # pragma: no cover

    app.dependency_overrides[get_chain] = lambda: Broken()
    with TestClient(app).stream("POST", "/api/v1/agent/stream", json={"user_input": "hi"},
                                headers=auth(token())) as r:
        events = parse_sse(r.read().decode())
    assert events == [("error", {"message": "rate limited"})]


def test_auth_off_without_supabase_settings():
    c = client(settings(supabase_jwt_secret=""))
    assert c.post("/api/v1/agent/run", json={"user_input": "hi"}).status_code == 200


def test_missing_openai_key_gives_a_clear_error():
    c = TestClient(create_app(settings()))  # real chain, no key
    r = c.post("/api/v1/agent/run", json={"user_input": "hi"}, headers=auth(token()))
    assert r.status_code == 500 and "OPENAI_API_KEY" in r.json()["detail"]


def test_empty_input_is_rejected():
    r = client().post("/api/v1/agent/run", json={"user_input": ""}, headers=auth(token()))
    assert r.status_code == 422


def test_demo_page_is_served():
    r = client().get("/demo")
    assert r.status_code == 200 and "agent/stream" in r.text


def test_keepalive_comments_while_the_model_is_quiet(monkeypatch):
    import asyncio

    import app.main as main_mod

    monkeypatch.setattr(main_mod, "KEEPALIVE_SECONDS", 0.05)

    class Slow:
        async def astream(self, _inputs):
            await asyncio.sleep(0.2)
            yield AIMessage(content="late")

    app = create_app(settings())
    app.dependency_overrides[get_chain] = lambda: Slow()
    with TestClient(app).stream("POST", "/api/v1/agent/stream", json={"user_input": "hi"},
                                headers=auth(token())) as r:
        body = r.read().decode()
    assert ": keepalive" in body
    assert parse_sse(body)[-1] == ("done", {"text": "late"})


def test_asymmetric_tokens_are_checked_against_jwks(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec

    import app.auth as auth_mod

    private = ec.generate_private_key(ec.SECP256R1())
    seen = {}

    class FakeJWKS:
        def get_signing_key_from_jwt(self, _token):
            return type("K", (), {"key": private.public_key()})()

    def fake_client(url):
        seen["url"] = url
        return FakeJWKS()

    monkeypatch.setattr(auth_mod, "_jwks_client", fake_client)
    s = settings(supabase_url="https://abc.supabase.co", supabase_jwt_secret="")
    t = jwt.encode({"sub": "u-es", "role": "authenticated", "aud": "authenticated",
                    "exp": int(time.time()) + 60}, private, algorithm="ES256")
    r = client(s).get("/api/v1/me", headers=auth(t))
    assert r.status_code == 200 and r.json()["id"] == "u-es"
    assert seen["url"] == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
