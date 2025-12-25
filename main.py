import json, time, hmac, hashlib, base64, os, asyncio, uuid, ssl, re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any
from dataclasses import dataclass
import logging
from dotenv import load_dotenv

import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from util.streaming_parser import parse_json_array_stream_async
from collections import deque
from threading import Lock
from functools import wraps

# ---------- 日志配置 ----------

# 内存日志缓冲区 (保留最近 3000 条日志，重启后清空)
log_buffer = deque(maxlen=3000)
log_lock = Lock()

# 统计数据持久化
STATS_FILE = "stats.json"
stats_lock = Lock()

def load_stats():
    """加载统计数据"""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "total_visitors": 0,
        "total_requests": 0,
        "request_timestamps": [],  # 最近1小时的请求时间戳
        "visitor_ips": {}  # {ip: timestamp} 记录访问IP和时间
    }

def save_stats(stats):
    """保存统计数据"""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[STATS] 保存统计数据失败: {str(e)[:50]}")

# 初始化统计数据
global_stats = load_stats()

class MemoryLogHandler(logging.Handler):
    """自定义日志处理器，将日志写入内存缓冲区"""
    def emit(self, record):
        log_entry = self.format(record)
        # 转换为北京时间（UTC+8）
        beijing_tz = timezone(timedelta(hours=8))
        beijing_time = datetime.fromtimestamp(record.created, tz=beijing_tz)
        with log_lock:
            log_buffer.append({
                "time": beijing_time.strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage()
            })

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gemini")

# 添加内存日志处理器
memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(memory_handler)

load_dotenv()
# ---------- 配置 ----------
PROXY        = os.getenv("PROXY") or None
TIMEOUT_SECONDS = 600
API_KEY      = os.getenv("API_KEY") or None  # API 访问密钥（可选）
PATH_PREFIX  = os.getenv("PATH_PREFIX")      # 路径前缀（必需，用于隐藏端点）
ADMIN_KEY    = os.getenv("ADMIN_KEY")        # 管理员密钥（必需，用于访问管理端点）
BASE_URL     = os.getenv("BASE_URL")         # 服务器完整URL（可选，用于图片URL生成）

# ---------- 公开展示配置 ----------
LOGO_URL     = os.getenv("LOGO_URL", "")  # Logo URL（公开，为空则不显示）
CHAT_URL     = os.getenv("CHAT_URL", "")  # 开始对话链接（公开，为空则不显示）
MODEL_NAME   = os.getenv("MODEL_NAME", "gemini-business")  # 模型名称（公开）
HIDE_HOME_PAGE = os.getenv("HIDE_HOME_PAGE", "").lower() == "true"  # 是否隐藏首页（默认不隐藏）

# ---------- 图片存储配置 ----------
# 自动检测存储路径：优先使用持久化存储，否则使用临时存储
if os.path.exists("/data"):
    IMAGE_DIR = "/data/images"  # HF Pro持久化存储（重启不丢失）
else:
    IMAGE_DIR = "./images"  # 临时存储（重启会丢失）

# ---------- 重试配置 ----------
MAX_NEW_SESSION_TRIES = int(os.getenv("MAX_NEW_SESSION_TRIES", "5"))  # 新会话创建最多尝试账户数（默认5）
MAX_REQUEST_RETRIES = int(os.getenv("MAX_REQUEST_RETRIES", "3"))      # 请求失败最多重试次数（默认3）
MAX_ACCOUNT_SWITCH_TRIES = int(os.getenv("MAX_ACCOUNT_SWITCH_TRIES", "5"))  # 每次重试找账户的最大尝试次数（默认5）
ACCOUNT_FAILURE_THRESHOLD = int(os.getenv("ACCOUNT_FAILURE_THRESHOLD", "3"))  # 账户连续失败阈值（默认3次）
ACCOUNT_COOLDOWN_SECONDS = int(os.getenv("ACCOUNT_COOLDOWN_SECONDS", "300"))  # 账户冷却时间（默认300秒=5分钟）
SESSION_CACHE_TTL_SECONDS = int(os.getenv("SESSION_CACHE_TTL_SECONDS", "3600"))  # 会话缓存过期时间（默认3600秒=1小时）

# ---------- 模型映射配置 ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-3-pro-preview": "gemini-3-pro-preview"
}

# ---------- HTTP 客户端 ----------
http_client = httpx.AsyncClient(
    proxies=PROXY,
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
)

# ---------- 工具函数 ----------
def get_base_url(request: Request) -> str:
    """获取完整的base URL（优先环境变量，否则从请求自动获取）"""
    # 优先使用环境变量
    if BASE_URL:
        return BASE_URL.rstrip("/")

    # 自动从请求获取（兼容反向代理）
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host"))

    return f"{forwarded_proto}://{forwarded_host}"

# ---------- 常量定义 ----------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

def get_common_headers(jwt: str) -> dict:
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": f"Bearer {jwt}",
        "content-type": "application/json",
        "origin": "https://business.gemini.google",
        "referer": "https://business.gemini.google/",
        "user-agent": USER_AGENT,
        "x-server-timeout": "1800",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }

def urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def kq_encode(s: str) -> str:
    b = bytearray()
    for ch in s:
        v = ord(ch)
        if v > 255:
            b.append(v & 255)
            b.append(v >> 8)
        else:
            b.append(v)
    return urlsafe_b64encode(bytes(b))

def create_jwt(key_bytes: bytes, key_id: str, csesidx: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {
        "iss": "https://business.gemini.google",
        "aud": "https://biz-discoveryengine.googleapis.com",
        "sub": f"csesidx/{csesidx}",
        "iat": now,
        "exp": now + 300,
        "nbf": now,
    }
    header_b64  = kq_encode(json.dumps(header, separators=(",", ":")))
    payload_b64 = kq_encode(json.dumps(payload, separators=(",", ":")))
    message     = f"{header_b64}.{payload_b64}"
    sig         = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
    return f"{message}.{urlsafe_b64encode(sig)}"

# ---------- 多账户支持 ----------
@dataclass
class AccountConfig:
    """单个账户配置"""
    account_id: str
    secure_c_ses: str
    host_c_oses: Optional[str]
    csesidx: str
    config_id: str
    expires_at: Optional[str] = None  # 账户过期时间 (格式: "2025-12-23 10:59:21")

    def get_remaining_hours(self) -> Optional[float]:
        """计算账户剩余小时数"""
        if not self.expires_at:
            return None
        try:
            # 解析过期时间（假设为北京时间）
            beijing_tz = timezone(timedelta(hours=8))
            expire_time = datetime.strptime(self.expires_at, "%Y-%m-%d %H:%M:%S")
            expire_time = expire_time.replace(tzinfo=beijing_tz)

            # 当前时间（北京时间）
            now = datetime.now(beijing_tz)

            # 计算剩余时间
            remaining = (expire_time - now).total_seconds() / 3600
            return remaining
        except Exception:
            return None

    def is_expired(self) -> bool:
        """检查账户是否已过期"""
        remaining = self.get_remaining_hours()
        if remaining is None:
            return False  # 未设置过期时间，默认不过期
        return remaining <= 0

def format_account_expiration(remaining_hours: Optional[float]) -> tuple:
    """
    格式化账户过期时间显示（基于12小时过期周期）

    Args:
        remaining_hours: 剩余小时数（None表示未设置过期时间）

    Returns:
        (status, status_color, expire_display) 元组
    """
    if remaining_hours is None:
        # 未设置过期时间时显示为"未设置"
        return ("未设置", "#9e9e9e", "未设置")
    elif remaining_hours <= 0:
        return ("已过期", "#f44336", "已过期")
    elif remaining_hours < 3:  # 少于3小时
        return ("即将过期", "#ff9800", f"{remaining_hours:.1f} 小时")
    else:  # 3小时及以上，统一显示小时
        return ("正常", "#4caf50", f"{remaining_hours:.1f} 小时")

class AccountManager:
    """单个账户管理器"""
    def __init__(self, config: AccountConfig):
        self.config = config
        self.jwt_manager: Optional['JWTManager'] = None  # 延迟初始化
        self.is_available = True
        self.last_error_time = 0.0
        self.error_count = 0

    async def get_jwt(self, request_id: str = "") -> str:
        """获取 JWT token (带错误处理)"""
        try:
            if self.jwt_manager is None:
                # 延迟初始化 JWTManager (避免循环依赖)
                self.jwt_manager = JWTManager(self.config)
            jwt = await self.jwt_manager.get(request_id)
            self.is_available = True
            self.error_count = 0
            return jwt
        except Exception as e:
            self.last_error_time = time.time()
            self.error_count += 1
            # 使用配置的失败阈值
            if self.error_count >= ACCOUNT_FAILURE_THRESHOLD:
                self.is_available = False
                logger.error(f"[ACCOUNT] [{self.config.account_id}] JWT获取连续失败{self.error_count}次，账户已标记为不可用")
            else:
                # 安全：只记录异常类型，不记录详细信息
                logger.warning(f"[ACCOUNT] [{self.config.account_id}] JWT获取失败({self.error_count}/{ACCOUNT_FAILURE_THRESHOLD}): {type(e).__name__}")
            raise

    def should_retry(self) -> bool:
        """检查账户是否可重试（使用配置的冷却期）"""
        if self.is_available:
            return True
        return time.time() - self.last_error_time > ACCOUNT_COOLDOWN_SECONDS

class MultiAccountManager:
    """多账户协调器"""
    def __init__(self):
        self.accounts: Dict[str, AccountManager] = {}
        self.account_list: List[str] = []  # 账户ID列表 (用于轮询)
        self.current_index = 0
        self._lock = asyncio.Lock()
        # 全局会话缓存：{conv_key: {"account_id": str, "session_id": str, "updated_at": float}}
        self.global_session_cache: Dict[str, dict] = {}
        self.cache_max_size = 1000  # 最大缓存条目数
        self.cache_ttl = SESSION_CACHE_TTL_SECONDS  # 缓存过期时间（秒）

    def _clean_expired_cache(self):
        """清理过期的缓存条目"""
        current_time = time.time()
        expired_keys = [
            key for key, value in self.global_session_cache.items()
            if current_time - value["updated_at"] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.global_session_cache[key]
        if expired_keys:
            logger.info(f"[CACHE] 清理 {len(expired_keys)} 个过期会话缓存")

    def _ensure_cache_size(self):
        """确保缓存不超过最大大小（LRU策略）"""
        if len(self.global_session_cache) > self.cache_max_size:
            # 按更新时间排序，删除最旧的20%
            sorted_items = sorted(
                self.global_session_cache.items(),
                key=lambda x: x[1]["updated_at"]
            )
            remove_count = len(sorted_items) - int(self.cache_max_size * 0.8)
            for key, _ in sorted_items[:remove_count]:
                del self.global_session_cache[key]
            logger.info(f"[CACHE] LRU清理 {remove_count} 个最旧会话缓存")

    async def set_session_cache(self, conv_key: str, account_id: str, session_id: str):
        """线程安全地设置会话缓存"""
        async with self._lock:
            self.global_session_cache[conv_key] = {
                "account_id": account_id,
                "session_id": session_id,
                "updated_at": time.time()
            }
            # 检查缓存大小
            self._ensure_cache_size()

    async def update_session_time(self, conv_key: str):
        """线程安全地更新会话时间戳"""
        async with self._lock:
            if conv_key in self.global_session_cache:
                self.global_session_cache[conv_key]["updated_at"] = time.time()

    def add_account(self, config: AccountConfig):
        """添加账户"""
        manager = AccountManager(config)
        self.accounts[config.account_id] = manager
        self.account_list.append(config.account_id)
        logger.info(f"[MULTI] [ACCOUNT] 添加账户: {config.account_id}")

    async def get_account(self, account_id: Optional[str] = None, request_id: str = "") -> AccountManager:
        """获取账户 (轮询或指定)"""
        async with self._lock:
            # 定期清理过期缓存（每次获取账户时检查）
            self._clean_expired_cache()

            req_tag = f"[req_{request_id}] " if request_id else ""

            # 如果指定了账户ID
            if account_id:
                if account_id not in self.accounts:
                    raise HTTPException(404, f"Account {account_id} not found")
                account = self.accounts[account_id]
                if not account.should_retry():
                    raise HTTPException(503, f"Account {account_id} temporarily unavailable")
                return account

            # 轮询选择可用账户
            available_accounts = [
                acc_id for acc_id in self.account_list
                if self.accounts[acc_id].should_retry()
            ]

            if not available_accounts:
                raise HTTPException(503, "No available accounts")

            # Round-robin（修复：基于可用账户列表的索引）
            if not hasattr(self, '_available_index'):
                self._available_index = 0

            account_id = available_accounts[self._available_index % len(available_accounts)]
            self._available_index = (self._available_index + 1) % len(available_accounts)

            account = self.accounts[account_id]
            logger.info(f"[MULTI] [ACCOUNT] {req_tag}选择账户: {account_id}")
            return account

# ---------- 多账户配置加载 ----------
def load_multi_account_config() -> MultiAccountManager:
    """从环境变量加载多账户配置（仅支持 ACCOUNTS_CONFIG JSON 格式）"""
    manager = MultiAccountManager()

    accounts_json = os.getenv("ACCOUNTS_CONFIG")
    if not accounts_json:
        raise ValueError(
            "未找到 ACCOUNTS_CONFIG 环境变量。\n"
            "请在环境变量中配置 JSON 格式的账户列表，格式示例：\n"
            '[{"id":"account_1","csesidx":"xxx","config_id":"yyy","secure_c_ses":"zzz","host_c_oses":null,"expires_at":"2025-12-23 10:59:21"}]'
        )

    try:
        accounts_data = json.loads(accounts_json)
        if not isinstance(accounts_data, list):
            raise ValueError("ACCOUNTS_CONFIG 必须是 JSON 数组格式")

        for i, acc in enumerate(accounts_data, 1):
            # 验证必需字段
            required_fields = ["secure_c_ses", "csesidx", "config_id"]
            missing_fields = [f for f in required_fields if f not in acc]
            if missing_fields:
                raise ValueError(f"账户 {i} 缺少必需字段: {', '.join(missing_fields)}")

            config = AccountConfig(
                account_id=acc.get("id", f"account_{i}"),
                secure_c_ses=acc["secure_c_ses"],
                host_c_oses=acc.get("host_c_oses"),
                csesidx=acc["csesidx"],
                config_id=acc["config_id"],
                expires_at=acc.get("expires_at")
            )

            # 检查账户是否已过期
            if config.is_expired():
                logger.warning(f"[CONFIG] 账户 {config.account_id} 已过期，跳过加载")
                continue

            manager.add_account(config)

        if not manager.accounts:
            raise ValueError("没有有效的账户配置（可能全部已过期）")

        logger.info(f"[CONFIG] 成功加载 {len(manager.accounts)} 个账户")
        return manager

    except json.JSONDecodeError as e:
        logger.error(f"[CONFIG] ACCOUNTS_CONFIG JSON 解析失败: {str(e)}")
        raise ValueError(f"ACCOUNTS_CONFIG 格式错误: {str(e)}")
    except KeyError as e:
        logger.error(f"[CONFIG] ACCOUNTS_CONFIG 缺少必需字段: {str(e)}")
        raise ValueError(f"ACCOUNTS_CONFIG 缺少必需字段: {str(e)}")
    except Exception as e:
        logger.error(f"[CONFIG] 加载账户配置失败: {str(e)}")
        raise


# 初始化多账户管理器
multi_account_mgr = load_multi_account_config()

# 验证必需的环境变量
if not PATH_PREFIX:
    logger.error("[SYSTEM] 未配置 PATH_PREFIX 环境变量，请设置后重启")
    import sys
    sys.exit(1)

if not ADMIN_KEY:
    logger.error("[SYSTEM] 未配置 ADMIN_KEY 环境变量，请设置后重启")
    import sys
    sys.exit(1)

# 启动日志
logger.info(f"[SYSTEM] 路径前缀已配置: {PATH_PREFIX[:4]}****")
logger.info(f"[SYSTEM] 用户端点: /{PATH_PREFIX}/v1/chat/completions")
logger.info(f"[SYSTEM] 管理端点: /{PATH_PREFIX}/admin/")
logger.info("[SYSTEM] 公开端点: /public/log/html")
logger.info("[SYSTEM] 系统初始化完成")

# ---------- JWT 管理 ----------
class JWTManager:
    def __init__(self, config: AccountConfig) -> None:
        self.config = config
        self.jwt: str = ""
        self.expires: float = 0
        self._lock = asyncio.Lock()

    async def get(self, request_id: str = "") -> str:
        async with self._lock:
            if time.time() > self.expires:
                await self._refresh(request_id)
            return self.jwt

    async def _refresh(self, request_id: str = "") -> None:
        cookie = f"__Secure-C_SES={self.config.secure_c_ses}"
        if self.config.host_c_oses:
            cookie += f"; __Host-C_OSES={self.config.host_c_oses}"

        req_tag = f"[req_{request_id}] " if request_id else ""
        r = await http_client.get(
            "https://business.gemini.google/auth/getoxsrf",
            params={"csesidx": self.config.csesidx},
            headers={
                "cookie": cookie,
                "user-agent": USER_AGENT,
                "referer": "https://business.gemini.google/"
            },
        )
        if r.status_code != 200:
            logger.error(f"[AUTH] [{self.config.account_id}] {req_tag}JWT 刷新失败: {r.status_code}")
            raise HTTPException(r.status_code, "getoxsrf failed")

        txt = r.text[4:] if r.text.startswith(")]}'") else r.text
        data = json.loads(txt)

        key_bytes = base64.urlsafe_b64decode(data["xsrfToken"] + "==")
        self.jwt      = create_jwt(key_bytes, data["keyId"], self.config.csesidx)
        self.expires = time.time() + 270
        logger.info(f"[AUTH] [{self.config.account_id}] {req_tag}JWT 刷新成功")

# ---------- Session & File 管理 ----------
async def create_google_session(account_manager: AccountManager, request_id: str = "") -> str:
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt)
    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "createSessionRequest": {
            "session": {"name": "", "displayName": ""}
        }
    }

    req_tag = f"[req_{request_id}] " if request_id else ""
    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetCreateSession",
        headers=headers,
        json=body,
    )
    if r.status_code != 200:
        logger.error(f"[SESSION] [{account_manager.config.account_id}] {req_tag}Session 创建失败: {r.status_code}")
        raise HTTPException(r.status_code, "createSession failed")
    sess_name = r.json()["session"]["name"]
    logger.info(f"[SESSION] [{account_manager.config.account_id}] {req_tag}创建成功: {sess_name[-12:]}")
    return sess_name

