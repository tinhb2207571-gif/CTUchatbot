"""Nhập một PDF tải từ web bằng pipeline Thông báo hiện có."""

from pathlib import Path
from threading import Lock

from .preprocess.pdf_pipeline import pipeline


# Các stage dùng OUTPUT_DIR cấp module; tránh hai file đổi đường dẫn lẫn nhau.
_pipeline_lock = Lock()


def process_notification(file_path: str) -> dict:
    # Lazy import để chỉ nạp driver/model khi xử lý loại tài liệu này.
    from .preprocess.kg_importer.nhap_file_moi import doc_file_chunks, nhap_file_moi

    source = Path(file_path).resolve()
    output_root = source.parent / "processed" / source.stem
    with _pipeline_lock:
        modules = [pipeline.load_step(step) for step in pipeline.PIPELINE_STEPS]
        original_outputs = [module.OUTPUT_DIR for module in modules]
        try:
            chunks_path = pipeline.run_single_input(source, output_root)
        finally:
            for module, original in zip(modules, original_outputs):
                module.OUTPUT_DIR = original

    document = doc_file_chunks(chunks_path)
    documents = document["tai_lieu"]
    if not documents:
        raise ValueError("PDF không có nội dung thông báo có thể nhập vào Neo4j.")

    # Import một cây mới và embedding trong cùng transaction, không full import.
    result = nhap_file_moi(chunks_path)
    counts = result["so_luong_nut"]
    nodes = sum(counts.values())
    return {
        "message": "Đã nhập Thông báo kế hoạch và embedding vào Neo4j.",
        "ingestion_applied": True,
        "nodes": nodes,
        # Mỗi node con trong importer có đúng một cạnh nối tới cha.
        "edges": nodes - 1,
        "section_count": counts.get("Muc", 0),
        "extraction_source": "thong_bao_pdf_pipeline",
        "id_thong_bao": result["id_thong_bao"],
        "node_counts": counts,
        "embedding_counts": result["so_luong_embedding"],
        "chunks_file": str(chunks_path),
    }
