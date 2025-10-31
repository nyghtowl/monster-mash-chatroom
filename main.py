"""Uvicorn entrypoint for local development."""

from __future__ import annotations

import logging

import uvicorn


def main() -> None:
    """Configure logging once and launch the development server."""
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "monster_mash_chatroom.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
