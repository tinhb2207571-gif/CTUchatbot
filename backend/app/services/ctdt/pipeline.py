"""Luồng hỏi đáp CTĐT theo source gốc, giữ logging và cấu hình runtime chung."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from app.services.common.llm_service import call_llm
from app.services.common.pipeline_logger import elapsed_ms, log_context, log_event, now
from app.services.ctdt.query_analyzer import analyze_ctdt_query, history_text, normalize_history
from app.services.ctdt.subgraph_retriever import GraphBuildResult, SubgraphRetriever
from app.services.ctdt.vector_retriever import ALLOWED_VECTOR_TARGETS, search_vector_target

logger = logging.getLogger("app.ctdt")


@dataclass(frozen=True)
class CTDTPipelineResult:
    answer: str
    context: str
    rewritten_query: str
    analysis: Dict[str, Any]
    graph_context: str
    vector_context: str
    metadata: Dict[str, Any]
    used_default_ctdt: bool


def _format_hybrid_context(graph_context: str, vector_context: str) -> str:
    graph_section = graph_context.strip() or "[GRAPH RESULT]\nKhông có kết quả graph."
    vector_section = vector_context.strip() or "[VECTOR RESULT]\nKhông có kết quả vector."
    return f"{graph_section}\n\n{vector_section}"


class CTDTPipeline:
    def __init__(self) -> None:
        self.subgraph_retriever = SubgraphRetriever()

    async def _retrieve_hybrid_context(
        self,
        query: str,
        graph_result: GraphBuildResult,
        vector_targets: List[str],
    ) -> tuple[str, str]:
        graph_context = graph_result.graph_text.strip() or "[GRAPH RESULT]\nKhông có dữ liệu phù hợp."
        selected_targets = vector_targets if vector_targets else ["HocPhan", "DieuKienTotNghiep"]

        vector_started = now()
        filtered_vector_sections: List[str] = []
        if not graph_result.is_graph_sufficient and selected_targets:
            vector_sections = await asyncio.gather(*[
                self._search_vector_section(query, target)
                for target in selected_targets
            ])
            filtered_vector_sections = [section for section in vector_sections if section]
        vector_context = (
            "[VECTOR RESULT]\n" + "\n\n".join(filtered_vector_sections)
            if filtered_vector_sections
            else "[VECTOR RESULT]\nKhông có kết quả vector."
        )

        log_event(
            "CTDT",
            "vector_retrieval",
            executed=not graph_result.is_graph_sufficient and bool(selected_targets),
            targets=selected_targets,
            result_sections=len(filtered_vector_sections),
            elapsed_ms=elapsed_ms(vector_started),
        )
        return graph_context, vector_context

    async def _search_vector_section(self, query: str, target: str) -> str:
        if target not in ALLOWED_VECTOR_TARGETS:
            return ""
        return await search_vector_target(query, target, top_k=3)

    async def _generate_answer(
        self,
        original_query: str,
        rewritten_query: str,
        context: str,
        used_default_ctdt: bool,
    ) -> str:
        default_note = (
            "Hệ thống đã áp dụng mặc định CTĐT: khoa=51, he=đại trà."
            if used_default_ctdt
            else "[Không dùng default CTĐT]"
        )
        prompt = f"""
Bạn là trợ lý tư vấn học vụ bằng tiếng Việt cho hệ thống GraphRAG.

Nhiệm vụ:
1. Phân tích context để xác định thông tin đủ hay chưa đủ.
2. Trả lời trực tiếp bằng tiếng Việt, ưu tiên fact từ GRAPH, dùng VECTOR để giải thích hoặc bổ sung bối cảnh.

Quy tắc:
- Không bịa thông tin ngoài context.
- Graph là nguồn sự thật chính.
- Vector chỉ là hỗ trợ diễn giải.
- Nếu context chưa đủ, nói rõ chưa đủ và nêu phần thiếu.
- Nếu có default CTĐT đã được dùng, nhắc ngắn gọn.

Thông tin bổ sung:
{default_note}

Câu hỏi gốc:
{original_query}

Câu hỏi đã chuẩn hóa:
{rewritten_query}

Context:
{context}

Hãy trả lời ngắn gọn, chính xác, và chỉ dùng thông tin trong context.
"""
        return (await call_llm(prompt, temperature=0.2, num_predict=12000)).strip()

    async def handle_query(self, query: str, history: List[Dict[str, Any]]) -> CTDTPipelineResult:
        total_started = now()
        query = (query or "").strip()
        cleaned_history = normalize_history(history)
        history_string = history_text(cleaned_history)

        analysis_started = now()
        analysis = await analyze_ctdt_query(query, history_string)
        rewritten_query = analysis.get("rewrite", query)
        vector_targets = analysis.get("vector_targets", []) or ["HocPhan", "DieuKienTotNghiep"]
        log_event(
            "CTDT",
            "analysis",
            original_query=query,
            rewritten_query=rewritten_query,
            analysis=analysis,
            elapsed_ms=elapsed_ms(analysis_started),
        )

        retrieval_analysis = dict(analysis)
        retrieval_analysis["query"] = query
        graph_started = now()
        graph_result = await asyncio.to_thread(self.subgraph_retriever.retrieve, retrieval_analysis)
        log_event(
            "CTDT",
            "graph_retrieval",
            sufficient=graph_result.is_graph_sufficient,
            used_default_ctdt=graph_result.used_default_ctdt,
            metadata=graph_result.metadata,
            elapsed_ms=elapsed_ms(graph_started),
        )

        graph_context, vector_context = await self._retrieve_hybrid_context(
            rewritten_query,
            graph_result,
            vector_targets,
        )
        context = _format_hybrid_context(graph_context, vector_context)
        log_context("CTDT", context)

        generation_started = now()
        answer = await self._generate_answer(
            original_query=query,
            rewritten_query=rewritten_query,
            context=context,
            used_default_ctdt=graph_result.used_default_ctdt,
        )
        log_event("CTDT", "generation", elapsed_ms=elapsed_ms(generation_started))
        log_event("CTDT", "done", total_ms=elapsed_ms(total_started))
        return CTDTPipelineResult(
            answer=answer,
            context=context,
            rewritten_query=rewritten_query,
            analysis=analysis,
            graph_context=graph_context,
            vector_context=vector_context,
            metadata=graph_result.metadata,
            used_default_ctdt=graph_result.used_default_ctdt,
        )


ctdt_pipeline = CTDTPipeline()
