"""FastAPI app: a JSON agent endpoint and a streaming (SSE) one, behind Supabase auth."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from app.agent import DEFAULT_SYSTEM, get_chain
from app.auth import User, current_user
from app.config import Settings

log = logging.getLogger("agent")

# Seconds between keepalive comments while the model is thinking, so proxies don't time out.
KEEPALIVE_SECONDS = 15.0
STATIC = Path(__file__).resolve().parent.parent / "static"


class AgentQuery(BaseModel):
    user_input: str = Field(min_length=1, max_length=20_000)
    system_instruction: str = DEFAULT_SYSTEM


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="FastAPI + LangChain AI Agent Starter",
        description="LLM agent endpoints with Supabase auth and live streaming over SSE.",
        version="2.0.0",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )
    if not settings.auth_enabled:
        log.warning("Auth is OFF: set SUPABASE_URL or SUPABASE_JWT_SECRET before deploying.")

    @app.get("/")
    def check_server_status():
        return {"status": "active", "framework": "FastAPI + LangChain AI Suite", "auth": settings.auth_enabled}

    @app.get("/demo", include_in_schema=False)
    def demo_page():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/v1/me")
    async def me(user: User = Depends(current_user)):
        return {"id": user.id, "email": user.email}

    @app.post("/api/v1/agent/run")
    async def run_agent(data: AgentQuery, user: User = Depends(current_user), chain: Runnable = Depends(get_chain)):
        try:
            response = await chain.ainvoke({"system": data.system_instruction, "input": data.user_input})
        except HTTPException:
            raise
        except Exception as e:
            log.exception("agent run failed for user %s", user.id)
            raise HTTPException(502, f"model call failed: {e}") from e
        return {"success": True, "agent_response": response.content}

    @app.post("/api/v1/agent/stream")
    async def stream_agent(data: AgentQuery, user: User = Depends(current_user), chain: Runnable = Depends(get_chain)):
        """Stream the answer as Server-Sent Events: `token` events, then one `done` (or `error`)."""
        inputs = {"system": data.system_instruction, "input": data.user_input}
        return StreamingResponse(
            sse_events(chain, inputs, user),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",  # stop nginx (and friends) buffering the stream
                "Connection": "keep-alive",
            },
        )

    return app


def sse(event: str, data: dict, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


async def sse_events(chain: Runnable, inputs: dict, user: User) -> AsyncIterator[str]:
    """Turn the chain's token stream into SSE frames, with keepalives while the model is quiet."""
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for chunk in chain.astream(inputs):
                if chunk.content:
                    await queue.put(("token", chunk.content))
            await queue.put(("done", None))
        except Exception as e:  # sent to the client as an `error` event
            log.exception("agent stream failed for user %s", user.id)
            await queue.put(("error", str(e)))

    task = asyncio.create_task(pump())
    seq, parts = 0, []
    try:
        while True:
            try:
                kind, value = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:  # same class as TimeoutError on 3.11+
                yield ": keepalive\n\n"
                continue
            seq += 1
            if kind == "token":
                parts.append(value)
                yield sse("token", {"text": value}, seq)
            elif kind == "done":
                yield sse("done", {"text": "".join(parts)}, seq)
                return
            else:
                yield sse("error", {"message": value}, seq)
                return
    finally:
        task.cancel()  # client went away: stop paying for tokens nobody will read


app = create_app()
