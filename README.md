# Ultimate FastAPI + LangChain AI Agent Boilerplate (Core Lite)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-Enabled-green.svg)](https://www.langchain.com)
[![npm](https://img.shields.io/badge/npm-create--ai--agent--boilerplate-CB3837?logo=npm)](https://www.npmjs.com/package/create-ai-agent-boilerplate)

Welcome to the ultimate open-source infrastructure foundation for building production-grade AI Automation Agents, asynchronous backend microservices, and specialized workflows. Designed explicitly for B2B AI Automation Agencies (AAA) and indie hackers who want to build and ship software rapidly.

This core repository provides a clean, ultra-lightweight environment layout to eliminate tedious structural configuration loops and get your AI features running locally in under 5 minutes.

---

## UPGRADE TO THE COMPLETE PRODUCTION-READY PRO VERSION
> **Looking to save an extra 40+ hours of setup, deploy structural database endpoints, and monetize your apps instantly?**
> ### [Get the AI Agent Boilerplate PRO Stack Here!](https://theapplab.gumroad.com/l/ai-agent-boilerplate)
> **The Pro stack includes:** a Next.js + FastAPI + CrewAI + Supabase monorepo with Supabase Auth, row-level-security multi-tenancy, SSE-streamed agent runs, per-run token and cost tracking, pgvector memory, ready-made CrewAI crews, a white-label client portal and deploy scripts for Vercel and Railway.

---

## Features Included in the Core Framework
- **FastAPI Framework Engine:** Production-ready asynchronous route handler framework optimized for highly scalable, sub-millisecond execution times.
- **LangChain Core Integration:** Clean, modern infrastructure setup configured natively to pipe incoming data matrices straight into advanced Language Models.
- **Secure Configuration Mapping:** Isolated local environment properties layer to ensure your production API keys are completely protected from exposure threats.

## Quick Local Start Setup Guide

Follow these simple structural commands to run this AI boilerplate locally on your workspace:

### 1. Download the Project Blueprints
```bash
git clone https://github.com/The-AppLab/ultimate-fastapi-langchain-boilerplate.git
cd ultimate-fastapi-langchain-boilerplate
```

### 2. Configure Your Isolated Environment Wrapper
```bash
python -m venv .venv
# On Windows Activation:
.venv\Scripts\Activate.ps1
# On Mac/Linux Activation:
source .venv/bin/activate
```

### 3. Install System Dependencies
```bash
pip install -r requirements.txt
```

### 4. Add Your OpenAI Key
```bash
cp .env.example .env
# then edit .env and paste your key into OPENAI_API_KEY
```

### 5. Fire Up the Microservice Engine
```bash
uvicorn main:app --reload
```
Open your browser and navigate to `http://127.0.0.1:8000` to verify your environment path link is completely operational!

Try the agent from the interactive docs at `http://127.0.0.1:8000/docs`, or:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/agent/run \
  -H 'Content-Type: application/json' \
  -d '{"user_input": "Draft a 3-step onboarding email sequence for a B2B SaaS"}'
```

---
## Operational License
This open-source core architecture is distributed freely under the MIT License. For multi-agent crews, multi-tenant auth and a client portal, check out the [Pro version](https://theapplab.gumroad.com/l/ai-agent-boilerplate).
