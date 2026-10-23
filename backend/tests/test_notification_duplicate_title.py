import unicodedata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.scripts.thong_bao.preprocess.kg_importer import nhap_file_moi as importer


def document(title, filename="renamed.pdf", year="2026"):
    return {"metadata": {"tieu_de": title, "ten_file": filename, "nam": year}, "tai_lieu": []}


def reader(title):
    tx = Mock()
    tx.run.return_value = [{"id": "old-notice", "title": title}]
    return tx


def test_same_title_is_duplicate_even_with_different_filename_and_year():
    with pytest.raises(ValueError, match="Tài liệu đã tồn tại"):
        importer.kiem_tra_tieu_de_moi(reader("Thông báo đợt 1"), document("Thông báo đợt 1", year="2027"))


def test_case_spacing_and_unicode_do_not_bypass_duplicate_check():
    existing = unicodedata.normalize("NFD", "  THÔNG BÁO\n  ĐỢT 1  ")
    with pytest.raises(ValueError, match="Tài liệu đã tồn tại"):
        importer.kiem_tra_tieu_de_moi(reader(existing), document("Thông báo đợt 1"))


def test_different_round_numbers_are_allowed():
    importer.kiem_tra_tieu_de_moi(reader("Thông báo đợt 1"), document("Thông báo đợt 2"))


def test_missing_title_is_not_imported():
    with pytest.raises(ValueError, match="Không trích xuất được tiêu đề"):
        importer.kiem_tra_tieu_de_moi(reader("other"), document("  "))


def test_duplicate_stops_before_model_loading_or_graph_write():
    connection = MagicMock()
    session = connection.driver.session.return_value.__enter__.return_value
    no_id_match = Mock()
    no_id_match.single.return_value = None
    session.run.side_effect = [no_id_match, [{"id": "existing", "title": "Thông báo đợt 1"}]]
    with patch.object(importer, "doc_file_chunks", return_value=document("Thông báo đợt 1")), patch.object(
        importer, "load_settings", return_value=SimpleNamespace()
    ), patch.object(importer, "Neo4jConnection", return_value=connection), patch.object(
        importer, "nap_model_embedding"
    ) as load_model:
        with pytest.raises(ValueError, match="Tài liệu đã tồn tại"):
            importer.nhap_file_moi(Path("renamed_chunks.json"))
    load_model.assert_not_called()
    connection.execute_write.assert_not_called()
    connection.close.assert_called_once()


def test_transaction_rechecks_title_before_creating_nodes():
    tx = Mock()
    no_id_match = Mock()
    no_id_match.single.return_value = None
    tx.run.side_effect = [no_id_match, [{"id": "existing", "title": "Thông báo đợt 1"}]]
    with patch.object(importer, "import_thongbao") as write:
        with pytest.raises(ValueError, match="Tài liệu đã tồn tại"):
            importer.them_thong_bao_moi(tx, document("Thông báo đợt 1"), "new-id")
    write.assert_not_called()
