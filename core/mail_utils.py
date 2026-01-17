import re
from typing import Optional


def extract_verification_code(text: str) -> Optional[str]:
    """提取验证码"""
    if not text:
        return None

    # 策略1: 上下文关键词匹配（中英文冒号）
    # 排除 CSS 样式值（如 14px, 16pt 等）
    context_pattern = r"(?:验证码|code|verification|passcode|pin).*?[:：]\s*([A-Za-z0-9]{4,8})\b"
    match = re.search(context_pattern, text, re.IGNORECASE)
    if match:
        candidate = match.group(1)
        # 排除 CSS 单位值
        if not re.match(r"^\d+(?:px|pt|em|rem|vh|vw|%)$", candidate, re.IGNORECASE):
            return candidate

    # 策略2: 6位数字
    digits = re.findall(r"\b\d{6}\b", text)
    if digits:
        return digits[0]

    # 策略3: 6位字母数字混合
    alphanumeric = re.findall(r"\b[A-Z0-9]{6}\b", text)
    for candidate in alphanumeric:
        has_letter = any(c.isalpha() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        if has_letter and has_digit:
            return candidate

    return None
