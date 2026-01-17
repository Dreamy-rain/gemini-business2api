import re
from typing import Optional


def extract_verification_code(text: str) -> Optional[str]:
    """提取验证码"""
    if not text:
        return None

    # 策略1: 上下文关键词匹配（中英文冒号）
    context_pattern = r"(?:验证码|code|verification|passcode|pin).*?[:：]\s*([A-Za-z0-9]{4,8})\b"
    match = re.search(context_pattern, text, re.IGNORECASE)
    if match:
        candidate = match.group(1)
        # 排除 CSS 单位值
        if not re.match(r"^\d+(?:px|pt|em|rem|vh|vw|%)$", candidate, re.IGNORECASE):
            return candidate

    # 策略2: 6位字母数字混合（与测试代码一致，优先级提高）
    match = re.search(r"[A-Z0-9]{6}", text)
    if match:
        return match.group(0)

    # 策略3: 6位数字（降级为备选）
    digits = re.findall(r"\b\d{6}\b", text)
    if digits:
        return digits[0]

    return None
