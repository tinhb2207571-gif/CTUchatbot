"""Tên LLM chung; tham số suy luận do từng nơi gọi quyết định."""

import os
from pathlib import Path

from dotenv import load_dotenv


_backend_root = Path(__file__).resolve().parents[2]
load_dotenv(_backend_root / ".env", override=False)
load_dotenv(_backend_root.parent / ".env", override=False)

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5:9b").strip()
if not LLM_MODEL:
    raise ValueError("LLM_MODEL không được để trống trong backend/.env")
