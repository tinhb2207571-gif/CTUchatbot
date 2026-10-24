"""Các lời gọi LLM dùng chung cho router, social và luồng Thông báo.

CTĐT và QCHV giữ prompt/domain logic riêng trong package tương ứng.
"""
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from app.core.llm_config import LLM_MODEL
from app.services.common.streaming import answer_token_handler, stream_ollama_answer
from app.services.common.pipeline_logger import elapsed_ms, log_event, now


def _load_env_files() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    repo_root = backend_root.parent
    load_dotenv(backend_root / ".env", override=False)
    load_dotenv(repo_root / ".env", override=False)


def _get_env(*keys: str, default: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return default


_load_env_files()

OLLAMA_BASE_URL = _get_env("OLLAMA_BASE_URL", "OLLAMA_HOST", default="http://localhost:11434").rstrip("/")
OLLAMA_GENERATE_URL = os.getenv("OLLAMA_GENERATE_URL", f"{OLLAMA_BASE_URL}/api/generate")
OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", f"{OLLAMA_BASE_URL}/api/chat")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))

ROUTER_DOMAINS = {"CTDT", "QCHV", "THONG_BAO", "SOCIAL"}
logger = logging.getLogger("app.llm")


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_router_domain(value: object) -> str | None:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "CTDT": "CTDT",
        "QCHV": "QCHV",
        "QUY_CHE": "QCHV",
        "QUYCHE": "QCHV",
        "THONG_BAO": "THONG_BAO",
        "THONGBAO": "THONG_BAO",
        "NOTIFICATION": "THONG_BAO",
        "SOCIAL": "SOCIAL",
        "SOCIALIZE": "SOCIAL",
    }
    domain = aliases.get(normalized)
    return domain if domain in ROUTER_DOMAINS else None




def _fold_text(text: str) -> str:
    """Chuẩn hóa nhẹ chỉ để match rule router; không thay đổi câu hỏi gốc."""
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_marks.replace("đ", "d")).strip()


def _high_confidence_domain(query: str) -> tuple[str | None, str | None]:
    """Rule bảo thủ: chỉ trả domain khi tín hiệu đủ rõ, còn lại giao LLM.

    Không dùng keyword đơn lẻ kiểu ``hoc phan -> CTDT`` hay ``ke hoach -> THONG_BAO``.
    """
    text = _fold_text(query)
    if not text:
        return "SOCIAL", "empty_query"

    # SOCIAL chỉ bắt câu xã giao thuần túy; nếu có nội dung học vụ thì để LLM xử lý.
    social_patterns = (
        r"^(xin )?(chao|hello|hi)( ban| chatbot| tro ly)?[.!? ]*$",
        r"^(cam on|thanks|thank you)( ban)?[.!? ]*$",
        r"^(ban la ai|ban co the lam gi|tro ly nay lam gi)[.!? ]*$",
    )
    if any(re.fullmatch(pattern, text) for pattern in social_patterns):
        return "SOCIAL", "pure_social"

    # Tham chiếu cấu trúc văn bản pháp quy là QCHV với độ tin cậy cao.
    if re.search(r"\b(chuong|dieu|khoan|diem)\s+([ivxlcdm]+|\d+|[a-z])\b", text):
        return "QCHV", "regulation_reference"

    # Quy định/định nghĩa học vụ rõ ràng -> QCHV.
    if text.startswith("quy dinh ") or "theo quy dinh" in text:
        return "QCHV", "explicit_regulation"

    qchv_definition_patterns = (
        r"\bke hoach hoc tap chuan toan khoa\b.*\bla gi\b",
        r"\bhoc phan tien quyet\b.*\bla gi\b",
        r"\bhoc phan song hanh\b.*\bla gi\b",
        r"\bhoc ky\b.*\bla gi\b",
    )
    if any(re.search(pattern, text) for pattern in qchv_definition_patterns):
        return "QCHV", "academic_definition"

    # Mã học phần + câu hỏi thuộc tính/quan hệ của chính học phần -> CTDT.
    has_course_code = bool(re.search(r"(?<![a-z0-9])[a-z]{2,4}\d{3}[a-z]?(?![a-z0-9])", text))
    ctdt_course_intents = (
        "bao nhieu tin chi",
        "tien quyet",
        "song hanh",
        "hoc phan truoc",
        "thuoc khoi",
        "hoc ky nao",
        "ten hoc phan",
    )
    notification_course_intents = (
        "bi xoa",
        "xoa lop",
        "mo lop",
        "lich hoc",
        "dang ky khi nao",
    )
    if has_course_code and any(term in text for term in notification_course_intents):
        return "THONG_BAO", "course_event"
    if has_course_code and any(term in text for term in ctdt_course_intents):
        return "CTDT", "course_structure"

    # Ngành/chương trình cụ thể + cấu trúc đào tạo -> CTDT.
    has_program_marker = any(term in text for term in ("nganh ", "chuong trinh dao tao", "ctdt"))
    ctdt_program_intents = (
        "bao nhieu tin chi",
        "gom nhung hoc phan",
        "gom cac hoc phan",
        "hoc nhung mon",
        "hoc mon gi",
        "chuan dau ra",
        "cau truc chuong trinh",
        "ke hoach hoc tap chuan",
    )
    if has_program_marker and any(term in text for term in ctdt_program_intents):
        return "CTDT", "program_structure"

    # Thông báo: phải có tín hiệu triển khai/sự kiện cụ thể, không chỉ có từ "kế hoạch".
    temporal_patterns = (
        r"\bkhi nao\b",
        r"\bngay nao\b",
        r"\bthoi gian\b",
        r"\bhan(?: chot)?\b",
        r"\bdot\b",
        r"\bbat dau\b",
        r"\bket thuc\b",
        r"\blich\b",
    )
    event_terms = (
        "dang ky hoc phan",
        "dang ky khht",
        "dang ky ke hoach hoc tap",
        "dieu chinh khht",
        "dieu chinh ke hoach hoc tap",
        "hoc ky",
        "nghi",
        "xoa lop",
        "chuyen nganh",
        "dong hoc phi",
    )
    if any(re.search(pattern, text) for pattern in temporal_patterns) and any(term in text for term in event_terms):
        return "THONG_BAO", "scheduled_event"

    if "danh sach" in text and any(term in text for term in ("sinh vien", "chuyen nganh", "xoa lop", "lop hoc phan")):
        return "THONG_BAO", "announcement_list"

    return None, None


