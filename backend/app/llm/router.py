"""Chat API endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import db
from app.llm.service import handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""

    message: str


@router.post("")
async def post_chat(body: ChatRequest, request: Request) -> dict:
    """Send a message to the assistant; returns its reply and executed actions."""
    state = request.app.state
    return await handle_chat(state.price_cache, state.market_source, body.message)


@router.get("/history")
def chat_history() -> list[dict]:
    """Conversation history, oldest first."""
    return db.get_chat_messages(limit=100)
