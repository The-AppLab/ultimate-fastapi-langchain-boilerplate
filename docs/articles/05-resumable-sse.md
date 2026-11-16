---
title: "Resumable SSE for LLM streaming in FastAPI: event ids, Last-Event-ID, keepalives and cancellation"
published: true
description: "Streaming model output over Server-Sent Events works in a demo and breaks in production in four specific ways. Here is the FastAPI structure that survives proxies, idle timeouts, closed tabs and dropped connections."
tags: fastapi, python, webdev, ai
cover_image: https://raw.githubusercontent.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/main/docs/articles/covers/cover-article-5.png
---

Streaming tokens from a model to the browser over Server-Sent Events is a forty-line demo. Then you deploy it and four things happen:

1. Nothing streams. The proxy buffers the whole response and delivers it at the end.
2. The connection dies after 60 seconds of "thinking" with no bytes on the wire.
3. Users close the tab and you keep paying for tokens nobody reads.
4. Someone's wifi blips mid-answer and the run is gone. Refresh shows a spinner forever.

This post is the structure I use in FastAPI to handle all four. The first three fit in a small free starter; the fourth needs a database and is where most "streaming" tutorials stop.

## 0. The response that actually streams

```python
from fastapi import Request
from fastapi.responses import StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",   # nginx and friends: do not buffer
    "Connection": "keep-alive",
}

@app.post("/api/v1/agent/stream")
async def stream(req: AgentRequest, request: Request, user=Depends(current_user)):
    return StreamingResponse(
        event_stream(req, request, user),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
```

`X-Accel-Buffering: no` is the header most people are missing. Without it, nginx (and several hosting platforms that run nginx in front of you) collects the whole response before forwarding it.

## 1. Frame every event with an id

SSE frames are text. Give every event an id from day one, even if you do not resume yet; it costs nothing and makes step 4 possible.

```python
def sse(event: str, data: dict, id: int | None = None) -> str:
    out = ""
    if id is not None:
        out += f"id: {id}\n"
    out += f"event: {event}\n"
    out += f"data: {json.dumps(data)}\n\n"
    return out
```

Events I use: `token` (a chunk of text), `tool_call`, `tool_result`, `done` (with the full answer and usage), `error`. The browser switches on `event`, so adding new kinds later does not break old clients.

## 2. Keepalives while the model thinks

A model call can sit for 20 seconds before the first token. Load balancers and some browsers treat silence as death. Send a comment line, which SSE clients ignore, whenever nothing has happened for a while:

```python
async def event_stream(req, request, user):
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_model(req, queue))   # pushes events into the queue
    seq = 0
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is None:                             # producer finished
                break
            seq += 1
            yield sse(item["event"], item["data"], id=seq)
    finally:
        task.cancel()
```

Fifteen seconds is comfortably under the usual 60-second idle timeouts.

## 3. Stop paying when the tab closes

Starlette tells you when the client went away. Check it in the loop and cancel the producer, which cancels the model call:

```python
            if await request.is_disconnected():
                break            # the finally block cancels the task
```

With an async model client, cancelling the task closes the HTTP stream to the provider, and billing stops at the tokens already generated. Without this, a user who refreshes five times has five model calls running.

## 4. Resume after a dropped connection

Everything above is in-memory: the queue lives in the request. If the connection drops, the queue dies with it and the run's output is lost. Resuming needs three changes.

**4a. Persist events as they happen.** The worker that runs the model writes every event to a table with a per-run sequence number, and the API reads from that table instead of from an in-process queue. This also makes the API stateless across instances.

```sql
create table run_events (
  run_id uuid references runs(id) on delete cascade,
  seq    integer not null,
  event  text not null,
  data   jsonb not null,
  primary key (run_id, seq)
);
```

**4b. Replay then follow.** The stream endpoint takes the last id the client saw, replays everything after it, then follows new rows until the run is finished.

```python
@app.get("/api/v1/runs/{run_id}/stream")
async def stream_run(run_id: UUID, request: Request, user=Depends(current_user),
                     last_event_id: int = Header(default=0, alias="Last-Event-ID")):
    await assert_can_read_run(user, run_id)          # RLS does this if you query as the user

    async def gen():
        cursor = last_event_id
        while True:
            if await request.is_disconnected():
                return
            rows = await fetch_events_after(run_id, cursor)   # select ... where seq > $2 order by seq
            for row in rows:
                cursor = row["seq"]
                yield sse(row["event"], row["data"], id=cursor)
                if row["event"] in ("done", "error"):
                    return
            if not rows:
                if await run_is_finished(run_id):      # finished and nothing left to send
                    return
                got = await broker.wait(run_id, timeout=15)   # LISTEN/NOTIFY or a poll
                if not got:
                    yield ": keepalive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
```

`broker.wait` can be Postgres `LISTEN`/`NOTIFY` (the worker notifies on each insert) or, to start, a one-second poll on the table. The poll is embarrassingly simple and works across any number of API instances; I shipped with it and added the broker later.

**4c. Reconnect from the browser with the id.** `EventSource` does send `Last-Event-ID` on reconnect, but it cannot send an `Authorization` header, which pushes people to put the user's token in the URL (where it lands in logs). Use `fetch` with a `ReadableStream` and track the id yourself:

```ts
export async function followRun(runId: string, token: string, onEvent: (e: SseEvent) => void) {
  let lastId = 0, attempt = 0;
  while (true) {
    const res = await fetch(`/api/v1/runs/${runId}/stream`, {
      headers: { Authorization: `Bearer ${token}`, "Last-Event-ID": String(lastId) },
    });
    if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
    attempt = 0;
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += value;
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const frame = parseFrame(buf.slice(0, i)); buf = buf.slice(i + 2);
          if (!frame) continue;                        // keepalive comment
          if (frame.id) lastId = Number(frame.id);
          onEvent(frame);
          if (frame.event === "done" || frame.event === "error") return;
        }
      }
    } catch {
      // fall through to reconnect
    }
    await new Promise(r => setTimeout(r, Math.min(1000 * 2 ** attempt++, 10000)));
  }
}
```

Refresh the page, come back on another device, lose wifi in a tunnel: the client asks for everything after the last id it saw and the server replays it from the table.

## Things that bit me

- **Ids must be per run and monotonic.** A global counter breaks replay when two runs interleave. `(run_id, seq)` as the primary key gives you both ordering and idempotency.
- **Send a terminal event, always.** If the worker crashes, something must write `error` so clients stop reconnecting. A watchdog that marks runs older than their timeout as failed, and writes the event, closes that gap.
- **Do not stream from the worker process.** The API streams from the table; the worker only writes. That is what lets you run two API instances behind a load balancer without sticky sessions.
- **Authenticate the reconnect.** The stream endpoint is a normal authenticated route; with RLS and querying as the user, a client cannot follow a run it cannot read.
- **Keep `done` small-ish.** I include the final text and usage in `done`, which is convenient, but cap it; very long answers already arrived as tokens.

## Where to get the code

Steps 0 to 3 (headers, ids, keepalives, cancellation, and the `fetch`-based demo page) are in a small [free MIT FastAPI + LangChain starter](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate) with 16 tests that need no API keys. Step 4, with the Postgres-backed run queue, the `run_events` table, the follow loop and the React hook, is part of [AI Agent Boilerplate Pro](https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=sse), the paid kit the free starter is cut from.

Corrections welcome, especially on the reconnect loop; it is the part I have rewritten most often.
