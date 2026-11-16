---
title: "CrewAI starter: how to run CrewAI crews inside a real web app (FastAPI, streaming, cost limits)"
published: true
description: "Define a crew, run it in a background worker, stream task results to the browser, cap iterations and record token cost per run."
tags: crewai, python, ai, fastapi
cover_image: https://raw.githubusercontent.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/main/docs/articles/covers/cover-article-3.png
---

Most CrewAI examples end with `crew.kickoff()` in a script. The moment you put a crew behind a web app, four new problems show up: the request times out, the user stares at a spinner, nobody knows what the run cost, and one confused agent loops until your API bill hurts. Here's the structure I use to solve all four.

## 1. Define the crew as a plain module

Keep each crew in one file with its inputs and output type declared next to it. The web app can then build a form from `INPUTS` and render the typed result from `OUTPUT`, without knowing anything about CrewAI.

```python
from agentkit.schemas import ResearchReport

NAME = "research_crew"
DESCRIPTION = "A researcher gathers sources on a topic, an analyst turns them into a cited report."
INPUTS = [
    {"name": "topic", "label": "Topic", "type": "text"},
    {"name": "audience", "label": "Who is the report for?", "type": "text"},
]
OUTPUT = ResearchReport
TOOLS = ["web_search", "http_fetch", "knowledge_search"]

def build(llm, tools):
    from crewai import Agent, Crew, Process, Task

    researcher = Agent(
        role="Senior Researcher",
        goal="Find accurate, current, well-sourced information about {topic}",
        backstory="You verify claims against primary sources and always keep the URL.",
        llm=llm, tools=tools, allow_delegation=False,
    )
    analyst = Agent(
        role="Research Analyst",
        goal="Turn raw research into a clear report for {audience}",
        backstory="You write tight executive summaries and never invent facts or sources.",
        llm=llm, allow_delegation=False,
    )
    gather = Task(
        description="Research {topic}. Collect 5-8 key facts, each with its source URL.",
        expected_output="A bullet list of facts, each followed by its source URL.",
        agent=researcher,
    )
    report = Task(
        description="Write a report on {topic} for {audience} using only the research provided.",
        expected_output="A research report with summary, key findings and sources.",
        agent=analyst, context=[gather], output_pydantic=ResearchReport,
    )
    return Crew(agents=[researcher, analyst], tasks=[gather, report], process=Process.sequential)
```

`output_pydantic` matters: if the crew's output feeds a UI, you want a validated object, not free text.

## 2. Never run a crew inside the web request

A crew can take a minute or more. Inside a request, that's a timeout and a blocked worker. Instead:

1. `POST /runs` inserts a row with status `queued` and returns the id immediately.
2. A background worker claims queued runs with `SELECT ... FOR UPDATE SKIP LOCKED`, so several API instances can share one queue safely.
3. `crew.kickoff()` is synchronous, so the worker runs it in a thread to keep the event loop free:

```python
result = await asyncio.to_thread(crew.kickoff, inputs=inputs)
```

Add a timeout, a cancel flag the worker checks, and crash recovery (runs stuck in `running` after a restart get re-queued or failed).

## 3. Stream what the crew is doing

CrewAI calls back from its own thread. Push those callbacks onto an asyncio queue with `call_soon_threadsafe`, and a small pump task writes them to your event store, which the browser reads over SSE:

```python
loop = asyncio.get_running_loop()
events: asyncio.Queue = asyncio.Queue()

def push(type_, data):
    loop.call_soon_threadsafe(events.put_nowait, (type_, data))

def on_task(out):
    push("task", {"agent": str(getattr(out, "agent", "")), "output": str(out)[:8000]})

crew = module.build(llm, tools)
crew.task_callback = on_task
```

Wrap your tools the same way so every tool call and its result show up live. Users who can watch the researcher's tool calls happen trust the final report a lot more than users who watched a spinner.

## 4. Cap iterations and record cost

Set `max_iter` on every agent (8 is a sensible default), and a `max_tokens` per model call. After the run, read CrewAI's usage metrics and price them:

```python
for agent in crew.agents:
    agent.max_iter = max_iter

# after kickoff
m = crew.usage_metrics
cost = estimate_cost(model, m.prompt_tokens, m.completion_tokens)  # LiteLLM's price table
```

Store tokens and cost on the run row. Then add a monthly budget per workspace and refuse new runs once it's reached. That one check is the difference between "a bug cost me $3" and "a bug cost me $300."

## 5. Choose the model with config, not code

CrewAI's `LLM` class goes through LiteLLM, so `LLM(model="gpt-4o-mini")`, `LLM(model="anthropic/...")` or a local Ollama model is a config change. Read the model name from an environment variable or a per-agent setting.

## 6. Test crews without spending money

Give `build()` a scripted LLM in tests, so the crew's wiring (tools, callbacks, typed output) is checked in CI with no API key. Then do one manual run with a real key before you ship.

## A CrewAI starter with this done

*Disclosure: I'm the maker of AI Agent Boilerplate Pro. Its Agency tier ($299) includes three crews built this way (research, content, support triage), streaming task results and tool calls into a live run view, `max_iter` caps, token and cost metering, a white-label client portal, and a Next.js 16 + FastAPI + Supabase app around them, with tests that run a real CrewAI crew against a scripted model. One-time price, 14-day guarantee: https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=crewai*

*Free: the AI Agent SaaS Production Checklist PDF (https://theapplab-checklist.subscribepage.io/?utm_source=devto&utm_medium=article&utm_campaign=december&utm_content=checklist) and an MIT FastAPI + LangChain starter (https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate).*
