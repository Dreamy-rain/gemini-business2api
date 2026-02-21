"""
轻量化会话绑定管理器

实现 ChatID → AccountID 的固定绑定，利用 Gemini 网页端原生上下文。
"""
import asyncio
import hashlib
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _hash_tag(value: str, length: int = 12) -> str:
    """返回稳定哈希标签，用于日志脱敏。"""
    if not value:
        return "none"
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def _extract_bearer_token(headers: dict) -> Optional[str]:
    """严格解析 Authorization: Bearer <token>。"""
    auth_header = (headers.get("authorization") or "").strip()
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1].strip():
        logger.warning("[SESSION-BIND] event=invalid_authorization_header")
        return None

    return parts[1].strip()


def extract_chat_id(
    messages: list,
    client_ip: str = "",
    headers: dict = None,
    body: dict = None
) -> tuple[str, str]:
    """
    提取或生成 ChatID（多源优先级检测）
    
    优先级：
    1. 请求头 X-Conversation-Id / X-Chat-Id
    2. 请求体 conversation_id / chat_id / metadata.conversation_id
    3. 消息指纹（基于第一条 user 消息 + IP）
    
    Args:
        messages: 消息列表
        client_ip: 客户端 IP 地址
        headers: 请求头字典
        body: 请求体字典
    
    Returns:
        (chat_id, source) 元组，source 表示 ID 来源
    """
    headers = headers or {}
    body = body or {}
    
    # 0. 【最高优先级】基于 API Key 锁定 (Single User Mode)
    # 用户需求：无论客户端如何切分上下文，API Key 永远对应同一个云端会话
    api_key = _extract_bearer_token(headers)
    if api_key:
        # 使用 API Key 的哈希作为全局唯一 ChatID
        chat_id = hashlib.md5(f"apikey:{api_key}".encode()).hexdigest()
        logger.info(
            "[SESSION-BIND] event=chat_id_from_apikey source=authorization token_hash=%s chat_hash=%s",
            _hash_tag(api_key),
            _hash_tag(chat_id),
        )
        return chat_id, "apikey_hash"

    # 1. 优先检查请求头
    header_keys = ['x-conversation-id', 'x-chat-id', 'conversation-id', 'chat-id']
    for key in header_keys:
        value = headers.get(key, "").strip()
        if value:
            logger.info(
                "[SESSION-BIND] event=chat_id_from_header source=%s value_hash=%s",
                key,
                _hash_tag(value),
            )
            return value, f"header:{key}"
    
    # 2. 检查请求体字段
    body_keys = ['conversation_id', 'chat_id', 'session_id', 'thread_id']
    for key in body_keys:
        value = body.get(key, "")
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            logger.info(
                "[SESSION-BIND] event=chat_id_from_body source=%s value_hash=%s",
                key,
                _hash_tag(normalized),
            )
            return normalized, f"body:{key}"
    
    # 检查 metadata 中的 ID
    metadata = body.get('metadata', {})
    if isinstance(metadata, dict):
        for key in body_keys:
            value = metadata.get(key, "")
            if isinstance(value, str) and value.strip():
                normalized = value.strip()
                logger.info(
                    "[SESSION-BIND] event=chat_id_from_metadata source=%s value_hash=%s",
                    key,
                    _hash_tag(normalized),
                )
                return normalized, f"metadata:{key}"
    
    # 3. 回退到消息指纹
    chat_id = generate_chat_id_from_messages(messages, client_ip)
    return chat_id, "fingerprint"


