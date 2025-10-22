"""Uvicorn entrypoint for local development."""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "monster_mash_chatroom.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
