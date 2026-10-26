"""The LangChain chain behind both endpoints. Swap the model or prompt here."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.config import Settings

DEFAULT_SYSTEM = "You are an advanced B2B operations optimization assistant."


def build_model(settings: Settings) -> BaseChatModel:
    if not settings.openai_api_key or "your_openai_api_key" in settings.openai_api_key:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Configuration error: set OPENAI_API_KEY in .env",
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=settings.openai_model, temperature=0.3, api_key=settings.openai_api_key)


def get_chain(request: Request) -> Runnable:
    """FastAPI dependency. Tests override this with a fake model."""
    model = build_model(request.app.state.settings)
    prompt = ChatPromptTemplate.from_messages([("system", "{system}"), ("user", "{input}")])
    return prompt | model
