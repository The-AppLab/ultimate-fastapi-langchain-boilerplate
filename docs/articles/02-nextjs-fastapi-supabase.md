---
title: "Next.js + FastAPI + Supabase starter: auth, row-level security and streaming, wired together (2026)"
published: true
description: "How to wire Next.js to FastAPI with Supabase auth: verify Supabase JWTs in Python, enforce RLS per user, and stream results with SSE."
tags: nextjs, fastapi, supabase, python
cover_image: https://raw.githubusercontent.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/main/docs/articles/covers/cover-article-2.png
---

Next.js for the UI, FastAPI for the Python work (agents, data, ML), Supabase for auth and Postgres: it's a popular stack, and the hard part isn't any one of them. It's the seams between them. This guide covers the three seams you'll hit first, with working code.

**What you'll end up with**

```text
Browser (Next.js)  --Supabase session-->  Supabase Auth
       |                                       |
       |  Authorization: Bearer <access token> |
       v                                       |
FastAPI  --verify JWT (HS256 or JWKS)----------+
       |
       |  set role authenticated + JWT claims
       v
Postgres (Supabase)  -- row-level security decides what this user can see
```

## Seam 1: send the Supabase token from Next.js to FastAPI

Supabase signs the user in on the Next.js side. Every call to your Python API should carry the user's access token in the `Authorization` header. A small typed wrapper keeps that in one place:

```ts
export async function accessToken(): Promise<string | null> {
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = await accessToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_URL}${path}`, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (res.status === 204 ? undefined : await res.json()) as T;
}
```

Don't forget CORS on the FastAPI side: allow your Next.js origin and the `Authorization` header.

## Seam 2: verify Supabase JWTs in FastAPI (both key types)

Supabase projects sign access tokens with either the legacy shared secret (HS256) or newer asymmetric keys published as a JWKS. If you only handle one, your API breaks the day the project switches. Read the token's header and pick the key:

```python
import jwt

@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600)

def decode_supabase_jwt(token: str, settings: Settings) -> dict:
    try:
        alg = jwt.get_unverified_header(token).get("alg", "HS256")
        if alg == "HS256":
            key = settings.supabase_jwt_secret
        else:
            jwks_url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key,
            algorithms=["HS256", "RS256", "ES256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}") from e
```

Wrap it in a FastAPI dependency that reads `Authorization: Bearer ...`, and every route gets `user = Depends(get_principal)`. A missing or bad token is a 401, never a 500.

## Seam 3: let Postgres enforce who sees what

The tempting shortcut is to connect to Postgres as a superuser and add `WHERE org_id = :org` to every query. One forgotten `WHERE` and a customer sees another customer's data.

Instead, do what Supabase's own REST API does: open a transaction, set the user's JWT claims, and switch to the `authenticated` role. Now every row-level security policy applies to every query, including ones you forgot to filter.

```python
@asynccontextmanager
async def as_user(self, principal):
    async with self.pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "select set_config('request.jwt.claims', $1, true), "
            "set_config('role', 'authenticated', true)",
            json.dumps(principal.claims),
        )
        yield conn
```

And the policies, for example on a `runs` table:

```sql
alter table public.runs enable row level security;

create policy runs_select on public.runs for select to authenticated
  using (public.is_staff(org_id) or created_by = auth.uid());
```

Turn RLS on for **every** table that holds customer data, including your pgvector table. Without it, a similarity search can return another customer's documents.

**Test it.** Create two users in two workspaces. Have user A create a row. Check that user B gets a 403 or 404 through the API, then run raw SQL as user B with no `WHERE` clause and assert zero of A's rows come back. Run that test in CI.

## Bonus seam: stream long results without leaking the token

For long-running work (an agent run, a report), return a job id immediately and stream progress with server-sent events. Two details matter:

1. **Use `fetch`, not `EventSource`.** `EventSource` can't send headers, which pushes people to put the JWT in the URL, where it ends up in logs. A fetch-based reader keeps it in `Authorization`.
2. **Store events with an increasing id and resume from `Last-Event-ID`.** Then a dropped connection picks up exactly where it left off.

On the FastAPI side, send these headers so proxies don't buffer the stream, plus a comment line every few seconds as a keep-alive:

```python
return StreamingResponse(
    gen(),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
)
# inside gen(), when idle:  yield ": keep-alive\n\n"
```

## Local development

Run Supabase locally with its CLI (it needs Docker), apply your migrations with it, then start FastAPI on :8000 and Next.js on :3000. Keep one `.env` and make sure every process actually loads it; a classic bug is the API process never seeing your model or Supabase keys.

## A starter with all of this done

*Disclosure: I'm the maker of AI Agent Boilerplate Pro, which is this exact stack already wired and tested: Next.js 16 + FastAPI + Supabase, JWT checks for both key types, workspaces and roles, RLS on every table (with the two-user test), resumable SSE streaming, and per-run cost tracking for AI agents. Starter $99, Agency $299, one-time, with a 14-day guarantee: https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=stack*

*Free alternatives: the MIT FastAPI + LangChain starter (https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate) and the AI Agent SaaS Production Checklist PDF (https://theapplab-checklist.subscribepage.io/?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=checklist).*
