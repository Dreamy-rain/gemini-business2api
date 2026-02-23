import json, time, os, asyncio, uuid, ssl, re, yaml, shutil, base64
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any
from pathlib import Path
import logging
from dotenv import load_dotenv

import httpx
import aiofiles
from fastapi import FastAPI, HTTPException, Header, Request, Body, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from util.streaming_parser import parse_json_array_stream_async
from collections import deque
from threading import Lock

# ---------- 数据目录配置 ----------
# 自动检测环境：HF Spaces Pro 使用 /data，本地使用 ./data
if os.path.exists("/data"):
    DATA_DIR = "/data"  # HF Pro 持久化存储
    logger_prefix = "[HF-PRO]"
else:
    DATA_DIR = "./data"  # 本地持久化存储
    logger_prefix = "[LOCAL]"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 统一的数据文件路径
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.yaml")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")

# 确保图片和视频目录存在
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# 媒体文件清理配置
MEDIA_CLEANUP_INTERVAL_SECONDS = 1800  # 每30分钟清理一次
MEDIA_MAX_AGE_SECONDS = 3600  # 文件最大保留1小时

# 导入认证模块
from core.auth import verify_api_key
from core.session_auth import is_logged_in, login_user, logout_user, require_login, generate_session_secret

# 导入核心模块
from core.message import (
    get_conversation_key,
    parse_last_message,
    build_full_context_text,
    strip_to_last_user_message,
    extract_text_from_content
)
from core.session_binding import (
    generate_chat_id,
    extract_chat_id,
    get_session_binding_manager
)
from core.google_api import (
    get_common_headers,
    create_google_session,
    upload_context_file,
    get_session_file_metadata,
    download_image_with_jwt,
    save_image_to_hf
)
from core.account import (
    AccountManager,
    MultiAccountManager,
    format_account_expiration,
    load_multi_account_config,
    load_accounts_from_source,
    reload_accounts as _reload_accounts,
    update_accounts_config as _update_accounts_config,
    delete_account as _delete_account,
    update_account_disabled_status as _update_account_disabled_status,
    bulk_update_account_disabled_status as _bulk_update_account_disabled_status,
    bulk_delete_accounts as _bulk_delete_accounts
)
from core.proxy_utils import parse_proxy_setting

# 导入 Uptime 追踪器
from core import uptime as uptime_tracker

# 导入配置管理和模板系统
from core.config import config_manager, config

# 数据库存储支持
from core import storage
from core.outbound_proxy import (
    DEFAULT_GEMINI_PROXY_HOST_SUFFIXES,
    ProxyAwareAsyncClient,
    normalize_proxy_url,
)

# 模型到配额类型的映射
MODEL_TO_QUOTA_TYPE = {
    "gemini-imagen": "images",
    "gemini-veo": "videos"
}

# ---------- 日志配置 ----------

# 内存日志缓冲区 (保留最近 1000 条日志，重启后清空)
log_buffer = deque(maxlen=1000)
log_lock = Lock()

# 统计数据持久化
stats_lock = asyncio.Lock()  # 改为异步锁

async def load_stats():
    """加载统计数据（异步）。"""
    data = None
    if storage.is_database_enabled():
        try:
            data = await asyncio.to_thread(storage.load_stats_sync)
            if not isinstance(data, dict):
                data = None
        except Exception as e:
            logger.error(f"[STATS] 数据库加载失败: {str(e)[:50]}")
    if data is None:
        try:
            if os.path.exists(STATS_FILE):
                async with aiofiles.open(STATS_FILE, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
        except Exception:
            pass

    # 如果没有加载到数据，返回默认值
    if data is None:
        data = {
            "total_visitors": 0,
            "total_requests": 0,
            "request_timestamps": [],
            "model_request_timestamps": {},
            "failure_timestamps": [],
            "rate_limit_timestamps": [],
            "visitor_ips": {},
            "account_conversations": {},
            "recent_conversations": []
        }

    # 将列表转换为 deque（限制大小防止内存无限增长）
    if isinstance(data.get("request_timestamps"), list):
        data["request_timestamps"] = deque(data["request_timestamps"], maxlen=20000)
    if isinstance(data.get("failure_timestamps"), list):
        data["failure_timestamps"] = deque(data["failure_timestamps"], maxlen=10000)
    if isinstance(data.get("rate_limit_timestamps"), list):
        data["rate_limit_timestamps"] = deque(data["rate_limit_timestamps"], maxlen=10000)

    return data

async def save_stats(stats):
    """保存统计数据（已优化：内部使用 storage 缓冲区，非阻塞）"""
    stats_to_save = stats.copy()
    if isinstance(stats_to_save.get("request_timestamps"), deque):
        stats_to_save["request_timestamps"] = list(stats_to_save["request_timestamps"])
    if isinstance(stats_to_save.get("failure_timestamps"), deque):
        stats_to_save["failure_timestamps"] = list(stats_to_save["failure_timestamps"])
    if isinstance(stats_to_save.get("rate_limit_timestamps"), deque):
        stats_to_save["rate_limit_timestamps"] = list(stats_to_save["rate_limit_timestamps"])

    # 1. 尝试保存到数据库（通过 storage 的后台缓冲区，极快）
    # [OPTIMIZE] 为了节省 Neon 数据库资源，不再将统计数据写入数据库，仅保存在本地文件
    # if storage.is_database_enabled():
    #     storage.save_stats_sync(stats_to_save)
    
    # 2. 定期保存到本地文件作为备份 (每 50 次请求保存一次文件，减少磁盘写入)
    if stats_to_save.get("total_requests", 0) % 50 == 0:
        try:
            async with aiofiles.open(STATS_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(stats_to_save, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"[STATS] 保存本地备份失败: {str(e)[:50]}")

# 初始化统计数据（需要在启动时异步加载）
global_stats = {
    "total_visitors": 0,
    "total_requests": 0,
    "request_timestamps": deque(maxlen=20000),
    "model_request_timestamps": {},
    "failure_timestamps": deque(maxlen=10000),
    "rate_limit_timestamps": deque(maxlen=10000),
    "visitor_ips": {},
    "account_conversations": {},
    "recent_conversations": []
}


def get_beijing_time_str(ts: Optional[float] = None) -> str:
    tz = timezone(timedelta(hours=8))
    current = datetime.fromtimestamp(ts or time.time(), tz=tz)
    return current.strftime("%Y-%m-%d %H:%M:%S")

def clean_global_stats(stats: dict, window_seconds: int = 12 * 3600) -> dict:
    """清理过期统计数据并限制字典大小"""
    now = time.time()
    
    # 清理 deque 数据
    for key in ["request_timestamps", "failure_timestamps", "rate_limit_timestamps"]:
        if key in stats and isinstance(stats[key], (deque, list)):
            cleaned = [ts for ts in stats[key] if now - ts < window_seconds]
            stats[key] = deque(cleaned, maxlen=getattr(stats[key], 'maxlen', 20000) if hasattr(stats[key], 'maxlen') else 20000)
            
    # 清理模型请求统计
    if "model_request_timestamps" in stats and isinstance(stats["model_request_timestamps"], dict):
        for model in list(stats["model_request_timestamps"].keys()):
            timestamps = stats["model_request_timestamps"][model]
            if isinstance(timestamps, list):
                cleaned = [ts for ts in timestamps if now - ts < window_seconds]
                if not cleaned:
                    del stats["model_request_timestamps"][model]
                else:
                    stats["model_request_timestamps"][model] = cleaned

    # 限制访客 IP 记录（LRU 策略：如果超过 5000 个，清理最旧的）
    if "visitor_ips" in stats and isinstance(stats["visitor_ips"], dict):
        if len(stats["visitor_ips"]) > 5000:
            # 按最后访问时间排序
            sorted_ips = sorted(stats["visitor_ips"].items(), key=lambda x: x[1].get("last_seen", 0) if isinstance(x[1], dict) else 0)
            # 移除最旧的 1000 个
            for ip, _ in sorted_ips[:1000]:
                del stats["visitor_ips"][ip]
                
    # 限制最近会话记录
    if "recent_conversations" in stats and isinstance(stats["recent_conversations"], list):
        if len(stats["recent_conversations"]) > 1000:
            stats["recent_conversations"] = stats["recent_conversations"][-1000:]
            
    return stats


def build_recent_conversation_entry(
    request_id: str,
    model: Optional[str],
    message_count: Optional[int],
    start_ts: float,
    status: str,
    duration_s: Optional[float] = None,
    error_detail: Optional[str] = None,
) -> dict:
    start_time = get_beijing_time_str(start_ts)
    if model:
        start_content = f"{model}"
        if message_count:
            start_content = f"{model} | {message_count}条消息"
    else:
        start_content = "请求处理中"

    events = [{
        "time": start_time,
        "type": "start",
        "content": start_content,
    }]

    end_time = get_beijing_time_str(start_ts + duration_s) if duration_s is not None else get_beijing_time_str()

    if status == "success":
        if duration_s is not None:
            events.append({
                "time": end_time,
                "type": "complete",
                "status": "success",
            "content": f"响应完成 | 耗时{duration_s:.2f}s",
            })
        else:
            events.append({
                "time": end_time,
                "type": "complete",
                "status": "success",
            "content": "响应完成",
            })
    elif status == "timeout":
        events.append({
            "time": end_time,
            "type": "complete",
            "status": "timeout",
            "content": "请求超时",
        })
    else:
        detail = error_detail or "请求失败"
        events.append({
            "time": end_time,
            "type": "complete",
            "status": "error",
            "content": detail[:120],
        })

    return {
        "request_id": request_id,
        "start_time": start_time,
        "start_ts": start_ts,
        "status": status,
        "events": events,
    }

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

# ---------- Linux zombie process reaper ----------
# DrissionPage / Chromium may spawn subprocesses that exit without being waited on,
# which can accumulate as zombies (<defunct>) in long-running services.
try:
    from core.child_reaper import install_child_reaper

    install_child_reaper(log=lambda m: logger.warning(m))
except Exception:
    # Never fail startup due to optional process reaper.
    pass

# 添加内存日志处理器
memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(memory_handler)

# ---------- 配置管理（使用统一配置系统）----------
# 所有配置通过 config_manager 访问，优先级：环境变量 > YAML > 默认值
TIMEOUT_SECONDS = 600
API_KEY = config.basic.api_key
ADMIN_KEY = config.security.admin_key
_proxy_auth, _no_proxy_auth = parse_proxy_setting(config.basic.proxy_for_auth)
_proxy_chat, _no_proxy_chat = parse_proxy_setting(config.basic.proxy_for_chat)
PROXY_FOR_AUTH = _proxy_auth
PROXY_FOR_CHAT = _proxy_chat
_NO_PROXY = ",".join(filter(None, {_no_proxy_auth, _no_proxy_chat}))
if _NO_PROXY:
    os.environ["NO_PROXY"] = _NO_PROXY
BASE_URL = config.basic.base_url
SESSION_SECRET_KEY = config.security.session_secret_key
SESSION_EXPIRE_HOURS = config.session.expire_hours

# ---------- 公开展示配置 ----------
LOGO_URL = config.public_display.logo_url
CHAT_URL = config.public_display.chat_url

# ---------- 图片生成配置 ----------
IMAGE_GENERATION_ENABLED = config.image_generation.enabled
IMAGE_GENERATION_MODELS = config.image_generation.supported_models

# ---------- 虚拟模型映射 ----------
VIRTUAL_MODELS = {
    "gemini-imagen": {"imageGenerationSpec": {}},
    "gemini-veo": {"videoGenerationSpec": {}},
}

def get_tools_spec(model_name: str) -> dict:
    """根据模型名称返回工具配置"""
    # 虚拟模型
    if model_name in VIRTUAL_MODELS:
        return VIRTUAL_MODELS[model_name]
    
    # 普通模型
    tools_spec = {
        "webGroundingSpec": {},
        "toolRegistry": "default_tool_registry",
    }
    
    if IMAGE_GENERATION_ENABLED and model_name in IMAGE_GENERATION_MODELS:
        tools_spec["imageGenerationSpec"] = {}
    
    return tools_spec


# ---------- 重试配置 ----------
MAX_NEW_SESSION_TRIES = config.retry.max_new_session_tries
MAX_REQUEST_RETRIES = config.retry.max_request_retries
MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
ACCOUNT_FAILURE_THRESHOLD = config.retry.account_failure_threshold
RATE_LIMIT_COOLDOWN_SECONDS = config.retry.rate_limit_cooldown_seconds
SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds
MIN_HEALTHY_ACCOUNTS = 21

# ---------- 模型映射配置 ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-3-pro-preview": "gemini-3-pro-preview",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview"
}

# ---------- HTTP 客户端 ----------
def _build_http_client(specific_proxy=None):
    client_kwargs = {
        "verify": False,
        "http2": True,  # 启用 HTTP/2 提升并发性能
        "timeout": httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
        "limits": httpx.Limits(
            max_keepalive_connections=100,
            max_connections=200,
        ),
        "trust_env": False,
    }

    outbound = config.basic.outbound_proxy
    if getattr(outbound, "is_configured", None) and outbound.is_configured():
        proxy_url = outbound.to_proxy_url(config.security.admin_key)
        return ProxyAwareAsyncClient(
            proxy_url=proxy_url or None,
            no_proxy=outbound.no_proxy,
            direct_fallback=outbound.direct_fallback,
            proxied_host_suffixes=(),
            client_kwargs=client_kwargs,
        )

    proxy_url = normalize_proxy_url(specific_proxy or "")
    if proxy_url:
        try:
            return httpx.AsyncClient(proxy=proxy_url, **client_kwargs)
        except (httpx.InvalidURL, Exception):
            logger.warning(f"[CONFIG] 代理格式无效，已忽略: {specific_proxy}")
            return httpx.AsyncClient(proxy=None, **client_kwargs)

    return httpx.AsyncClient(proxy=None, **client_kwargs)


# 对话操作客户端（用于JWT获取、创建会话、发送消息）
http_client = _build_http_client(PROXY_FOR_CHAT)

# 对话流式客户端（用于流式响应）
http_client_chat = _build_http_client(PROXY_FOR_CHAT)

# 账户操作客户端（用于注册/登录/刷新）
http_client_auth = _build_http_client(PROXY_FOR_AUTH)

# 打印代理配置日志
logger.info(f"[PROXY] Account operations (register/login/refresh): {PROXY_FOR_AUTH if PROXY_FOR_AUTH else 'disabled'}")
logger.info(f"[PROXY] Chat operations (JWT/session/messages): {PROXY_FOR_CHAT if PROXY_FOR_CHAT else 'disabled'}")

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

# ---------- 多账户支持 ----------
# (AccountConfig, AccountManager, MultiAccountManager 已移至 core/account.py)

# ---------- 配置文件管理 ----------
# (配置管理函数已移至 core/account.py)

# 初始化多账户管理器
multi_account_mgr = load_multi_account_config(
    http_client,
    USER_AGENT,
    ACCOUNT_FAILURE_THRESHOLD,
    RATE_LIMIT_COOLDOWN_SECONDS,
    SESSION_CACHE_TTL_SECONDS,
    global_stats
)

# ---------- 自动注册/刷新服务 ----------
register_service = None
login_service = None

def _set_multi_account_mgr(new_mgr):
    global multi_account_mgr
    multi_account_mgr = new_mgr
    if register_service:
        register_service.multi_account_mgr = new_mgr
    if login_service:
        login_service.multi_account_mgr = new_mgr

def _get_global_stats():
    return global_stats

try:
    from core.register_service import RegisterService
    from core.login_service import LoginService
    register_service = RegisterService(
        multi_account_mgr,
        http_client_auth,
        USER_AGENT,
        ACCOUNT_FAILURE_THRESHOLD,
        RATE_LIMIT_COOLDOWN_SECONDS,
        SESSION_CACHE_TTL_SECONDS,
        _get_global_stats,
        _set_multi_account_mgr,
    )
    login_service = LoginService(
        multi_account_mgr,
        http_client_auth,
        USER_AGENT,
        ACCOUNT_FAILURE_THRESHOLD,
        RATE_LIMIT_COOLDOWN_SECONDS,
        SESSION_CACHE_TTL_SECONDS,
        _get_global_stats,
        _set_multi_account_mgr,
    )
except Exception as e:
    logger.warning("[SYSTEM] 自动注册/刷新服务不可用: %s", e)
    register_service = None
    login_service = None

# 验证必需的环境变量
if not ADMIN_KEY:
    logger.error("[SYSTEM] 未配置 ADMIN_KEY 环境变量，请设置后重启")
    import sys
    sys.exit(1)

# 启动日志
logger.info("[SYSTEM] API端点: /v1/chat/completions")
logger.info("[SYSTEM] Admin API endpoints: /admin/*")
logger.info("[SYSTEM] Public endpoints: /public/log, /public/stats, /public/uptime")
logger.info(f"[SYSTEM] Session过期时间: {SESSION_EXPIRE_HOURS}小时")
logger.info("[SYSTEM] 系统初始化完成")

# ---------- JWT 管理 ----------
# (JWTManager已移至 core/jwt.py)

# ---------- Session & File 管理 ----------
# (Google API函数已移至 core/google_api.py)

# ---------- 消息处理逻辑 ----------
# (消息处理函数已移至 core/message.py)

# ---------- 媒体处理函数 ----------
def process_image(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """处理图片：根据配置返回 base64 或 URL"""
    output_format = config_manager.image_output_format

    if output_format == "base64":
        b64 = base64.b64encode(data).decode()
        logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] 图片{idx}已编码为base64")
        return f"\n\n![生成的图片](data:{mime};base64,{b64})\n\n"
    else:
        url = save_image_to_hf(data, chat_id, file_id, mime, base_url, IMAGE_DIR)
        logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] 图片{idx}已保存: {url}")
        return f"\n\n![生成的图片]({url})\n\n"