def generate_chat_id_from_messages(messages: list, client_ip: str = "") -> str:
    """
    基于消息生成 ChatID（仅作为回退方案）
    
    策略：基于【第一条 user 消息内容 + 客户端IP】生成稳定指纹
    """
    if not messages:
        chat_id = hashlib.md5(f"{client_ip}:{time.time()}".encode()).hexdigest()
        logger.warning("[SESSION-BIND] event=generated_chat_id_random reason=empty_messages chat_hash=%s", _hash_tag(chat_id))
        return chat_id

    logger.info("[SESSION-BIND] event=messages_received count=%s", len(messages))
    
    # 找第一条 user 消息（而非 messages[0]，避免 system prompt 干扰）
    first_user_msg = None
    for msg in messages:
        if msg.get("role") == "user":
            first_user_msg = msg
            break
    
    # 如果没有 user 消息，回退到第一条消息
    target_msg = first_user_msg if first_user_msg else messages[0]
    
    role = target_msg.get("role", "")
    content = target_msg.get("content", "")
    
    # 处理多模态内容
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = "".join(text_parts)
    
    # 标准化处理
    content = str(content).strip()[:500]
    
    # 生成指纹：IP + 角色 + 内容
    fingerprint = f"{client_ip}|{role}|{content}"
    chat_id = hashlib.md5(fingerprint.encode()).hexdigest()
    
    logger.info(
        "[SESSION-BIND] event=chat_id_from_fingerprint ip_hash=%s role=%s content_length=%s chat_hash=%s",
        _hash_tag(client_ip),
        role or "unknown",
        len(content),
        _hash_tag(chat_id),
    )
    
    return chat_id


# 为了向后兼容，保留旧函数名
def generate_chat_id(messages: list, client_ip: str = "") -> str:
    """向后兼容函数，请使用 extract_chat_id"""
    return generate_chat_id_from_messages(messages, client_ip)


