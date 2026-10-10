# FastAPI + LangChain AI Agent Starter

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C.svg)](https://www.langchain.com)

A small, free FastAPI app that puts an LLM agent behind a JSON endpoint. Clone it, add your OpenAI key, and you have a working `POST /api/v1/agent/run` you can call from any frontend, script or automation tool.

It's one file of real code, so you can read all of it in two minutes and change anything.

- One FastAPI app with a health check and an agent endpoint
- LangChain prompt → model chain, called async so the server stays responsive
- Typed request body with Pydantic, so `/docs` shows exactly what to send
- Keys and model name read from `.env`, never hard-coded
- MIT licensed: use it in personal or client work

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

Open http://127.0.0.1:8000/docs to try the endpoint in your browser, or call it from a terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Write a 3-step onboarding email sequence for a B2B SaaS"}'
```

```json
{ "success": true, "agent_response": "Email 1: Welcome..." }
```

---

## The API

| Method | Path | What it does |
|---|---|---|
| `GET` | `/` | Health check. Returns `{"status": "active", ...}`. |
| `POST` | `/api/v1/agent/run` | Sends your input to the model and returns its answer. |
| `GET` | `/docs` | Interactive API docs (built in to FastAPI). |

Request body for `/api/v1/agent/run`:

| Field | Required | Default |
|---|---|---|
| `user_input` | yes | — |
| `system_instruction` | no | `"You are an advanced B2B operations optimization assistant."` |

## Configuration

Set these in `.env`:

| Variable | Required | Default |
|---|---|---|
| `OPENAI_API_KEY` | yes | — |
| `OPENAI_MODEL` | no | `gpt-4o-mini` |

## Project layout

```text
.
├── main.py            # the whole app: routes, request model, LangChain chain
├── requirements.txt
├── .env.example       # copy to .env and add your key
└── LICENSE            # MIT
```

## Ideas for what to build next

- Change `system_instruction` per route to make specialised agents (support, research, sales emails).
- Swap `ChatOpenAI` for another LangChain chat model to use a different provider.
- Add an API key check on the route before you put it on the internet.

---

## Need the rest of the stack?

This starter is the backend endpoint. A real AI product also needs logins, separate data for each customer, live streaming of agent output, cost tracking and a deploy setup. That part is what **AI Agent Boilerplate Pro** is for.

| | This free starter | Pro |
|---|---|---|
| FastAPI agent endpoint | ✅ | ✅ |
| Next.js dashboard | — | ✅ |
| Supabase login + per-customer data isolation (RLS) | — | ✅ |
| Agent output streamed live to the browser | — | ✅ |
| Token and cost tracking per run | — | ✅ |
| Multi-agent CrewAI crews + white-label client portal | — | Agency tier |
| Price | Free, MIT | One-time payment, full source |

**[See what's in Pro →](https://theapplab.gumroad.com/l/ai-agent-boilerplate?utm_source=github&utm_medium=readme&utm_campaign=free_starter)**

## License

MIT. See [LICENSE](LICENSE).

Found a bug or want something added? [Open an issue](https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate/issues). A ⭐ helps other developers find this repo.