def _query_numbers(text: str) -> list[str]:
    return re.findall(r"\d+", text or "")


def _protected_notification_identifiers(text: str) -> set[str]:
    patterns = (
        r"(?<![A-Z0-9])[A-Z]{2,4}\d{3}[A-Z]?(?![A-Z0-9])",
        r"(?<![A-Z0-9])[A-Z]\d{7}(?![A-Z0-9])",
        r"\bK\s*\d{2}\b",
        r"\b\d{1,6}\s*/\s*[A-ZĐ][A-ZĐ-]{1,20}\b",
    )
    return {
        re.sub(r"\s+", "", match.group(0)).upper()
        for pattern in patterns
        for match in re.finditer(pattern, text or "", flags=re.IGNORECASE)
    }


def _valid_notification_normalization(original: str, normalized: object) -> str | None:
    candidate = re.sub(r"\s+", " ", str(normalized or "")).strip()
    if not candidate or len(candidate) > 500:
        return None
    if _query_numbers(original) != _query_numbers(candidate):
        return None
    if _protected_notification_identifiers(original) != _protected_notification_identifiers(candidate):
        return None
    return candidate


def _log_ollama_completion(
    payload: Dict[str, Any], content: str, *, model: str, endpoint: str,
    think: bool, num_predict: int | None,
) -> None:
    message = payload.get("message") or {}
    thinking = payload.get("thinking") or message.get("thinking") or ""
    fields = {
        "model": model, "endpoint": endpoint, "think": think,
        "num_predict": num_predict,
        "done": payload.get("done"),
        "done_reason": payload.get("done_reason"),
        "eval_count": payload.get("eval_count"),
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "response_chars": len(content), "thinking_chars": len(thinking),
    }
    # Thiếu metadata được giữ là null, không suy đoán lý do dừng.
    warn = not content.strip() or payload.get("done_reason") == "length"
    log = logger.warning if warn else logger.info
    log("[LLM][COMPLETION] %s", json.dumps(fields, ensure_ascii=False))


