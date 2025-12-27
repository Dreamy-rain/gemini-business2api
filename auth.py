"""
认证相关装饰器和工具函数
"""
from functools import wraps
from fastapi import HTTPException, Header
from typing import Optional


def extract_admin_key(key: Optional[str] = None, authorization: Optional[str] = None) -> Optional[str]:
    """
    统一提取管理员密钥

    优先级：
    1. URL 参数 ?key=xxx
    2. Authorization Header (支持 Bearer token 格式)

    Args:
        key: URL 查询参数中的密钥
        authorization: Authorization Header 中的密钥

    Returns:
        提取到的密钥，如果都为空则返回 None
    """
    if key:
        return key
    if authorization:
        # 支持 Bearer token 格式
        return authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    return None


def require_path_prefix(path_prefix_value: str):
    """
    验证路径前缀的装饰器

    Args:
        path_prefix_value: 正确的路径前缀值

    Returns:
        装饰器函数

    Example:
        @app.get("/{path_prefix}/admin")
        @require_path_prefix(PATH_PREFIX)
        async def admin_home(path_prefix: str, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, path_prefix: str, **kwargs):
            if path_prefix != path_prefix_value:
                # 返回 404 而不是 401，假装端点不存在（安全性考虑）
                raise HTTPException(404, "Not Found")
            return await func(*args, path_prefix=path_prefix, **kwargs)
        return wrapper
    return decorator


def require_admin_auth(admin_key_value: str):
    """
    验证管理员权限的装饰器

    支持两种认证方式：
    1. URL 参数：?key=xxx
    2. Authorization Header：Bearer xxx 或直接传密钥

    Args:
        admin_key_value: 正确的管理员密钥

    Returns:
        装饰器函数

    Example:
        @app.get("/{path_prefix}/admin")
        @require_admin_auth(ADMIN_KEY)
        async def admin_home(key: str = None, authorization: str = Header(None), ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, key: str = None, authorization: str = Header(None), **kwargs):
            admin_key = extract_admin_key(key, authorization)
            if admin_key != admin_key_value:
                # 返回 404 而不是 401，假装端点不存在（安全性考虑）
                raise HTTPException(404, "Not Found")
            return await func(*args, key=key, authorization=authorization, **kwargs)
        return wrapper
    return decorator


def require_path_and_admin(path_prefix_value: str, admin_key_value: str):
    """
    同时验证路径前缀和管理员权限的组合装饰器

    Args:
        path_prefix_value: 正确的路径前缀值
        admin_key_value: 正确的管理员密钥

    Returns:
        装饰器函数

    Example:
        @app.get("/{path_prefix}/admin")
        @require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
        async def admin_home(path_prefix: str, key: str = None, authorization: str = Header(None), ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, path_prefix: str, key: str = None, authorization: str = Header(None), **kwargs):
            # 验证路径前缀
            if path_prefix != path_prefix_value:
                raise HTTPException(404, "Not Found")

            # 验证管理员密钥
            admin_key = extract_admin_key(key, authorization)
            if admin_key != admin_key_value:
                raise HTTPException(404, "Not Found")

            return await func(*args, path_prefix=path_prefix, key=key, authorization=authorization, **kwargs)
        return wrapper
    return decorator
