import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd

from app.scripts.XuLyChuongTrinhDaoTao import CurriculumETL
from app.services.ctdt.schema import CTDT_VECTOR_INDEXES
from app.services.ctdt.subgraph_retriever import SubgraphRetriever
from app.services.ctdt import vector_retriever


class CTDTContextTests(unittest.TestCase):
    def test_program_context_keeps_four_requested_properties(self):
        nodes = {1: {"labels": ["ChuongTrinhDaoTao", "Entity"], "props": {
            "id": "7480101_51_STD", "ma_chuong_trinh": "7480101_51_STD",
            "khoa": 51, "he": "Đại trà", "tong_tin_chi": 161,
            "thoi_gian_dao_tao": 4.5, "ngon_ngu": "Tiếng Việt",
            "thang_diem": 4, "embedding": [0.123],
        }}}
        context = SubgraphRetriever().serialize_subgraph(nodes, {})
        self.assertEqual(context, "[GRAPH RESULT]\nCác nút liên quan:\n"
                         "- ChuongTrinhDaoTao: 7480101_51_STD (khoa=51, he=Đại trà, tong_tin_chi=161, thoi_gian_dao_tao=4.5)")
        self.assertNotIn("embedding", context)

    def test_program_gets_duration_even_when_entity_is_first_label(self):
        context = SubgraphRetriever().serialize_subgraph({1: {
            "labels": ["Entity", "ChuongTrinhDaoTao"],
            "props": {"ma_chuong_trinh": "7480101_51_STD", "khoa": 51,
                      "he": "Đại trà", "tong_tin_chi": 161, "thoi_gian_dao_tao": 4.5},
        }}, {})
        self.assertIn("thoi_gian_dao_tao=4.5", context)

    def test_missing_duration_is_not_invented_or_replaced_by_other_property(self):
        summary = SubgraphRetriever()._pick_props({
            "khoa": 51, "he": "Đại trà", "tong_tin_chi": 161,
            "thoi_gian_dao_tao": None, "text": "Văn bản dài", "embedding": [0.1],
        }, ["ChuongTrinhDaoTao"])
        self.assertEqual(summary, "khoa=51, he=Đại trà, tong_tin_chi=161")

    def test_course_context_matches_original_summary(self):
        context = SubgraphRetriever().serialize_subgraph({1: {
            "labels": ["HocPhan", "Entity"], "props": {
                "ma_hoc_phan": "CT101", "ten_hoc_phan": "Lập trình",
                "so_tin_chi": 3, "so_tiet_ly_thuyet": 0, "bat_buoc": False,
                "dieu_kien": "Đạt CT100", "yeu_cau_stc_toi_thieu": 30,
            },
        }}, {})
        self.assertEqual(context, "[GRAPH RESULT]\nCác nút liên quan:\n"
                         "- HocPhan: Lập trình (ma_hoc_phan=CT101, ten_hoc_phan=Lập trình, so_tin_chi=3)")

    def test_zero_and_false_values_are_not_dropped_from_original_fallback(self):
        summary = SubgraphRetriever()._pick_props({"so_tiet_ly_thuyet": 0, "bat_buoc": False})
        self.assertIn("so_tiet_ly_thuyet=0", summary)
        self.assertIn("bat_buoc=False", summary)


