import unicodedata
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ctdt import pipeline
from app.services.ctdt.query_normalizer import entity_name_variants, normalize_ctdt_query
from app.services.ctdt.subgraph_retriever import GraphBuildResult


@pytest.mark.parametrize("text,expected", [
    ("Niên luận cơ sở ngành KHMT", "Niên luận cơ sở ngành Khoa học máy tính"),
    ("ngành khmt và CNTT", "ngành Khoa học máy tính và Công nghệ thông tin"),
    ("CT201E, B2400695, khóa 51, ≥ 125 TC", "CT201E, B2400695, khóa 51, ≥ 125 TC"),
    ("KHMT123 CT_KHMT", "KHMT123 CT_KHMT"),
    (unicodedata.normalize("NFD", "Niên luận KHMT"), "Niên luận Khoa học máy tính"),
])
def test_only_standalone_known_abbreviations_are_expanded(text, expected):
    assert normalize_ctdt_query(text) == expected


def test_entity_variants_keep_full_and_abbreviated_course_names():
    assert entity_name_variants("Niên luận cơ sở ngành KHMT") == [
        "Niên luận cơ sở ngành KHMT", "Niên luận cơ sở ngành Khoa học máy tính",
    ]
    assert entity_name_variants("Thực tập doanh nghiệp - Khoa học máy tính") == [
        "Thực tập doanh nghiệp - Khoa học máy tính", "Thực tập doanh nghiệp - KHMT",
    ]
    assert entity_name_variants("CT201E") == ["CT201E"]


@pytest.mark.asyncio
async def test_llm_entity_abbreviation_gets_full_name_search_variant():
    service = pipeline.CTDTPipeline()
    original_analysis = {"rewrite": "Tiên quyết Niên luận cơ sở ngành KHMT?", "entities": [
        {"type": "HocPhan", "value": "Niên luận cơ sở ngành KHMT"},
    ], "relations": ["YEU_CAU_TIEN_QUYET"]}
    graph = GraphBuildResult("[GRAPH RESULT]\nKết quả", {}, True, True)
    with patch.object(pipeline, "analyze_ctdt_query", new_callable=AsyncMock, return_value=original_analysis), patch.object(
        service.subgraph_retriever, "retrieve", return_value=graph
    ) as retrieve, patch.object(service, "_generate_answer", new_callable=AsyncMock, return_value="Đáp án"):
        result = await service.handle_query("Tiên quyết Niên luận cơ sở ngành KHMT?", [])
    entities = retrieve.call_args.args[0]["entities"]
    assert entities == [
        {"type": "HocPhan", "value": "Niên luận cơ sở ngành KHMT"},
        {"type": "HocPhan", "value": "Niên luận cơ sở ngành Khoa học máy tính"},
    ]
    assert original_analysis["entities"] == [{"type": "HocPhan", "value": "Niên luận cơ sở ngành KHMT"}]
    assert result.analysis["relations"] == ["YEU_CAU_TIEN_QUYET"]


def test_other_node_types_still_use_original_three_property_limit():
    props = {"ma_nganh": "7480101", "ten_nganh_vi": "Khoa học máy tính",
             "loai": "ngành", "nhom": "CNTT"}
    assert pipeline.SubgraphRetriever()._pick_props(props, ["Nganh"]) == (
        "ma_nganh=7480101, ten_nganh_vi=Khoa học máy tính, loai=ngành"
    )
