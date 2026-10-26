"""Kept so `uvicorn main:app` from the original quickstart still works. The code lives in app/."""

from app.main import app

__all__ = ["app"]
