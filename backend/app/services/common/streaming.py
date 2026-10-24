"""Callback chỉ hoạt động trong request chat đang truyền câu trả lời."""

from contextvars import ContextVar
from typing import Callable, Optional
import json

import httpx

answer_token_handler: ContextVar[Optional[Callable[[str], None]]] = ContextVar(
    "answer_token_handler", default=None,
)


async def stream_ollama_answer(model, prompt, *, generate_url, chat_url, timeout,
                               temperature, num_predict, think=True):
    """Giữ kết quả đầy đủ cho caller và phát từng phần cho request hiện tại."""
    handler = answer_token_handler.get()
    parts = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for is_chat, url in ((False, generate_url), (True, chat_url)):
            payload = {
                "model": model, "stream": True, "think": think, "keep_alive": "1h",
                "options": {"temperature": temperature, "num_predict": num_predict},
            }
            payload.update({"messages": [{"role": "user", "content": prompt}]} if is_chat else {"prompt": prompt})
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404 and not is_chat:
                    continue
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("error"):
                        raise RuntimeError(item["error"])
                    text = (item.get("message") or {}).get("content", "") if is_chat else item.get("response", "")
                    if text:
                        parts.append(text)
                        if handler:
                            handler(text)
                    if item.get("done"):
                        return "".join(parts)
                raise RuntimeError("Kết nối Ollama kết thúc trước khi trả lời hoàn tất.")
