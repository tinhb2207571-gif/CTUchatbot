"""Vector fallback CTĐT theo source gốc, dùng tên index của KB hiện tại."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from app.db.neo4j import get_driver
from app.services.common.embedding import get_embedding_model
from app.services.ctdt.schema import CTDT_VECTOR_INDEXES

logger = logging.getLogger("app.ctdt.vector")

ALLOWED_VECTOR_TARGETS = {"HocPhan", "DieuKienTotNghiep", "ChuanDauRa", "VanBanPhapLy"}
_VECTOR_INDEX_CANDIDATES = {label: [name] for label, name in CTDT_VECTOR_INDEXES.items()}


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _strip_embedding(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_embedding(item)
            for key, item in value.items()
            if str(key).lower() != "embedding"
        }
    if isinstance(value, list):
        return [_strip_embedding(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_strip_embedding(item) for item in value)
    return value


def _execute_vector_query(index_name: str, embedding: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
    cypher = (
        f"CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding) "
        "YIELD node, score "
        "RETURN labels(node) AS labels, properties(node) AS node, score "
        "ORDER BY score DESC "
        "LIMIT $top_k"
    )
    with get_driver().session(database=os.getenv("NEO4J_DATABASE") or None) as session:
        return session.run(cypher, embedding=embedding, top_k=top_k).data()


def _format_vector_rows(target: str, rows: List[Dict[str, Any]], index_name: str) -> str:
    if not rows:
        return ""
    lines = [f"- {target} [{index_name}]"]
    for index, row in enumerate(rows, 1):
        sanitized_row = _strip_embedding(row)
        score = sanitized_row.get("score")
        labels = sanitized_row.get("labels", [])
        node = sanitized_row.get("node", {})
        lines.append(f"  {index}. score={score} labels={_stringify(labels)} node={_stringify(node)}")
    return "\n".join(lines)


async def search_vector_target(query: str, target: str, top_k: int = 3) -> str:
    try:
        embedding_batch = await asyncio.to_thread(get_embedding_model().get_embedding_batch, [query])
        if not embedding_batch:
            return ""
        embedding = embedding_batch[0]
    except Exception as exc:
        logger.warning("[chat][vector] embedding failed target=%s error=%s", target, exc)
        return ""

    for index_name in _VECTOR_INDEX_CANDIDATES.get(target, []):
        try:
            rows = await asyncio.to_thread(_execute_vector_query, index_name, embedding, top_k)
        except Exception as exc:
            logger.info("[chat][vector] index=%s unavailable target=%s error=%s", index_name, target, exc)
            continue
        if rows:
            return _format_vector_rows(target, rows, index_name)
    return ""