def process_video(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """处理视频：根据配置返回不同格式"""
    url = save_image_to_hf(data, chat_id, file_id, mime, base_url, VIDEO_DIR, "videos")
    logger.info(f"[VIDEO] [{account_id}] [req_{request_id}] 视频{idx}已保存: {url}")

    output_format = config_manager.video_output_format

    if output_format == "html":
        return f'\n\n<video controls width="100%" style="max-width: 640px;"><source src="{url}" type="{mime}">您的浏览器不支持视频播放</video>\n\n'
    elif output_format == "markdown":
        return f"\n\n![生成的视频]({url})\n\n"
    else:  # url
        return f"\n\n{url}\n\n"

def process_media(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """统一媒体处理入口：根据 MIME 类型分发到对应处理器"""
    logger.info(f"[MEDIA] [{account_id}] [req_{request_id}] 处理媒体{idx}: MIME={mime}")
    if mime.startswith("video/"):
        return process_video(data, mime, chat_id, file_id, base_url, idx, request_id, account_id)
    else:
        return process_image(data, mime, chat_id, file_id, base_url, idx, request_id, account_id)

# ---------- OpenAI 兼容接口 ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
allow_all_origins = os.getenv("ALLOW_ALL_ORIGINS", "0") == "1"
if allow_all_origins and not frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.exists(os.path.join("static", "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join("static", "assets")), name="assets")
if os.path.exists(os.path.join("static", "vendor")):
    app.mount("/vendor", StaticFiles(directory=os.path.join("static", "vendor")), name="vendor")

@app.get("/")
async def serve_frontend_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(404, "Not Found")

@app.get("/logo.svg")
async def serve_logo():
    logo_path = os.path.join("static", "logo.svg")
    if os.path.exists(logo_path):
        return FileResponse(logo_path)
    raise HTTPException(404, "Not Found")

@app.get("/admin/health")
async def health_check():
    """健康检查端点，用于 Docker HEALTHCHECK"""
    return {"status": "ok"}

# ---------- Session 中间件配置 ----------
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    max_age=SESSION_EXPIRE_HOURS * 3600,  # 转换为秒
    same_site="lax",
    https_only=False  # 本地开发可设为False，生产环境建议True
)

# ---------- Uptime 追踪中间件 ----------
@app.middleware("http")
async def track_uptime_middleware(request: Request, call_next):
    """Uptime 监控：跟踪非对话接口的请求结果。"""
    path = request.url.path
    if (
        path.startswith("/images/")
        or path.startswith("/public/")
        or path.startswith("/favicon")
        or path.endswith("/v1/chat/completions")
    ):
        return await call_next(request)

    start_time = time.time()

    try:
        response = await call_next(request)
        latency_ms = int((time.time() - start_time) * 1000)
        success = response.status_code < 400
        uptime_tracker.record_request("api_service", success, latency_ms, response.status_code)
        return response

    except Exception:
        uptime_tracker.record_request("api_service", False)
        raise


# ---------- 图片和视频静态服务初始化 ----------
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/videos", StaticFiles(directory=VIDEO_DIR), name="videos")
if IMAGE_DIR == "/data/images":
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (HF Pro持久化)")
    logger.info(f"[SYSTEM] 视频静态服务已启用: /videos/ -> {VIDEO_DIR} (HF Pro持久化)")
else:
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (本地持久化)")
    logger.info(f"[SYSTEM] 视频静态服务已启用: /videos/ -> {VIDEO_DIR} (本地持久化)")

# ---------- 后台任务启动 ----------

# 全局变量：记录上次检测到的账号更新时间（用于自动刷新检测）
_last_known_accounts_version: float | None = None

async def global_stats_cleanup_task(interval_seconds: int = 3600):
    """后台任务：定期清理全局统计数据，防止内存溢出"""
    logger.info(f"[SYSTEM] 统计数据自动清理任务已启动（间隔: {interval_seconds}秒）")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with stats_lock:
                clean_global_stats(global_stats)
                # [OPTIMIZE] 彻底禁用每小时的统计归档，确保存储真正休眠
                # 如果数据库启用，顺便保存一份
                # if storage.is_database_enabled():
                #     await storage.save_stats(global_stats)
            logger.debug("[CLEANUP] 全局统计数据清理完成")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CLEANUP] 统计清理任务出错: {e}")
            await asyncio.sleep(60)


async def media_cleanup_task():
    """后台任务：定期清理过期的图片和视频文件"""
    while True:
        try:
            await asyncio.sleep(MEDIA_CLEANUP_INTERVAL_SECONDS)
            
            now = time.time()
            deleted_count = 0
            
            # 清理图片目录
            for filename in os.listdir(IMAGE_DIR):
                filepath = os.path.join(IMAGE_DIR, filename)
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > MEDIA_MAX_AGE_SECONDS:
                        try:
                            os.remove(filepath)
                            deleted_count += 1
                        except Exception:
                            pass
            
            # 清理视频目录
            for filename in os.listdir(VIDEO_DIR):
                filepath = os.path.join(VIDEO_DIR, filename)
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > MEDIA_MAX_AGE_SECONDS:
                        try:
                            os.remove(filepath)
                            deleted_count += 1
                        except Exception:
                            pass
            
            if deleted_count > 0:
                logger.info(f"[CLEANUP] 已清理 {deleted_count} 个过期媒体文件")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CLEANUP] 媒体清理任务出错: {type(e).__name__}: {str(e)[:50]}")

async def auto_refresh_accounts_task():
    """后台任务：定期检查数据库中的账号变化，自动刷新"""
    global multi_account_mgr, _last_known_accounts_version

    # 初始化：记录当前账号更新时间
    if storage.is_database_enabled() and not os.environ.get("ACCOUNTS_CONFIG"):
        _last_known_accounts_version = await asyncio.to_thread(
            storage.get_accounts_updated_at_sync
        )

    while True:
        try:
            # 获取配置的刷新间隔（支持热更新）
            refresh_interval = config_manager.auto_refresh_accounts_seconds
            if refresh_interval <= 0:
                # 自动刷新已禁用，等待一段时间后再检查配置
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(refresh_interval)

            # 环境变量优先时无需自动刷新
            if os.environ.get("ACCOUNTS_CONFIG"):
                continue

            # 检查数据库是否启用
            if not storage.is_database_enabled():
                continue

            # 获取数据库中的账号更新时间
            db_version = await asyncio.to_thread(storage.get_accounts_updated_at_sync)
            if db_version is None:
                continue

            # 比较更新时间变化
            if _last_known_accounts_version != db_version:
                logger.info("[AUTO-REFRESH] 检测到账号变化，正在自动刷新...")

                # 重新加载账号配置
                new_mgr = _reload_accounts(
                    multi_account_mgr,
                    http_client,
                    USER_AGENT,
                    ACCOUNT_FAILURE_THRESHOLD,
                    RATE_LIMIT_COOLDOWN_SECONDS,
                    SESSION_CACHE_TTL_SECONDS,
                    global_stats
                )
                _set_multi_account_mgr(new_mgr)

                _last_known_accounts_version = db_version
                logger.info(f"[AUTO-REFRESH] 账号刷新完成，当前账号数: {len(multi_account_mgr.accounts)}")

            # -----------------------------------------------------------------
            # [MAINTENANCE] 追加：自动清理过期账号 与 自动补号逻辑
            # 注：只要执行到这里，说明没有通过环境变量强行挂载只读配置，且启用了数据库。
            # -----------------------------------------------------------------
            
            # 1. 自动清理过期账号
            expired_ids = []
            for acc in multi_account_mgr.accounts.values():
                # 注意：is_expired() 现在仅代表物理过期，不含提前量。物理清理逻辑只应针对物理过期的账号。
                if acc.config.is_expired():
                    expired_ids.append(acc.config.account_id)
            
            if expired_ids:
                logger.info(f"[MAINTENANCE] 发现过期账号 {len(expired_ids)} 个，准备自动清理...")
                try:
                    new_mgr, success_count, _ = _bulk_delete_accounts(
                        expired_ids,
                        multi_account_mgr,
                        http_client,
                        USER_AGENT,
                        ACCOUNT_FAILURE_THRESHOLD,
                        RATE_LIMIT_COOLDOWN_SECONDS,
                        SESSION_CACHE_TTL_SECONDS,
                        global_stats
                    )
                    _set_multi_account_mgr(new_mgr)
                    logger.info(f"[MAINTENANCE] 过期账号清理完成，成功删除 {success_count} 个")
                    # 【关键点】清理后会触发内部写库，为了防止下一轮被当成外部变更而发生重复reload，这里立即重置一下版本状态。
                    _last_known_accounts_version = await asyncio.to_thread(storage.get_accounts_updated_at_sync)
                except Exception as e:
                    logger.error(f"[MAINTENANCE] 清理过期账号时出错: {e}")

            # 2. 统计健康账号数量并自动补号
            valid_active_count = 0
            for acc_id, acc in multi_account_mgr.accounts.items():
                c = acc.config
                # 【逻辑加固】健康账号判定标准：
                # 1. 未物理过期 (is_expired)
                # 2. 未手动禁用 (disabled)
                # 3. 必需字段完整 (secure_c_ses等)
                # 4. 【关键】账户不是永久性损坏的。
                #    这里改用专门设计的 is_healthy_for_capacity()：它会将 429 限流冷却期的账号也判定为 True。
                if not c.is_expired() and not c.disabled and acc.is_healthy_for_capacity():
                    if c.secure_c_ses and c.csesidx and c.config_id:
                        valid_active_count += 1
            
            if valid_active_count < MIN_HEALTHY_ACCOUNTS:
                need_count = MIN_HEALTHY_ACCOUNTS - valid_active_count
                if register_service:
                    try:
                        # 尝试启动新号注册任务（依靠内置逻辑防止并发）
                        await register_service.start_register(count=need_count)
                        logger.info(f"[MAINTENANCE] 健康账号数量({valid_active_count})低于{MIN_HEALTHY_ACCOUNTS}，启动补号任务: {need_count} 个")
                    except ValueError as e:
                        # 预期行为：如果在运行中，会抛出 ValueError
                        logger.debug(f"[MAINTENANCE] 补号任务挂起/拦截 (已在运行或不满足条件): {e}")
                    except Exception as e:
                        logger.error(f"[MAINTENANCE] 尝试启动补号任务出错: {e}")
            # -----------------------------------------------------------------

        except asyncio.CancelledError:
            logger.info("[AUTO-REFRESH] 自动刷新任务已停止")
            break
        except Exception as e:
            logger.error(f"[AUTO-REFRESH] 自动刷新任务异常: {type(e).__name__}: {str(e)[:100]}")
            await asyncio.sleep(60)  # 出错后等待60秒再重试


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化后台任务"""
    global global_stats

    # 文件迁移逻辑：将根目录的旧文件迁移到 data 目录
    old_accounts = "accounts.json"
    if os.path.exists(old_accounts) and not os.path.exists(ACCOUNTS_FILE):
        try:
            shutil.copy(old_accounts, ACCOUNTS_FILE)
            logger.info(f"{logger_prefix} 已迁移 {old_accounts} -> {ACCOUNTS_FILE}")
        except Exception as e:
            logger.warning(f"{logger_prefix} 文件迁移失败: {e}")

    # 加载统计数据
    global_stats = await load_stats()
    global_stats.setdefault("request_timestamps", [])
    global_stats.setdefault("model_request_timestamps", {})
    global_stats.setdefault("failure_timestamps", [])
    global_stats.setdefault("rate_limit_timestamps", [])
    global_stats.setdefault("recent_conversations", [])
    uptime_tracker.configure_storage(os.path.join(DATA_DIR, "uptime.json"))
    uptime_tracker.load_heartbeats()
    logger.info(f"[SYSTEM] 统计数据已加载: {global_stats['total_requests']} 次请求, {global_stats['total_visitors']} 位访客")

    # 启动缓存清理任务
    asyncio.create_task(multi_account_mgr.start_background_cleanup())
    logger.info("[SYSTEM] 后台缓存清理任务已启动（间隔: 5分钟）")

    # 启动自动刷新账号任务（仅数据库模式有效）
    if os.environ.get("ACCOUNTS_CONFIG"):
        logger.info("[SYSTEM] 自动刷新账号已跳过（使用 ACCOUNTS_CONFIG）")
    elif storage.is_database_enabled() and AUTO_REFRESH_ACCOUNTS_SECONDS > 0:
        asyncio.create_task(auto_refresh_accounts_task())
        logger.info(f"[SYSTEM] 自动刷新账号任务已启动（间隔: {AUTO_REFRESH_ACCOUNTS_SECONDS}秒）")
    elif storage.is_database_enabled():
        logger.info("[SYSTEM] 自动刷新账号功能已禁用（配置为0）")

    # 启动数据库统计数据后台持久化任务
    # [OPTIMIZE] 彻底禁用统计数据上报数据库
    # if storage.is_database_enabled():
    #     asyncio.create_task(storage.start_stats_persistence_task(interval=60))
    #     logger.info("[SYSTEM] 数据库统计后台持久化任务已启动 (间隔: 60s)")

    # 启动全局统计定时清理任务
    asyncio.create_task(global_stats_cleanup_task())

    # 启动媒体文件定时清理任务
    asyncio.create_task(media_cleanup_task())
    logger.info(f"[SYSTEM] 媒体文件清理任务已启动（间隔: {MEDIA_CLEANUP_INTERVAL_SECONDS}秒，保留: {MEDIA_MAX_AGE_SECONDS}秒）")

    # 启动自动登录刷新轮询
    if login_service:
        try:
            asyncio.create_task(login_service.start_polling())
            logger.info("[SYSTEM] 账户过期检查轮询已启动（间隔: 30分钟）")
        except Exception as e:
            logger.error(f"[SYSTEM] 启动登录服务失败: {e}")
    else:
        logger.info("[SYSTEM] 自动登录刷新未启用或依赖不可用")

    # 启动会话绑定管理器（从数据库加载绑定关系，启动持久化任务）
    try:
        binding_mgr = get_session_binding_manager()
        # [OPTIMIZE] 禁用会话绑定持久化，避免流浪模式产生的海量临时数据写入数据库
        # await binding_mgr.load_from_db()
        # asyncio.create_task(binding_mgr.start_persist_task())
        logger.info("[SYSTEM] 会话绑定管理器已启动（内存模式，不持久化）")
    except Exception as e:
        logger.error(f"[SYSTEM] 启动会话绑定管理器失败: {e}")

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
# ---------- Auth endpoints (API) ----------

@app.post("/login")
async def admin_login_post(request: Request, admin_key: str = Form(...)):
    """Admin login (API)"""
    if admin_key == ADMIN_KEY:
        login_user(request)
        logger.info("[AUTH] Admin login success")
        return {"success": True}
    logger.warning("[AUTH] Login failed - invalid key")
    raise HTTPException(401, "Invalid key")


@app.get("/session/status")
async def session_status(request: Request):
    """检查当前 Session 是否已认证"""
    if is_logged_in(request):
        return {"authenticated": True}
    raise HTTPException(401, "Unauthorized")


@app.post("/logout")
@require_login(redirect_to_login=False)
async def admin_logout(request: Request):
    """Admin logout (API)"""
    logout_user(request)
    logger.info("[AUTH] Admin logout")
    return {"success": True}



@app.get("/admin/stats")
@require_login()
async def admin_stats(request: Request):
    now = time.time()
    window_seconds = 12 * 3600

    active_accounts = 0
    failed_accounts = 0
    rate_limited_accounts = 0
    idle_accounts = 0

    for account_manager in multi_account_mgr.accounts.values():
        config = account_manager.config
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()
        is_rate_limited = cooldown_seconds > 0 and cooldown_reason and "429" in cooldown_reason
        is_expired = config.is_expired()
        is_auto_disabled = (not account_manager.is_available) and (not config.disabled)
        is_failed = is_auto_disabled or is_expired or cooldown_reason == "错误禁用"
        is_active = (not is_failed) and (not config.disabled) and (not is_rate_limited)

        if is_rate_limited:
            rate_limited_accounts += 1
        elif is_failed:
            failed_accounts += 1
        elif is_active:
            active_accounts += 1
        else:
            idle_accounts += 1

    total_accounts = len(multi_account_mgr.accounts)

    beijing_tz = timezone(timedelta(hours=8))
    now_dt = datetime.now(beijing_tz)
    start_dt = (now_dt - timedelta(hours=11)).replace(minute=0, second=0, microsecond=0)
    start_ts = start_dt.timestamp()
    labels = [(start_dt + timedelta(hours=i)).strftime("%H:00") for i in range(12)]

    def bucketize(timestamps: list) -> list:
        buckets = [0] * 12
        for ts in timestamps:
            idx = int((ts - start_ts) // 3600)
            if 0 <= idx < 12:
                buckets[idx] += 1
        return buckets

    async with stats_lock:
        global_stats.update(clean_global_stats(global_stats))
        
        request_timestamps = list(global_stats.get("request_timestamps", []))
        failure_timestamps = list(global_stats.get("failure_timestamps", []))
        rate_limit_timestamps = list(global_stats.get("rate_limit_timestamps", []))
        model_request_timestamps = global_stats.get("model_request_timestamps", {})
        
        model_requests = {}
        for model in MODEL_MAPPING.keys():
            model_requests[model] = bucketize(model_request_timestamps.get(model, []))
        for model, timestamps in model_request_timestamps.items():
            if model not in model_requests:
                model_requests[model] = bucketize(timestamps)

    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "failed_accounts": failed_accounts,
        "rate_limited_accounts": rate_limited_accounts,
        "idle_accounts": idle_accounts,
        "trend": {
            "labels": labels,
            "total_requests": bucketize(request_timestamps),
            "failed_requests": bucketize(failure_timestamps),
            "rate_limited_requests": bucketize(rate_limit_timestamps),
            "model_requests": model_requests,
        }
    }

@app.get("/admin/accounts")
@require_login()
async def admin_get_accounts(request: Request):
    """获取所有账户的状态信息"""
    accounts_info = []
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()
        status, status_color, remaining_display = format_account_expiration(remaining_hours)
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()
        quota_status = account_manager.get_quota_status()

        accounts_info.append({
            "id": config.account_id,
            "status": status,
            "expires_at": config.expires_at or "未设置",
            "remaining_hours": remaining_hours,
            "remaining_display": remaining_display,
            "is_available": account_manager.is_available,
            "error_count": account_manager.error_count,
            "disabled": config.disabled,
            "cooldown_seconds": cooldown_seconds,
            "cooldown_reason": cooldown_reason,
            "conversation_count": account_manager.conversation_count,
            "session_usage_count": account_manager.session_usage_count,
            "quota_status": quota_status  # 新增配额状态
        })

    return {"total": len(accounts_info), "accounts": accounts_info}

@app.get("/admin/accounts-config")
@require_login()
async def admin_get_config(request: Request):
    """获取完整账户配置"""
    try:
        accounts_data = load_accounts_from_source()
        return {"accounts": accounts_data}
    except Exception as e:
        logger.error(f"[CONFIG] 获取配置失败: {str(e)}")
        raise HTTPException(500, f"获取失败: {str(e)}")

@app.put("/admin/accounts-config")
@require_login()
async def admin_update_config(request: Request, accounts_data: list = Body(...)):
    """更新整个账户配置"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_accounts_config(
            accounts_data, multi_account_mgr, http_client, USER_AGENT,
            ACCOUNT_FAILURE_THRESHOLD, RATE_LIMIT_COOLDOWN_SECONDS,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": "配置已更新", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 更新配置失败: {str(e)}")
        raise HTTPException(500, f"更新失败: {str(e)}")

