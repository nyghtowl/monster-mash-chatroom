"""Monster Mash Chatroom package."""

from .app import app  # re-export for uvicorn entrypoint

__all__ = ["app"]
