import unicodedata
from copy import deepcopy
from unittest.mock import patch

import pytest

from app.services.ctdt import subgraph_retriever as module


MAJOR = {
    "seed_id": 42, "labels": ["Entity", "Nganh"],
    "props": {"id": "7480101", "ma_nganh": "7480101",
              "ten_nganh_vi": "Khoa học máy tính", "ten_nganh_en": "Computer Science"},
}
FILTERS = {"khoa": 51, "he": "đại trà"}


@pytest.mark.parametrize("value", [
    "Khoa hoc may tinh", "KHOA HỌC MÁY TÍNH", "  khoa   hoc may tinh ",
    unicodedata.normalize("NFD", "Khoa học máy tính"), "7480101", "Computer Science",
])
def test_major_name_or_code_resolves_to_actual_kb_node(value):
    with patch.object(module, "read_query", return_value=[deepcopy(MAJOR)]) as read:
        seeds, trace = module.SubgraphRetriever()._resolve_major_seeds(
            [{"type": "Nganh", "value": value}], FILTERS,
        )
    assert [row["seed_id"] for row in seeds] == [42]
    assert trace[0]["canonical_name"] == "Khoa học máy tính"
    assert trace[0]["node_id"] == "7480101"
    assert read.call_args.args[1] == FILTERS
    assert "[:THUOC_VE]->(n:Nganh)" in read.call_args.args[0]


def test_d_stroke_is_folded_without_changing_kb_properties():
    row = deepcopy(MAJOR)
    row["props"]["ten_nganh_vi"] = "Điện tử"
    with patch.object(module, "read_query", return_value=[row]):
        seeds, _ = module.SubgraphRetriever()._resolve_major_seeds(
            [{"type": "Nganh", "value": "Dien tu"}], FILTERS,
        )
    assert seeds[0]["props"]["ten_nganh_vi"] == "Điện tử"


@pytest.mark.parametrize("value", ["Khoa hoc", "ngành không tồn tại"])
def test_unknown_or_partial_names_are_not_guessed(value):
    with patch.object(module, "read_query", return_value=[MAJOR]):
        seeds, trace = module.SubgraphRetriever()._resolve_major_seeds(
            [{"type": "Nganh", "value": value}], FILTERS,
        )
    assert seeds == []
    assert trace[0]["status"] == "not_found"


def test_ambiguous_folded_names_are_not_arbitrarily_selected():
    duplicate = deepcopy(MAJOR)
    duplicate["seed_id"] = 43
    duplicate["props"]["id"] = "other"
    with patch.object(module, "read_query", return_value=[MAJOR, duplicate]):
        seeds, trace = module.SubgraphRetriever()._resolve_major_seeds(
            [{"type": "Nganh", "value": "Khoa hoc may tinh"}], FILTERS,
        )
    assert seeds == []
    assert trace[0]["status"] == "ambiguous"


def test_other_entity_types_do_not_load_major_catalog():
    with patch.object(module, "read_query") as read:
        seeds, trace = module.SubgraphRetriever()._resolve_major_seeds(
            [{"type": "HocPhan", "value": "CT101"}], FILTERS,
        )
    assert (seeds, trace) == ([], [])
    read.assert_not_called()


def test_logged_query_uses_resolved_node_id_for_graph_expansion():
    retriever = module.SubgraphRetriever()
    analysis = {"rewrite": "Tổng số tín chỉ và thời gian đào tạo KHMT?",
                "entities": [{"type": "Nganh", "value": "Khoa hoc may tinh"}],
                "relations": ["THUOC_VE"], "query_type": "attribute"}
    with patch.object(module, "read_query", return_value=[deepcopy(MAJOR)]), patch.object(
        retriever, "_fetch_seed_nodes"
    ) as keyword_search, patch.object(retriever, "_expand_subgraph", return_value=({}, {})) as expand:
        result = retriever.retrieve(analysis)
    keyword_search.assert_not_called()
    assert expand.call_args.args[0] == [42]
    assert expand.call_args.args[1] == FILTERS
    assert result.metadata["entity_resolution"][0]["status"] == "matched"
    assert analysis["entities"][0]["value"] == "Khoa hoc may tinh"


def test_course_seeds_are_preserved_when_question_also_names_major():
    retriever = module.SubgraphRetriever()
    with patch.object(module, "read_query", return_value=[MAJOR]), patch.object(
        retriever, "_fetch_seed_nodes", return_value=[{"seed_id": 90, "labels": ["HocPhan"]}]
    ) as keyword_search, patch.object(retriever, "_expand_subgraph", return_value=({}, {})) as expand:
        retriever.retrieve({"rewrite": "Học phần CT101 của KHMT?", "entities": [
            {"type": "Nganh", "value": "Khoa hoc may tinh"},
            {"type": "HocPhan", "value": "CT101"},
        ]})
    keyword_search.assert_called_once()
    assert set(expand.call_args.args[0]) == {42, 90}