@app.post("/admin/register/start")
@require_login()
async def admin_start_register(
    request: Request,
    count: Optional[int] = Body(default=None),
    domain: Optional[str] = Body(default=None),
    mail_provider: Optional[str] = Body(default=None),
):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = await register_service.start_register(count=count, domain=domain, mail_provider=mail_provider)
    return task.to_dict()


@app.post("/admin/register/cancel/{task_id}")
@require_login()
async def admin_cancel_register_task(request: Request, task_id: str, payload: dict = Body(default=None)):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    payload = payload or {}
    reason = payload.get("reason") or "cancelled"
    task = await register_service.cancel_task(task_id, reason=reason)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/register/task/{task_id}")
@require_login()
async def admin_get_register_task(request: Request, task_id: str):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = register_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/register/current")
@require_login()
async def admin_get_current_register_task(request: Request):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = register_service.get_current_task()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.post("/admin/login/start")
@require_login()
async def admin_start_login(request: Request, account_ids: List[str] = Body(...)):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = await login_service.start_login(account_ids)
    return task.to_dict()


@app.post("/admin/login/cancel/{task_id}")
@require_login()
async def admin_cancel_login_task(request: Request, task_id: str, payload: dict = Body(default=None)):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    payload = payload or {}
    reason = payload.get("reason") or "cancelled"
    task = await login_service.cancel_task(task_id, reason=reason)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/login/task/{task_id}")
