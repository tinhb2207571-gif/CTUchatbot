import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.scripts.thong_bao import ingestion
from app.scripts.thong_bao.preprocess.kg_importer import nhap_file_moi as importer


class EmbeddingDimensionTests(unittest.TestCase):
    def test_model_dimension_uses_sentence_transformer_api(self):
        model = Mock(spec=["get_sentence_embedding_dimension"])
        model.get_sentence_embedding_dimension.return_value = 1024
        shared = SimpleNamespace(model=model, model_name="BAAI/bge-m3", device="cpu")
        with patch("app.services.common.embedding.get_embedding_model", return_value=shared):
            self.assertIs(importer.nap_model_embedding("BAAI/bge-m3", "cpu", 1024), model)
            with self.assertRaisesRegex(ValueError, "1024.*768"):
                importer.nap_model_embedding("BAAI/bge-m3", "cpu", 768)


class NotificationIngestionTests(unittest.TestCase):
    def setUp(self):
        self.source = Path(__file__).resolve().parent / "notice.pdf"
        self.modules = [SimpleNamespace(OUTPUT_DIR=Path("original")) for _ in range(6)]
        self.stack = []
        for target, kwargs in [
            ("load_step", {"side_effect": self.modules}),
            ("run_single_input", {"return_value": Path("notice_chunks.json")}),
        ]:
            patcher = patch.object(ingestion.pipeline, target, **kwargs)
            self.stack.append(patcher.start())
            self.addCleanup(patcher.stop)

    def test_success_returns_web_counts_and_imports_only_generated_file(self):
        with patch.object(importer, "doc_file_chunks", return_value={"tai_lieu": [{}]}), patch.object(
            importer, "nhap_file_moi", return_value={
                "id_thong_bao": "notice",
                "so_luong_nut": {"ThongBao": 1, "TaiLieu": 1, "Muc": 3},
                "so_luong_embedding": {"Muc": 3},
            }
        ) as write:
            result = ingestion.process_notification(str(self.source))
        self.assertTrue(result["ingestion_applied"])
        self.assertEqual((result["nodes"], result["edges"]), (5, 4))
        write.assert_called_once_with(Path("notice_chunks.json"))
        self.stack[1].assert_called_once_with(
            self.source.resolve(), self.source.parent / "processed" / "notice"
        )

    def test_pipeline_failure_restores_paths_and_does_not_import(self):
        def fail(*args):
            self.modules[0].OUTPUT_DIR = Path("changed")
            raise RuntimeError("extraction failed")

        self.stack[1].side_effect = fail
        with patch.object(importer, "nhap_file_moi") as write:
            with self.assertRaisesRegex(RuntimeError, "extraction failed"):
                ingestion.process_notification(str(self.source))
            write.assert_not_called()
        self.assertTrue(all(module.OUTPUT_DIR == Path("original") for module in self.modules))

    def test_empty_pdf_is_rejected_before_import(self):
        with patch.object(importer, "doc_file_chunks", return_value={"tai_lieu": []}), patch.object(
            importer, "nhap_file_moi"
        ) as write:
            with self.assertRaises(ValueError):
                ingestion.process_notification(str(self.source))
            write.assert_not_called()

    def test_database_or_embedding_error_propagates_to_job_worker(self):
        with patch.object(importer, "doc_file_chunks", return_value={"tai_lieu": [{}]}), patch.object(
            importer, "nhap_file_moi", side_effect=RuntimeError("database unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                ingestion.process_notification(str(self.source))