class SessionBindingManager:
    """
    会话绑定管理器
    
    维护 ChatID → AccountID 的映射关系，支持：
    - 固定绑定：同一 ChatID 始终使用同一账号
    - 异常漂移：账号出错时自动解绑
    - 持久化：绑定关系存入数据库
    """
    
    def __init__(self, persist_interval: int = 60):
        # 内存缓存：{chat_id: {"account_id": str, "created_at": float}}
        self._bindings: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._dirty = False  # 是否有未持久化的变更
        self._persist_interval = persist_interval
        self._max_bindings = 10000  # 最大绑定数量
        self._binding_ttl = 86400 * 7  # 绑定过期时间（7天）
        
    async def get_binding(self, chat_id: str) -> Optional[dict]:
        """
        获取 ChatID 对应的绑定信息
        
        Returns:
            {
                "account_id": str,
                "session_id": str (optional),
                "created_at": float
            }
            如果未绑定则返回 None
        """
        async with self._lock:
            binding = self._bindings.get(chat_id)
            if not binding:
                return None
            
            # 检查是否过期
            if time.time() - binding.get("created_at", 0) > self._binding_ttl:
                del self._bindings[chat_id]
                self._dirty = True
                return None
            
            return binding
    
    async def set_binding(self, chat_id: str, account_id: str, session_id: str = None) -> None:
        """
        设置绑定关系
        
        Args:
            chat_id: 对话ID
            account_id: 账号ID
            session_id: Google会话ID (projects/.../locations/global/sessions/...)
        """
        async with self._lock:
            # 保留旧的创建时间（如果是更新现有绑定）
            old_binding = self._bindings.get(chat_id, {})
            created_at = old_binding.get("created_at", time.time())
            
            # 如果提供了新的 session_id，则更新，否则尝试保留旧的（如果账号没变）
            final_session_id = session_id
            if not final_session_id and old_binding.get("account_id") == account_id:
                final_session_id = old_binding.get("session_id")

            self._bindings[chat_id] = {
                "account_id": account_id,
                "session_id": final_session_id,
                "created_at": created_at
            }
            self._dirty = True
            
            # 检查缓存大小，LRU 清理
            if len(self._bindings) > self._max_bindings:
                self._cleanup_oldest()
        
        sess_tag = "set" if session_id else "none"
        logger.info(
            "[SESSION-BIND] event=binding_set chat_hash=%s account_hash=%s session=%s",
            _hash_tag(chat_id),
            _hash_tag(account_id),
            sess_tag,
        )
    
    async def remove_binding(self, chat_id: str) -> bool:
        """
        解除绑定（用于异常漂移）

        Returns:
            是否成功解除（True=存在并已解除，False=不存在）
        """
        async with self._lock:
            if chat_id in self._bindings:
                del self._bindings[chat_id]
                self._dirty = True
                logger.info(
                    "[SESSION-BIND] event=binding_removed chat_hash=%s",
                    _hash_tag(chat_id),
                )
                return True
            return False
    
    async def reset_session_binding(self, chat_id: str) -> bool:
        """
        重置会话绑定（仅清除 session_id，保留 account_id）
        
        Returns:
            是否成功重置（True=存在并已重置，False=不存在）
        """
        async with self._lock:
            if chat_id in self._bindings:
                binding = self._bindings[chat_id]
                binding["session_id"] = None  # 清除 Session ID
                self._dirty = True
                logger.info(
                    "[SESSION-BIND] event=session_binding_reset chat_hash=%s account_hash=%s",
                    _hash_tag(chat_id),
                    _hash_tag(str(binding.get('account_id', ''))),
                )
                return True
            return False
    
    def _cleanup_oldest(self) -> None:
        """清理最旧的绑定（LRU策略）"""
        if not self._bindings:
            return
        
        # 按创建时间排序，删除最旧的 10%
        sorted_items = sorted(
            self._bindings.items(),
            key=lambda x: x[1].get("created_at", 0)
        )
        
        remove_count = max(1, len(sorted_items) // 10)
        for chat_id, _ in sorted_items[:remove_count]:
            del self._bindings[chat_id]
        
        logger.info(f"[SESSION-BIND] LRU 清理 {remove_count} 个过期绑定")
    
    async def load_from_db(self) -> None:
        """从数据库加载绑定关系"""
        try:
            from core import storage
            if not storage.is_database_enabled():
                logger.info("[SESSION-BIND] 数据库未启用，使用内存缓存模式")
                return
            
            # 直接调用异步 DB 方法（利用 per-loop pool 机制）
            data = await storage.db_get("session_bindings")
            if data and isinstance(data, dict):
                async with self._lock:
                    self._bindings = data
                logger.info(f"[SESSION-BIND] 从数据库加载 {len(data)} 个绑定")
            else:
                logger.info("[SESSION-BIND] 数据库中无绑定记录")
        except Exception as e:
            logger.error(f"[SESSION-BIND] 加载绑定失败: {e}")
    
    async def persist_to_db(self) -> bool:
        """持久化绑定关系到数据库"""
        if not self._dirty:
            return True
        
        try:
            from core import storage
            if not storage.is_database_enabled():
                return False
            
            async with self._lock:
                data = dict(self._bindings)
                self._dirty = False
            
            # 直接调用异步 DB 方法
            await storage.db_set("session_bindings", data)
            logger.info(f"[SESSION-BIND] 持久化 {len(data)} 个绑定到数据库")
            return True
        except Exception as e:
            logger.error(f"[SESSION-BIND] 持久化失败: {e}")
            self._dirty = True  # 标记仍需持久化
            return False
    
    async def start_persist_task(self) -> None:
        """启动后台持久化任务"""
        while True:
            try:
                await asyncio.sleep(self._persist_interval)
                await self.persist_to_db()
            except asyncio.CancelledError:
                # 退出前保存
                await self.persist_to_db()
                break
            except Exception as e:
                logger.error(f"[SESSION-BIND] 持久化任务异常: {e}")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "total_bindings": len(self._bindings),
            "dirty": self._dirty
        }


# 全局单例
_session_binding_manager: Optional[SessionBindingManager] = None


def get_session_binding_manager() -> SessionBindingManager:
    """获取全局会话绑定管理器"""
    global _session_binding_manager
    if _session_binding_manager is None:
        _session_binding_manager = SessionBindingManager()
    return _session_binding_manager
