"""File chạy độc lập riêng luồng THÔNG BÁO (Notification Stream).

- Không can thiệp hoặc chỉnh sửa bất kỳ file hệ thống nào.
- Trả về đầy đủ context (ngữ cảnh trích xuất từ Knowledge Graph/Retriever) và câu trả lời (Answer sinh bởi LLM).
- Có thể dùng dưới dạng script dòng lệnh (CLI), chế độ tương tác (interactive), hoặc import hàm vào code khác.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional


# ============================================================================
# 1. THIẾT LẬP MÔI TRƯỜNG VÀ ĐƯỜNG DẪN IMPORT
# ============================================================================

def _setup_paths_and_env() -> Path:
    """Đảm bảo Python nhận diện được package `app` trong `backend` và nạp .env."""
    current_file = Path(__file__).resolve()
    # Tìm thư mục backend
    if (current_file.parent / "backend" / "app").exists():
        backend_root = current_file.parent / "backend"
    elif (current_file.parent / "app").exists():
        backend_root = current_file.parent
    else:
        # Fallback tìm từ thư mục hiện tại
        backend_root = current_file.parent

    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    # Nạp file .env
    try:
        from dotenv import load_dotenv
        if (backend_root / ".env").exists():
            load_dotenv(backend_root / ".env", override=False)
        if (backend_root.parent / ".env").exists():
            load_dotenv(backend_root.parent / ".env", override=False)
    except ImportError:
        pass

    return backend_root


def _configure_utf8_console() -> None:
    """Cấu hình encoding UTF-8 để terminal Windows / PowerShell hiển thị tiếng Việt không bị lỗi font."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


# Thiết lập ngay khi module được load
_BACKEND_ROOT = _setup_paths_and_env()
_configure_utf8_console()


# ============================================================================
# 2. HÀM XỬ LÝ CHÍNH CHO LUỒNG THÔNG BÁO
# ============================================================================

async def run_thong_bao(
    query: str,
    *,
    top_k: Optional[int] = None,
    max_context_chars: Optional[int] = None,
    generate_answer: bool = True,
) -> Dict[str, Any]:
    """Chạy độc lập pipeline THÔNG BÁO và sinh câu trả lời.

    Args:
        query: Câu hỏi cần tra cứu thông báo (tiếng Việt).
        top_k: Số lượng candidate gốc cần trích xuất (mặc định lấy từ .env hoặc 6).
        max_context_chars: Số ký tự tối đa của context (mặc định lấy từ .env hoặc 12000).
        generate_answer: True nếu muốn gọi LLM sinh câu trả lời từ context; False nếu chỉ lấy context.

    Returns:
        Dict chứa:
            - 'query': Câu hỏi gốc
            - 'normalized_query': Câu hỏi sau khi chuẩn hóa
            - 'context': Toàn bộ ngữ cảnh trích xuất được từ Knowledge Graph & Retriever
            - 'answer': Câu trả lời sinh bởi LLM (hoặc chuỗi rỗng nếu generate_answer=False)
            - 'temporal_scope': Phạm vi thời gian / học kỳ nhận diện được
            - 'details': Chi tiết thống kê candidates và thời gian thực thi
    """
    from app.services.common.llm_service import LLMService
    from app.services.thong_bao.pipeline import ThongBaoPipeline

    question = (query or "").strip()
    if not question:
        raise ValueError("Câu hỏi không được để trống!")

    # Cấu hình top_k và max_context_chars
    if top_k is None:
        try:
            top_k = max(1, int(os.getenv("CHAT_GLOBAL_TOP_K", "6")))
        except ValueError:
            top_k = 6

    if max_context_chars is None:
        try:
            max_context_chars = max(1000, int(os.getenv("MAX_CONTEXT_CHARS", "12000")))
        except ValueError:
            max_context_chars = 12000

    total_start = time.perf_counter()
    pipeline = ThongBaoPipeline()
    llm = LLMService()

    # 1. Chạy retrieval pipeline của miền Thông báo
    pipeline_start = time.perf_counter()
    result = await pipeline.run(
        question,
        top_k=top_k,
        max_context_chars=max_context_chars,
    )
    pipeline_ms = (time.perf_counter() - pipeline_start) * 1000

    # 2. Sinh câu trả lời qua LLM dựa trên Context
    answer = ""
    gen_ms = 0.0
    if generate_answer:
        gen_start = time.perf_counter()
        answer = await llm.generate(result.normalized_query, result.context)
        gen_ms = (time.perf_counter() - gen_start) * 1000

    total_ms = (time.perf_counter() - total_start) * 1000

    return {
        "query": result.original_query or question,
        "normalized_query": result.normalized_query or question,
        "context": result.context,
        "answer": answer,
        "temporal_scope": asdict(result.temporal_scope) if hasattr(result, "temporal_scope") else {},
        "details": {
            "notice_type": getattr(result, "notice_type", None),
            "notification_ids": getattr(result, "notification_ids", []),
            "exact_values": getattr(result, "exact_values", {}),
            "candidate_count": len(result.candidates),
            "selected_candidates_count": len(result.selected_candidates),
            "expanded_candidates_count": len(result.expanded_candidates),
            "timing_ms": {
                "retrieval_pipeline_ms": round(pipeline_ms, 2),
                "generation_ms": round(gen_ms, 2),
                "total_ms": round(total_ms, 2),
            },
        },
    }


def run_thong_bao_sync(
    query: str,
    *,
    top_k: Optional[int] = None,
    max_context_chars: Optional[int] = None,
    generate_answer: bool = True,
) -> Dict[str, Any]:
    """Phiên bản đồng bộ (synchronous) của hàm run_thong_bao để gọi tiện lợi."""
    return asyncio.run(
        run_thong_bao(
            query,
            top_k=top_k,
            max_context_chars=max_context_chars,
            generate_answer=generate_answer,
        )
    )


