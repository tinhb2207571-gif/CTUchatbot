from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.ctdt import pipeline, query_analyzer, vector_retriever
from app.services.ctdt.subgraph_retriever import GraphBuildResult, SubgraphRetriever


@pytest.mark.asyncio
async def test_original_query_and_llm_rewrite_are_not_rule_normalized():
    service = pipeline.CTDTPipeline()
    question = "Các HP của ngành KHMT?"
    analysis = {"rewrite": "HP của KHMT", "entities": [], "vector_targets": []}
    graph = GraphBuildResult("[GRAPH RESULT]\nDữ liệu graph", {}, True, True)
    with patch.object(pipeline, "analyze_ctdt_query", new_callable=AsyncMock, return_value=analysis) as analyze, patch.object(
        service.subgraph_retriever, "retrieve", return_value=graph
    ) as retrieve, patch.object(service, "_search_vector_section", new_callable=AsyncMock) as vector, patch.object(
        service, "_generate_answer", new_callable=AsyncMock, return_value="Đáp án"
    ) as generate:
        result = await service.handle_query("  " + question + "  ", [{"role": "user", "content": "KHMT"}])
    analyze.assert_awaited_once_with(question, "user: KHMT")
    assert retrieve.call_args.args[0]["query"] == question
    assert retrieve.call_args.args[0]["rewrite"] == "HP của KHMT"
    vector.assert_not_awaited()
    expected = "[GRAPH RESULT]\nDữ liệu graph\n\n[VECTOR RESULT]\nKhông có kết quả vector."
    assert result.context == expected
    assert generate.call_args.kwargs["context"] == expected


@pytest.mark.asyncio
async def test_insufficient_graph_uses_original_vector_sections_without_expansion():
    service = pipeline.CTDTPipeline()
    graph = GraphBuildResult("[GRAPH RESULT]\nKhông có dữ liệu phù hợp.", {}, True, False)
    with patch.object(pipeline, "search_vector_target", new_callable=AsyncMock, side_effect=[
        "- HocPhan [vector_hocphan_embedding]\n  1. Môn học", "",
    ]) as search:
        graph_context, vector_context = await service._retrieve_hybrid_context("KHMT", graph, [])
    assert graph_context == graph.graph_text
    assert vector_context == "[VECTOR RESULT]\n- HocPhan [vector_hocphan_embedding]\n  1. Môn học"
    assert [(c.args, c.kwargs) for c in search.await_args_list] == [
        (("KHMT", "HocPhan"), {"top_k": 3}),
        (("KHMT", "DieuKienTotNghiep"), {"top_k": 3}),
    ]
    assert "VECTOR GRAPH EXPANSION" not in vector_context


@pytest.mark.asyncio
async def test_original_answer_prompt_keeps_12000_token_budget():
    with patch.object(pipeline, "call_llm", new_callable=AsyncMock, return_value="  Đáp án  ") as call:
        result = await pipeline.CTDTPipeline()._generate_answer("Câu hỏi", "Câu viết lại", "Ngữ cảnh", True)
    assert result == "Đáp án"
    assert call.call_args.kwargs == {"temperature": 0.2, "num_predict": 12000}
    prompt = call.call_args.args[0]
    assert "1. Phân tích context để xác định thông tin đủ hay chưa đủ." in prompt
    assert "- Vector chỉ là hỗ trợ diễn giải." in prompt
    assert "VECTOR GRAPH EXPANSION" not in prompt


@pytest.mark.asyncio
async def test_original_analyzer_prompt_keeps_shared_model_and_12000_tokens():
    with patch.object(query_analyzer, "call_model_json", new_callable=AsyncMock,
                      return_value={"entities": [{"type": "Nganh", "value": "KHMT"}]}) as call:
        await query_analyzer.analyze_ctdt_query("KHMT?", "Lịch sử")
    assert call.call_args.args[0] == query_analyzer.LLM_MODEL
    assert call.call_args.kwargs == {"num_predict": 12000}
    assert "entities là danh sách linh hoạt" in call.call_args.args[1]
    assert "History:\nLịch sử" in call.call_args.args[1]


def test_original_seed_search_uses_keywords_without_major_catalog_resolution():
    retriever = SubgraphRetriever()
    with patch.object(retriever, "_fetch_seed_nodes", return_value=[{
        "seed_id": 42, "labels": ["Nganh"],
    }]) as fetch, patch.object(retriever, "_expand_subgraph", return_value=({}, {})) as expand:
        result = retriever.retrieve({"rewrite": "Câu hỏi độc lập", "entities": [
            {"type": "Nganh", "value": "Khoa hoc may tinh"},
        ]})
    fetch.assert_called_once_with(["Câu hỏi độc lập", "Khoa hoc may tinh"], {"khoa": 51, "he": "đại trà"})
    assert expand.call_args.args[0] == [42]
    assert "entity_resolution" not in result.metadata


def test_vector_rows_keep_original_format_and_strip_embedding():
    text = vector_retriever._format_vector_rows("HocPhan", [{
        "score": 0.75, "labels": ["HocPhan", "Entity"],
        "node": {"ma_hoc_phan": "CT101", "ten_hoc_phan": "Lập trình", "embedding": [0.1]},
    }], "vector_hocphan_embedding")
    assert text == ('- HocPhan [vector_hocphan_embedding]\n'
                    '  1. score=0.75 labels=["HocPhan", "Entity"] '
                    'node={"ma_hoc_phan": "CT101", "ten_hoc_phan": "Lập trình"}')


@pytest.mark.asyncio
async def test_vector_fallback_uses_current_kb_index_and_shared_embedding():
    embedding = SimpleNamespace(get_embedding_batch=Mock(return_value=[[0.1]]))
    with patch.object(vector_retriever, "get_embedding_model", return_value=embedding), patch.object(
        vector_retriever, "_execute_vector_query", return_value=[{"score": 0.9, "labels": ["HocPhan"], "node": {"id": "CT101"}}]
    ) as execute:
        result = await vector_retriever.search_vector_target("KHMT", "HocPhan")
    execute.assert_called_once_with("vector_hocphan_embedding", [0.1], 3)
    assert result.startswith("- HocPhan [vector_hocphan_embedding]")
