from __future__ import annotations

import json
import asyncio
import logging
from contextlib import suppress
from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.orchestrator import chat_orchestrator
from app.services.common.streaming import answer_token_handler

router = APIRouter()


class MessagePart(BaseModel):
    type: str = "text"
    text: str


class MessageItem(BaseModel):
    id: Optional[str] = None
    role: str
    parts: List[MessagePart]


class ChatRequest(BaseModel):
    # Payload đơn giản cho backend/test.
    message: Optional[str] = None
    history: List[dict] = Field(default_factory=list)

    # Payload của frontend main (Vercel AI stream style).
    id: Optional[str] = None
    messages: Optional[List[MessageItem]] = None
    trigger: Optional[str] = None


def _extract_request(req: ChatRequest) -> tuple[str, List[dict]]:
    message = (req.message or "").strip()
    history = list(req.history or [])
    if message or not req.messages:
        return message, history

    user_messages = [item for item in req.messages if item.role == "user" and item.parts]
    if user_messages:
        message = (user_messages[-1].parts[0].text or "").strip()

    history = []
    for item in req.messages[:-1]:
        if not item.parts:
            continue
        content = (item.parts[0].text or "").strip()
        if content:
            history.append({"role": item.role, "content": content})
    return message, history


@router.post("/chat")
async def chat(req: ChatRequest):
    message, history = _extract_request(req)
    async def stream_results():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        emitted = False
        active = True

        def on_token(text):
            nonlocal emitted
            if not active:
                return
            emitted = True
            loop.call_soon_threadsafe(queue.put_nowait, ("0", text))

        async def produce():
            token = answer_token_handler.set(on_token)
            try:
                result = await chat_orchestrator.handle_query(message, history)
                if not emitted:
                    answer = str(result.get("answer", "")).strip()
                    queue.put_nowait(("0", answer or "Mình chưa tìm thấy đủ dữ liệu để trả lời chính xác."))
            except Exception:
                logging.getLogger("app.chat").exception("Lỗi xử lý chat")
                loop.call_soon(queue.put_nowait, ("3", "Không thể hoàn tất câu trả lời. Bạn vui lòng thử lại."))
            finally:
                answer_token_handler.reset(token)
                # Callback từ thread được đưa vào loop trước dấu kết thúc.
                loop.call_soon(queue.put_nowait, None)

        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                kind, text = item
                yield f"{kind}:{json.dumps(text, ensure_ascii=False)}\n"
        finally:
            active = False
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        stream_results(),
        media_type="text/plain",
        headers={"X-Vercel-AI-Data-Stream": "v1", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