# ============================================================================
# 3. GIAO DIỆN DÒNG LỆNH (CLI) & IN KẾT QUẢ
# ============================================================================

def _print_formatted_result(data: Dict[str, Any], show_details: bool = False) -> None:
    """In kết quả trực quan ra màn hình Console."""
    line_sep = "=" * 80
    sub_sep = "-" * 80

    print(f"\n{line_sep}")
    print("🔹 CÂU HỎI:")
    print(f"   Gốc:      {data['query']}")
    if data['query'] != data['normalized_query']:
        print(f"   Chuẩn hóa: {data['normalized_query']}")
    print(f"{line_sep}")

    print("📄 CONTEXT TRÍCH XUẤT (TỪ RETRIEVER / KNOWLEDGE GRAPH):")
    context_text = data.get("context", "").strip()
    if context_text:
        print(context_text)
    else:
        print("   [Không tìm thấy context phù hợp]")
    print(f"{line_sep}")

    print("💡 CÂU TRẢ LỜI (TỪ LLM):")
    answer_text = data.get("answer", "").strip()
    if answer_text:
        print(answer_text)
    else:
        print("   [Chưa có câu trả lời]")
    print(f"{line_sep}")

    timing = data.get("details", {}).get("timing_ms", {})
    print(
        f"⏱️  Thời gian: Pipeline = {timing.get('retrieval_pipeline_ms', 0)}ms | "
        f"LLM = {timing.get('generation_ms', 0)}ms | "
        f"Tổng = {timing.get('total_ms', 0)}ms"
    )

    if show_details:
        details = data.get("details", {})
        print(f"\n🔍 CHI TIẾT DEBUG:")
        print(f"   - Temporal Scope:    {data.get('temporal_scope')}")
        print(f"   - Notice Type:       {details.get('notice_type')}")
        print(f"   - Notification IDs:  {details.get('notification_ids')}")
        print(f"   - Candidate Counts:  Raw={details.get('candidate_count')}, "
              f"Selected={details.get('selected_candidates_count')}, "
              f"Expanded={details.get('expanded_candidates_count')}")
    print(f"{line_sep}\n")


def _close_neo4j() -> None:
    """Đóng driver kết nối Neo4j khi kết thúc chương trình."""
    try:
        from app.db.neo4j import close_driver
        close_driver()
    except Exception:
        pass


async def _run_interactive_loop(top_k: Optional[int], max_context_chars: Optional[int], show_details: bool) -> None:
    """Chế độ tương tác nhập liên tục nhiều câu hỏi."""
    print("\n" + "=" * 80)
    print("🚀 CHẾ ĐỘ TƯƠNG TÁC LUỒNG THÔNG BÁO")
    print("Nhập câu hỏi cần kiểm tra (Gõ 'exit' hoặc 'quit' để thoát)")
    print("=" * 80 + "\n")

    while True:
        try:
            query = input("Nhập câu hỏi Thông Báo > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            print("Tạm biệt!")
            break

        try:
            result = await run_thong_bao(
                query,
                top_k=top_k,
                max_context_chars=max_context_chars,
            )
            _print_formatted_result(result, show_details=show_details)
        except Exception as exc:
            print(f"❌ Lỗi khi xử lý: {exc}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chạy riêng luồng THÔNG BÁO, trả về Context và Câu trả lời (LLM)."
    )
    parser.add_argument("query", nargs="?", help="Câu hỏi Thông báo (ví dụ: 'Khi nào đăng ký KHHT học kỳ 2?')")
    parser.add_argument("-i", "--interactive", action="store_true", help="Bật chế độ nhập tương tác nhiều câu hỏi liên tiếp.")
    parser.add_argument("--top-k", type=int, default=None, help="Số lượng candidate retrieval (mặc định lấy từ cấu hình .env).")
    parser.add_argument("--max-context-chars", type=int, default=None, help="Giới hạn ký tự context tối đa (mặc định 12000).")
    parser.add_argument("--no-llm", action="store_true", help="Chỉ trích xuất Context, không gọi LLM sinh câu trả lời.")
    parser.add_argument("--json", action="store_true", help="Xuất toàn bộ kết quả dưới dạng JSON.")
    parser.add_argument("-v", "--verbose", action="store_true", help="In thêm thông tin debug chi tiết.")

    args = parser.parse_args()

    # Mặc định query mẫu nếu người dùng không truyền tham số và không bật interactive
    default_sample_query = "Thời gian đăng ký kế hoạch học tập học kỳ 2 năm học 2024-2025 khi nào?"
    query = (args.query or "").strip()

    try:
        if args.interactive:
            asyncio.run(
                _run_interactive_loop(
                    top_k=args.top_k,
                    max_context_chars=args.max_context_chars,
                    show_details=args.verbose,
                )
            )
        else:
            if not query:
                print(f"ℹ️ Không có câu hỏi được truyền vào, sử dụng câu hỏi mẫu: '{default_sample_query}'")
                print("   (Mẹo: Dùng `python run_thong_bao.py \"<câu hỏi của bạn>\"` hoặc `python run_thong_bao.py -i`)")
                query = default_sample_query

            result = asyncio.run(
                run_thong_bao(
                    query,
                    top_k=args.top_k,
                    max_context_chars=args.max_context_chars,
                    generate_answer=not args.no_llm,
                )
            )

            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                _print_formatted_result(result, show_details=args.verbose)

        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"\n❌ Lỗi thực thi: {exc}", file=sys.stderr)
        return 1
    finally:
        _close_neo4j()


if __name__ == "__main__":
    raise SystemExit(main())