async def upload_context_file(session_name: str, mime_type: str, base64_content: str, account_manager: AccountManager, request_id: str = "") -> str:
    """上传文件到指定 Session，返回 fileId"""
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt)

    # 生成随机文件名
    ext = mime_type.split('/')[-1] if '/' in mime_type else "bin"
    file_name = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "addContextFileRequest": {
            "name": session_name,
            "fileName": file_name,
            "mimeType": mime_type,
            "fileContents": base64_content
        }
    }

    r = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetAddContextFile",
        headers=headers,
        json=body,
    )

    req_tag = f"[req_{request_id}] " if request_id else ""
    if r.status_code != 200:
        logger.error(f"[FILE] [{account_manager.config.account_id}] {req_tag}文件上传失败: {r.status_code}")
        raise HTTPException(r.status_code, f"Upload failed: {r.text}")

    data = r.json()
    file_id = data.get("addContextFileResponse", {}).get("fileId")
    logger.info(f"[FILE] [{account_manager.config.account_id}] {req_tag}文件上传成功: {mime_type}")
    return file_id

# ---------- 消息处理逻辑 ----------
def get_conversation_key(messages: List[dict]) -> str:
    """使用第一条user消息生成对话指纹"""
    if not messages:
        return "empty"

    # 只使用第一条user消息生成指纹（对话起点不变）
    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    if not user_messages:
        return "no_user_msg"

    # 只取第一条user消息
    first_user_msg = user_messages[0]
    content = first_user_msg.get("content", "")

    # 统一处理内容格式（字符串或数组）
    if isinstance(content, list):
        text = "".join([x.get("text", "") for x in content if x.get("type") == "text"])
    else:
        text = str(content)

    # 标准化：去除首尾空白，转小写（避免因空格/大小写导致指纹不同）
    text = text.strip().lower()

    # 生成指纹
    return hashlib.md5(text.encode()).hexdigest()

def parse_last_message(messages: List['Message']):
    """解析最后一条消息，分离文本和图片"""
    if not messages:
        return "", []
    
    last_msg = messages[-1]
    content = last_msg.content
    
    text_content = ""
    images = [] # List of {"mime": str, "data": str_base64}

    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                text_content += part.get("text", "")
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                # 解析 Data URI: data:image/png;base64,xxxxxx
                match = re.match(r"data:(image/[^;]+);base64,(.+)", url)
                if match:
                    images.append({"mime": match.group(1), "data": match.group(2)})
                else:
                    logger.warning(f"[FILE] 不支持的图片格式: {url[:30]}...")

    return text_content, images

def build_full_context_text(messages: List['Message']) -> str:
    """仅拼接历史文本，图片只处理当次请求的"""
    prompt = ""
    for msg in messages:
        role = "User" if msg.role in ["user", "system"] else "Assistant"
        content_str = ""
        if isinstance(msg.content, str):
            content_str = msg.content
        elif isinstance(msg.content, list):
            for part in msg.content:
                if part.get("type") == "text":
                    content_str += part.get("text", "")
                elif part.get("type") == "image_url":
                    content_str += "[图片]"
        
        prompt += f"{role}: {content_str}\n\n"
    return prompt

# ---------- OpenAI 兼容接口 ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway")

# ---------- 图片静态服务初始化 ----------
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
if IMAGE_DIR == "/data/images":
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (持久化存储)")
else:
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (临时存储，重启会丢失)")

# ---------- 认证装饰器 ----------

def require_admin_key(func):
    """验证管理员密钥（支持 URL 参数或 Header）"""
    @wraps(func)
    async def wrapper(*args, key: str = None, authorization: str = None, **kwargs):
        # 支持 URL 参数 ?key=xxx 或 Authorization Header
        admin_key = key
        if not admin_key and authorization:
            admin_key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization

        if admin_key != ADMIN_KEY:
            # 返回 404 而不是 401，假装端点不存在
            raise HTTPException(404, "Not Found")

        return await func(*args, **kwargs)
    return wrapper

# ---------- 日志脱敏函数 ----------
def get_sanitized_logs(limit: int = 100) -> list:
    """获取脱敏后的日志列表，按请求ID分组并提取关键事件"""
    with log_lock:
        logs = list(log_buffer)

    # 按请求ID分组（支持两种格式：带[req_xxx]和不带的）
    request_logs = {}
    orphan_logs = []  # 没有request_id的日志（如选择账户）

    for log in logs:
        message = log["message"]
        req_match = re.search(r'\[req_([a-z0-9]+)\]', message)

        if req_match:
            request_id = req_match.group(1)
            if request_id not in request_logs:
                request_logs[request_id] = []
            request_logs[request_id].append(log)
        else:
            # 没有request_id的日志（如选择账户），暂存
            orphan_logs.append(log)

    # 将orphan_logs（如选择账户）关联到对应的请求
    # 策略：将orphan日志关联到时间上最接近的后续请求
    for orphan in orphan_logs:
        orphan_time = orphan["time"]
        # 找到时间上最接近且在orphan之后的请求
        closest_request_id = None
        min_time_diff = None

        for request_id, req_logs in request_logs.items():
            if req_logs:
                first_log_time = req_logs[0]["time"]
                # orphan应该在请求之前或同时
                if first_log_time >= orphan_time:
                    if min_time_diff is None or first_log_time < min_time_diff:
                        min_time_diff = first_log_time
                        closest_request_id = request_id

        # 如果找到最接近的请求，将orphan日志插入到该请求的日志列表开头
        if closest_request_id:
            request_logs[closest_request_id].insert(0, orphan)

    # 为每个请求提取关键事件
    sanitized = []
    for request_id, req_logs in request_logs.items():
        # 收集关键信息
        model = None
        message_count = None
        retry_events = []
        final_status = "in_progress"
        duration = None
        start_time = req_logs[0]["time"]

        # 遍历该请求的所有日志
        for log in req_logs:
            message = log["message"]

            # 提取模型名称和消息数量（开始对话）
            if '收到请求:' in message and not model:
                model_match = re.search(r'收到请求: ([^ |]+)', message)
                if model_match:
                    model = model_match.group(1)
                count_match = re.search(r'(\d+)条消息', message)
                if count_match:
                    message_count = int(count_match.group(1))

            # 提取重试事件（包括失败尝试、账户切换、选择账户）
            # 注意：不提取"正在重试"日志，因为它和"失败 (尝试"是配套的
            if any(keyword in message for keyword in ['切换账户', '选择账户', '失败 (尝试']):
                retry_events.append({
                    "time": log["time"],
                    "message": message
                })

            # 提取响应完成（最高优先级 - 最终成功则忽略中间错误）
            if '响应完成:' in message:
                time_match = re.search(r'响应完成: ([\d.]+)秒', message)
                if time_match:
                    duration = time_match.group(1) + 's'
                    final_status = "success"

            # 检测非流式响应完成
            if '非流式响应完成' in message:
                final_status = "success"

            # 检测失败状态（仅在非success状态下）
            if final_status != "success" and (log['level'] == 'ERROR' or '失败' in message):
                final_status = "error"

            # 检测超时（仅在非success状态下）
            if final_status != "success" and '超时' in message:
                final_status = "timeout"

        # 如果没有模型信息但有错误，仍然显示
        if not model and final_status == "in_progress":
            continue

        # 构建关键事件列表
        events = []

        # 1. 开始对话
        if model:
            events.append({
                "time": start_time,
                "type": "start",
                "content": f"{model} | {message_count}条消息" if message_count else model
            })
        else:
            # 没有模型信息但有错误的情况
            events.append({
                "time": start_time,
                "type": "start",
                "content": "请求处理中"
            })

        # 2. 重试事件
        failure_count = 0  # 失败重试计数
        account_select_count = 0  # 账户选择计数

        for i, retry in enumerate(retry_events):
            msg = retry["message"]

            # 识别不同类型的重试事件（按优先级匹配）
            if '失败 (尝试' in msg:
                # 创建会话失败
                failure_count += 1
                events.append({
                    "time": retry["time"],
                    "type": "retry",
                    "content": f"服务异常，正在重试（{failure_count}）"
                })
            elif '选择账户' in msg:
                # 账户选择/切换
                account_select_count += 1

                # 检查下一条日志是否是"切换账户"，如果是则跳过当前"选择账户"（避免重复）
                next_is_switch = (i + 1 < len(retry_events) and '切换账户' in retry_events[i + 1]["message"])

                if not next_is_switch:
                    if account_select_count == 1:
                        # 第一次选择：显示为"选择服务节点"
                        events.append({
                            "time": retry["time"],
                            "type": "select",
                            "content": "选择服务节点"
                        })
                    else:
                        # 第二次及以后：显示为"切换服务节点"
                        events.append({
                            "time": retry["time"],
                            "type": "switch",
                            "content": "切换服务节点"
                        })
            elif '切换账户' in msg:
                # 运行时切换账户（显示为"切换服务节点"）
                events.append({
                    "time": retry["time"],
                    "type": "switch",
                    "content": "切换服务节点"
                })

        # 3. 完成事件
        if final_status == "success":
            if duration:
                events.append({
                    "time": req_logs[-1]["time"],
                    "type": "complete",
                    "status": "success",
                    "content": f"响应完成 | 耗时{duration}"
                })
            else:
                events.append({
                    "time": req_logs[-1]["time"],
                    "type": "complete",
                    "status": "success",
                    "content": "响应完成"
                })
        elif final_status == "error":
            events.append({
                "time": req_logs[-1]["time"],
                "type": "complete",
                "status": "error",
                "content": "请求失败"
            })
        elif final_status == "timeout":
            events.append({
                "time": req_logs[-1]["time"],
                "type": "complete",
                "status": "timeout",
                "content": "请求超时"
            })

        sanitized.append({
            "request_id": request_id,
            "start_time": start_time,
            "status": final_status,
            "events": events
        })

    # 按时间排序并限制数量
    sanitized.sort(key=lambda x: x["start_time"], reverse=True)
    return sanitized[:limit]

