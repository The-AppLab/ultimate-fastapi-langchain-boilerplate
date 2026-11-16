---
title: "Row-level security on pgvector is not enough on its own: the two-tenant test that caught my leak"
published: true
description: "A Reddit comment was right. Here is the Postgres RLS setup for a multi-tenant pgvector knowledge base, the test that proves it, and the bug it found."
tags: supabase, postgres, security, python
cover_image: https://raw.githubusercontent.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/main/docs/articles/covers/cover-article-4.png
---

A few weeks ago I posted about a multi-tenant AI agent kit I build and sell. One comment stuck with me:

> RLS on the vector table gets missed because similarity search looks fine with one customer.

My first reaction was "I have RLS on that table." My second reaction, after a day, was to go and prove it. This post is what I found: the policies, the test that actually proves isolation, the ways my old test was lying to me, and one real bug the new test turned up.

## The setup

Each workspace (tenant) uploads documents. They get chunked, embedded and stored in one `memories` table. An agent searches them with pgvector during a run.

```sql
create table memories (
  id          uuid primary key default gen_random_uuid(),
  org_id      uuid not null references orgs(id) on delete cascade,
  agent_id    uuid references agents(id) on delete cascade,  -- null = workspace-wide
  content     text not null,
  embedding   vector(1536) not null,
  metadata    jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index on memories using hnsw (embedding vector_cosine_ops);
alter table memories enable row level security;
```

Two code paths read this table:

1. **The API**, as the signed-in user. The FastAPI app opens a connection, sets the request's JWT claims, and queries under the `authenticated` role, so Postgres applies RLS using `auth.uid()`.
2. **The agent's `knowledge_search` tool**, inside a background worker. Workers have no user session, so they use a service connection that bypasses RLS and filter by `org_id` explicitly.

## The policies

Staff of a workspace (owner, admin, member) can read, insert and delete that workspace's memories. Clients (a separate role in the Agency tier) cannot touch this table at all.

```sql
create or replace function is_staff_of(org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from org_members m
    where m.org_id = org and m.user_id = auth.uid()
      and m.role in ('owner','admin','member')
  );
$$;

create policy memories_select on memories for select
  using (is_staff_of(org_id));

create policy memories_insert on memories for insert
  with check (is_staff_of(org_id));

create policy memories_delete on memories for delete
  using (is_staff_of(org_id));
```

So far this is the textbook setup, and the textbook setup is where I stopped the first time.

## The test that was lying to me

My original isolation test looked reasonable: create user A with documents, create user B, search as B, assert B gets nothing back.

It passed. It also kept passing when I did the following on purpose:

- Replaced `is_staff_of(org_id)` with `true` in the select policy.
- Removed the `org_id` filter from the worker's query.

Why? Because **B had no data and A's documents were about a different topic**. A similarity search as B with a broken policy returned A's rows, but my assertion only checked that the top result was not one of B's seeded ids. There were none. "The other user has nothing" is not a test; it is a coin that always lands on the same side.

## The test that is not lying

The new test seeds two workspaces with **near-identical documents about the same subject**, so that if anything leaks, the other tenant's rows rank first, not last.

```python
DOCS_A = ["Refund policy: full refund within 14 days. Contact billing@acme.example."]
DOCS_B = ["Refund policy: full refund within 30 days. Contact billing@globex.example."]

async def test_vector_search_with_two_seeded_tenants(api, db, worker):
    a, b = await seed_org("Acme", DOCS_A), await seed_org("Globex", DOCS_B)

    # 1. API search as tenant A's user
    r = await api.get("/memory/search", params={"q": "refund policy"}, headers=auth(a.user))
    assert all(m["org_id"] == a.org_id for m in r.json()["results"])
    assert "globex" not in r.text.lower()

    # 2. The agent's knowledge tool inside a real run (worker connection, no RLS)
    run = await worker.run_agent(a.agent_id, "What is our refund window?")
    hits = [e for e in run.events if e.type == "tool_result" and e.tool == "knowledge_search"]
    assert hits and "globex" not in hits[0].output.lower()

    # 3. Raw SQL as tenant A with NO where clause: RLS alone must do the work
    async with db.as_user(a.user) as conn:
        rows = await conn.fetch("select org_id from memories")
    assert {r["org_id"] for r in rows} == {a.org_id}

    # 4. Cross-tenant insert is refused
    async with db.as_user(a.user) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "insert into memories (org_id, content, embedding) values ($1, 'x', $2)",
                b.org_id, zeros(1536),
            )

    # 5. Cross-tenant delete deletes nothing
    async with db.as_user(a.user) as conn:
        tag = await conn.execute("delete from memories where org_id = $1", b.org_id)
    assert tag == "DELETE 0"
    assert await count_memories(b.org_id) == len(DOCS_B)
```

Then I broke things on purpose again. This is the matrix that matters:

| Sabotage | Old test | New test |
|---|---|---|
| `using (true)` in the select policy | passes | **fails** (check 1 and 3) |
| `alter table memories disable row level security` | passes | **fails** (check 3, 4, 5) |
| Remove `org_id` filter in the worker | passes | **fails** (check 2) |
| Drop the new agent/org policy (below) | n/a | **fails** |

Every row that says "passes" in the old column is a leak that would have shipped.

A note on check 2: **any path that uses the service role needs its own test**, because RLS is not protecting it. Workers, cron jobs, admin scripts. The policy can be perfect and the worker can still hand one tenant's documents to another.

## The bug it found

Check 2 passed, but while writing it I noticed something else. Uploading knowledge took an optional `agent_id` to pin a document to one agent. The insert policy checked `is_staff_of(org_id)`, and the foreign key checked that the agent existed. Nothing checked that **the agent belonged to the same workspace**.

So a user in workspace A could attach a document, in A, to an agent id from workspace B. Searches were still scoped by `org_id`, so B never saw A's document and A never saw B's. Nothing leaked. But it is exactly the kind of gap that becomes a leak the day someone adds "search by agent" without re-reading the policies.

The fix is one more policy and a 404 in the API:

```sql
create policy memories_agent_same_org on memories
  as restrictive for insert
  with check (
    agent_id is null or exists (
      select 1 from agents a where a.id = agent_id and a.org_id = memories.org_id
    )
  );
```

`restrictive` matters: it is ANDed with the permissive policies instead of ORed, so it can only take rights away.

## Takeaways

1. Seed two tenants with competing data. A second user with no data proves nothing.
2. Assert on what came back, not only on what did not. "No B ids in the results" passes when there are no B ids anywhere.
3. Sabotage your own policies and watch the test go red. If it stays green, the test is not testing.
4. Every service-role path (workers, cron) gets its own isolation test; RLS does not apply there.
5. Use `restrictive` policies for invariants like "the agent must belong to this org".
6. Run the suite against real Postgres with the real migrations. Mocked RLS is theatre.

There has been no outside audit of any of this, and I would not claim there has. What I can say is that the test above runs on every push, and it fails when it should.

---

*This is the memory layer of [AI Agent Boilerplate Pro](https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=rls), a Next.js 16 + FastAPI + Supabase kit I build. The backend core (Supabase JWT verification, SSE streaming, 16 tests) is [free and MIT on GitHub](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate). Questions about the policies are welcome in the comments; I answer all of them.*