@require_login()
async def admin_get_login_task(request: Request, task_id: str):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = login_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/login/current")
@require_login()
async def admin_get_current_login_task(request: Request):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = login_service.get_current_task()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.post("/admin/login/check")
@require_login()
async def admin_check_login_refresh(request: Request):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = await login_service.check_and_refresh()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.post("/admin/auto-refresh/pause")
@require_login()
async def admin_pause_auto_refresh(request: Request):
    """暂停自动刷新（运行时开关，不保存到数据库）"""
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    login_service.pause_auto_refresh()
    return {"status": "paused", "message": "Auto-refresh paused (runtime only)"}

@app.post("/admin/auto-refresh/resume")
@require_login()
async def admin_resume_auto_refresh(request: Request):
    """恢复自动刷新并立即执行一次检查"""
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    was_paused = login_service.resume_auto_refresh()
    # 如果之前是暂停状态，立即执行一次检查
    if was_paused:
        asyncio.create_task(login_service.check_and_refresh())
        return {"status": "active", "message": "Auto-refresh resumed and checking now"}
    return {"status": "active", "message": "Auto-refresh resumed"}

@app.get("/admin/auto-refresh/status")
@require_login()
async def admin_get_auto_refresh_status(request: Request):
    """获取自动刷新状态"""
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    is_paused = login_service.is_auto_refresh_paused()
    return {"paused": is_paused, "status": "paused" if is_paused else "active"}

