"""Chuẩn hóa viết tắt CTĐT bằng quy tắc nhỏ, không gọi thêm LLM."""

import re
import unicodedata


_ABBREVIATIONS = {"KHMT": "Khoa học máy tính", "CNTT": "Công nghệ thông tin"}


def normalize_ctdt_query(text: str) -> str:
    text = unicodedata.normalize("NFC", text).strip()
    for short, full in _ABBREVIATIONS.items():
        text = re.sub(rf"(?<!\w){short}(?!\w)", full, text, flags=re.IGNORECASE)
    return text


def entity_name_variants(text: str) -> list[str]:
    original = unicodedata.normalize("NFC", text).strip()
    expanded = normalize_ctdt_query(original)
    abbreviated = expanded
    for short, full in _ABBREVIATIONS.items():
        abbreviated = re.sub(rf"(?<!\w){re.escape(full)}(?!\w)", short, abbreviated, flags=re.IGNORECASE)
    # KB có cả tên đầy đủ lẫn tên chứa KHMT/CNTT, nên giữ cả hai cách viết.
    variants = []
    for value in (original, expanded, abbreviated):
        if value and value.casefold() not in {item.casefold() for item in variants}:
            variants.append(value)
    return variants
