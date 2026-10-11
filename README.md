# FastAPI + LangChain AI Agent Starter

[![CI](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/actions/workflows/ci.yml/badge.svg)](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C.svg)](https://www.langchain.com)

A small, free FastAPI backend for an LLM agent, with the three parts that usually take a weekend to get right:

- **Supabase auth in Python.** A FastAPI dependency that verifies Supabase access tokens, both the legacy shared-secret (HS256) tokens and the newer asymmetric keys (JWKS, RS256/ES256). Checks signature, expiry, audience and that the token belongs to a signed-in user.
- **Live streaming over SSE.** `POST /api/v1/agent/stream` sends tokens as they arrive, with the headers that stop nginx-style proxies buffering the whole answer, keepalive comments while the model is thinking, and cancellation when the browser goes away (so you stop paying for tokens nobody reads).
- **A browser demo that streams with `fetch`, not `EventSource`**, so the token travels in a header instead of the URL.

Plus a plain JSON endpoint, typed requests with Pydantic, 16 tests that need no API keys, and CI on Python 3.10, 3.12 and 3.13. About 250 lines of app code you can read in ten minutes. MIT licensed.

---

## Quickstart

You need Python 3.10 or newer and an [OpenAI API key](https://platform.openai.com/api-keys).

```bash
git clone https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate.git
cd ultimate-fastapi-langchain-boilerplate

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env               # then paste your key into OPENAI_API_KEY

uvicorn main:app --reload
```

Open http://127.0.0.1:8000/demo to watch an answer stream in, or http://127.0.0.1:8000/docs for the API.

With no Supabase settings in `.env`, auth is off so you can try it straight away (the server logs a warning). **Turn it on before you deploy** (see below).

```bash
curl -N -X POST http://127.0.0.1:8000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Write a 3-step onboarding email sequence for a B2B SaaS"}'
```

```text
id: 1
event: token
data: {"text": "Email"}

id: 2
event: token
data: {"text": " 1:"}
...
id: 87
event: done
data: {"text": "Email 1: Welcome..."}
```

---

## The API

| Method | Path | Auth | What it does |
|---|---|---|---|
| `GET` | `/` | no | Health check. Says whether auth is on. |
| `GET` | `/api/v1/me` | yes | The signed-in Supabase user (`id`, `email`). |
| `POST` | `/api/v1/agent/run` | yes | Sends your input to the model and returns the whole answer as JSON. |
| `POST` | `/api/v1/agent/stream` | yes | Same, streamed as Server-Sent Events: `token` events, then `done` (or `error`). |
| `GET` | `/demo` | no | A one-file HTML page that calls the stream endpoint. |
| `GET` | `/docs` | no | Interactive API docs (built in to FastAPI). |

Request body for both agent endpoints:

| Field | Required | Default |
|---|---|---|
| `user_input` | yes | — |
| `system_instruction` | no | `"You are an advanced B2B operations optimization assistant."` |

## Supabase auth

Set one or both in `.env`:

| Variable | Use it when |
|---|---|
| `SUPABASE_URL` | Your project signs tokens with the new asymmetric signing keys. Keys are fetched from `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` and cached for 10 minutes. |
| `SUPABASE_JWT_SECRET` | Your project still uses the legacy JWT secret (Project Settings → API). |
| `SUPABASE_JWT_AUDIENCE` | Optional. Defaults to `authenticated`. |

From your frontend, send the signed-in user's access token:

```ts
const { data } = await supabase.auth.getSession();
await fetch("/api/v1/agent/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${data.session.access_token}` },
  body: JSON.stringify({ user_input: "..." }),
});
```

In your own routes, depend on the user:

```python
from fastapi import Depends
from app.auth import User, current_user

@app.get("/api/v1/things")
async def things(user: User = Depends(current_user)):
    ...  # user.id is the Supabase auth.users id
```

## Configuration

| Variable | Required | Default |
|---|---|---|
| `OPENAI_API_KEY` | yes | — |
| `OPENAI_MODEL` | no | `gpt-4o-mini` |
| `SUPABASE_URL` / `SUPABASE_JWT_SECRET` | before deploying | auth off |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a fake chat model and tokens signed with a test key, so they need no OpenAI key or Supabase project. They cover expired, forged and wrong-audience tokens, the anon role, JWKS keys, SSE framing, keepalives and model errors mid-stream.

## Project layout

```text
.
├── app/
│   ├── main.py        # routes, SSE stream with keepalives and cancellation
│   ├── auth.py        # Supabase JWT verification (HS256 + JWKS)
│   ├── agent.py       # the LangChain prompt → model chain; swap the model here
│   └── config.py      # settings from .env
├── static/index.html  # streaming demo page (fetch + ReadableStream)
├── tests/test_api.py
├── main.py            # keeps `uvicorn main:app` working
├── requirements.txt
└── .env.example
```

## Ideas for what to build next

- Change `system_instruction` per route to make specialised agents (support, research, sales emails).
- Swap `ChatOpenAI` in `app/agent.py` for another LangChain chat model to use a different provider.
- Restrict `allow_origins` in `app/main.py` to your frontend's domain.

---

## Need the rest of the stack?

This starter is the backend core. A product people pay for also needs a dashboard, separate data for each customer, runs that survive a dropped connection, cost tracking and a deploy setup. That part is what **AI Agent Boilerplate Pro** is for. (I'm the maker, Rob.)

| | This free starter | Pro |
|---|---|---|
| FastAPI agent endpoints | ✅ | ✅ |
| Supabase token verification (HS256 + JWKS) | ✅ | ✅ |
| Agent output streamed over SSE | ✅ | ✅, plus resume after a dropped connection |
| Next.js 16 dashboard (agents, runs, usage, settings) | — | ✅ |
| Multi-tenant workspaces with row-level security on every table | — | ✅ |
| Tool calling, pgvector knowledge base, Postgres run queue | — | ✅ |
| Token and cost tracking per run, monthly budgets | — | ✅ |
| 3 CrewAI crews + white-label client portal + deploy scripts | — | Agency tier |
| Price | Free, MIT | One-time payment, full source |

**[See what's in Pro →](https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=github&utm_medium=readme&utm_campaign=evergreen)**

## License

MIT. See [LICENSE](LICENSE).

Found a bug or want something added? [Open an issue](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/issues).