@app.delete("/admin/accounts/{account_id}")
@require_login()
async def admin_delete_account(request: Request, account_id: str):
    """删除单个账户"""
    global multi_account_mgr
    try:
        multi_account_mgr = _delete_account(
            account_id, multi_account_mgr, http_client, USER_AGENT,
            ACCOUNT_FAILURE_THRESHOLD, RATE_LIMIT_COOLDOWN_SECONDS,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": f"账户 {account_id} 已删除", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 删除账户失败: {str(e)}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.put("/admin/accounts/bulk-delete")
@require_login()
async def admin_bulk_delete_accounts(request: Request, account_ids: list[str]):
    """批量删除账户，单次最多50个"""
    global multi_account_mgr

    # 数量限制验证
    if len(account_ids) > 50:
        raise HTTPException(400, f"单次最多删除50个账户，当前请求 {len(account_ids)} 个")
    if not account_ids:
        raise HTTPException(400, "账户ID列表不能为空")

    try:
        multi_account_mgr, success_count, errors = _bulk_delete_accounts(
            account_ids,
            multi_account_mgr,
            http_client,
            USER_AGENT,
            ACCOUNT_FAILURE_THRESHOLD,
            RATE_LIMIT_COOLDOWN_SECONDS,
            SESSION_CACHE_TTL_SECONDS,
            global_stats
        )
        return {"status": "success", "success_count": success_count, "errors": errors}
    except Exception as e:
        logger.error(f"[CONFIG] 批量删除账户失败: {str(e)}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.put("/admin/accounts/{account_id}/disable")
@require_login()
async def admin_disable_account(request: Request, account_id: str):
    """手动禁用账户"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_account_disabled_status(
            account_id, True, multi_account_mgr, http_client, USER_AGENT,
            ACCOUNT_FAILURE_THRESHOLD, RATE_LIMIT_COOLDOWN_SECONDS,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": f"账户 {account_id} 已禁用", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 禁用账户失败: {str(e)}")
        raise HTTPException(500, f"禁用失败: {str(e)}")

@app.put("/admin/accounts/{account_id}/enable")
@require_login()
async def admin_enable_account(request: Request, account_id: str):
    """启用账户（同时重置错误禁用状态）"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_account_disabled_status(
            account_id, False, multi_account_mgr, http_client, USER_AGENT,
            ACCOUNT_FAILURE_THRESHOLD, RATE_LIMIT_COOLDOWN_SECONDS,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )

        # 重置运行时错误状态（允许手动恢复错误禁用的账户）
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            account_mgr.is_available = True
            account_mgr.error_count = 0
            account_mgr.last_429_time = 0.0
            logger.info(f"[CONFIG] 账户 {account_id} 错误状态已重置")

        return {"status": "success", "message": f"账户 {account_id} 已启用", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 启用账户失败: {str(e)}")
        raise HTTPException(500, f"启用失败: {str(e)}")

@app.put("/admin/accounts/bulk-enable")
@require_login()
async def admin_bulk_enable_accounts(request: Request, account_ids: list[str]):
    """批量启用账户，单次最多50个"""
    global multi_account_mgr
    success_count, errors = _bulk_update_account_disabled_status(
        account_ids, False, multi_account_mgr
    )
    # 重置运行时错误状态
    for account_id in account_ids:
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            account_mgr.is_available = True
            account_mgr.error_count = 0
            account_mgr.last_429_time = 0.0
    return {"status": "success", "success_count": success_count, "errors": errors}

@app.put("/admin/accounts/bulk-disable")
@require_login()
async def admin_bulk_disable_accounts(request: Request, account_ids: list[str]):
    """批量禁用账户，单次最多50个"""
    global multi_account_mgr
    success_count, errors = _bulk_update_account_disabled_status(
        account_ids, True, multi_account_mgr
    )
    return {"status": "success", "success_count": success_count, "errors": errors}

# ---------- Auth endpoints (API) ----------
@app.get("/admin/settings")
@require_login()
async def admin_get_settings(request: Request):
    """获取系统设置"""
    # 返回当前配置（转换为字典格式）
    outbound = config.basic.outbound_proxy
    outbound_password = outbound.decrypt_password(config.security.admin_key) if getattr(outbound, "decrypt_password", None) else ""
    return {
        "basic": {
            "api_key": config.basic.api_key,
            "api_keys": [k.model_dump() for k in config.basic.api_keys],
            "base_url": config.basic.base_url,
            "proxy": config.basic.proxy,
            "proxy_for_auth": config.basic.proxy_for_auth,
            "proxy_for_chat": config.basic.proxy_for_chat,
            "duckmail_base_url": config.basic.duckmail_base_url,
            "duckmail_api_key": config.basic.duckmail_api_key,
            "duckmail_verify_ssl": config.basic.duckmail_verify_ssl,
            "temp_mail_provider": config.basic.temp_mail_provider,
            "moemail_base_url": config.basic.moemail_base_url,
            "moemail_api_key": config.basic.moemail_api_key,
            "moemail_domain": config.basic.moemail_domain,
            "freemail_base_url": config.basic.freemail_base_url,
            "freemail_jwt_token": config.basic.freemail_jwt_token,
            "freemail_verify_ssl": config.basic.freemail_verify_ssl,
            "freemail_domain": config.basic.freemail_domain,
            "mail_proxy_enabled": config.basic.mail_proxy_enabled,
            "gptmail_base_url": config.basic.gptmail_base_url,
            "gptmail_api_key": config.basic.gptmail_api_key,
            "gptmail_verify_ssl": config.basic.gptmail_verify_ssl,
            "browser_engine": config.basic.browser_engine,
            "browser_headless": config.basic.browser_headless,
            "refresh_window_hours": config.basic.refresh_window_hours,
            "register_default_count": config.basic.register_default_count,
            "register_domain": config.basic.register_domain,
        },
        "image_generation": {
            "enabled": config.image_generation.enabled,
            "supported_models": config.image_generation.supported_models,
            "output_format": config.image_generation.output_format
        },
        "video_generation": {
            "output_format": config.video_generation.output_format
        },
        "retry": {
            "max_new_session_tries": config.retry.max_new_session_tries,
            "max_request_retries": config.retry.max_request_retries,
            "max_account_switch_tries": config.retry.max_account_switch_tries,
            "account_failure_threshold": config.retry.account_failure_threshold,
            "rate_limit_cooldown_seconds": config.retry.rate_limit_cooldown_seconds,
            "session_cache_ttl_seconds": config.retry.session_cache_ttl_seconds,
            "auto_refresh_accounts_seconds": config.retry.auto_refresh_accounts_seconds
        },
        "public_display": {
            "logo_url": config.public_display.logo_url,
            "chat_url": config.public_display.chat_url
        },
        "session": {
            "expire_hours": config.session.expire_hours
        }
    }

@app.put("/admin/settings")
@require_login()
async def admin_update_settings(request: Request, new_settings: dict = Body(...)):
    """更新系统设置"""
    global API_KEY, PROXY_FOR_AUTH, PROXY_FOR_CHAT, BASE_URL, LOGO_URL, CHAT_URL
    global IMAGE_GENERATION_ENABLED, IMAGE_GENERATION_MODELS
    global MAX_NEW_SESSION_TRIES, MAX_REQUEST_RETRIES, MAX_ACCOUNT_SWITCH_TRIES
    global ACCOUNT_FAILURE_THRESHOLD, RATE_LIMIT_COOLDOWN_SECONDS, SESSION_CACHE_TTL_SECONDS, AUTO_REFRESH_ACCOUNTS_SECONDS
    global SESSION_EXPIRE_HOURS, multi_account_mgr, http_client, http_client_chat, http_client_auth

    try:
        basic = dict(new_settings.get("basic") or {})
        
        # Debug Log: Check if api_keys received
        logger.info(f"[SETTINGS] Update received basic keys: {list(basic.keys())}")
        
        if "proxy" in basic:
            basic["proxy"] = normalize_proxy_url(str(basic.get("proxy") or ""))
        
        # 显式提取新代理字段，防止被重组字典时遗漏
        basic["proxy_for_auth"] = str(basic.get("proxy_for_auth") or "").strip()
        basic["proxy_for_chat"] = str(basic.get("proxy_for_chat") or "").strip()

        # 确保 api_keys 被正确处理
        if "api_keys" in basic:
             logger.info(f"[SETTINGS] Using new api_keys: {len(basic['api_keys'])}")
        else:
             # Preserve existing
             basic["api_keys"] = [k.model_dump() for k in config.basic.api_keys]
             logger.info(f"[SETTINGS] Preserving api_keys: {len(basic['api_keys'])}")
             
        basic.setdefault("duckmail_base_url", config.basic.duckmail_base_url)
        basic.setdefault("duckmail_api_key", config.basic.duckmail_api_key)
        basic.setdefault("duckmail_verify_ssl", config.basic.duckmail_verify_ssl)
        basic.setdefault("temp_mail_provider", config.basic.temp_mail_provider)
        basic.setdefault("moemail_base_url", config.basic.moemail_base_url)
        basic.setdefault("moemail_api_key", config.basic.moemail_api_key)
        basic.setdefault("moemail_domain", config.basic.moemail_domain)
        basic.setdefault("freemail_base_url", config.basic.freemail_base_url)
        basic.setdefault("freemail_jwt_token", config.basic.freemail_jwt_token)
        basic.setdefault("freemail_verify_ssl", config.basic.freemail_verify_ssl)
        basic.setdefault("freemail_domain", config.basic.freemail_domain)
        basic.setdefault("mail_proxy_enabled", config.basic.mail_proxy_enabled)
        basic.setdefault("gptmail_base_url", config.basic.gptmail_base_url)
        basic.setdefault("gptmail_api_key", config.basic.gptmail_api_key)
        basic.setdefault("gptmail_verify_ssl", config.basic.gptmail_verify_ssl)
        basic.setdefault("browser_engine", config.basic.browser_engine)
        basic.setdefault("browser_headless", config.basic.browser_headless)
        basic.setdefault("refresh_window_hours", config.basic.refresh_window_hours)
        basic.setdefault("register_default_count", config.basic.register_default_count)
        basic.setdefault("register_domain", config.basic.register_domain)
        if not isinstance(basic.get("register_domain"), str):
            basic["register_domain"] = ""
        basic.pop("duckmail_proxy", None)

        outbound_defaults = config.basic.outbound_proxy.model_dump()
        outbound_proxy = dict(basic.get("outbound_proxy") or {})
        for k, v in outbound_defaults.items():
            outbound_proxy.setdefault(k, v)

        outbound_password = outbound_proxy.pop("password", None)
        outbound_proxy.pop("password_enc", None)
        if outbound_password is not None:
            outbound_proxy["password_enc"] = config.basic.outbound_proxy.encrypt_password(
                str(outbound_password or ""), config.security.admin_key
            )
        else:
            outbound_proxy["password_enc"] = outbound_defaults.get("password_enc") or ""

        basic["outbound_proxy"] = outbound_proxy
        new_settings["basic"] = basic

        image_generation = dict(new_settings.get("image_generation") or {})
        output_format = str(image_generation.get("output_format") or config_manager.image_output_format).lower()
        if output_format not in ("base64", "url"):
            output_format = "base64"
        image_generation["output_format"] = output_format
        new_settings["image_generation"] = image_generation

        video_generation = dict(new_settings.get("video_generation") or {})
        video_output_format = str(video_generation.get("output_format") or config_manager.video_output_format).lower()
        if video_output_format not in ("html", "url", "markdown"):
            video_output_format = "html"
        video_generation["output_format"] = video_output_format
        new_settings["video_generation"] = video_generation

        retry = dict(new_settings.get("retry") or {})
        retry.setdefault("auto_refresh_accounts_seconds", config.retry.auto_refresh_accounts_seconds)
        new_settings["retry"] = retry

        # 保存旧配置用于对比
        old_proxy = config.basic.proxy
        old_outbound = config.basic.outbound_proxy.model_dump()
        old_proxy_auth = config.basic.proxy_for_auth
        old_proxy_chat = config.basic.proxy_for_chat
        old_retry_config = {
            "account_failure_threshold": config.retry.account_failure_threshold,
            "rate_limit_cooldown_seconds": config.retry.rate_limit_cooldown_seconds,
            "session_cache_ttl_seconds": config.retry.session_cache_ttl_seconds
        }

        # 保存到 YAML
        config_manager.save_yaml(new_settings)

        # 热更新配置
        config_manager.reload()

        # 更新全局变量（实时生效）
        API_KEY = config.basic.api_key
        _proxy_auth, _no_proxy_auth = parse_proxy_setting(config.basic.proxy_for_auth)
        _proxy_chat, _no_proxy_chat = parse_proxy_setting(config.basic.proxy_for_chat)
        PROXY_FOR_AUTH = _proxy_auth
        PROXY_FOR_CHAT = _proxy_chat
        _NO_PROXY = ",".join(filter(None, {_no_proxy_auth, _no_proxy_chat}))
        if _NO_PROXY:
            os.environ["NO_PROXY"] = _NO_PROXY
        BASE_URL = config.basic.base_url
        LOGO_URL = config.public_display.logo_url
        CHAT_URL = config.public_display.chat_url
        IMAGE_GENERATION_ENABLED = config.image_generation.enabled
        IMAGE_GENERATION_MODELS = config.image_generation.supported_models
        MAX_NEW_SESSION_TRIES = config.retry.max_new_session_tries
        MAX_REQUEST_RETRIES = config.retry.max_request_retries
        MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
        ACCOUNT_FAILURE_THRESHOLD = config.retry.account_failure_threshold
        RATE_LIMIT_COOLDOWN_SECONDS = config.retry.rate_limit_cooldown_seconds
        SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
        AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds
        SESSION_EXPIRE_HOURS = config.session.expire_hours

        # 检查是否需要重建 HTTP 客户端（代理配置发生任何变化）
        proxy_changed = (
            old_proxy != config.basic.proxy or
            old_outbound != config.basic.outbound_proxy.model_dump() or
            old_proxy_auth != config.basic.proxy_for_auth or
            old_proxy_chat != config.basic.proxy_for_chat
        )

        if proxy_changed:
            logger.info(f"[CONFIG] 代理配置已变化，正在重建所有 HTTP 客户端...")
            
            # 关闭旧客户端
            await asyncio.gather(
                http_client.aclose(),
                http_client_chat.aclose(),
                http_client_auth.aclose()
            )

            # 重建客户端
            http_client = _build_http_client(PROXY_FOR_CHAT)
            http_client_chat = _build_http_client(PROXY_FOR_CHAT)
            http_client_auth = _build_http_client(PROXY_FOR_AUTH)

            # 更新所有依赖组件的引用
            multi_account_mgr.update_http_client(http_client)
            if register_service:
                register_service.http_client = http_client
                register_service.http_client_auth = http_client_auth
            if login_service:
                login_service.http_client = http_client
                login_service.http_client_auth = http_client_auth

            logger.info("[CONFIG] HTTP 客户端重建完成")

        # 检查是否需要更新账户管理器配置（重试策略变化）
        retry_changed = (
            old_retry_config["account_failure_threshold"] != ACCOUNT_FAILURE_THRESHOLD or
            old_retry_config["rate_limit_cooldown_seconds"] != RATE_LIMIT_COOLDOWN_SECONDS or
            old_retry_config["session_cache_ttl_seconds"] != SESSION_CACHE_TTL_SECONDS
        )

        if retry_changed:
            logger.info(f"[CONFIG] 重试策略已变化，更新账户管理器配置")
            # 更新所有账户管理器的配置
            multi_account_mgr.cache_ttl = SESSION_CACHE_TTL_SECONDS
            for account_id, account_mgr in multi_account_mgr.accounts.items():
                account_mgr.account_failure_threshold = ACCOUNT_FAILURE_THRESHOLD
                account_mgr.rate_limit_cooldown_seconds = RATE_LIMIT_COOLDOWN_SECONDS

        logger.info(f"[CONFIG] 系统设置已更新并实时生效")
        return {"status": "success", "message": "设置已保存并实时生效！"}
    except Exception as e:
        logger.error(f"[CONFIG] 更新设置失败: {str(e)}")
        raise HTTPException(500, f"更新失败: {str(e)}")

@app.get("/admin/log")
@require_login()
async def admin_get_logs(
    request: Request,
    limit: int = 300,
    level: str = None,
    search: str = None,
    start_time: str = None,
    end_time: str = None
):
    with log_lock:
        logs = list(log_buffer)

    stats_by_level = {}
    error_logs = []
    chat_count = 0
    for log in logs:
        level_name = log.get("level", "INFO")
        stats_by_level[level_name] = stats_by_level.get(level_name, 0) + 1
        if level_name in ["ERROR", "CRITICAL"]:
            error_logs.append(log)
        if "收到请求" in log.get("message", ""):
            chat_count += 1

    if level:
        level = level.upper()
        logs = [log for log in logs if log["level"] == level]
    if search:
        logs = [log for log in logs if search.lower() in log["message"].lower()]
    if start_time:
        logs = [log for log in logs if log["time"] >= start_time]
    if end_time:
        logs = [log for log in logs if log["time"] <= end_time]

    limit = min(limit, log_buffer.maxlen)
    filtered_logs = logs[-limit:]

    return {
        "total": len(filtered_logs),
        "limit": limit,
        "filters": {"level": level, "search": search, "start_time": start_time, "end_time": end_time},
        "logs": filtered_logs,
        "stats": {
            "memory": {"total": len(log_buffer), "by_level": stats_by_level, "capacity": log_buffer.maxlen},
            "errors": {"count": len(error_logs), "recent": error_logs[-10:]},
            "chat_count": chat_count
        }
    }

@app.delete("/admin/log")
@require_login()
async def admin_clear_logs(request: Request, confirm: str = None):
    if confirm != "yes":
        raise HTTPException(400, "需要 confirm=yes 参数确认清空操作")
    with log_lock:
        cleared_count = len(log_buffer)
        log_buffer.clear()
    logger.info("[LOG] 日志已清空")
    return {"status": "success", "message": "已清空内存日志", "cleared_count": cleared_count}

# ---------- Auth endpoints (API) ----------

@app.get("/v1/models")
async def list_models(authorization: str = Header(None)):
    data = []
    now = int(time.time())
    for m in MODEL_MAPPING.keys():
        data.append({"id": m, "object": "model", "created": now, "owned_by": "google", "permission": []})
    data.append({"id": "gemini-imagen", "object": "model", "created": now, "owned_by": "google", "permission": []})
    data.append({"id": "gemini-veo", "object": "model", "created": now, "owned_by": "google", "permission": []})
    return {"object": "list", "data": data}

@app.get("/v1/models/{model_id}")
async def get_model(model_id: str, authorization: str = Header(None)):
    return {"id": model_id, "object": "model"}

# ---------- Auth endpoints (API) ----------

from core.config import ApiKeyMode, ApiKeyConfig

@app.post("/v1/chat/completions")
async def chat(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    # API Key 验证 (返回配置对象)
    key_config = verify_api_key(authorization, config.basic)
    
    # ... (保留原有的chat逻辑)
    return await chat_impl(req, request, authorization, key_config)

# chat实现函数
async def chat_impl(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str],
    key_config: ApiKeyConfig
):
    # 生成请求ID（最优先，用于所有日志追踪）
    request_id = str(uuid.uuid4())[:6]

    start_ts = time.time()
    request.state.first_response_time = None
    
    # 记录原始消息数量（用于统计）
    original_message_count = len(req.messages)
    message_count = original_message_count
    
    # 保存原始消息用于后续瘦身处理
    original_messages_dict = [m.model_dump() for m in req.messages]

    monitor_recorded = False

    async def finalize_result(
        status: str,
        status_code: Optional[int] = None,
        error_detail: Optional[str] = None
    ) -> None:
        nonlocal monitor_recorded
        if monitor_recorded:
            return
        monitor_recorded = True
        duration_s = time.time() - start_ts
        latency_ms = None
        first_response_time = getattr(request.state, "first_response_time", None)
        if first_response_time:
            latency_ms = int((first_response_time - start_ts) * 1000)
        else:
            latency_ms = int(duration_s * 1000)

        uptime_tracker.record_request("api_service", status == "success", latency_ms, status_code)

        entry = build_recent_conversation_entry(
            request_id=request_id,
            model=req.model if req else None,
            message_count=message_count,
            start_ts=start_ts,
            status=status,
            duration_s=duration_s if status == "success" else None,
            error_detail=error_detail,
        )

        async with stats_lock:
            global_stats.setdefault("failure_timestamps", [])
            global_stats.setdefault("rate_limit_timestamps", [])
            global_stats.setdefault("recent_conversations", [])
            if status != "success":
                if status_code == 429:
                    global_stats["rate_limit_timestamps"].append(time.time())
                else:
                    global_stats["failure_timestamps"].append(time.time())
            global_stats["recent_conversations"].append(entry)
            global_stats["recent_conversations"] = global_stats["recent_conversations"][-60:]
            await save_stats(global_stats)

    def classify_error_status(status_code: Optional[int], error: Exception) -> str:
        if status_code == 504:
            return "timeout"
        if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
            return "timeout"
        return "error"


    # 获取客户端IP（用于会话隔离）
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # 记录请求统计
    async with stats_lock:
        timestamp = time.time()
        global_stats["total_requests"] += 1
        global_stats["request_timestamps"].append(timestamp)
        global_stats.setdefault("model_request_timestamps", {})
        global_stats["model_request_timestamps"].setdefault(req.model, []).append(timestamp)
        await save_stats(global_stats)

    # 2. 模型校验

    if req.model not in MODEL_MAPPING and req.model not in VIRTUAL_MODELS:
        logger.error(f"[CHAT] [req_{request_id}] 不支持的模型: {req.model}")
        all_models = list(MODEL_MAPPING.keys()) + list(VIRTUAL_MODELS.keys())
        await finalize_result("error", 404, f"HTTP 404: Model '{req.model}' not found")
        raise HTTPException(
            status_code=404,
            detail=f"Model '{req.model}' not found. Available models: {all_models}"
        )

    # 保存模型信息到 request.state（用于 Uptime 追踪）
    request.state.model = req.model

    # 3. 提取 ChatID（多源优先级检测：请求头 → 请求体 → 消息指纹）
    # 构建请求头字典（小写化）
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    
    # 构建请求体字典（包含可能的额外字段）
    body_dict = {}
    try:
        # 尝试获取原始请求体中的额外字段
        body_dict = dict(req)  # 从 Pydantic model 转换
    except Exception:
        pass
    
    chat_id_for_binding, chat_id_source = extract_chat_id(
        [m.model_dump() for m in req.messages],
        client_ip,
        headers=headers_dict,
        body=body_dict
    )
    logger.info(f"[CHAT] [req_{request_id}] ChatID: {chat_id_for_binding[:8]}... (来源: {chat_id_source})")
    
    # 获取会话绑定管理器
    binding_mgr = get_session_binding_manager()
    
    # ---------------------------------------------------------
    # 5. [新增] Memory 模式管理指令拦截
    # 仅当 api_key 模式为 MEMORY 且用户发送特定指令时触发
    # ---------------------------------------------------------
    if key_config.mode == ApiKeyMode.MEMORY:
        last_user_content = ""
        if req.messages:
            last_msg = req.messages[-1]
            if last_msg.role == "user":
                 # 兼容 content 为 string 或 list (multimodal)
                 if isinstance(last_msg.content, str):
                     last_user_content = last_msg.content.strip()
                 elif isinstance(last_msg.content, list):
                     # 如果是列表，提取第一个文本部分
                     for part in last_msg.content:
                         if isinstance(part, dict) and part.get("type") == "text":
                             last_user_content = part.get("text", "").strip()
                             break

        # 指令处理
        intercept_response_content = None
        if last_user_content == "重置":
            logger.info(f"[COMMAND] [req_{request_id}] 触发指令: 重置 (ChatID: {chat_id_for_binding})")
            await binding_mgr.reset_session_binding(chat_id_for_binding)
            await multi_account_mgr.clear_session_cache(chat_id_for_binding)
            intercept_response_content = "✅ 记忆已重置，当前账号环境保留。"
        
        elif last_user_content == "换号":
            logger.info(f"[COMMAND] [req_{request_id}] 触发指令: 换号 (ChatID: {chat_id_for_binding})")
            await binding_mgr.remove_binding(chat_id_for_binding)
            await multi_account_mgr.clear_session_cache(chat_id_for_binding)
            intercept_response_content = "🔄 账号已切换，正在连接新分身..."

        if intercept_response_content:
            # 构造响应 ID
            resp_id = f"chatcmpl-{uuid.uuid4()}"
            curr_time = int(time.time())
            
            # 记录成功请求 (Uptime)
            await finalize_result("success", 200, None)

            if req.stream:
                async def mock_stream_generator():
                    # 模拟流式输出
                    chunk = {
                        "id": resp_id,
                        "object": "chat.completion.chunk",
                        "created": curr_time,
                        "model": req.model,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": intercept_response_content}, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    
                    finish_chunk = {
                        "id": resp_id,
                        "object": "chat.completion.chunk",
                        "created": curr_time,
                        "model": req.model,
                        "choices": [{"index": 0, "delta":{}, "finish_reason": "stop"}]
                    }
                    yield f"data: {json.dumps(finish_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                
                return StreamingResponse(mock_stream_generator(), media_type="text/event-stream")
            else:
                return {
                    "id": resp_id,
                    "object": "chat.completion",
                    "created": curr_time,
                    "model": req.model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": intercept_response_content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
    
    # 检查是否已有绑定账号
    binding_info = None
    session_cache_key = ""

    if key_config.mode == ApiKeyMode.FAST:
        # Fast 模式：强制不读取绑定，每次请求视为独立，随机轮询
        logger.info(f"[CHAT] [req_{request_id}] 模式: FAST (流浪模式) - 跳过绑定检查，随机选择账号")
        binding_info = None
        # 使用一次性 Cache Key，避免锁竞争和污染缓存
        session_cache_key = f"fast_{request_id}_{uuid.uuid4().hex[:6]}"
    else:
        # Memory 模式：正常读取绑定
        logger.info(f"[CHAT] [req_{request_id}] 模式: MEMORY (深度记忆) - 检查绑定关系")
        binding_info = await binding_mgr.get_binding(chat_id_for_binding)
        # 使用 chat_id_for_binding 作为 Session 缓存 key
        session_cache_key = chat_id_for_binding

    bound_account_id = binding_info.get("account_id") if binding_info else None
    bound_session_id = binding_info.get("session_id") if binding_info else None
    
    # 优化并发：FAST 模式跳过全局锁竞争
    if key_config.mode == ApiKeyMode.FAST:
        # Fast 模式：使用本地一次性锁，避免通过管理器获取全局锁
        # 这里的锁仅用于保持 async with 结构一致性，实际上无竞争
        session_lock = asyncio.Lock()
    else:
        # Memory 模式：正常从管理器获取会话锁（存在全局锁竞争）
        session_lock = await multi_account_mgr.acquire_session_lock(session_cache_key)

    # 4. 在锁的保护下检查缓存和处理Session（保证同一对话的请求串行化）
    async with session_lock:
        cached_session = multi_account_mgr.global_session_cache.get(session_cache_key)

        if cached_session:
            # 使用已绑定的账户和缓存的 Session
            account_id = cached_session["account_id"]
            account_manager = await multi_account_mgr.get_account(account_id, request_id)
            google_session = cached_session["session_id"]
            is_new_conversation = False
            logger.info(f"[CHAT] [{account_id}] [req_{request_id}] 复用Session(内存缓存): {google_session[-12:]}")
        elif bound_account_id:
            # 有持久化绑定但无缓存Session
            try:
                account_manager = await multi_account_mgr.get_account(bound_account_id, request_id)
                
                # 尝试复用持久化的 Session ID
                if bound_session_id:
                    google_session = bound_session_id
                    is_new_conversation = False  # 复用旧会话，视为延续
                    logger.info(f"[CHAT] [{bound_account_id}] [req_{request_id}] 复用Session(持久化): {google_session[-12:]}")
                else:
                    # 无持久化 Session ID，创建新的
                    google_session = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    is_new_conversation = True
                    logger.info(f"[CHAT] [{bound_account_id}] [req_{request_id}] 绑定账号重建Session")
                
                # 更新缓存
                await multi_account_mgr.set_session_cache(
                    session_cache_key,
                    account_manager.config.account_id,
                    google_session
                )
                
                # 更新绑定（确保 Session ID 被持久化）
                if key_config.mode == ApiKeyMode.MEMORY:
                    await binding_mgr.set_binding(chat_id_for_binding, account_manager.config.account_id, google_session)
                
                uptime_tracker.record_request("account_pool", True)
            except Exception as e:
                # 绑定账号不可用，解绑并漂移到新账号
                logger.warning(f"[CHAT] [req_{request_id}] 绑定账号 {bound_account_id} 不可用/Session无效，自动解绑: {e}")
                await binding_mgr.remove_binding(chat_id_for_binding)
                bound_account_id = None  # 触发下面的新账号选择逻辑
                bound_session_id = None
        
        if not cached_session and not bound_account_id:
            # 新对话：轮询选择可用账户，失败时尝试其他账户
            max_account_tries = min(MAX_NEW_SESSION_TRIES, len(multi_account_mgr.accounts))
            last_error = None

            for attempt in range(max_account_tries):
                try:
                    account_manager = await multi_account_mgr.get_account(None, request_id)
                    google_session = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    # 线程安全地绑定账户到此对话
                    await multi_account_mgr.set_session_cache(
                        session_cache_key,
                        account_manager.config.account_id,
                        google_session
                    )
                    # 持久化绑定关系（含 Session ID）
                    if key_config.mode == ApiKeyMode.MEMORY:
                        await binding_mgr.set_binding(chat_id_for_binding, account_manager.config.account_id, google_session)
                    is_new_conversation = True
                    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 新会话创建并绑定账户")
                    # 记录账号池状态（账户可用）
                    uptime_tracker.record_request("account_pool", True)
                    break
                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    # 安全获取账户ID
                    account_id = account_manager.config.account_id if 'account_manager' in locals() and account_manager else 'unknown'
                    logger.error(f"[CHAT] [req_{request_id}] 账户 {account_id} 创建会话失败 (尝试 {attempt + 1}/{max_account_tries}) - {error_type}: {str(e)}")
                    # 记录账号池状态（单个账户失败）
                    status_code = e.status_code if isinstance(e, HTTPException) else None
                    uptime_tracker.record_request("account_pool", False, status_code=status_code)
                    if attempt == max_account_tries - 1:
                        logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用")
                        status = classify_error_status(503, last_error if isinstance(last_error, Exception) else Exception("account_pool_unavailable"))
                        await finalize_result(status, 503, f"All accounts unavailable: {str(last_error)[:100]}")
                        raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")
                    # 继续尝试下一个账户
                    # 记录账号池状态（账户可用）
                    uptime_tracker.record_request("account_pool", True)
                    break
                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    # 安全获取账户ID
                    account_id = account_manager.config.account_id if 'account_manager' in locals() and account_manager else 'unknown'
                    logger.error(f"[CHAT] [req_{request_id}] 账户 {account_id} 创建会话失败 (尝试 {attempt + 1}/{max_account_tries}) - {error_type}: {str(e)}")
                    # 记录账号池状态（单个账户失败）
                    status_code = e.status_code if isinstance(e, HTTPException) else None
                    uptime_tracker.record_request("account_pool", False, status_code=status_code)
                    if attempt == max_account_tries - 1:
                        logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用")
                        status = classify_error_status(503, last_error if isinstance(last_error, Exception) else Exception("account_pool_unavailable"))
                        await finalize_result(status, 503, f"All accounts unavailable: {str(last_error)[:100]}")
                        raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")
                    # 继续尝试下一个账户

    # 消息瘦身：根据是否首次对话决定是否保留 system 提示词
    stripped_messages_dict = strip_to_last_user_message(original_messages_dict, is_first_message=is_new_conversation)
    
    # 重建消息对象（用瘦身后的消息替换原消息）
    if stripped_messages_dict and req.messages:
        req.messages = [type(req.messages[0])(**m) for m in stripped_messages_dict]
        if is_new_conversation:
            system_count = sum(1 for m in stripped_messages_dict if m.get("role") == "system")
            logger.info(f"[CHAT] [req_{request_id}] 消息瘦身: {original_message_count}条 → {len(stripped_messages_dict)}条 (含{system_count}条system提示词)")
        else:
            logger.info(f"[CHAT] [req_{request_id}] 消息瘦身: {original_message_count}条 → {len(stripped_messages_dict)}条")

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
    try:
        last_text, current_images = await parse_last_message(req.messages, http_client, request_id)
    except HTTPException as e:
        status = classify_error_status(e.status_code, e)
        await finalize_result(status, e.status_code, f"HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        status = classify_error_status(None, e)
        await finalize_result(status, 500, f"{type(e).__name__}: {str(e)[:200]}")
        raise

    # 4. 准备文本内容
    # 提取 System Prompt (如果有的的话)
    system_text = ""
    for m in req.messages:
        if m.role == "system":
            system_text += f"{extract_text_from_content(m.content)}\n\n"

    if is_new_conversation:
        # 即使是新会话，如果请求包含历史消息（说明是上下文重置或指纹漂移），
        # 我们必须发送完整的上下文，以便 Google 能够"追上"之前的对话状态。
        if len(req.messages) > 1:
            logger.info(f"[CHAT] [req_{request_id}] 检测到新会话但包含历史消息，正在恢复上下文...")
            text_to_send = build_full_context_text(req.messages)
        else:
            # 新会话且只有一条消息（或只有 System + User）
            text_to_send = system_text + last_text if system_text else last_text
        
        # 标记为重试模式（意为：我们发送的是全量上下文，而非增量）
        is_retry_mode = True
    else:
        # 继续对话：发送 System (如果有) + 当前消息
        # 用户反馈：System 提示词之前被丢弃了，现在强制加上
        text_to_send = (system_text + last_text) if system_text else last_text
        is_retry_mode = False
        # 线程安全地更新时间戳
        await multi_account_mgr.update_session_time(session_cache_key)

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

        while retry_count <= max_retries:
            # ------------------------------------------------------------------
            # 1. 账户切换逻辑 (仅在重试阶段触发)
            # ------------------------------------------------------------------
            if retry_count > 0:
                logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 正在重试 ({retry_count}/{max_retries})")

                # 快速失败：检查是否还有可用账户（避免无效重试）
                available_count = sum(
                    1 for acc in multi_account_mgr.accounts.values()
                    if (acc.should_retry() and
                        not acc.config.is_expired() and
                        not acc.config.disabled and
                        acc.config.account_id not in failed_accounts)
                )

                if available_count == 0:
                    logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用，快速失败")
                    await finalize_result("error", 503, "All accounts unavailable")
                    if req.stream: yield f"data: {json.dumps({'error': {'message': 'All accounts unavailable'}})}\n\n"
                    return

                # 尝试切换账户
                try:
                    max_switch_tries = min(MAX_ACCOUNT_SWITCH_TRIES, available_count)
                    new_account = None

                    for _ in range(max_switch_tries):
                        candidate = await multi_account_mgr.get_account(None, request_id)
                        if candidate.config.account_id not in failed_accounts:
                            new_account = candidate
                            break

                    if not new_account:
                        raise Exception("All available accounts failed to switch")

                    logger.info(f"[CHAT] [req_{request_id}] 切换账户: {account_manager.config.account_id} -> {new_account.config.account_id}")

                    # 创建新 Session
                    new_sess = await create_google_session(new_account, http_client, USER_AGENT, request_id)

                    # 更新缓存绑定
                    await multi_account_mgr.set_session_cache(
                        session_cache_key,
                        new_account.config.account_id,
                        new_sess
                    )

                    # 更新当前上下文状态
                    account_manager = new_account
                    current_retry_mode = True
                    current_file_ids = []  # 清空 ID，强制重新上传

                except Exception as create_err:
                    error_type = type(create_err).__name__
                    logger.error(f"[CHAT] [req_{request_id}] 账户切换失败 ({error_type}): {str(create_err)}")
                    
                    status_code = create_err.status_code if isinstance(create_err, HTTPException) else None
                    uptime_tracker.record_request("account_pool", False, status_code=status_code)
                    
                    status = classify_error_status(status_code, create_err)
                    await finalize_result(status, status_code, f"Account Failover Failed: {str(create_err)[:200]}")
                    if req.stream: yield f"data: {json.dumps({'error': {'message': 'Account Failover Failed'}})}\n\n"
                    return

            # ------------------------------------------------------------------
            # 2. 执行请求逻辑
            # ------------------------------------------------------------------
            try:
                # A. Session 检查与恢复
                cached = multi_account_mgr.global_session_cache.get(session_cache_key)
                if not cached:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 缓存已清理，重建Session")
                    new_sess = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    await multi_account_mgr.set_session_cache(
                        session_cache_key,
                        account_manager.config.account_id,
                        new_sess
                    )
                    current_session = new_sess
                    current_retry_mode = True
                    current_file_ids = []
                else:
                    current_session = cached["session_id"]

                # B. 图片上传 (如果有图片且未上传)
                if current_images and not current_file_ids:
                    for img in current_images:
                        fid = await upload_context_file(current_session, img["mime"], img["data"], account_manager, http_client, USER_AGENT, request_id)
                        current_file_ids.append(fid)

                # C. 准备文本 (重试模式下可能需要发送全文)
                if current_retry_mode:
                    current_text = build_full_context_text(req.messages)

                # D. 发起对话流
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

                # --- 成功路径 ---
                account_manager.is_available = True
                account_manager.error_count = 0
                account_manager.conversation_count += 1
                uptime_tracker.record_request("account_pool", True)

                async with stats_lock:
                    if "account_conversations" not in global_stats:
                        global_stats["account_conversations"] = {}
                    global_stats["account_conversations"][account_manager.config.account_id] = account_manager.conversation_count
                    await save_stats(global_stats)

                await finalize_result("success", 200, None)
                return

            except (httpx.HTTPError, ssl.SSLError, HTTPException, ValueError) as e:
                # --- 失败处理 ---
                is_http_exception = isinstance(e, HTTPException)
                status_code = e.status_code if is_http_exception else None
                error_detail = (
                    f"HTTP {e.status_code}: {e.detail}"
                    if is_http_exception
                    else f"{type(e).__name__}: {str(e)[:200]}"
                )

                # 记录失败
                failed_accounts.add(account_manager.config.account_id)
                uptime_tracker.record_request("account_pool", False, status_code=status_code)

                # 错误处理回调
                quota_type = MODEL_TO_QUOTA_TYPE.get(req.model)
                if is_http_exception:
                    account_manager.handle_http_error(status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id, quota_type)
                else:
                    account_manager.handle_non_http_error("聊天请求", request_id)

                retry_count += 1

                # 检查是否超过最大重试次数
                if retry_count > max_retries:
                    logger.error(f"[CHAT] [req_{request_id}] 已达到最大重试次数 ({max_retries})，请求失败")
                    status = classify_error_status(status_code, e)
                    await finalize_result(status, status_code, error_detail)
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
    seen_file_ids = set()  # 用于去重

    for data in data_list:
        sar = data.get("streamAssistResponse")
        if not sar:
            continue

        # 获取session信息（优先使用最新的）
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
            if file_info and file_info.get("fileId"):
                file_id = file_info["fileId"]
                # 去重：同一个 fileId 只处理一次
                if file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)

                mime_type = file_info.get("mimeType", "image/png")
                logger.debug(f"[PARSE] 解析文件: fileId={file_id}, mimeType={mime_type}")
                file_ids.append({
                    "fileId": file_id,
                    "mimeType": mime_type
                })

    return file_ids, session_name


async def stream_chat_generator(session: str, text_content: str, file_ids: List[str], model_name: str, chat_id: str, created_time: int, account_manager: AccountManager, is_stream: bool = True, request_id: str = "", request: Request = None):
    start_time = time.time()
    full_content = ""
    first_response_time = None

    # 记录发送给API的内容
    text_preview = text_content[:500] + "...(已截断)" if len(text_content) > 500 else text_content
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 发送内容: {text_preview}")
    if file_ids:
        logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 附带文件: {len(file_ids)}个")

    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, USER_AGENT)


    tools_spec = get_tools_spec(model_name)

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "streamAssistRequest": {
            "session": session,
            "query": {"parts": [{"text": text_content}]},
            "filter": "",
            "fileIds": file_ids, # 注入文件 ID
            "answerGenerationMode": "NORMAL",
            "toolsSpec": tools_spec,
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
    json_objects = []  # 收集所有响应对象用于图片解析
    file_ids_info = None  # 保存图片信息

    async with http_client.stream(
        "POST",
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist",
        headers=headers,
        json=body,
    ) as r:
        if r.status_code != 200:
            error_text = await r.aread()
            uptime_tracker.record_request(model_name, False, status_code=r.status_code)
            raise HTTPException(status_code=r.status_code, detail=f"Upstream Error {error_text.decode()}")

        # 使用异步解析器处理 JSON 数组流
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
                        if first_response_time is None:
                            first_response_time = time.time()
                        # 正常内容使用 content 字段
                        full_content += text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": text}, None)
                        yield f"data: {chunk}\n\n"

            # 提取图片信息（在 async with 块内）
            if json_objects:
                file_ids, session_name = parse_images_from_response(json_objects)
                if file_ids and session_name:
                    file_ids_info = (file_ids, session_name)
                    logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 检测到{len(file_ids)}张生成图片")

        except ValueError as e:
            uptime_tracker.record_request(model_name, False)
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] JSON解析失败: {str(e)}")
        except Exception as e:
            error_type = type(e).__name__
            uptime_tracker.record_request(model_name, False)
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 流处理错误 ({error_type}): {str(e)}")
            raise

    # 在 async with 块外处理图片下载（避免占用上游连接）
    if file_ids_info:
        file_ids, session_name = file_ids_info
        try:
            base_url = get_base_url(request) if request else ""
            file_metadata = await get_session_file_metadata(account_manager, session_name, http_client, USER_AGENT, request_id)

            # 并行下载所有图片
            download_tasks = []
            for file_info in file_ids:
                fid = file_info["fileId"]
                mime = file_info["mimeType"]
                meta = file_metadata.get(fid, {})
                # 优先使用 metadata 中的 MIME 类型
                mime = meta.get("mimeType", mime)
                correct_session = meta.get("session") or session_name
                task = download_image_with_jwt(account_manager, correct_session, fid, http_client, USER_AGENT, request_id)
                download_tasks.append((fid, mime, task))

            results = await asyncio.gather(*[task for _, _, task in download_tasks], return_exceptions=True)

            # 处理下载结果
            success_count = 0
            for idx, ((fid, mime, _), result) in enumerate(zip(download_tasks, results), 1):
                if isinstance(result, Exception):
                    logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片{idx}下载失败: {type(result).__name__}: {str(result)[:100]}")
                    # 降级处理：返回错误提示而不是静默失败
                    error_msg = f"\n\n⚠️ 图片 {idx} 下载失败\n\n"
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"
                    continue

                try:
                    markdown = process_media(result, mime, chat_id, fid, base_url, idx, request_id, account_manager.config.account_id)
                    success_count += 1
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                    yield f"data: {chunk}\n\n"
                except Exception as save_error:
                    logger.error(f"[MEDIA] [{account_manager.config.account_id}] [req_{request_id}] 媒体{idx}处理失败: {str(save_error)[:100]}")
                    error_msg = f"\n\n⚠️ 媒体 {idx} 处理失败\n\n"
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"

            logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片处理完成: {success_count}/{len(file_ids)} 成功")

        except Exception as e:
            logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片处理失败: {type(e).__name__}: {str(e)[:100]}")
            # 降级处理：通知用户图片处理失败
            error_msg = f"\n\n⚠️ 图片处理失败: {type(e).__name__}\n\n"
            chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
            yield f"data: {chunk}\n\n"

    if full_content:
        response_preview = full_content[:500] + "...(已截断)" if len(full_content) > 500 else full_content
        logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] AI响应: {response_preview}")

    if first_response_time:
        latency_ms = int((first_response_time - start_time) * 1000)
        uptime_tracker.record_request(model_name, True, latency_ms)
    else:
        # 如果没有首字时间，说明没有任何内容生成
        if not full_content and not file_ids_info:
             uptime_tracker.record_request(model_name, False)
             logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应为空 (无文本且无图片)")
             raise ValueError("Empty response from model")
        uptime_tracker.record_request(model_name, True)

    total_time = time.time() - start_time
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应完成: {total_time:.2f}秒")
    
    if is_stream:
        final_chunk = create_chunk(chat_id, created_time, model_name, {}, "stop")
        yield f"data: {final_chunk}\n\n"
        yield "data: [DONE]\n\n"

# ---------- 公开端点（无需认证） ----------
@app.get("/public/uptime")
async def get_public_uptime(days: int = 90):
    """获取 Uptime 监控数据（JSON格式）"""
    if days < 1 or days > 90:
        days = 90
    return await uptime_tracker.get_uptime_summary(days)


@app.get("/public/stats")
async def get_public_stats():
    """获取公开统计信息"""
    async with stats_lock:
        # 清理1小时前的请求时间戳
        current_time = time.time()
        recent_requests = [
            ts for ts in global_stats["request_timestamps"]
            if current_time - ts < 3600
        ]

        # 计算每分钟请求数
        recent_minute = [
            ts for ts in recent_requests
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

@app.get("/public/display")
async def get_public_display():
    """获取公开展示信息"""
    return {
        "logo_url": LOGO_URL,
        "chat_url": CHAT_URL
    }

@app.get("/public/log")
async def get_public_logs(request: Request, limit: int = 100):
    try:
        # 基于IP的访问统计（24小时内去重）
        client_ip = request.client.host
        current_time = time.time()

        async with stats_lock:
            # 清理24小时前的IP记录
            if "visitor_ips" not in global_stats:
                global_stats["visitor_ips"] = {}
            global_stats["visitor_ips"] = {
                ip: timestamp for ip, timestamp in global_stats["visitor_ips"].items()
                if current_time - timestamp <= 86400
            }

            # 记录新访问（24小时内同一IP只计数一次）
            if client_ip not in global_stats["visitor_ips"]:
                global_stats["visitor_ips"][client_ip] = current_time
                global_stats["total_visitors"] = global_stats.get("total_visitors", 0) + 1

            global_stats.setdefault("recent_conversations", [])
            await save_stats(global_stats)

            stored_logs = list(global_stats.get("recent_conversations", []))

        sanitized_logs = get_sanitized_logs(limit=min(limit, 1000))

        log_map = {log.get("request_id"): log for log in sanitized_logs}
        for log in stored_logs:
            request_id = log.get("request_id")
            if request_id and request_id not in log_map:
                log_map[request_id] = log

        def get_log_ts(item: dict) -> float:
            if "start_ts" in item:
                return float(item["start_ts"])
            try:
                return datetime.strptime(item.get("start_time", ""), "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                return 0.0

        merged_logs = sorted(log_map.values(), key=get_log_ts, reverse=True)[:min(limit, 1000)]
        output_logs = []
        for log in merged_logs:
            if "start_ts" in log:
                log = dict(log)
                log.pop("start_ts", None)
            output_logs.append(log)

        return {
            "total": len(output_logs),
            "logs": output_logs
        }
    except Exception as e:
        logger.error(f"[LOG] 获取公开日志失败: {e}")
        return {"total": 0, "logs": [], "error": str(e)}
    except Exception as e:
        logger.error(f"[LOG] 获取公开日志失败: {e}")
        return {"total": 0, "logs": [], "error": str(e)}

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
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
