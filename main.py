import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="AI Agent Automation API Boilerplate",
    description="A lightweight, production-ready framework for B2B AI Automation workflows.",
    version="1.0.1",
)


class AgentQuery(BaseModel):
    user_input: str
    system_instruction: str = "You are an advanced B2B operations optimization assistant."


@app.get("/")
def check_server_status():
    return {"status": "active", "framework": "FastAPI + LangChain AI Suite"}


@app.post("/api/v1/agent/run")
async def run_ai_automation_agent(data: AgentQuery):
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or "your_openai_api_key" in openai_key:
        raise HTTPException(
            status_code=500,
            detail="Configuration Error: Valid OPENAI_API_KEY must be provided.",
        )

    try:
        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.3)
        prompt = ChatPromptTemplate.from_messages([
            ("system", data.system_instruction),
            ("user", "{input}"),
        ])
        chain = prompt | llm
        response = await chain.ainvoke({"input": data.user_input})
        return {"success": True, "agent_response": response.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Engine anomaly: {str(e)}")