class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatRequest(BaseModel):
    model: str = "gemini-auto"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0

def create_chunk(id: str, created: int, model: str, delta: dict, finish_reason: Union[str, None]) -> str:
    chunk = {
        "id": id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "logprobs": None,  # OpenAI 标准字段
            "finish_reason": finish_reason
        }],
        "system_fingerprint": None  # OpenAI 标准字段（可选）
    }
    return json.dumps(chunk)

# ---------- API Key 验证 ----------
def verify_api_key(authorization: str = None):
    """验证 API Key（如果配置了 API_KEY）"""
    # 如果未配置 API_KEY，则跳过验证
    if API_KEY is None:
        return True

    # 检查 Authorization header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # 支持两种格式：
    # 1. Bearer YOUR_API_KEY
    # 2. YOUR_API_KEY
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if token != API_KEY:
        logger.warning(f"[AUTH] API Key 验证失败")
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    return True

def generate_admin_html(request: Request, show_hide_tip: bool = False) -> str:
    """生成管理页面HTML - 端点带Key参数完整版"""
    # 获取当前页面的完整URL
    current_url = get_base_url(request)

    # 获取错误统计
    error_count = 0
    with log_lock:
        for log in log_buffer:
            if log.get("level") in ["ERROR", "CRITICAL"]:
                error_count += 1

    # --- 1. 构建提示信息 ---
    hide_tip = ""
    if show_hide_tip:
        hide_tip = """
        <div class="alert alert-info">
            <div class="alert-icon">💡</div>
            <div class="alert-content">
                <strong>提示</strong>：此页面默认在首页显示。如需隐藏，请设置环境变量：<br>
                <code style="margin-top:4px; display:inline-block;">HIDE_HOME_PAGE=true</code>
            </div>
        </div>
        """

    api_key_status = ""
    if API_KEY:
        api_key_status = """
        <div class="alert alert-success">
            <div class="alert-icon">🔒</div>
            <div class="alert-content">
                <strong>安全模式已启用</strong>
                <div class="alert-desc">请求 Header 需携带 Authorization 密钥。</div>
            </div>
        </div>
        """
    else:
        api_key_status = """
        <div class="alert alert-warning">
            <div class="alert-icon">⚠️</div>
            <div class="alert-content">
                <strong>API Key 未设置</strong>
                <div class="alert-desc">API 当前允许公开访问，建议配置 API_KEY。</div>
            </div>
        </div>
        """

    error_alert = ""
    if error_count > 0:
        error_alert = f"""
        <div class="alert alert-error">
            <div class="alert-icon">🚨</div>
            <div class="alert-content">
                <strong>检测到 {error_count} 条错误日志</strong>
                <a href="/public/log/html" class="alert-link">查看详情 &rarr;</a>
            </div>
        </div>
        """

    # --- 2. 构建账户卡片 ---
    accounts_html = ""
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()
        status_text, status_color, expire_display = format_account_expiration(remaining_hours)
        
        is_avail = account_manager.is_available
        dot_color = "#34c759" if is_avail else "#ff3b30"
        dot_title = "可用" if is_avail else "不可用"

        accounts_html += f"""
        <div class="card account-card">
            <div class="acc-header">
                <div class="acc-title">
                    <span class="status-dot" style="background-color: {dot_color};" title="{dot_title}"></span>
                    {config.account_id}
                </div>
                <span class="acc-status-text" style="color: {status_color}">{status_text}</span>
            </div>
            <div class="acc-body">
                <div class="acc-row">
                    <span>过期时间</span>
                    <span class="font-mono">{config.expires_at or '未设置'}</span>
                </div>
                <div class="acc-row">
                    <span>剩余时长</span>
                    <span style="color: {status_color}; font-weight: 600;">{expire_display}</span>
                </div>
            </div>
        </div>
        """

    # --- 3. 构建 HTML ---
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>系统管理 - Gemini Business API</title>
        <style>
            :root {{
                --bg-body: #f5f5f7;
                --text-main: #1d1d1f;
                --text-sec: #86868b;
                --border: #d2d2d7;
                --border-light: #e5e5ea;
                --blue: #0071e3;
                --red: #ff3b30;
                --green: #34c759;
                --orange: #ff9500;
            }}
            
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif;
                background-color: var(--bg-body);
                color: var(--text-main);
                font-size: 13px;
                line-height: 1.5;
                -webkit-font-smoothing: antialiased;
                padding: 30px 20px;
                cursor: default;
            }}
            
            .container {{ max-width: 1100px; margin: 0 auto; }}
            
            /* Header */
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 24px;
                flex-wrap: wrap;
                gap: 16px;
            }}
            .header-info h1 {{
                font-size: 24px;
                font-weight: 600;
                letter-spacing: -0.5px;
                color: var(--text-main);
                margin-bottom: 4px;
            }}
            .header-info .subtitle {{ font-size: 14px; color: var(--text-sec); }}
            .header-actions {{ display: flex; gap: 10px; }}
            
            /* Buttons */
            .btn {{
                display: inline-flex;
                align-items: center;
                padding: 8px 16px;
                background: #ffffff;
                border: 1px solid var(--border-light);
                border-radius: 8px;
                color: var(--text-main);
                font-weight: 500;
                text-decoration: none;
                transition: all 0.2s;
                font-size: 13px;
                cursor: pointer;
                box-shadow: 0 1px 2px rgba(0,0,0,0.03);
            }}
            .btn:hover {{ background: #fafafa; border-color: var(--border); text-decoration: none; }}
            .btn-primary {{ background: var(--blue); color: white; border: none; }}
            .btn-primary:hover {{ background: #0077ed; border: none; text-decoration: none; }}
            
            /* Alerts */
            .alert {{
                padding: 12px 16px;
                border-radius: 10px;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                font-size: 13px;
                border: 1px solid transparent;
                margin-bottom: 12px;
            }}
            .alert-icon {{ font-size: 16px; margin-top: 1px; flex-shrink: 0; }}
            .alert-content {{ flex: 1; }}
            .alert-desc {{ color: inherit; opacity: 0.9; margin-top: 2px; font-size: 12px; }}
            .alert-link {{ color: inherit; text-decoration: underline; margin-left: 10px; font-weight: 600; cursor: pointer; }}
            .alert-info {{ background: #eef7fe; border-color: #dcebfb; color: #1c5b96; }}
            .alert-success {{ background: #eafbf0; border-color: #d3f3dd; color: #15682e; }}
            .alert-warning {{ background: #fff8e6; border-color: #fcebc2; color: #9c6e03; }}
            .alert-error {{ background: #ffebeb; border-color: #fddddd; color: #c41e1e; }}
            
            /* Sections & Grids */
            .section {{ margin-bottom: 30px; }}
            .section-title {{
                font-size: 15px;
                font-weight: 600;
                color: var(--text-main);
                margin-bottom: 12px;
                padding-left: 4px;
            }}
            .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; align-items: start; }}
            .grid-env {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
            .account-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
            .stack-col {{ display: flex; flex-direction: column; gap: 16px; }}
            
            /* Cards */
            .card {{
                background: #fafaf9;
                padding: 20px;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
                transition: all 0.15s ease;
            }}
            .card:hover {{ border-color: #d4d4d4; box-shadow: 0 0 8px rgba(0,0,0,0.08); }}
            .card h3 {{
                font-size: 13px;
                font-weight: 600;
                color: var(--text-sec);
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid #f5f5f5;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}

            /* Account & Env Styles */
            .account-card .acc-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f5f5f5; }}
            .acc-title {{ font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px; }}
            .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
            .acc-status-text {{ font-size: 12px; font-weight: 500; }}
            .acc-row {{ display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; color: var(--text-sec); }}
            
            .env-var {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f5f5f5; }}
            .env-var:last-child {{ border-bottom: none; }}
            .env-name {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-main); font-weight: 600; }}
            .env-desc {{ font-size: 11px; color: var(--text-sec); margin-top: 2px; }}
            .env-value {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; font-size: 12px; color: var(--text-sec); text-align: right; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
            
            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 600; vertical-align: middle; margin-left: 6px; }}
            .badge-required {{ background: #ffebeb; color: #c62828; }}
            .badge-optional {{ background: #e8f5e9; color: #2e7d32; }}
            
            code {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; background: #f5f5f7; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--blue); }}
            a {{ color: var(--blue); text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .font-mono {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; }}

            /* --- Service Info Styles --- */
            .model-grid {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
            .model-tag {{
                background: #f0f0f2;
                color: #1d1d1f;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 12px;
                font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace;
                border: 1px solid transparent;
            }}
            .model-tag.highlight {{ background: #eef7ff; color: #0071e3; border-color: #dcebfb; font-weight: 500; }}
            
            .info-box {{ background: #f9f9f9; border: 1px solid #e5e5ea; border-radius: 8px; padding: 14px; }}
            .info-box-title {{ font-weight: 600; font-size: 12px; color: #1d1d1f; margin-bottom: 6px; }}
            .info-box-text {{ font-size: 12px; color: #86868b; line-height: 1.5; }}

            .ep-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            .ep-table tr {{ border-bottom: 1px solid #f5f5f5; }}
            .ep-table tr:last-child {{ border-bottom: none; }}
            .ep-table td {{ padding: 10px 0; vertical-align: middle; }}
            
            .method {{
                display: inline-block;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                min-width: 48px;
                text-align: center;
                margin-right: 8px;
            }}
            .m-post {{ background: #eafbf0; color: #166534; border: 1px solid #dcfce7; }}
            .m-get {{ background: #eff6ff; color: #1e40af; border: 1px solid #dbeafe; }}
            .m-del {{ background: #fef2f2; color: #991b1b; border: 1px solid #fee2e2; }}
            
            .ep-path {{ font-family: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace; color: #1d1d1f; margin-right: 8px; font-size: 12px; }}
            .ep-desc {{ color: #86868b; font-size: 12px; margin-left: auto; }}
            
            .current-url-row {{
                display: flex;
                align-items: center;
                padding: 10px 12px;
                background: #f2f7ff;
                border-radius: 8px;
                margin-bottom: 16px;
                border: 1px solid #e1effe;
            }}

            @media (max-width: 800px) {{
                .grid-3, .grid-env {{ grid-template-columns: 1fr; }}
                .header {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
                .header-actions {{ width: 100%; justify-content: flex-start; }}
                .ep-table td {{ display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }}
                .ep-desc {{ margin-left: 0; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-info">
                    <h1>Gemini-Business2api</h1>
                    <div class="subtitle">多账户代理面板</div>
                </div>
                <div class="header-actions">
                    <a href="/public/log/html" class="btn" target="_blank">📄 公开日志</a>
                    <a href="/{PATH_PREFIX}/admin/log/html?key={ADMIN_KEY}" class="btn btn-primary" target="_blank">🔧 管理日志</a>
                </div>
            </div>

            {hide_tip}
            {api_key_status}
            {error_alert}

            <div class="section">
                <div class="section-title">账户状态 ({len(multi_account_mgr.accounts)} 个)</div>
                <div class="account-grid">
                    {accounts_html if accounts_html else '<div class="card"><p style="color: #6b6b6b; font-size: 14px; text-align:center;">暂无账户</p></div>'}
                </div>
            </div>

            <div class="section">
                <div class="section-title">环境变量配置</div>
                <div class="grid-env">
                    <div class="stack-col">
                        <div class="card">
                            <h3>必需变量 <span class="badge badge-required">REQUIRED</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNTS_CONFIG</div><div class="env-desc">JSON格式账户列表</div></div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">PATH_PREFIX</div><div class="env-desc">API路径前缀</div></div>
                                    <div class="env-value">当前: {PATH_PREFIX}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ADMIN_KEY</div><div class="env-desc">管理员密钥</div></div>
                                    <div class="env-value">已设置</div>
                                </div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>重试配置 <span class="badge badge-optional">OPTIONAL</span></h3>
                            <div style="margin-top: 12px;">
                                <div class="env-var">
                                    <div><div class="env-name">MAX_NEW_SESSION_TRIES</div><div class="env-desc">新会话尝试账户数</div></div>
                                    <div class="env-value">{MAX_NEW_SESSION_TRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">MAX_REQUEST_RETRIES</div><div class="env-desc">请求失败重试次数</div></div>
                                    <div class="env-value">{MAX_REQUEST_RETRIES}</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNT_FAILURE_THRESHOLD</div><div class="env-desc">账户失败阈值</div></div>
                                    <div class="env-value">{ACCOUNT_FAILURE_THRESHOLD} 次</div>
                                </div>
                                <div class="env-var">
                                    <div><div class="env-name">ACCOUNT_COOLDOWN_SECONDS</div><div class="env-desc">账户冷却时间</div></div>
                                    <div class="env-value">{ACCOUNT_COOLDOWN_SECONDS} 秒</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>可选变量 <span class="badge badge-optional">OPTIONAL</span></h3>
                        <div style="margin-top: 12px;">
                            <div class="env-var">
                                <div><div class="env-name">API_KEY</div><div class="env-desc">API访问密钥</div></div>
                                <div class="env-value">{'已设置' if API_KEY else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">BASE_URL</div><div class="env-desc">图片URL生成（推荐设置）</div></div>
                                <div class="env-value">{'已设置' if BASE_URL else '未设置（自动检测）'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">PROXY</div><div class="env-desc">代理地址</div></div>
                                <div class="env-value">{'已设置' if PROXY else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">SESSION_CACHE_TTL_SECONDS</div><div class="env-desc">会话缓存过期时间</div></div>
                                <div class="env-value">{SESSION_CACHE_TTL_SECONDS} 秒</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">LOGO_URL</div><div class="env-desc">Logo URL（公开，为空则不显示）</div></div>
                                <div class="env-value">{'已设置' if LOGO_URL else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">CHAT_URL</div><div class="env-desc">开始对话链接（公开，为空则不显示）</div></div>
                                <div class="env-value">{'已设置' if CHAT_URL else '未设置'}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">MODEL_NAME</div><div class="env-desc">模型名称（公开）</div></div>
                                <div class="env-value">{MODEL_NAME}</div>
                            </div>
                            <div class="env-var">
                                <div><div class="env-name">HIDE_HOME_PAGE</div><div class="env-desc">隐藏首页管理面板</div></div>
                                <div class="env-value">{'已隐藏' if HIDE_HOME_PAGE else '未隐藏'}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="section">
                <div class="section-title">服务信息</div>
                <div class="grid-3">
                    <div class="card">
                        <h3>支持的模型</h3>
                        <div class="model-grid">
                            <span class="model-tag">gemini-auto</span>
                            <span class="model-tag">gemini-2.5-flash</span>
                            <span class="model-tag">gemini-2.5-pro</span>
                            <span class="model-tag">gemini-3-flash-preview</span>
                            <span class="model-tag highlight">gemini-3-pro-preview</span>
                        </div>
                        
                        <div class="info-box">
                            <div class="info-box-title">📸 图片生成说明</div>
                            <div class="info-box-text">
                                仅 <code style="background:none;padding:0;color:#0071e3;">gemini-3-pro-preview</code> 支持绘图。<br>
                                路径: <code>{IMAGE_DIR}</code><br>
                                类型: {'<span style="color: #34c759; font-weight: 600;">持久化（重启保留）</span>' if IMAGE_DIR == '/data/images' else '<span style="color: #ff3b30; font-weight: 600;">临时（重启丢失）</span>'}
                            </div>
                        </div>
                    </div>

                    <div class="card" style="grid-column: span 2;">
                        <h3>API 端点</h3>
                        
                        <div class="current-url-row">
                            <span style="font-size:12px; font-weight:600; color:#0071e3; margin-right:8px;">当前页面:</span>
                            <code style="background:none; padding:0; color:#1d1d1f;">{current_url}</code>
                        </div>

                        <table class="ep-table">
                            <tr>
                                <td width="70"><span class="method m-post">POST</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/v1/chat/completions</span></td>
                                <td><span class="ep-desc">OpenAI 兼容对话接口</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/v1/models</span></td>
                                <td><span class="ep-desc">获取模型列表</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin</span></td>
                                <td><span class="ep-desc">管理首页</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin/health?key={{ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">健康检查 (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin/accounts?key={{ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">账户状态 JSON (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin/log?key={{ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">获取日志 JSON (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin/log/html?key={{ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">日志查看器 HTML (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-del">DEL</span></td>
                                <td><span class="ep-path">/{PATH_PREFIX}/admin/log?confirm=yes&key={{ADMIN_KEY}}</span></td>
                                <td><span class="ep-desc">清空系统日志 (需 Key)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/public/stats</span></td>
                                <td><span class="ep-desc">公开统计数据</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/public/log</span></td>
                                <td><span class="ep-desc">公开日志 (JSON, 脱敏)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/public/log/html</span></td>
                                <td><span class="ep-desc">公开日志查看器 (HTML)</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/docs</span></td>
                                <td><span class="ep-desc">Swagger API 文档</span></td>
                            </tr>
                            <tr>
                                <td><span class="method m-get">GET</span></td>
                                <td><span class="ep-path">/redoc</span></td>
                                <td><span class="ep-desc">ReDoc API 文档</span></td>
                            </tr>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.get("/")
async def home(request: Request):
    """首页 - 默认显示管理面板（可通过环境变量隐藏）"""
    # 检查是否隐藏首页
    if HIDE_HOME_PAGE:
        raise HTTPException(404, "Not Found")

    # 显示管理页面（带隐藏提示）
    html_content = generate_admin_html(request, show_hide_tip=True)
    return HTMLResponse(content=html_content)

@app.get("/{path_prefix}/admin")
@app.get("/{path_prefix}/admin/")
async def admin_home(path_prefix: str, request: Request, key: str = None, authorization: str = Header(None)):
    """管理首页 - 显示API信息和错误提醒"""
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    # 显示管理页面（不显示隐藏提示）
    html_content = generate_admin_html(request, show_hide_tip=False)
    return HTMLResponse(content=html_content)

@app.get("/{path_prefix}/v1/models")
async def list_models(path_prefix: str, authorization: str = Header(None)):
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证 API Key
    verify_api_key(authorization)

    data = []
    now = int(time.time())
    for m in MODEL_MAPPING.keys():
        data.append({
            "id": m,
            "object": "model",
            "created": now,
            "owned_by": "google",
            "permission": []
        })
    return {"object": "list", "data": data}

@app.get("/{path_prefix}/v1/models/{model_id}")
async def get_model(path_prefix: str, model_id: str, authorization: str = Header(None)):
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证 API Key
    verify_api_key(authorization)

    return {"id": model_id, "object": "model"}

@app.get("/{path_prefix}/admin/health")
async def admin_health(path_prefix: str, key: str = None, authorization: str = Header(None)):
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/{path_prefix}/admin/accounts")
async def admin_get_accounts(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """获取所有账户的状态信息"""
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    accounts_info = []
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()

        # 使用统一的格式化函数
        status, status_color, remaining_display = format_account_expiration(remaining_hours)

        accounts_info.append({
            "id": config.account_id,
            "status": status,
            "expires_at": config.expires_at or "未设置",
            "remaining_hours": remaining_hours,
            "remaining_display": remaining_display,
            "is_available": account_manager.is_available,
            "error_count": account_manager.error_count
        })

    return {
        "total": len(accounts_info),
        "accounts": accounts_info
    }

@app.get("/{path_prefix}/admin/log")
async def admin_get_logs(
    path_prefix: str,
    limit: int = 1500,
    key: str = None,
    authorization: str = Header(None),
    level: str = None,
    search: str = None,
    start_time: str = None,
    end_time: str = None
):
    """
    获取系统日志（包含统计信息）

    参数:
    - limit: 返回最近 N 条日志 (默认 1500, 最大 3000)
    - level: 过滤日志级别 (INFO, WARNING, ERROR, DEBUG)
    - search: 搜索关键词（在消息中搜索）
    - start_time: 开始时间 (格式: 2025-12-17 10:00:00)
    - end_time: 结束时间 (格式: 2025-12-17 11:00:00)
    """
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    with log_lock:
        logs = list(log_buffer)

    # 计算统计信息（在过滤前）
    stats_by_level = {}
    error_logs = []
    chat_count = 0
    for log in logs:
        level_name = log.get("level", "INFO")
        stats_by_level[level_name] = stats_by_level.get(level_name, 0) + 1

        # 收集错误日志
        if level_name in ["ERROR", "CRITICAL"]:
            error_logs.append(log)

        # 统计对话次数（匹配包含"收到请求"的日志）
        if "收到请求" in log.get("message", ""):
            chat_count += 1

    # 按级别过滤
    if level:
        level = level.upper()
        logs = [log for log in logs if log["level"] == level]

    # 按关键词搜索
    if search:
        logs = [log for log in logs if search.lower() in log["message"].lower()]

    # 按时间范围过滤
    if start_time:
        logs = [log for log in logs if log["time"] >= start_time]
    if end_time:
        logs = [log for log in logs if log["time"] <= end_time]

    # 限制数量（返回最近的）
    limit = min(limit, 3000)
    filtered_logs = logs[-limit:]

    return {
        "total": len(filtered_logs),
        "limit": limit,
        "filters": {
            "level": level,
            "search": search,
            "start_time": start_time,
            "end_time": end_time
        },
        "logs": filtered_logs,
        "stats": {
            "memory": {
                "total": len(log_buffer),
                "by_level": stats_by_level,
                "capacity": log_buffer.maxlen
            },
            "errors": {
                "count": len(error_logs),
                "recent": error_logs[-10:]  # 最近10条错误
            },
            "chat_count": chat_count
        }
    }

@app.delete("/{path_prefix}/admin/log")
async def admin_clear_logs(path_prefix: str, confirm: str = None, key: str = None, authorization: str = Header(None)):
    """
    清空所有日志（内存缓冲 + 文件）

    参数:
    - confirm: 必须传入 "yes" 才能清空
    """
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    if confirm != "yes":
        raise HTTPException(
            status_code=400,
            detail="需要 confirm=yes 参数确认清空操作"
        )

    # 清空内存缓冲
    with log_lock:
        cleared_count = len(log_buffer)
        log_buffer.clear()

    logger.info("[LOG] 日志已清空")

    return {
        "status": "success",
        "message": "已清空内存日志",
        "cleared_count": cleared_count
    }

@app.get("/{path_prefix}/admin/log/html")
async def admin_logs_html(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """返回美化的 HTML 日志查看界面"""
    # 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 验证管理员密钥
    admin_key = key or (authorization.replace("Bearer ", "") if authorization and authorization.startswith("Bearer ") else authorization)
    if admin_key != ADMIN_KEY:
        raise HTTPException(404, "Not Found")

    html_content = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>日志查看器</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            html, body { height: 100%; overflow: hidden; }
            body {
                font-family: 'Consolas', 'Monaco', monospace;
                background: #fafaf9;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 15px;
            }
            .container {
                width: 100%;
                max-width: 1400px;
                height: calc(100vh - 30px);
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                flex-direction: column;
            }
            h1 { color: #1a1a1a; font-size: 22px; font-weight: 600; margin-bottom: 20px; text-align: center; }
            .stats {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
                gap: 12px;
                margin-bottom: 16px;
            }
            .stat {
                background: #fafaf9;
                padding: 12px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                text-align: center;
                transition: all 0.15s ease;
            }
            .stat:hover { border-color: #d4d4d4; }
            .stat-label { color: #6b6b6b; font-size: 11px; margin-bottom: 4px; }
            .stat-value { color: #1a1a1a; font-size: 18px; font-weight: 600; }
            .controls {
                display: flex;
                gap: 8px;
                margin-bottom: 16px;
                flex-wrap: wrap;
            }
            .controls input, .controls select, .controls button {
                padding: 6px 10px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                font-size: 13px;
            }
            .controls select {
                appearance: none;
                -webkit-appearance: none;
                -moz-appearance: none;
                background-image: url("data:image/svg+xml,%3Csvg width='12' height='12' viewBox='0 0 12 12' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%236b6b6b' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
                background-repeat: no-repeat;
                background-position: right 12px center;
                padding-right: 32px;
            }
            .controls input[type="text"] { flex: 1; min-width: 150px; }
            .controls button {
                background: #1a73e8;
                color: white;
                border: none;
                cursor: pointer;
                font-weight: 500;
                transition: background 0.15s ease;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .controls button:hover { background: #1557b0; }
            .controls button.danger { background: #dc2626; }
            .controls button.danger:hover { background: #b91c1c; }
            .controls button svg { flex-shrink: 0; }
            .log-container {
                flex: 1;
                background: #fafaf9;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px;
                overflow-y: auto;
                scrollbar-width: thin;
                scrollbar-color: rgba(0,0,0,0.15) transparent;
            }
            /* Webkit 滚动条样式 - 更窄且不占位 */
            .log-container::-webkit-scrollbar {
                width: 4px;
            }
            .log-container::-webkit-scrollbar-track {
                background: transparent;
            }
            .log-container::-webkit-scrollbar-thumb {
                background: rgba(0,0,0,0.15);
                border-radius: 2px;
            }
            .log-container::-webkit-scrollbar-thumb:hover {
                background: rgba(0,0,0,0.3);
            }
            .log-entry {
                padding: 8px 10px;
                margin-bottom: 4px;
                background: white;
                border-radius: 6px;
                border: 1px solid #e5e5e5;
                font-size: 12px;
                color: #1a1a1a;
                display: flex;
                align-items: center;
                gap: 8px;
                word-break: break-word;
            }
            .log-entry > div:first-child {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .log-message {
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .log-entry:hover { border-color: #d4d4d4; }
            .log-time { color: #6b6b6b; }
            .log-level {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: 600;
            }
            .log-level::before {
                content: '';
                width: 6px;
                height: 6px;
                border-radius: 50%;
            }
            .log-level.INFO { background: #e3f2fd; color: #1976d2; }
            .log-level.INFO::before { background: #1976d2; }
            .log-level.WARNING { background: #fff3e0; color: #f57c00; }
            .log-level.WARNING::before { background: #f57c00; }
            .log-level.ERROR { background: #ffebee; color: #d32f2f; }
            .log-level.ERROR::before { background: #d32f2f; }
            .log-level.DEBUG { background: #f3e5f5; color: #7b1fa2; }
            .log-level.DEBUG::before { background: #7b1fa2; }
            .log-group {
                margin-bottom: 8px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: white;
            }
            .log-group-header {
                padding: 10px 12px;
                background: #f9f9f9;
                border-radius: 8px 8px 0 0;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: background 0.15s ease;
            }
            .log-group-header:hover {
                background: #f0f0f0;
            }
            .log-group-content {
                padding: 8px;
            }
            .log-group .log-entry {
                margin-bottom: 4px;
            }
            .log-group .log-entry:last-child {
                margin-bottom: 0;
            }
            .toggle-icon {
                display: inline-block;
                transition: transform 0.2s ease;
            }
            .toggle-icon.collapsed {
                transform: rotate(-90deg);
            }
            @media (max-width: 768px) {
                body { padding: 0; }
                .container { padding: 15px; height: 100vh; border-radius: 0; max-width: 100%; }
                h1 { font-size: 18px; margin-bottom: 12px; }
                .stats { grid-template-columns: repeat(3, 1fr); gap: 8px; }
                .stat { padding: 8px; }
                .controls { gap: 6px; }
                .controls input, .controls select { min-height: 38px; }
                .controls select { flex: 0 0 auto; }
                .controls input[type="text"] { flex: 1 1 auto; min-width: 80px; }
                .controls input[type="number"] { flex: 0 0 60px; }
                .controls button { padding: 10px 8px; font-size: 12px; flex: 1 1 22%; justify-content: center; min-height: 38px; }
                .log-entry {
                    font-size: 12px;
                    padding: 10px;
                    gap: 8px;
                    flex-direction: column;
                    align-items: flex-start;
                }
                .log-entry > div:first-child {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    width: 100%;
                    flex-wrap: wrap;
                }
                .log-time { font-size: 11px; color: #9e9e9e; }
                .log-level { font-size: 10px; }
                .log-message {
                    width: 100%;
                    white-space: normal;
                    word-break: break-word;
                    line-height: 1.5;
                    margin-top: 4px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Gemini API 日志查看器</h1>
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">总数</div>
                    <div class="stat-value" id="total-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">对话</div>
                    <div class="stat-value" id="chat-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">INFO</div>
                    <div class="stat-value" id="info-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">WARNING</div>
                    <div class="stat-value" id="warning-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">ERROR</div>
                    <div class="stat-value" id="error-count">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">更新</div>
                    <div class="stat-value" id="last-update" style="font-size: 11px;">-</div>
                </div>
            </div>
            <div class="controls">
                <select id="level-filter">
                    <option value="">全部</option>
                    <option value="INFO">INFO</option>
                    <option value="WARNING">WARNING</option>
                    <option value="ERROR">ERROR</option>
                </select>
                <input type="text" id="search-input" placeholder="搜索...">
                <input type="number" id="limit-input" value="1500" min="10" max="3000" step="100" style="width: 80px;">
                <button onclick="loadLogs()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                    查询
                </button>
                <button onclick="exportJSON()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    导出
                </button>
                <button id="auto-refresh-btn" onclick="toggleAutoRefresh()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    自动刷新
                </button>
                <button onclick="clearAllLogs()" class="danger">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                    清空
                </button>
            </div>
            <div class="log-container" id="log-container">
                <div style="color: #6b6b6b;">正在加载...</div>
            </div>
        </div>
        <script>
            let autoRefreshTimer = null;
            async function loadLogs() {
                const level = document.getElementById('level-filter').value;
                const search = document.getElementById('search-input').value;
                const limit = document.getElementById('limit-input').value;
                // 从当前 URL 获取 key 参数
                const urlParams = new URLSearchParams(window.location.search);
                const key = urlParams.get('key');
                // 构建 API URL（使用当前路径的前缀）
                const pathPrefix = window.location.pathname.split('/')[1];
                let url = `/${pathPrefix}/admin/log?limit=${limit}`;
                if (key) url += `&key=${key}`;
                if (level) url += `&level=${level}`;
                if (search) url += `&search=${encodeURIComponent(search)}`;
                try {
                    const response = await fetch(url);
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    const data = await response.json();
                    if (data && data.logs) {
                        displayLogs(data.logs);
                        updateStats(data.stats);
                        document.getElementById('last-update').textContent = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});
                    } else {
                        throw new Error('Invalid data format');
                    }
                } catch (error) {
                    document.getElementById('log-container').innerHTML = '<div class="log-entry ERROR">加载失败: ' + error.message + '</div>';
                }
            }
            function updateStats(stats) {
                document.getElementById('total-count').textContent = stats.memory.total;
                document.getElementById('info-count').textContent = stats.memory.by_level.INFO || 0;
                document.getElementById('warning-count').textContent = stats.memory.by_level.WARNING || 0;
                const errorCount = document.getElementById('error-count');
                errorCount.textContent = stats.memory.by_level.ERROR || 0;
                if (stats.errors && stats.errors.count > 0) errorCount.style.color = '#dc2626';
                document.getElementById('chat-count').textContent = stats.chat_count || 0;
            }
            // 分类颜色配置（提取到外部避免重复定义）
            const CATEGORY_COLORS = {
                'SYSTEM': '#9e9e9e',
                'CONFIG': '#607d8b',
                'LOG': '#9e9e9e',
                'AUTH': '#4caf50',
                'SESSION': '#00bcd4',
                'FILE': '#ff9800',
                'CHAT': '#2196f3',
                'API': '#8bc34a',
                'CACHE': '#9c27b0',
                'ACCOUNT': '#f44336',
                'MULTI': '#673ab7'
            };

            // 账户颜色配置（提取到外部避免重复定义）
            const ACCOUNT_COLORS = {
                'account_1': '#9c27b0',
                'account_2': '#e91e63',
                'account_3': '#00bcd4',
                'account_4': '#4caf50',
                'account_5': '#ff9800'
            };

            function getCategoryColor(category) {
                return CATEGORY_COLORS[category] || '#757575';
            }

            function getAccountColor(accountId) {
                return ACCOUNT_COLORS[accountId] || '#757575';
            }

            function displayLogs(logs) {
                const container = document.getElementById('log-container');
                if (logs.length === 0) {
                    container.innerHTML = '<div class="log-entry">暂无日志</div>';
                    return;
                }

                // 按请求ID分组
                const groups = {};
                const ungrouped = [];

                logs.forEach(log => {
                    const msg = escapeHtml(log.message);
                    const reqMatch = msg.match(/\[req_([a-z0-9]+)\]/);

                    if (reqMatch) {
                        const reqId = reqMatch[1];
                        if (!groups[reqId]) {
                            groups[reqId] = [];
                        }
                        groups[reqId].push(log);
                    } else {
                        ungrouped.push(log);
                    }
                });

                // 渲染分组
                let html = '';

                // 先渲染未分组的日志
                ungrouped.forEach(log => {
                    html += renderLogEntry(log);
                });

                // 读取折叠状态
                const foldState = JSON.parse(localStorage.getItem('log-fold-state') || '{}');

                // 按请求ID分组渲染（最新的组在下面）
                Object.keys(groups).forEach(reqId => {
                    const groupLogs = groups[reqId];
                    const firstLog = groupLogs[0];
                    const lastLog = groupLogs[groupLogs.length - 1];

                    // 判断状态
                    let status = 'in_progress';
                    let statusColor = '#ff9800';
                    let statusText = '进行中';

                    if (lastLog.message.includes('响应完成') || lastLog.message.includes('非流式响应完成')) {
                        status = 'success';
                        statusColor = '#4caf50';
                        statusText = '成功';
                    } else if (lastLog.level === 'ERROR' || lastLog.message.includes('失败')) {
                        status = 'error';
                        statusColor = '#f44336';
                        statusText = '失败';
                    } else {
                        // 检查超时（最后日志超过 5 分钟）
                        const lastLogTime = new Date(lastLog.time);
                        const now = new Date();
                        const diffMinutes = (now - lastLogTime) / 1000 / 60;
                        if (diffMinutes > 5) {
                            status = 'timeout';
                            statusColor = '#ffc107';
                            statusText = '超时';
                        }
                    }

                    // 提取账户ID和模型
                    const accountMatch = firstLog.message.match(/\[account_(\d+)\]/);
                    const modelMatch = firstLog.message.match(/收到请求: ([^ ]+)/);
                    const accountId = accountMatch ? `account_${accountMatch[1]}` : '';
                    const model = modelMatch ? modelMatch[1] : '';

                    // 检查折叠状态
                    const isCollapsed = foldState[reqId] === true;
                    const contentStyle = isCollapsed ? 'style="display: none;"' : '';
                    const iconClass = isCollapsed ? 'class="toggle-icon collapsed"' : 'class="toggle-icon"';

                    html += `
                        <div class="log-group" data-req-id="${reqId}">
                            <div class="log-group-header" onclick="toggleGroup('${reqId}')">
                                <span style="color: ${statusColor}; font-weight: 600; font-size: 11px;">⬤ ${statusText}</span>
                                <span style="color: #666; font-size: 11px; margin-left: 8px;">req_${reqId}</span>
                                ${accountId ? `<span style="color: ${getAccountColor(accountId)}; font-size: 11px; margin-left: 8px;">${accountId}</span>` : ''}
                                ${model ? `<span style="color: #999; font-size: 11px; margin-left: 8px;">${model}</span>` : ''}
                                <span style="color: #999; font-size: 11px; margin-left: 8px;">${groupLogs.length}条日志</span>
                                <span ${iconClass} style="margin-left: auto; color: #999;">▼</span>
                            </div>
                            <div class="log-group-content" ${contentStyle}>
                                ${groupLogs.map(log => renderLogEntry(log)).join('')}
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = html;

                // 自动滚动到底部，显示最新日志
                container.scrollTop = container.scrollHeight;
            }

            function renderLogEntry(log) {
                const msg = escapeHtml(log.message);
                let displayMsg = msg;
                let categoryTags = [];
                let accountId = null;

                // 解析所有标签：[CATEGORY1] [CATEGORY2] [account_X] [req_X] message
                let remainingMsg = msg;
                const tagRegex = /^\[([A-Z_a-z0-9]+)\]/;

                while (true) {
                    const match = remainingMsg.match(tagRegex);
                    if (!match) break;

                    const tag = match[1];
                    remainingMsg = remainingMsg.substring(match[0].length).trim();

                    // 跳过req_标签（已在组头部显示）
                    if (tag.startsWith('req_')) {
                        continue;
                    }
                    // 判断是否为账户ID
                    else if (tag.startsWith('account_')) {
                        accountId = tag;
                    } else {
                        // 普通分类标签
                        categoryTags.push(tag);
                    }
                }

                displayMsg = remainingMsg;

                // 生成分类标签HTML
                const categoryTagsHtml = categoryTags.map(cat =>
                    `<span class="log-category" style="background: ${getCategoryColor(cat)}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-left: 2px;">${cat}</span>`
                ).join('');

                // 生成账户标签HTML
                const accountTagHtml = accountId
                    ? `<span style="color: ${getAccountColor(accountId)}; font-size: 11px; font-weight: 600; margin-left: 2px;">${accountId}</span>`
                    : '';

                return `
                    <div class="log-entry ${log.level}">
                        <div>
                            <span class="log-time">${log.time}</span>
                            <span class="log-level ${log.level}">${log.level}</span>
                            ${categoryTagsHtml}
                            ${accountTagHtml}
                        </div>
                        <div class="log-message">${displayMsg}</div>
                    </div>
                `;
            }

            function toggleGroup(reqId) {
                const group = document.querySelector(`.log-group[data-req-id="${reqId}"]`);
                const content = group.querySelector('.log-group-content');
                const icon = group.querySelector('.toggle-icon');

                const isCollapsed = content.style.display === 'none';
                if (isCollapsed) {
                    content.style.display = 'block';
                    icon.classList.remove('collapsed');
                } else {
                    content.style.display = 'none';
                    icon.classList.add('collapsed');
                }

                // 保存折叠状态到 localStorage
                const foldState = JSON.parse(localStorage.getItem('log-fold-state') || '{}');
                foldState[reqId] = !isCollapsed;
                localStorage.setItem('log-fold-state', JSON.stringify(foldState));
            }
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            async function exportJSON() {
                try {
                    const urlParams = new URLSearchParams(window.location.search);
                    const key = urlParams.get('key');
                    const pathPrefix = window.location.pathname.split('/')[1];
                    let url = `/${pathPrefix}/admin/log?limit=3000`;
                    if (key) url += `&key=${key}`;
                    const response = await fetch(url);
                    const data = await response.json();
                    const blob = new Blob([JSON.stringify({exported_at: new Date().toISOString(), logs: data.logs}, null, 2)], {type: 'application/json'});
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = 'logs_' + new Date().toISOString().slice(0, 19).replace(/:/g, '-') + '.json';
                    a.click();
                    URL.revokeObjectURL(blobUrl);
                    alert('导出成功');
                } catch (error) {
                    alert('导出失败: ' + error.message);
                }
            }
            async function clearAllLogs() {
                if (!confirm('确定清空所有日志？')) return;
                try {
                    const urlParams = new URLSearchParams(window.location.search);
                    const key = urlParams.get('key');
                    const pathPrefix = window.location.pathname.split('/')[1];
                    let url = `/${pathPrefix}/admin/log?confirm=yes`;
                    if (key) url += `&key=${key}`;
                    const response = await fetch(url, {method: 'DELETE'});
                    if (response.ok) {
                        alert('已清空');
                        loadLogs();
                    } else {
                        alert('清空失败');
                    }
                } catch (error) {
                    alert('清空失败: ' + error.message);
                }
            }
            let autoRefreshEnabled = true;
            function toggleAutoRefresh() {
                autoRefreshEnabled = !autoRefreshEnabled;
                const btn = document.getElementById('auto-refresh-btn');
                if (autoRefreshEnabled) {
                    btn.style.background = '#1a73e8';
                    autoRefreshTimer = setInterval(loadLogs, 5000);
                } else {
                    btn.style.background = '#6b6b6b';
                    if (autoRefreshTimer) {
                        clearInterval(autoRefreshTimer);
                        autoRefreshTimer = null;
                    }
                }
            }
            document.addEventListener('DOMContentLoaded', () => {
                loadLogs();
                autoRefreshTimer = setInterval(loadLogs, 5000);
                document.getElementById('search-input').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') loadLogs();
                });
                document.getElementById('level-filter').addEventListener('change', loadLogs);
                document.getElementById('limit-input').addEventListener('change', loadLogs);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/{path_prefix}/v1/chat/completions")
async def chat(
    path_prefix: str,
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    # 0. 验证路径前缀
    if path_prefix != PATH_PREFIX:
        raise HTTPException(404, "Not Found")

    # 1. API Key 验证
    verify_api_key(authorization)

    # 1. 生成请求ID（最优先，用于所有日志追踪）
    request_id = str(uuid.uuid4())[:6]

    # 记录请求统计
    with stats_lock:
        global_stats["total_requests"] += 1
        global_stats["request_timestamps"].append(time.time())
        save_stats(global_stats)

    # 2. 模型校验
    if req.model not in MODEL_MAPPING:
        logger.error(f"[CHAT] [req_{request_id}] 不支持的模型: {req.model}")
        raise HTTPException(
            status_code=404,
            detail=f"Model '{req.model}' not found. Available models: {list(MODEL_MAPPING.keys())}"
        )

    # 3. 生成会话指纹，检查是否已有绑定的账户
    conv_key = get_conversation_key([m.dict() for m in req.messages])
    cached_session = multi_account_mgr.global_session_cache.get(conv_key)

    if cached_session:
        # 使用已绑定的账户
        account_id = cached_session["account_id"]
        account_manager = await multi_account_mgr.get_account(account_id, request_id)
        google_session = cached_session["session_id"]
        is_new_conversation = False
        logger.info(f"[CHAT] [{account_id}] [req_{request_id}] 继续会话: {google_session[-12:]}")
    else:
        # 新对话：轮询选择可用账户，失败时尝试其他账户
        max_account_tries = min(MAX_NEW_SESSION_TRIES, len(multi_account_mgr.accounts))
        last_error = None

        for attempt in range(max_account_tries):
            try:
                account_manager = await multi_account_mgr.get_account(None, request_id)
                google_session = await create_google_session(account_manager, request_id)
                # 线程安全地绑定账户到此对话
                await multi_account_mgr.set_session_cache(
                    conv_key,
                    account_manager.config.account_id,
                    google_session
                )
                is_new_conversation = True
                logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 新会话创建并绑定账户")
                break
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                # 安全获取账户ID
                account_id = account_manager.config.account_id if 'account_manager' in locals() and account_manager else 'unknown'
                logger.error(f"[CHAT] [req_{request_id}] 账户 {account_id} 创建会话失败 (尝试 {attempt + 1}/{max_account_tries}) - {error_type}: {str(e)}")
                if attempt == max_account_tries - 1:
                    logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用")
                    raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")
                # 继续尝试下一个账户

    # 提取用户消息内容用于日志
    if req.messages:
        last_content = req.messages[-1].content
        if isinstance(last_content, str):
            # 显示完整消息，但限制在500字符以内
            if len(last_content) > 500:
                preview = last_content[:500] + "...(已截断)"
            else:
                preview = last_content
        else:
            preview = f"[多模态: {len(last_content)}部分]"
    else:
        preview = "[空消息]"

    # 记录请求基本信息
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 收到请求: {req.model} | {len(req.messages)}条消息 | stream={req.stream}")

    # 单独记录用户消息内容（方便查看）
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 用户消息: {preview}")

    # 3. 解析请求内容
    last_text, current_images = parse_last_message(req.messages)

    # 4. 准备文本内容
    if is_new_conversation:
        # 新对话只发送最后一条
        text_to_send = last_text
        is_retry_mode = True
    else:
        # 继续对话只发送当前消息
        text_to_send = last_text
        is_retry_mode = False
        # 线程安全地更新时间戳
        await multi_account_mgr.update_session_time(conv_key)

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    # 封装生成器 (含图片上传和重试逻辑)
    async def response_wrapper():
        nonlocal account_manager  # 允许修改外层的 account_manager

        retry_count = 0
        max_retries = MAX_REQUEST_RETRIES  # 使用配置的最大重试次数

        current_text = text_to_send
        current_retry_mode = is_retry_mode

        # 图片 ID 列表 (每次 Session 变化都需要重新上传，因为 fileId 绑定在 Session 上)
        current_file_ids = []

        # 记录已失败的账户，避免重复使用
        failed_accounts = set()

        # 重试逻辑：最多尝试 max_retries+1 次（初次+重试）
        while retry_count <= max_retries:
            try:
                # 安全：使用.get()防止缓存被清理导致KeyError
                cached = multi_account_mgr.global_session_cache.get(conv_key)
                if not cached:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 缓存已清理，重建Session")
                    new_sess = await create_google_session(account_manager, request_id)
                    await multi_account_mgr.set_session_cache(
                        conv_key,
                        account_manager.config.account_id,
                        new_sess
                    )
                    current_session = new_sess
                    current_retry_mode = True
                    current_file_ids = []
                else:
                    current_session = cached["session_id"]

                # A. 如果有图片且还没上传到当前 Session，先上传
                # 注意：每次重试如果是新 Session，都需要重新上传图片
                if current_images and not current_file_ids:
                    for img in current_images:
                        fid = await upload_context_file(current_session, img["mime"], img["data"], account_manager, request_id)
                        current_file_ids.append(fid)

                # B. 准备文本 (重试模式下发全文)
                if current_retry_mode:
                    current_text = build_full_context_text(req.messages)

                # C. 发起对话
                async for chunk in stream_chat_generator(
                    current_session,
                    current_text,
                    current_file_ids,
                    req.model,
                    chat_id,
                    created_time,
                    account_manager,
                    req.stream,
                    request_id,
                    request
                ):
                    yield chunk
                break

            except (httpx.ConnectError, httpx.ReadTimeout, ssl.SSLError, HTTPException) as e:
                # 记录当前失败的账户
                failed_accounts.add(account_manager.config.account_id)

                retry_count += 1

                # 详细记录错误信息
                error_type = type(e).__name__
                error_detail = str(e)

                # 特殊处理HTTPException，提取状态码和详情
                if isinstance(e, HTTPException):
                    logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] HTTP错误 {e.status_code}: {e.detail}")
                else:
                    logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] {error_type}: {error_detail}")

                # 检查是否还能继续重试
                if retry_count <= max_retries:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 正在重试 ({retry_count}/{max_retries})")
                    # 尝试切换到其他账户（客户端会传递完整上下文）
                    try:
                        # 获取新账户，跳过已失败的账户
                        max_account_tries = MAX_ACCOUNT_SWITCH_TRIES  # 使用配置的账户切换尝试次数
                        new_account = None

                        for _ in range(max_account_tries):
                            candidate = await multi_account_mgr.get_account(None, request_id)
                            if candidate.config.account_id not in failed_accounts:
                                new_account = candidate
                                break

                        if not new_account:
                            logger.error(f"[CHAT] [req_{request_id}] 所有账户均已失败，无可用账户")
                            if req.stream: yield f"data: {json.dumps({'error': {'message': 'All Accounts Failed'}})}\n\n"
                            return

                        logger.info(f"[CHAT] [req_{request_id}] 切换账户: {account_manager.config.account_id} -> {new_account.config.account_id}")

                        # 创建新 Session
                        new_sess = await create_google_session(new_account, request_id)

                        # 更新缓存绑定到新账户
                        await multi_account_mgr.set_session_cache(
                            conv_key,
                            new_account.config.account_id,
                            new_sess
                        )

                        # 更新账户管理器
                        account_manager = new_account

                        # 设置重试模式（发送完整上下文）
                        current_retry_mode = True
                        current_file_ids = []  # 清空 ID，强制重新上传到新 Session

                    except Exception as create_err:
                        error_type = type(create_err).__name__
                        logger.error(f"[CHAT] [req_{request_id}] 账户切换失败 ({error_type}): {str(create_err)}")
                        if req.stream: yield f"data: {json.dumps({'error': {'message': 'Account Failover Failed'}})}\n\n"
                        return
                else:
                    # 已达到最大重试次数
                    logger.error(f"[CHAT] [req_{request_id}] 已达到最大重试次数 ({max_retries})，请求失败")
                    if req.stream: yield f"data: {json.dumps({'error': {'message': f'Max retries ({max_retries}) exceeded: {e}'}})}\n\n"
                    return

    if req.stream:
        return StreamingResponse(response_wrapper(), media_type="text/event-stream")
    
    full_content = ""
    full_reasoning = ""
    async for chunk_str in response_wrapper():
        if chunk_str.startswith("data: [DONE]"): break
        if chunk_str.startswith("data: "):
            try:
                data = json.loads(chunk_str[6:])
                delta = data["choices"][0]["delta"]
                if "content" in delta:
                    full_content += delta["content"]
                if "reasoning_content" in delta:
                    full_reasoning += delta["reasoning_content"]
            except json.JSONDecodeError as e:
                logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] JSON解析失败: {str(e)}")
            except (KeyError, IndexError) as e:
                logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 响应格式错误 ({type(e).__name__}): {str(e)}")

    # 构建响应消息
    message = {"role": "assistant", "content": full_content}
    if full_reasoning:
        message["reasoning_content"] = full_reasoning

    # 非流式请求完成日志
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 非流式响应完成")

    # 记录响应内容（限制500字符）
    response_preview = full_content[:500] + "...(已截断)" if len(full_content) > 500 else full_content
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] AI响应: {response_preview}")

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_time,
        "model": req.model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

# ---------- 图片生成处理函数 ----------
def parse_images_from_response(data_list: list) -> tuple[list, str]:
    """从API响应中解析图片文件引用
    返回: (file_ids_list, session_name)
    file_ids_list: [{"fileId": str, "mimeType": str}, ...]
    """
    file_ids = []
    session_name = ""

    for data in data_list:
        sar = data.get("streamAssistResponse")
        if not sar:
            continue

        # 获取session信息
        session_info = sar.get("sessionInfo", {})
        if session_info.get("session"):
            session_name = session_info["session"]

        answer = sar.get("answer") or {}
        replies = answer.get("replies") or []

        for reply in replies:
            gc = reply.get("groundedContent", {})
            content = gc.get("content", {})

            # 检查file字段（图片生成的关键）
            file_info = content.get("file")
            if file_info:
                logger.info(f"[IMAGE] [DEBUG] 发现file字段: {file_info}")
                if file_info.get("fileId"):
                    file_ids.append({
                        "fileId": file_info["fileId"],
                        "mimeType": file_info.get("mimeType", "image/png")
                    })

    return file_ids, session_name


async def get_session_file_metadata(account_mgr: AccountManager, session_name: str, request_id: str = "") -> dict:
    """获取session中的文件元数据，包括正确的session路径"""
    jwt = await account_mgr.get_jwt(request_id)
    headers = get_common_headers(jwt)
    body = {
        "configId": account_mgr.config.config_id,
        "additionalParams": {"token": "-"},
        "listSessionFileMetadataRequest": {
            "name": session_name,
            "filter": "file_origin_type = AI_GENERATED"
        }
    }

    resp = await http_client.post(
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetListSessionFileMetadata",
        headers=headers,
        json=body
    )

    if resp.status_code == 401:
        # JWT过期，刷新后重试
        jwt = await account_mgr.get_jwt(request_id)
        headers = get_common_headers(jwt)
        resp = await http_client.post(
            "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetListSessionFileMetadata",
            headers=headers,
            json=body
        )

    if resp.status_code != 200:
        logger.warning(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] 获取文件元数据失败: {resp.status_code}")
        return {}

    data = resp.json()
    result = {}
    file_metadata_list = data.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])
    for fm in file_metadata_list:
        fid = fm.get("fileId")
        if fid:
            result[fid] = fm

    return result


def build_image_download_url(session_name: str, file_id: str) -> str:
    """构造图片下载URL"""
    return f"https://biz-discoveryengine.googleapis.com/v1alpha/{session_name}:downloadFile?fileId={file_id}&alt=media"


async def download_image_with_jwt(account_mgr: AccountManager, session_name: str, file_id: str, request_id: str = "") -> bytes:
    """使用JWT认证下载图片"""
    url = build_image_download_url(session_name, file_id)
    logger.info(f"[IMAGE] [DEBUG] 下载URL: {url}")
    logger.info(f"[IMAGE] [DEBUG] Session完整路径: {session_name}")
    jwt = await account_mgr.get_jwt(request_id)
    headers = get_common_headers(jwt)

    # 复用全局http_client
    resp = await http_client.get(url, headers=headers, follow_redirects=True)

    if resp.status_code == 401:
        # JWT过期，刷新后重试
        jwt = await account_mgr.get_jwt(request_id)
        headers = get_common_headers(jwt)
        resp = await http_client.get(url, headers=headers, follow_redirects=True)

    resp.raise_for_status()
    return resp.content


def save_image_to_hf(image_data: bytes, chat_id: str, file_id: str, mime_type: str, base_url: str) -> str:
    """保存图片到持久化存储,返回完整的公开URL"""
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
    ext = ext_map.get(mime_type, ".png")

    filename = f"{chat_id}_{file_id}{ext}"
    save_path = os.path.join(IMAGE_DIR, filename)

    # 目录已在启动时创建(Line 635),无需重复创建
    with open(save_path, "wb") as f:
        f.write(image_data)

    return f"{base_url}/images/{filename}"

async def stream_chat_generator(session: str, text_content: str, file_ids: List[str], model_name: str, chat_id: str, created_time: int, account_manager: AccountManager, is_stream: bool = True, request_id: str = "", request: Request = None):
    start_time = time.time()

    # 记录发送给API的内容
    text_preview = text_content[:500] + "...(已截断)" if len(text_content) > 500 else text_content
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 发送内容: {text_preview}")
    if file_ids:
        logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 附带文件: {len(file_ids)}个")

    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt)

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "streamAssistRequest": {
            "session": session,
            "query": {"parts": [{"text": text_content}]},
            "filter": "",
            "fileIds": file_ids, # 注入文件 ID
            "answerGenerationMode": "NORMAL",
            "toolsSpec": {
                "webGroundingSpec": {},
                "toolRegistry": "default_tool_registry",
                "imageGenerationSpec": {},
                "videoGenerationSpec": {}
            },
            "languageCode": "zh-CN",
            "userMetadata": {"timeZone": "Asia/Shanghai"},
            "assistSkippingMode": "REQUEST_ASSIST"
        }
    }

    target_model_id = MODEL_MAPPING.get(model_name)
    if target_model_id:
        body["streamAssistRequest"]["assistGenerationConfig"] = {
            "modelId": target_model_id
        }

    if is_stream:
        chunk = create_chunk(chat_id, created_time, model_name, {"role": "assistant"}, None)
        yield f"data: {chunk}\n\n"

    # 使用流式请求
    async with http_client.stream(
        "POST",
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist",
        headers=headers,
        json=body,
    ) as r:
        if r.status_code != 200:
            error_text = await r.aread()
            raise HTTPException(status_code=r.status_code, detail=f"Upstream Error {error_text.decode()}")

        # 使用异步解析器处理 JSON 数组流
        json_objects = []  # 收集所有响应对象用于图片解析
        try:
            async for json_obj in parse_json_array_stream_async(r.aiter_lines()):
                json_objects.append(json_obj)  # 收集响应

                # 提取文本内容
                for reply in json_obj.get("streamAssistResponse", {}).get("answer", {}).get("replies", []):
                    content_obj = reply.get("groundedContent", {}).get("content", {})
                    text = content_obj.get("text", "")

                    if not text:
                        continue

                    # 区分思考过程和正常内容
                    if content_obj.get("thought"):
                        # 思考过程使用 reasoning_content 字段（类似 OpenAI o1）
                        chunk = create_chunk(chat_id, created_time, model_name, {"reasoning_content": text}, None)
                        yield f"data: {chunk}\n\n"
                    else:
                        # 正常内容使用 content 字段
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": text}, None)
                        yield f"data: {chunk}\n\n"

            # 处理图片生成
            if json_objects:
                logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 开始解析图片，共{len(json_objects)}个响应对象")
                file_ids, session_name = parse_images_from_response(json_objects)
                logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 解析结果: {len(file_ids)}张图片")
                logger.info(f"[IMAGE] [DEBUG] 响应中的session路径: {session_name}")

                if file_ids and session_name:
                    logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 检测到{len(file_ids)}张生成图片")

                    try:
                        # 获取base_url
                        base_url = get_base_url(request) if request else ""
                        logger.info(f"[IMAGE] [DEBUG] 使用base_url: {base_url}")

                        # 获取文件元数据，找到正确的session路径
                        file_metadata = await get_session_file_metadata(account_manager, session_name, request_id)
                        logger.info(f"[IMAGE] [DEBUG] 获取到{len(file_metadata)}个文件元数据")

                        for idx, file_info in enumerate(file_ids, 1):
                            try:
                                fid = file_info["fileId"]
                                mime = file_info["mimeType"]

                                # 从元数据中获取正确的session路径
                                meta = file_metadata.get(fid, {})
                                correct_session = meta.get("session") or session_name
                                logger.info(f"[IMAGE] [DEBUG] 文件{fid}使用session: {correct_session}")

                                image_data = await download_image_with_jwt(account_manager, correct_session, fid, request_id)
                                image_url = save_image_to_hf(image_data, chat_id, fid, mime, base_url)
                                logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片已保存: {image_url}")

                                # 返回Markdown格式图片
                                markdown = f"\n\n![生成的图片]({image_url})\n\n"
                                chunk = create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                                yield f"data: {chunk}\n\n"
                            except Exception as e:
                                logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 单张图片处理失败: {str(e)}")

                    except Exception as e:
                        logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片处理失败: {str(e)}")

        except ValueError as e:
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] JSON解析失败: {str(e)}")
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 流处理错误 ({error_type}): {str(e)}")
            raise

        total_time = time.time() - start_time
        logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应完成: {total_time:.2f}秒")
    
    if is_stream:
        final_chunk = create_chunk(chat_id, created_time, model_name, {}, "stop")
        yield f"data: {final_chunk}\n\n"
        yield "data: [DONE]\n\n"

# ---------- 公开端点（无需认证） ----------
@app.get("/public/stats")
async def get_public_stats():
    """获取公开统计信息"""
    with stats_lock:
        # 清理1小时前的请求时间戳
        current_time = time.time()
        global_stats["request_timestamps"] = [
            ts for ts in global_stats["request_timestamps"]
            if current_time - ts < 3600
        ]

        # 计算每分钟请求数
        recent_minute = [
            ts for ts in global_stats["request_timestamps"]
            if current_time - ts < 60
        ]
        requests_per_minute = len(recent_minute)

        # 计算负载状态
        if requests_per_minute < 10:
            load_status = "low"
            load_color = "#10b981"  # 绿色
        elif requests_per_minute < 30:
            load_status = "medium"
            load_color = "#f59e0b"  # 黄色
        else:
            load_status = "high"
            load_color = "#ef4444"  # 红色

        return {
            "total_visitors": global_stats["total_visitors"],
            "total_requests": global_stats["total_requests"],
            "requests_per_minute": requests_per_minute,
            "load_status": load_status,
            "load_color": load_color
        }

@app.get("/public/log")
async def get_public_logs(request: Request, limit: int = 100):
    """获取脱敏后的日志（JSON格式）"""
    # 基于IP的访问统计（24小时内去重）
    # 优先从 X-Forwarded-For 获取真实IP（处理代理情况）
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        # X-Forwarded-For 可能包含多个IP，取第一个
        client_ip = client_ip.split(",")[0].strip()
    else:
        # 没有代理时使用直连IP
        client_ip = request.client.host if request.client else "unknown"

    current_time = time.time()

    with stats_lock:
        # 清理24小时前的IP记录
        if "visitor_ips" not in global_stats:
            global_stats["visitor_ips"] = {}

        expired_ips = [
            ip for ip, timestamp in global_stats["visitor_ips"].items()
            if current_time - timestamp > 86400  # 24小时
        ]
        for ip in expired_ips:
            del global_stats["visitor_ips"][ip]

        # 记录新访问（24小时内同一IP只计数一次）
        if client_ip not in global_stats["visitor_ips"]:
            global_stats["visitor_ips"][client_ip] = current_time
            global_stats["total_visitors"] = len(global_stats["visitor_ips"])
            save_stats(global_stats)

    sanitized_logs = get_sanitized_logs(limit=min(limit, 1000))
    return {
        "total": len(sanitized_logs),
        "logs": sanitized_logs
    }

@app.get("/public/log/html")
async def get_public_logs_html():
    """公开的脱敏日志查看器"""
    html_content = r"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>服务状态</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            html, body { height: 100%; overflow: hidden; }
            body {
                font-family: 'Consolas', 'Monaco', monospace;
                background: #fafaf9;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 15px;
            }
            .container {
                width: 100%;
                max-width: 1200px;
                height: calc(100vh - 30px);
                background: white;
                border-radius: 16px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                display: flex;
                flex-direction: column;
            }
            h1 {
                color: #1a1a1a;
                font-size: 22px;
                font-weight: 600;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
            }
            h1 img {
                width: 32px;
                height: 32px;
                border-radius: 8px;
            }
            .info-bar {
                background: #f9f9f9;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px 16px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 12px;
            }
            .info-item {
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 13px;
                color: #6b6b6b;
            }
            .info-item strong { color: #1a1a1a; }
            .info-item a {
                color: #1a73e8;
                text-decoration: none;
                font-weight: 500;
            }
            .info-item a:hover { text-decoration: underline; }
            .stats {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-bottom: 16px;
            }
            .stat {
                background: #fafaf9;
                padding: 12px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                text-align: center;
                transition: all 0.15s ease;
            }
            .stat:hover { border-color: #d4d4d4; }
            .stat-label { color: #6b6b6b; font-size: 11px; margin-bottom: 4px; }
            .stat-value { color: #1a1a1a; font-size: 18px; font-weight: 600; }
            .log-container {
                flex: 1;
                background: #fafaf9;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                padding: 12px;
                overflow-y: auto;
                scrollbar-width: thin;
                scrollbar-color: rgba(0,0,0,0.15) transparent;
            }
            .log-container::-webkit-scrollbar { width: 4px; }
            .log-container::-webkit-scrollbar-track { background: transparent; }
            .log-container::-webkit-scrollbar-thumb {
                background: rgba(0,0,0,0.15);
                border-radius: 2px;
            }
            .log-container::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.3); }
            .log-group {
                margin-bottom: 8px;
                border: 1px solid #e5e5e5;
                border-radius: 8px;
                background: white;
            }
            .log-group-header {
                padding: 10px 12px;
                background: #f9f9f9;
                border-radius: 8px 8px 0 0;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: background 0.15s ease;
            }
            .log-group-header:hover { background: #f0f0f0; }
            .log-group-content { padding: 8px; }
            .log-entry {
                padding: 8px 10px;
                margin-bottom: 4px;
                background: white;
                border: 1px solid #e5e5e5;
                border-radius: 6px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 13px;
                transition: all 0.15s ease;
            }
            .log-entry:hover { border-color: #d4d4d4; }
            .log-time { color: #6b6b6b; font-size: 12px; min-width: 140px; }
            .log-status {
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                min-width: 60px;
                text-align: center;
            }
            .status-success { background: #d1fae5; color: #065f46; }
            .status-error { background: #fee2e2; color: #991b1b; }
            .status-in_progress { background: #fef3c7; color: #92400e; }
            .status-timeout { background: #fef3c7; color: #92400e; }
            .log-info { flex: 1; color: #374151; }
            .toggle-icon {
                display: inline-block;
                transition: transform 0.2s ease;
            }
            .toggle-icon.collapsed { transform: rotate(-90deg); }
            .subtitle-public {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            @media (max-width: 768px) {
                body { padding: 0; }
                .container {
                    padding: 15px;
                    height: 100vh;
                    border-radius: 0;
                    max-width: 100%;
                }
                h1 { font-size: 18px; margin-bottom: 12px; }
                .subtitle-public {
                    flex-direction: column;
                    gap: 6px;
                }
                .subtitle-public span {
                    font-size: 11px;
                    line-height: 1.6;
                }
                .subtitle-public a {
                    font-size: 12px;
                    font-weight: 600;
                }
                .info-bar {
                    padding: 10px 12px;
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 8px;
                }
                .info-item { font-size: 12px; }
                .stats {
                    grid-template-columns: repeat(2, 1fr);
                    gap: 8px;
                    margin-bottom: 12px;
                }
                .stat { padding: 8px; }
                .stat-label { font-size: 10px; }
                .stat-value { font-size: 16px; }
                .log-container { padding: 8px; }
                .log-group { margin-bottom: 6px; }
                .log-group-header {
                    padding: 8px 10px;
                    font-size: 11px;
                    flex-wrap: wrap;
                }
                .log-group-header span { font-size: 10px !important; }
                .log-entry {
                    padding: 6px 8px;
                    font-size: 11px;
                    flex-direction: column;
                    align-items: flex-start;
                    gap: 4px;
                }
                .log-time {
                    min-width: auto;
                    font-size: 10px;
                }
                .log-info {
                    font-size: 11px;
                    word-break: break-word;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>
                """ + (f'<img src="{LOGO_URL}" alt="Logo">' if LOGO_URL else '') + r"""
                Gemini服务状态
            </h1>
            <div style="text-align: center; color: #999; font-size: 12px; margin-bottom: 16px;" class="subtitle-public">
                <span>展示最近1000条对话日志 · 每5秒自动更新</span>
                """ + (f'<a href="{CHAT_URL}" target="_blank" style="color: #1a73e8; text-decoration: none;">开始对话</a>' if CHAT_URL else '<span style="color: #999;">开始对话</span>') + r"""
            </div>
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">总访问</div>
                    <div class="stat-value" id="stat-visitors">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">每分钟请求</div>
                    <div class="stat-value" id="stat-load">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">平均响应</div>
                    <div class="stat-value" id="stat-avg-time">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">成功率</div>
                    <div class="stat-value" id="stat-success-rate" style="color: #10b981;">-</div>
                </div>
                <div class="stat">
                    <div class="stat-label">对话次数</div>
                    <div class="stat-value" id="stat-total">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">成功</div>
                    <div class="stat-value" id="stat-success" style="color: #10b981;">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">失败</div>
                    <div class="stat-value" id="stat-error" style="color: #ef4444;">0</div>
                </div>
                <div class="stat">
                    <div class="stat-label">更新时间</div>
                    <div class="stat-value" id="stat-update-time" style="font-size: 14px; color: #6b6b6b;">--:--</div>
                </div>
            </div>
            <div class="log-container" id="log-container">
                <div style="text-align: center; color: #999; padding: 20px;">加载中...</div>
            </div>
        </div>
        <script>
            async function loadData() {
                try {
                    // 并行加载日志和统计数据
                    const [logsResponse, statsResponse] = await Promise.all([
                        fetch('/public/log?limit=1000'),
                        fetch('/public/stats')
                    ]);

                    const logsData = await logsResponse.json();
                    const statsData = await statsResponse.json();

                    displayLogs(logsData.logs);
                    updateStats(logsData.logs, statsData);
                } catch (error) {
                    document.getElementById('log-container').innerHTML = '<div style="text-align: center; color: #f44336; padding: 20px;">加载失败: ' + error.message + '</div>';
                }
            }

            function displayLogs(logs) {
                const container = document.getElementById('log-container');
                if (logs.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">暂无日志</div>';
                    return;
                }

                // 读取折叠状态
                const foldState = JSON.parse(localStorage.getItem('public-log-fold-state') || '{}');

                let html = '';
                logs.forEach(log => {
                    const reqId = log.request_id;

                    // 状态图标和颜色
                    let statusColor = '#ff9800';
                    let statusText = '进行中';

                    if (log.status === 'success') {
                        statusColor = '#4caf50';
                        statusText = '成功';
                    } else if (log.status === 'error') {
                        statusColor = '#f44336';
                        statusText = '失败';
                    } else if (log.status === 'timeout') {
                        statusColor = '#ffc107';
                        statusText = '超时';
                    }

                    // 检查折叠状态
                    const isCollapsed = foldState[reqId] === true;
                    const contentStyle = isCollapsed ? 'style="display: none;"' : '';
                    const iconClass = isCollapsed ? 'class="toggle-icon collapsed"' : 'class="toggle-icon"';

                    // 构建事件列表
                    let eventsHtml = '';
                    log.events.forEach(event => {
                        let eventClass = 'log-entry';
                        let eventLabel = '';

                        if (event.type === 'start') {
                            eventLabel = '<span style="color: #2563eb; font-weight: 600;">开始对话</span>';
                        } else if (event.type === 'select') {
                            eventLabel = '<span style="color: #8b5cf6; font-weight: 600;">选择</span>';
                        } else if (event.type === 'retry') {
                            eventLabel = '<span style="color: #f59e0b; font-weight: 600;">重试</span>';
                        } else if (event.type === 'switch') {
                            eventLabel = '<span style="color: #06b6d4; font-weight: 600;">切换</span>';
                        } else if (event.type === 'complete') {
                            if (event.status === 'success') {
                                eventLabel = '<span style="color: #10b981; font-weight: 600;">完成</span>';
                            } else if (event.status === 'error') {
                                eventLabel = '<span style="color: #ef4444; font-weight: 600;">失败</span>';
                            } else if (event.status === 'timeout') {
                                eventLabel = '<span style="color: #f59e0b; font-weight: 600;">超时</span>';
                            }
                        }

                        eventsHtml += `
                            <div class="${eventClass}">
                                <div class="log-time">${event.time}</div>
                                <div style="min-width: 60px;">${eventLabel}</div>
                                <div class="log-info">${event.content}</div>
                            </div>
                        `;
                    });

                    html += `
                        <div class="log-group" data-req-id="${reqId}">
                            <div class="log-group-header" onclick="toggleGroup('${reqId}')">
                                <span style="color: ${statusColor}; font-weight: 600; font-size: 11px;">⬤ ${statusText}</span>
                                <span style="color: #666; font-size: 11px; margin-left: 8px;">req_${reqId}</span>
                                ${accountId ? `<span style="color: ${getAccountColor(accountId)}; font-size: 11px; margin-left: 8px;">${accountId}</span>` : ''}
                                ${model ? `<span style="color: #999; font-size: 11px; margin-left: 8px;">${model}</span>` : ''}
                                <span style="color: #999; font-size: 11px; margin-left: 8px;">${log.events.length}条事件</span>
                                <span ${iconClass} style="margin-left: auto; color: #999;">▼</span>
                            </div>
                            <div class="log-group-content" ${contentStyle}>
                                ${eventsHtml}
                            </div>
                        </div>
                    `;
                });

                container.innerHTML = html;
            }

            function updateStats(logs, statsData) {
                const total = logs.length;
                const successLogs = logs.filter(log => log.status === 'success');
                const success = successLogs.length;
                const error = logs.filter(log => log.status === 'error').length;

                // 计算平均响应时间
                let avgTime = '-';
                if (success > 0) {
                    let totalDuration = 0;
                    let count = 0;
                    successLogs.forEach(log => {
                        log.events.forEach(event => {
                            if (event.type === 'complete' && event.content.includes('耗时')) {
                                const match = event.content.match(/([\d.]+)s/);
                                if (match) {
                                    totalDuration += parseFloat(match[1]);
                                    count++;
                                }
                            }
                        });
                    });
                    if (count > 0) {
                        avgTime = (totalDuration / count).toFixed(1) + 's';
                    }
                }

                // 计算成功率
                const totalCompleted = success + error;
                const successRate = totalCompleted > 0 ? ((success / totalCompleted) * 100).toFixed(1) + '%' : '-';

                // 更新日志统计
                document.getElementById('stat-total').textContent = total;
                document.getElementById('stat-success').textContent = success;
                document.getElementById('stat-error').textContent = error;
                document.getElementById('stat-success-rate').textContent = successRate;
                document.getElementById('stat-avg-time').textContent = avgTime;

                // 更新全局统计
                document.getElementById('stat-visitors').textContent = statsData.total_visitors;

                // 更新负载状态（带颜色）
                const loadElement = document.getElementById('stat-load');
                loadElement.textContent = statsData.requests_per_minute;
                loadElement.style.color = statsData.load_color;

                // 更新时间
                document.getElementById('stat-update-time').textContent = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
            }

            function toggleGroup(reqId) {
                const group = document.querySelector(`.log-group[data-req-id="${reqId}"]`);
                const content = group.querySelector('.log-group-content');
                const icon = group.querySelector('.toggle-icon');

                const isCollapsed = content.style.display === 'none';
                if (isCollapsed) {
                    content.style.display = 'block';
                    icon.classList.remove('collapsed');
                } else {
                    content.style.display = 'none';
                    icon.classList.add('collapsed');
                }

                // 保存折叠状态
                const foldState = JSON.parse(localStorage.getItem('public-log-fold-state') || '{}');
                foldState[reqId] = !isCollapsed;
                localStorage.setItem('public-log-fold-state', JSON.stringify(foldState));
            }

            // 初始加载
            loadData();

            // 自动刷新（每5秒）
            setInterval(loadData, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ---------- 全局 404 处理（必须在最后） ----------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """全局 404 处理器"""
    return JSONResponse(
        status_code=404,
        content={"detail": "Not Found"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)