async def call_model(
    model: str,
    prompt: str,
    temperature: float = 0.3,
    keep_alive: str = "1h",
    *,
    think: bool = True,
    num_predict: int | None = 4096,
) -> str:
    """Gọi Ollama bằng /api/generate; fallback /api/chat nếu endpoint generate không có.

    Mặc định bật thinking; chỉ phần trả lời cuối được chuyển cho người dùng.
    ``num_predict`` cho phép từng tác vụ giới hạn số token đầu ra riêng.
    """
    options: Dict[str, Any] = {"temperature": temperature}
    if num_predict is not None:
        options["num_predict"] = int(num_predict)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                OLLAMA_GENERATE_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "think": think,
                    "keep_alive": keep_alive,
                    "options": options,
                },
            )
            if response.status_code == 404:
                raise httpx.HTTPStatusError(
                    "Generate endpoint not found",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("response")
            if not isinstance(content, str):
                raise RuntimeError(f"Invalid Ollama generate response: {payload}")
            _log_ollama_completion(
                payload, content, model=model, endpoint="generate",
                think=think, num_predict=num_predict,
            )
            return content
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise

        response = await client.post(
            OLLAMA_CHAT_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": think,
                "keep_alive": keep_alive,
                "options": options,
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = (payload.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Invalid Ollama chat response: {payload}")
        _log_ollama_completion(
            payload, content, model=model, endpoint="chat",
            think=think, num_predict=num_predict,
        )
        return content


async def call_model_json(
    model: str,
    prompt: str,
    *,
    num_predict: int = 4096,
) -> Dict[str, Any]:
    content = await call_model(
        model,
        prompt,
        temperature=0.0,
        think=True,
        num_predict=num_predict,
    )
    data = _extract_json_object(content)
    if not data:
        reason = "empty_response" if not content.strip() else "empty_or_invalid_json_object"
        logger.warning("[LLM][JSON_WARNING] %s", json.dumps({
            "model": model, "reason": reason,
            "response_chars": len(content),
            "response_preview": content[:2000],
            "preview_truncated": len(content) > 2000,
        }, ensure_ascii=False))
    return data


async def call_llm(
    prompt: str,
    temperature: float = 0.3,
    *,
    num_predict: int = 4096,
) -> str:
    if answer_token_handler.get() is not None:
        return await stream_ollama_answer(
            LLM_MODEL, prompt, generate_url=OLLAMA_GENERATE_URL,
            chat_url=OLLAMA_CHAT_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
            temperature=temperature, num_predict=num_predict, think=True,
        )
    return await call_model(
        LLM_MODEL,
        prompt,
        temperature=temperature,
        think=True,
        num_predict=num_predict,
    )


class LLMService:
    async def classify_domain(self, query: str, history: str = "") -> str:
        """Router lai: rule độ tin cậy cao trước, LLM fallback cho câu còn mơ hồ.

        ``history`` được giữ trong chữ ký để tương thích nhưng không đưa vào prompt router,
        tránh lượt hội thoại trước kéo sai domain của câu hiện tại.
        """
        started = now()
        rule_domain, rule_reason = _high_confidence_domain(query)
        if rule_domain is not None:
            logger.info(
                "[router-rule] query=%r domain=%s reason=%s",
                query,
                rule_domain,
                rule_reason,
            )
            log_event(
                "ROUTER", "result", domain=rule_domain, method="rule",
                reason=rule_reason, llm_ms=0.0, total_ms=elapsed_ms(started),
            )
            return rule_domain

        prompt = f"""
Phân loại câu hỏi theo NGUỒN DỮ LIỆU cần dùng để trả lời trong chatbot Đại học Cần Thơ.

QCHV:
- Văn bản quy chế học vụ: định nghĩa, khái niệm, nguyên tắc, điều kiện, quyền/nghĩa vụ,
  quy trình và quy định học vụ.

CTDT:
- Dữ liệu chương trình đào tạo/ngành/học phần cụ thể: mã học phần, tín chỉ, tiên quyết,
  song hành, chuẩn đầu ra, khối kiến thức, cấu trúc hoặc kế hoạch đào tạo của một ngành.

THONG_BAO:
- Thông báo/kế hoạch triển khai cụ thể: thời gian, ngày, hạn, đợt, lịch, danh sách,
  mốc thực hiện, quyết định của một học kỳ/năm học.

SOCIAL:
- Chỉ dùng cho chào hỏi, cảm ơn hoặc hội thoại không cần tra cứu dữ liệu.
- Nếu câu hỏi có nội dung học vụ thì KHÔNG chọn SOCIAL.

Các trường hợp dễ nhầm:
- "Kế hoạch học tập chuẩn toàn khóa là gì?" -> QCHV
- "Kế hoạch học tập chuẩn của ngành Khoa học máy tính gồm những học phần nào?" -> CTDT
- "Khi nào đăng ký kế hoạch học tập?" -> THONG_BAO
- "Học phần tiên quyết là gì?" -> QCHV
- "CT177 có học phần tiên quyết nào?" -> CTDT
- "Học kỳ là gì?" -> QCHV
- "Học kỳ 3 ngành Khoa học máy tính học môn gì?" -> CTDT
- "Học kỳ mới bắt đầu khi nào?" -> THONG_BAO

Chỉ trả JSON, không giải thích:
{{"domain":"QCHV|CTDT|THONG_BAO|SOCIAL"}}

Câu hỏi:
{query}
"""
        llm_started = now()
        try:
            data = await call_model_json(LLM_MODEL, prompt, num_predict=4096)
        except Exception:
            log_event(
                "ROUTER", "result", method="llm", model=LLM_MODEL,
                status="error", llm_ms=elapsed_ms(llm_started), total_ms=elapsed_ms(started),
            )
            raise
        llm_ms = elapsed_ms(llm_started)
        domain = _normalize_router_domain(data.get("domain") if isinstance(data, dict) else None)
        fallback = domain is None
        if domain is None:
            logger.warning("[router-llm] output không hợp lệ: %s; fallback=CTDT", data)
            domain = "CTDT"
        logger.info("[router-llm] query=%r domain=%s", query, domain)
        log_event(
            "ROUTER", "result", domain=domain, method="llm", model=LLM_MODEL,
            fallback=fallback, llm_ms=llm_ms, total_ms=elapsed_ms(started),
        )
        return domain

    async def generate_without_query(self, query: str, history: str = "") -> str:
        prompt = f"""
Bạn là trợ lý tư vấn Đại học Cần Thơ (CTU). Trả lời ngắn gọn, tự nhiên bằng tiếng Việt.
Đây là nhánh SOCIAL nên không được tự bịa thông tin chuyên môn từ Knowledge Base.

History:
{history or "[empty]"}

User:
{query}
"""
        return (await call_llm(prompt, temperature=0.4, num_predict=4096)).strip()

    async def normalize_notification_query(self, query: str) -> str:
        """Chuẩn hóa câu THONG_BAO nhưng bảo vệ mọi số và định danh exact."""
        original = (query or "").strip()
        if not original:
            return original

        prompt = f"""
Bạn là công cụ chuẩn hóa câu hỏi tiếng Việt để truy xuất dữ liệu Thông báo CTU.

Chỉ sửa cách diễn đạt phục vụ retrieval:
- Sửa lỗi gõ đơn giản và thêm dấu khi chắc chắn.
- Mở rộng viết tắt rõ nghĩa: KHHT = kế hoạch học tập; ĐKHP = đăng ký học phần;
  HK1/HK2 = học kỳ 1/2; SV = sinh viên.
- Không trả lời và không suy luận thêm thông tin.
- Giữ nguyên mã học phần, MSSV, khóa, năm học, năm, ngày, con số, mã văn bản,
  tên ngành, tên học phần và tên chương trình.
- Không tự thêm khóa, học kỳ, năm hay entity mới.

Chỉ trả JSON:
{{"normalized_query": "câu đã chuẩn hóa"}}

Câu hỏi gốc:
{original}
"""
        try:
            data = await call_model_json(
                LLM_MODEL,
                prompt,
                num_predict=4096,
            )
        except Exception as exc:
            logger.warning("[notification_normalizer] lỗi LLM, dùng câu gốc: %s", exc)
            return original

        normalized = _valid_notification_normalization(original, data.get("normalized_query"))
        if normalized is None:
            logger.warning("[notification_normalizer] output không an toàn, dùng câu gốc")
            return original
        return normalized

    async def generate(self, query: str, context: str) -> str:
        """Sinh câu trả lời cho THONG_BAO từ context retrieval đã hoàn tất."""
        prompt = f"""
Bạn là trợ lý tư vấn Đại học Cần Thơ (CTU).

Chỉ trả lời dựa trên Context bên dưới.
Quy tắc bắt buộc:
- Trả lời chính xác ngày nếu có thay vì khoảng thời gian chung.
- Trả lời đúng phần người dùng hỏi, không tóm tắt toàn bộ Context.
- Câu hỏi đơn giản: ưu tiên 1-3 câu ngắn.
- Chỉ dùng bullet khi câu hỏi thực sự có nhiều ý hoặc nhiều trường hợp cần phân biệt.
- Không nhắc lại các thông tin liên quan nhưng không cần thiết để trả lời câu hỏi.
- Không dùng kiến thức bên ngoài, không suy đoán hoặc bịa dữ liệu.
- Nếu Context không đủ, nói ngắn gọn rằng chưa tìm thấy đủ thông tin.
- Không thêm lời mời hỏi tiếp, lời khuyên chung hoặc kết luận dài nếu người dùng không yêu cầu.

Context:
{context or "[Không có context]"}

Câu hỏi:
{query}

Trả lời ngắn gọn và trực tiếp.
"""
        return (await call_llm(prompt, temperature=0.2, num_predict=4096)).strip()
