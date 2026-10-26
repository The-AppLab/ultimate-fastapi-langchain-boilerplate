"""Settings, read once from the environment (and .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    supabase_url: str
    supabase_jwt_secret: str
    jwt_audience: str

    @property
    def auth_enabled(self) -> bool:
        """Auth is on as soon as either Supabase setting is present."""
        return bool(self.supabase_url or self.supabase_jwt_secret)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET", ""),
            jwt_audience=os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated"),
        )
