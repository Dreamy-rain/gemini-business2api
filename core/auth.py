"""
API认证模块
提供API Key验证功能（用于API端点）
管理端点使用Session认证（见core/session_auth.py）
"""
from typing import Optional
from fastapi import HTTPException


def verify_api_key(api_key_value: str, authorization: Optional[str] = None) -> bool:
    """
    验证 API Key

    Args:
        api_key_value: 配置的API Key值（如果为空则跳过验证）
        authorization: Authorization Header中的值

    Returns:
        验证通过返回True，否则抛出HTTPException

    支持格式：
    1. Bearer YOUR_API_KEY
    2. YOUR_API_KEY
    """
    # 如果未配置 API_KEY，则跳过验证
    if not api_key_value:
        return True

    # 检查 Authorization header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # 提取token（支持Bearer格式）
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if token != api_key_value:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    return True
