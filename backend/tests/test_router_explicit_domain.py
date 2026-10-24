import unicodedata
from unittest.mock import AsyncMock, patch

import pytest

from app.services.common import llm_service


@pytest.mark.parametrize("question,domain", [
    ('theo ctdt, Học phần "Cấu trúc dữ liệu" có học phần tiên quyết là gì?', "CTDT"),
    ("Theo CTĐT: Học phần tiên quyết là gì?", "CTDT"),
    ("  THEO CTDT\nĐiều 5 quy định gì?", "CTDT"),
    ("theo qchv, CT177 có học phần tiên quyết nào?", "QCHV"),
    ("Theo QCHV: Khi nào đăng ký học phần?", "QCHV"),
    ("theo thông báo, Học phần tiên quyết là gì?", "THONG_BAO"),
    ("Theo THONG BAO: Quy định đăng ký học phần", "THONG_BAO"),
    ("theo\tthông   báo, chào bạn", "THONG_BAO"),
    (unicodedata.normalize("NFD", "Theo thông báo: Điều 5?"), "THONG_BAO"),
])
def test_explicit_prefix_takes_priority_over_other_rules(question, domain):
    assert llm_service._high_confidence_domain(question) == (domain, "explicit_domain")


@pytest.mark.parametrize("question,domain", [
    ("Học phần tiên quyết là gì?", "QCHV"),
    ("CT177 có học phần tiên quyết nào?", "CTDT"),
    ("Khi nào đăng ký học phần?", "THONG_BAO"),
    ("Xin chào", "SOCIAL"),
])
def test_existing_rules_still_apply_without_prefix(question, domain):
    actual, reason = llm_service._high_confidence_domain(question)
    assert actual == domain
    assert reason != "explicit_domain"


@pytest.mark.parametrize("question", [
    "Theo ctdt123, học phần tiên quyết là gì?",
    "Theo qchv_extra, câu hỏi thử",
    'Cụm "theo ctdt" có nghĩa là gì?',
])
def test_partial_names_or_mentioned_prefix_do_not_force_domain(question):
    _, reason = llm_service._high_confidence_domain(question)
    assert reason != "explicit_domain"


@pytest.mark.asyncio
async def test_explicit_route_skips_llm_and_logs_reason():
    question = 'theo ctdt, Học phần "Cấu trúc dữ liệu" có học phần tiên quyết là gì?'
    with patch.object(llm_service, "call_model_json", new_callable=AsyncMock) as model, patch.object(
        llm_service, "log_event"
    ) as log:
        result = await llm_service.LLMService().classify_domain(question)
    assert result == "CTDT"
    model.assert_not_awaited()
    assert log.call_args.kwargs["method"] == "rule"
    assert log.call_args.kwargs["reason"] == "explicit_domain"
    assert log.call_args.kwargs["llm_ms"] == 0
