"""Logging gọn cho pipeline chat, không tham gia vào logic retrieval."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4
from collections.abc import Iterable
from typing import Any


_LOGGER_NAME = "ctu.pipeline"
_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().casefold() in _TRUTHY


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.propagate = False
    level_name = os.getenv("PIPELINE_LOG_LEVEL", "INFO").strip().upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    return logger


logger = _get_logger()
_request_timings: ContextVar[dict | None] = ContextVar("request_timings", default=None)


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 2)


def now() -> float:
    return time.perf_counter()


def _trim_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n... [đã cắt {len(text) - limit} ký tự]"


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _safe_value(vars(value))
    return str(value)


def log_event(scope: str, step: str, **fields: Any) -> None:
    """Ghi một sự kiện pipeline dạng JSON trên một dòng."""
    timings = _request_timings.get()
    if timings is not None:
        # Chỉ giữ số đo và trạng thái, không sao chép context/candidate lớn.
        captured = {
            key: fields[key] for key in (
                "elapsed_ms", "total_ms", "llm_ms", "branch_ms", "method", "domain", "executed"
            ) if key in fields
        }
        if captured:
            timings["events"].append((scope.upper(), step.upper(), captured))
    if not _enabled("PIPELINE_LOG_ENABLED"):
        return
    payload = _safe_value(fields)
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    logger.info("[%s][%s] %s", scope.upper(), step.upper(), rendered)


@contextmanager
def chat_timing_summary(query: str):
    """Thu thập số đo riêng cho từng lượt chat, kể cả task/thread con."""
    timings = {"id": uuid4().hex[:8], "events": [], "started": now()}
    token = _request_timings.set(timings)
    status = "Hoàn tất"
    try:
        yield
    except BaseException:
        status = "Bị ngắt hoặc gặp lỗi"
        raise
    finally:
        _request_timings.reset(token)
        if _enabled("PIPELINE_LOG_ENABLED"):
            _log_timing_summary(query, timings, status)


def _log_timing_summary(query: str, timings: dict, status: str) -> None:
    names = {
        "NORMALIZE": "Chuẩn hóa câu hỏi",
        "NORMALIZATION": "Chuẩn hóa câu hỏi",
        "PREPROCESS": "Chuẩn hóa câu hỏi bằng LLM",
        "ANALYSIS": "Phân tích câu hỏi / chọn văn bản",
        "EMBEDDING": "Tạo embedding câu hỏi",
        "RETRIEVAL": "Truy xuất Neo4j",
        "GRAPH_RETRIEVAL": "Truy xuất graph",
        "VECTOR_RETRIEVAL": "Truy xuất vector và mở rộng",
        "RANKING_TOP_K": "Xếp hạng và chọn Top-K",
        "EXPANSION": "Mở rộng ngữ cảnh",
        "CONTEXT_BUILD": "Ghép context",
        "GENERATION": "LLM sinh đáp án",
        "LLM": "LLM sinh đáp án",
    }
    lines = []
    domain = "Chưa xác định"
    branch_ms = None
    total_ms = elapsed_ms(timings["started"])

    def row(label, value):
        return f"  {label:<42} {float(value) / 1000:>9.3f} s"

    for scope, step, fields in timings["events"]:
        domain = fields.get("domain", domain)
        if scope == "ROUTER" and step == "RESULT":
            method = fields.get("method", "unknown")
            lines.append(row(f"Router — {method}", fields.get("total_ms", 0)))
            lines.append(row("  Trong đó: gọi LLM phân loại", fields.get("llm_ms", 0)))
        elif scope == "CHAT" and step == "DONE":
            branch_ms = fields.get("branch_ms")
            total_ms = fields.get("total_ms", total_ms)
        elif step in names and "elapsed_ms" in fields:
            label = names[step]
            if fields.get("executed") is False:
                lines.append(f"  {label:<42}   Bỏ qua")
            else:
                lines.append(row(label, fields["elapsed_ms"]))
    if not any(scope == "ROUTER" for scope, _, _ in timings["events"]):
        lines.insert(0, "  Router                                       Không chạy / chưa có kết quả")
    lines.append("  " + "-" * 54)
    if branch_ms is not None:
        lines.append(row(f"Tổng nhánh {domain}", branch_ms))
    lines.append(row("TỔNG XỬ LÝ CÂU HỎI", total_ms))
    logger.info(
        "[CHAT][TIMING_SUMMARY] id=%s | %s | %s\nCâu hỏi: %s\n%s\n"
        "  (Các dòng tổng và 'trong đó' không cộng thêm vào từng bước.)",
        timings["id"], domain, status, " ".join(str(query).split())[:160], "\n".join(lines),
    )


def log_context(domain: str, context: str) -> None:
    """In context nếu PIPELINE_LOG_CONTEXT bật; mặc định bật."""
    if not _enabled("PIPELINE_LOG_ENABLED") or not _enabled("PIPELINE_LOG_CONTEXT"):
        return
    limit = _positive_int("PIPELINE_LOG_MAX_CONTEXT_CHARS", 12000)
    logger.info(
        "[%s][CONTEXT]\n%s",
        domain.upper(),
        _trim_text(context, limit),
    )


def log_answer(domain: str, answer: str) -> None:
    """In câu trả lời cuối; giới hạn độc lập với context."""
    if not _enabled("PIPELINE_LOG_ENABLED"):
        return
    limit = _positive_int("PIPELINE_LOG_MAX_ANSWER_CHARS", 6000)
    logger.info(
        "[%s][ANSWER]\n%s",
        domain.upper(),
        _trim_text(answer, limit),
    )


def summarize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Rút candidate về các field cần để debug ranking mà không in embedding."""
    metadata = candidate.get("metadata") or {}
    properties = candidate.get("properties") or {}
    property_preview: dict[str, Any] = {}
    for key in (
        "ma_hoc_phan",
        "ma_sinh_vien",
        "khoa",
        "nganh",
        "tieu_de",
        "path",
        "gia_tri",
    ):
        value = properties.get(key)
        if value not in (None, "", []):
            property_preview[key] = value

    return {
        "node_id": candidate.get("node_id"),
        "label": candidate.get("label"),
        "source": candidate.get("source"),
        "cosine": round(float(candidate.get("cosine_score") or 0.0), 6),
        "loai_thong_bao": metadata.get("loai_thong_bao"),
        "notification_id": metadata.get("notification_id"),
        "nam_hoc": metadata.get("nam_hoc"),
        "hoc_ky": metadata.get("hoc_ky"),
        "ngay_ban_hanh": metadata.get("ngay_ban_hanh"),
        "parent_table_id": metadata.get("parent_table_id"),
        "properties": property_preview,
    }


def summarize_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(candidates)
    limit = _positive_int("PIPELINE_LOG_MAX_CANDIDATES", 50)
    summarized = [summarize_candidate(candidate) for candidate in items[:limit]]
    if len(items) > limit:
        summarized.append({"_truncated_candidates": len(items) - limit})
    return summarized