class CTDTExtractionTests(unittest.TestCase):
    def setUp(self):
        # Không nạp embedding hoặc gọi LLM khi kiểm tra đầu ra bộ trích xuất.
        self.etl = CurriculumETL.__new__(CurriculumETL)
        self.etl.nodes = []
        self.etl.edges = []
        self.etl.ma_nganh = "7480101"
        self.etl.ten_nganh = "Khoa học máy tính"
        self.etl.program_id = "7480101_51_STD"
        self.etl.loai_hinh_dao_tao = "Đại trà"

    def test_program_emits_he_and_canonical_relationships(self):
        self.etl._parse_curriculum(
            "Số lượng tín chỉ: 161\nThời gian đào tạo: 4,5\n"
            "Loại văn bằng: Kỹ sư\nHình thức đào tạo: Chính quy\n"
            "Phương thức tổ chức đào tạo: Trực tiếp\n", "năm 2025",
        )
        program = next(n for n in self.etl.nodes if n.metadata["type"] == "ChuongTrinhDaoTao")
        self.assertEqual(program.metadata["he"], "Đại trà")
        self.assertNotIn("loai_hinh", program.metadata)
        self.assertEqual(program.metadata["tong_tin_chi"], 161)
        self.assertEqual(program.metadata["thoi_gian_dao_tao"], 4.5)
        outgoing = [e for e in self.etl.edges if e["source"] == program.node_id]
        self.assertEqual({e["type"] for e in outgoing}, {"THUOC_VE", "CAP", "CO"})

    def test_optional_course_is_reachable_directly_from_program_and_block(self):
        self.etl._process_course_table(pd.DataFrame([
            ["BLOCK_HEADER: Cơ sở ngành", "", "", "", "", "", "", "", "", ""],
            ["1", "CT101", "Lập trình", "3", "AV", "10 AV hoặc PV", "30", "30", "CT100", "CT102"],
        ]))
        by_type = {n.metadata["type"]: n for n in self.etl.nodes}
        course = by_type["HocPhan"]
        self.assertEqual(course.metadata["ma_hoc_phan"], "CT101")
        self.assertEqual(course.metadata["ten_hoc_phan"], "Lập trình")
        self.assertNotIn("ma_hp", course.metadata)
        self.assertNotIn("ten_hp", course.metadata)
        self.assertEqual(by_type["YeuCauTuChon"].metadata["so_tin_chi_yeu_cau"], 10)
        edges = {(e["source"], e["type"], e["target"]) for e in self.etl.edges}
        self.assertIn((self.etl.program_id, "GOM", "CT101"), edges)
        self.assertIn((by_type["KhoiKienThuc"].node_id, "GOM", "CT101"), edges)
        self.assertIn((by_type["YeuCauTuChon"].node_id, "DOI_VOI", by_type["NhomHocPhanTuChon"].node_id), edges)
        self.assertIn(("CT101", "YEU_CAU_TIEN_QUYET", "CT100"), edges)

    def test_legal_document_and_level_use_kb_relations(self):
        self.etl._parse_quyet_dinh_ban_hanh("TRÌNH ĐỘ ĐẠI HỌC", "")
        self.assertEqual({e["type"] for e in self.etl.edges}, {"BAN_HANH_THEO", "DAO_TAO"})
        level = next(n for n in self.etl.nodes if n.metadata["type"] == "TrinhDo")
        self.assertEqual(level.metadata["ma_trinh_do"], level.node_id)


class CTDTIndexTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_creates_indexes_used_by_retrieval(self):
        from app.api import graph
        etl = SimpleNamespace(process=Mock(), nodes=[], edges=[], extraction_source="test",
                              extracted_text_length=0, section_count=0, extracted_preview="")
        db = SimpleNamespace(create_constraints=AsyncMock(), add_nodes=AsyncMock(),
                             add_edges=AsyncMock(), create_vector_index=AsyncMock(), close=AsyncMock())
        with patch.object(graph, "CurriculumETL", return_value=etl), patch.object(
            graph, "Neo4jConnector", return_value=db
        ), patch.dict("os.environ", {"NEO4J_PASSWORD": "test"}):
            result = await graph.ChuyenNganhDaoTaoProcessor().process("test.pdf")
        self.assertTrue(result["ingestion_applied"])
        calls = {(c.kwargs["label"], c.kwargs["index_name"]) for c in db.create_vector_index.await_args_list}
        self.assertEqual(calls, set(CTDT_VECTOR_INDEXES.items()))
        for label, index in calls:
            self.assertEqual(vector_retriever._VECTOR_INDEX_CANDIDATES[label], [index])
        db.close.assert_awaited_once()

    async def test_vector_query_honors_selected_database(self):
        driver = Mock()
        with patch.object(vector_retriever, "get_driver", return_value=driver), patch.dict(
            "os.environ", {"NEO4J_DATABASE": "ctdt"}
        ):
            driver.session.return_value.__enter__ = Mock(return_value=Mock())
            driver.session.return_value.__exit__ = Mock(return_value=False)
            vector_retriever._execute_vector_query("vector_hocphan_embedding", [0.1])
        driver.session.assert_called_once_with(database="ctdt")


if __name__ == "__main__":
    unittest.main()
