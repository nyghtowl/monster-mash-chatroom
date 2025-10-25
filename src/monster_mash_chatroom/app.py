"""FastAPI app for the monster mash chatroom."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.websockets import WebSocketState

from .config import get_settings
from .events import EventBus, build_event_bus
from .models import ChatMessage, SendMessageRequest

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def create_app() -> FastAPI:
    """Build the FastAPI application with wiring for the chatroom backend."""
    application = FastAPI(title="Monster Mash Chatroom", version="0.1.0")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files (CSS, etc.)
    application.mount(
        "/static",
        StaticFiles(directory=str(_BASE_DIR / "templates")),
        name="static",
    )

    @application.on_event("startup")
    async def startup() -> None:
        settings = get_settings()
        application.state.settings = settings
        application.state.event_bus = await build_event_bus(settings.bus)
        logger.info("Application startup complete; event bus online")

    @application.on_event("shutdown")
    async def shutdown() -> None:
        bus: EventBus | None = getattr(application.state, "event_bus", None)
        if bus:
            await bus.stop()
            logger.info("Application shutdown complete; event bus closed")

    async def get_bus() -> EventBus:
        """Resolve the shared event bus instance for request handlers."""
        # Retry logic handles race condition between startup event
        # and first request - event bus might not be ready yet
        for _attempt in range(50):
            bus = getattr(application.state, "event_bus", None)
            if bus is not None:
                return bus
            await asyncio.sleep(0.1)
        raise HTTPException(status_code=503, detail="Event bus not ready")

    @application.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        settings = getattr(application.state, "settings", get_settings())
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "demo_mode": settings.demo_mode,
                # UI customization (can be overridden via env vars or config)
                "app_title": "Monster Mash Chatroom",
                "app_emoji": "🎃",
                "welcome_author": "Caretaker",
                "welcome_message": (
                    "Welcome to the Monster Mash! Messages will appear here "
                    "as they drift through the ether. Say hello to wake the "
                    "monsters... if you dare! 🌙"
                ),
                "author_label": "Display name",
                "author_placeholder": "Human Visitor",
                "message_label": "Message",
                "message_placeholder": (
                    "Type a greeting or challenge for the monsters…"
                ),
                "submit_button_text": "Send message",
                "reconnect_button_text": "Reconnect",
                "shortcuts_help": (
                    "<strong>Shortcuts:</strong> Ctrl+K (focus), "
                    "Enter (send), Shift+Enter (new line), Esc (clear)"
                ),
                "status_connecting": "Connecting to the haunted stream…",
                "status_connected": "Connected to the haunted stream.",
                "status_disconnected": "Disconnected from the haunted stream.",
                "status_reconnecting": "Reconnecting…",
                "status_reconnect_prompt": (
                    "Connection lost. Click reconnect when ready."
                ),
            },
        )

    @application.post("/send", response_model=ChatMessage)
    async def send_message(
        request: SendMessageRequest,
        bus: EventBus = Depends(get_bus),  # noqa: B008
    ) -> JSONResponse:
        message = request.to_chat_message()
        await bus.publish(message)
        logger.debug(
            "Message published by %s with id=%s", message.author, message.id
        )
        return JSONResponse(content=message.model_dump(mode="json"))

    @application.websocket("/stream")
    async def stream(
        websocket: WebSocket,
        bus: EventBus = Depends(get_bus),  # noqa: B008
    ) -> None:
        await websocket.accept()
        logger.info("WebSocket client connected")
        history = await bus.get_recent()
        for record in history:
            await websocket.send_json(record.model_dump(mode="json"))

        connection_closed = False
        try:
            async for message in bus.subscribe():
                await websocket.send_json(message.model_dump(mode="json"))
                logger.debug(
                    "WebSocket dispatched message id=%s persona=%s",
                    message.id,
                    message.persona,
                )
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            connection_closed = True
        except RuntimeError as exc:
            logger.error("WebSocket streaming error: %s", exc)
        finally:
            with contextlib.suppress(RuntimeError):
                if (
                    not connection_closed
                    and websocket.client_state == WebSocketState.CONNECTED
                ):
                    await websocket.close()

    return application


app = create_app()
