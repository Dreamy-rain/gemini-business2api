import json, time, os, asyncio, uuid, ssl, re, yaml, base64
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
from core.database import stats_db

# ---------- 数据目录配置 ----------
DATA_DIR = "./data"
logger_prefix = "[LOCAL]"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 统一的数据文件路径
TASK_HISTORY_MTIME: float = 0.0
IMAGE_DIR = os.path.join(DATA_DIR, "images")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")

# 确保图片和视频目录存在
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# 导入认证模块
from core.auth import verify_api_key
from core.session_auth import is_logged_in, login_user, logout_user, require_login, generate_session_secret

# 导入核心模块
from core.message import (
    get_conversation_key,
    parse_last_message,
    build_full_context_text
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
    RetryPolicy,
    CooldownConfig,
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
from core import storage, account

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
    """加载统计数据（异步）。数据库不可用时使用内存默认值。"""
    data = None
    if storage.is_database_enabled():
        try:
            has_stats = await asyncio.to_thread(storage.has_stats_sync)
            if has_stats:
                data = await asyncio.to_thread(storage.load_stats_sync)
                if not isinstance(data, dict):
                    data = None
        except Exception as e:
            logger.error(f"[STATS] 数据库加载失败: {str(e)[:50]}")

    if data is None:
        data = {
            "total_visitors": 0,
            "total_requests": 0,
            "success_count": 0,
            "failed_count": 0,
            "request_timestamps": [],
            "model_request_timestamps": {},
            "failure_timestamps": [],
            "rate_limit_timestamps": [],
            "visitor_ips": {},
            "account_conversations": {},
            "account_failures": {},
            "recent_conversations": []
        }

    if isinstance(data.get("request_timestamps"), list):
        data["request_timestamps"] = deque(data["request_timestamps"], maxlen=20000)
    if isinstance(data.get("failure_timestamps"), list):
        data["failure_timestamps"] = deque(data["failure_timestamps"], maxlen=10000)
    if isinstance(data.get("rate_limit_timestamps"), list):
        data["rate_limit_timestamps"] = deque(data["rate_limit_timestamps"], maxlen=10000)

    return data

async def save_stats(stats):
    """保存统计数据(异步)。数据库不可用时不落盘。"""
    def convert_deques(obj):
        """递归转换所有 deque 对象为 list"""
        if isinstance(obj, deque):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_deques(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_deques(item) for item in obj]
        return obj

    stats_to_save = convert_deques(stats)

    if storage.is_database_enabled():
        try:
            saved = await asyncio.to_thread(storage.save_stats_sync, stats_to_save)
            if saved:
                return
        except Exception as e:
            logger.error(f"[STATS] 数据库保存失败: {str(e)[:50]}")
    return

# 初始化统计数据（需要在启动时异步加载）
global_stats = {
    "total_visitors": 0,
    "total_requests": 0,
    "success_count": 0,
    "failed_count": 0,
    "request_timestamps": deque(maxlen=20000),
    "model_request_timestamps": {},
    "failure_timestamps": deque(maxlen=10000),
    "rate_limit_timestamps": deque(maxlen=10000),
    "visitor_ips": {},
    "account_conversations": {},
    "account_failures": {},
    "recent_conversations": []
}

# 任务历史记录（内存存储，容器重启后清空）
task_history = deque(maxlen=100)  # 最多保留100条历史记录
task_history_lock = Lock()


def get_beijing_time_str(ts: Optional[float] = None) -> str:
    tz = timezone(timedelta(hours=8))
    current = datetime.fromtimestamp(ts or time.time(), tz=tz)
    return current.strftime("%Y-%m-%d %H:%M:%S")


def save_task_to_history(task_type: str, task_data: dict) -> None:
    """保存任务历史记录（只存储简要信息）"""
    with task_history_lock:
        history_entry = _build_history_entry(task_type, task_data)
        entry_id = history_entry.get("id")
        if entry_id:
            for i in range(len(task_history) - 1, -1, -1):
                if task_history[i].get("id") == entry_id:
                    task_history.remove(task_history[i])
                    break
        task_history.append(history_entry)
        _persist_task_history()
        logger.info(f"[HISTORY] Saved {task_type} task to history: {history_entry['id']}")


def _build_history_entry(task_type: str, task_data: dict, is_live: bool = False) -> dict:
    total_value = task_data.get("count") if task_type == "register" else len(task_data.get("account_ids", []))
    return {
        "id": task_data.get("id", ""),
        "type": task_type,  # "register" or "login"
        "status": task_data.get("status", ""),
        "progress": task_data.get("progress", 0),
        "total": total_value,
        "success_count": task_data.get("success_count", 0),
        "fail_count": task_data.get("fail_count", 0),
        "created_at": task_data.get("created_at", time.time()),
        "finished_at": task_data.get("finished_at"),
        "is_live": is_live,
    }


def _persist_task_history() -> None:
    """持久化任务历史到数据库（仅数据库模式）。"""
    if not storage.is_database_enabled():
        return
    try:
        if not task_history:
            storage.clear_task_history_sync()
            return
        storage.save_task_history_entry_sync(task_history[-1])
    except Exception as exc:
        logger.warning(f"[HISTORY] Persist task history failed: {exc}")


def _load_task_history() -> None:
    """从数据库加载任务历史（仅数据库模式）。"""
    if not storage.is_database_enabled():
        return
    try:
        history = storage.load_task_history_sync(limit=100)
        if not isinstance(history, list):
            return
        with task_history_lock:
            task_history.clear()
            for entry in history:
                if isinstance(entry, dict):
                    task_history.append(entry)
    except Exception as exc:
        logger.warning(f"[HISTORY] Load task history failed: {exc}")


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

_load_task_history()

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
TIMEOUT_SECONDS = 300
API_KEY = config.basic.api_key
ADMIN_KEY = config.security.admin_key
_proxy_auth, _no_proxy_auth = parse_proxy_setting(config.basic.proxy_for_auth)
_proxy_chat, _no_proxy_chat = parse_proxy_setting(config.basic.proxy_for_chat)
PROXY_FOR_AUTH = _proxy_auth
PROXY_FOR_CHAT = _proxy_chat
_NO_PROXY = ",".join(filter(None, {_no_proxy_auth, _no_proxy_chat}))
if _NO_PROXY:
    os.environ["NO_PROXY"] = _NO_PROXY
else:
    os.environ.pop("NO_PROXY", None)
BASE_URL = config.basic.base_url
SESSION_SECRET_KEY = config.security.session_secret_key
SESSION_EXPIRE_HOURS = config.session.expire_hours

# ---------- 公开展示配置 ----------
LOGO_URL = config.public_display.logo_url
CHAT_URL = config.public_display.chat_url

# ---------- 图片生成配置 ----------
IMAGE_GENERATION_ENABLED = config.image_generation.enabled
IMAGE_GENERATION_MODELS = config.image_generation.supported_models

def get_request_quota_type(model_name: str) -> str:
    """根据模型名称返回本次请求的配额类型。"""
    if model_name in MODEL_TO_QUOTA_TYPE:
        return MODEL_TO_QUOTA_TYPE[model_name]
    if IMAGE_GENERATION_ENABLED and model_name in IMAGE_GENERATION_MODELS:
        return "images"
    return "text"

def get_required_quota_types(model_name: str) -> List[str]:
    """所有请求都需要文本配额；图/视频请求还需要对应配额。"""
    required = ["text"]
    request_quota = get_request_quota_type(model_name)
    if request_quota != "text":
        required.append(request_quota)
    return required

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
MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds

def build_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        cooldowns=CooldownConfig(
            text=config.retry.text_rate_limit_cooldown_seconds,
            images=config.retry.images_rate_limit_cooldown_seconds,
            videos=config.retry.videos_rate_limit_cooldown_seconds,
        ),
    )

RETRY_POLICY = build_retry_policy()

# ---------- 模型映射配置 ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-3-pro-preview": "gemini-3-pro-preview"
}

# ---------- HTTP 客户端 ----------
# 对话操作客户端（用于JWT获取、创建会话、发送消息）
http_client = httpx.AsyncClient(
    proxy=(PROXY_FOR_CHAT or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

# 对话流式客户端（用于流式响应）
http_client_chat = httpx.AsyncClient(
    proxy=(PROXY_FOR_CHAT or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

# 账户操作客户端（用于注册/登录/刷新）
http_client_auth = httpx.AsyncClient(
    proxy=(PROXY_FOR_AUTH or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

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
    RETRY_POLICY,
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
        RETRY_POLICY,
        SESSION_CACHE_TTL_SECONDS,
        _get_global_stats,
        _set_multi_account_mgr,
    )
    login_service = LoginService(
        multi_account_mgr,
        http_client_auth,
        USER_AGENT,
        RETRY_POLICY,
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
logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR}")
logger.info(f"[SYSTEM] 视频静态服务已启用: /videos/ -> {VIDEO_DIR}")

# ---------- 后台任务启动 ----------

# 全局变量：记录上次检测到的账号更新时间（用于自动刷新检测）
_last_known_accounts_version: float | None = None


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
                multi_account_mgr = _reload_accounts(
                    multi_account_mgr,
                    http_client,
                    USER_AGENT,
                    RETRY_POLICY,
                    SESSION_CACHE_TTL_SECONDS,
                    global_stats
                )

                _last_known_accounts_version = db_version
                logger.info(f"[AUTO-REFRESH] 账号刷新完成，当前账号数: {len(multi_account_mgr.accounts)}")

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

    # 加载统计数据
    global_stats = await load_stats()
    global_stats.setdefault("request_timestamps", [])
    global_stats.setdefault("model_request_timestamps", {})
    global_stats.setdefault("failure_timestamps", [])
    global_stats.setdefault("rate_limit_timestamps", [])
    global_stats.setdefault("recent_conversations", [])
    global_stats.setdefault("success_count", 0)
    global_stats.setdefault("failed_count", 0)
    global_stats.setdefault("account_conversations", {})
    global_stats.setdefault("account_failures", {})
    uptime_tracker.configure_storage(os.path.join(DATA_DIR, "uptime.json"))
    uptime_tracker.load_heartbeats()
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        account_mgr.conversation_count = global_stats["account_conversations"].get(account_id, 0)
        account_mgr.failure_count = global_stats["account_failures"].get(account_id, 0)
    logger.info("[SYSTEM] 已恢复账户成功/失败统计")
    logger.info(f"[SYSTEM] 统计数据已加载: {global_stats['total_requests']} 次请求, {global_stats['total_visitors']} 位访客")

    # 启动缓存清理任务
    asyncio.create_task(multi_account_mgr.start_background_cleanup())
    logger.info("[SYSTEM] 后台缓存清理任务已启动（间隔: 5分钟）")

    # 启动数据库清理任务
    asyncio.create_task(cleanup_database_task())
    logger.info("[SYSTEM] 数据库清理任务已启动（每天清理一次，保留30天数据）")

    # 启动自动刷新账号任务（仅数据库模式有效）
    if os.environ.get("ACCOUNTS_CONFIG"):
        logger.info("[SYSTEM] 自动刷新账号已跳过（使用 ACCOUNTS_CONFIG）")
    elif storage.is_database_enabled() and AUTO_REFRESH_ACCOUNTS_SECONDS > 0:
        asyncio.create_task(auto_refresh_accounts_task())
        logger.info(f"[SYSTEM] 自动刷新账号任务已启动（间隔: {AUTO_REFRESH_ACCOUNTS_SECONDS}秒）")
    elif storage.is_database_enabled():
        logger.info("[SYSTEM] 自动刷新账号功能已禁用（配置为0）")

    # 启动自动登录刷新轮询（始终启动，但默认禁用）
    if login_service:
        try:
            asyncio.create_task(login_service.start_polling())
            logger.info("[SYSTEM] 账户刷新轮询服务已启动（默认禁用，可在设置中启用）")
        except Exception as e:
            logger.error(f"[SYSTEM] 启动登录服务失败: {e}")
    else:
        logger.info("[SYSTEM] 自动登录刷新未启用或依赖不可用")

    # 启动冷却状态定期保存任务（每5分钟保存一次）
    if storage.is_database_enabled():
        asyncio.create_task(save_cooldown_states_task())
        logger.info("[SYSTEM] 冷却状态定期保存任务已启动（间隔: 5分钟）")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时保存冷却状态"""
    if storage.is_database_enabled():
        try:
            success_count = await account.save_all_cooldown_states(multi_account_mgr)
            logger.info(f"[SYSTEM] 应用关闭，已保存 {success_count}/{len(multi_account_mgr.accounts)} 个账户的冷却状态")
        except Exception as e:
            logger.error(f"[SYSTEM] 关闭时保存冷却状态失败: {e}")


async def save_cooldown_states_task():
    """定期保存所有账户的冷却状态到数据库"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟执行一次
            success_count = await account.save_all_cooldown_states(multi_account_mgr)
            logger.debug(f"[COOLDOWN] 定期保存: {success_count}/{len(multi_account_mgr.accounts)} 个账户")
        except Exception as e:
            logger.error(f"[COOLDOWN] 定期保存失败: {e}")


async def cleanup_database_task():
    """定时清理数据库过期数据"""
    while True:
        try:
            await asyncio.sleep(24 * 3600)  # 每天执行一次
            deleted_count = await stats_db.cleanup_old_data(days=30)
            logger.info(f"[DATABASE] 清理了 {deleted_count} 条过期数据（保留30天）")
        except Exception as e:
            logger.error(f"[DATABASE] 清理数据失败: {e}")

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

class ImageGenerationRequest(BaseModel):
    """OpenAI /v1/images/generations 请求格式"""
    prompt: str
    model: str = "gemini-imagen"
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"
    response_format: Optional[str] = None  # "url" or "b64_json"，None 表示使用系统配置
    quality: Optional[str] = "standard"  # "standard" or "hd"
    style: Optional[str] = "natural"  # "natural" or "vivid"

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


@app.post("/logout")
@require_login(redirect_to_login=False)
async def admin_logout(request: Request):
    """Admin logout (API)"""
    logout_user(request)
    logger.info("[AUTH] Admin logout")
    return {"success": True}



@app.get("/admin/stats")
@require_login()
async def admin_stats(request: Request, time_range: str = "24h"):
    """
    获取统计数据

    Args:
        time_range: 时间范围 "24h", "7d", "30d"
    """
    now = time.time()

    active_accounts = 0
    failed_accounts = 0
    rate_limited_accounts = 0
    idle_accounts = 0

    for account_manager in multi_account_mgr.accounts.values():
        config = account_manager.config
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()

        # 判断账户状态
        is_expired = config.is_expired()
        is_manual_disabled = config.disabled
        is_rate_limited = cooldown_seconds > 0 and cooldown_reason and "冷却" in cooldown_reason
        is_failed = is_expired
        is_active = (not is_failed) and (not is_manual_disabled) and (not is_rate_limited)

        if is_rate_limited:
            rate_limited_accounts += 1
        elif is_failed:
            failed_accounts += 1
        elif is_active:
            active_accounts += 1
        else:
            idle_accounts += 1

    total_accounts = len(multi_account_mgr.accounts)

    # 从数据库获取统计数据
    trend_data = await stats_db.get_stats_by_time_range(time_range)
    success_count, failed_count = await stats_db.get_total_counts()

    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "failed_accounts": failed_accounts,
        "rate_limited_accounts": rate_limited_accounts,
        "idle_accounts": idle_accounts,
        "success_count": success_count,
        "failed_count": failed_count,
        "trend": trend_data
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
            "failure_count": account_manager.failure_count,
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
            RETRY_POLICY,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": "配置已更新", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 更新配置失败: {str(e)}")
        raise HTTPException(500, f"更新失败: {str(e)}")

@app.post("/admin/register/start")
@require_login()
async def admin_start_register(request: Request, count: Optional[int] = Body(default=None), domain: Optional[str] = Body(default=None), mail_provider: Optional[str] = Body(default=None)):
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

@app.delete("/admin/accounts/{account_id}")
@require_login()
async def admin_delete_account(request: Request, account_id: str):
    """删除单个账户"""
    global multi_account_mgr
    try:
        multi_account_mgr = _delete_account(
            account_id, multi_account_mgr, http_client, USER_AGENT,
            RETRY_POLICY,
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
            RETRY_POLICY,
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
            account_id, True, multi_account_mgr
        )

        # 立即保存当前状态到数据库，防止后台任务覆盖
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            await account.save_account_cooldown_state(account_id, account_mgr)

        return {"status": "success", "message": f"账户 {account_id} 已禁用", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 禁用账户失败: {str(e)}")
        raise HTTPException(500, f"禁用失败: {str(e)}")

@app.put("/admin/accounts/{account_id}/enable")
@require_login()
async def admin_enable_account(request: Request, account_id: str):
    """启用账户（同时重置冷却状态）"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_account_disabled_status(
            account_id, False, multi_account_mgr
        )

        # 重置运行时冷却状态（允许手动恢复冷却中的账户）
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            account_mgr.quota_cooldowns = {}
            logger.info(f"[CONFIG] 账户 {account_id} 冷却状态已重置")

            # 立即保存清空的冷却状态到数据库，防止后台任务覆盖
            await account.save_account_cooldown_state(account_id, account_mgr)

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
            account_mgr.quota_cooldowns = {}
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
    return {
        "basic": {
            "api_key": config.basic.api_key,
            "base_url": config.basic.base_url,
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
            "gptmail_domain": config.basic.gptmail_domain,
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
            "max_account_switch_tries": config.retry.max_account_switch_tries,
            "text_rate_limit_cooldown_seconds": config.retry.text_rate_limit_cooldown_seconds,
            "images_rate_limit_cooldown_seconds": config.retry.images_rate_limit_cooldown_seconds,
            "videos_rate_limit_cooldown_seconds": config.retry.videos_rate_limit_cooldown_seconds,
            "session_cache_ttl_seconds": config.retry.session_cache_ttl_seconds,
            "auto_refresh_accounts_seconds": config.retry.auto_refresh_accounts_seconds,
            "scheduled_refresh_enabled": config.retry.scheduled_refresh_enabled,
            "scheduled_refresh_interval_minutes": config.retry.scheduled_refresh_interval_minutes
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
    global MAX_ACCOUNT_SWITCH_TRIES
    global RETRY_POLICY
    global SESSION_CACHE_TTL_SECONDS, AUTO_REFRESH_ACCOUNTS_SECONDS
    global SESSION_EXPIRE_HOURS, multi_account_mgr, http_client, http_client_chat, http_client_auth

    try:
        basic = dict(new_settings.get("basic") or {})
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
        basic.setdefault("gptmail_domain", config.basic.gptmail_domain)
        basic.setdefault("browser_engine", config.basic.browser_engine)
        basic.setdefault("browser_headless", config.basic.browser_headless)
        basic.setdefault("refresh_window_hours", config.basic.refresh_window_hours)
        basic.setdefault("register_default_count", config.basic.register_default_count)
        basic.setdefault("register_domain", config.basic.register_domain)
        if not isinstance(basic.get("register_domain"), str):
            basic["register_domain"] = ""
        basic.pop("duckmail_proxy", None)
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
        retry.setdefault("scheduled_refresh_enabled", config.retry.scheduled_refresh_enabled)
        retry.setdefault("scheduled_refresh_interval_minutes", config.retry.scheduled_refresh_interval_minutes)
        retry.setdefault("text_rate_limit_cooldown_seconds", config.retry.text_rate_limit_cooldown_seconds)
        retry.setdefault("images_rate_limit_cooldown_seconds", config.retry.images_rate_limit_cooldown_seconds)
        retry.setdefault("videos_rate_limit_cooldown_seconds", config.retry.videos_rate_limit_cooldown_seconds)
        new_settings["retry"] = retry

        # 保存旧配置用于对比
        old_proxy_for_auth = PROXY_FOR_AUTH
        old_proxy_for_chat = PROXY_FOR_CHAT
        old_retry_config = {
            "text_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.text,
            "images_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.images,
            "videos_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.videos,
            "session_cache_ttl_seconds": SESSION_CACHE_TTL_SECONDS
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
        else:
            os.environ.pop("NO_PROXY", None)
        BASE_URL = config.basic.base_url
        LOGO_URL = config.public_display.logo_url
        CHAT_URL = config.public_display.chat_url
        IMAGE_GENERATION_ENABLED = config.image_generation.enabled
        IMAGE_GENERATION_MODELS = config.image_generation.supported_models
        MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
        RETRY_POLICY = build_retry_policy()
        SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
        AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds
        SESSION_EXPIRE_HOURS = config.session.expire_hours

        # 检查是否需要重建 HTTP 客户端（代理变化）
        if old_proxy_for_auth != PROXY_FOR_AUTH or old_proxy_for_chat != PROXY_FOR_CHAT:
            logger.info(f"[CONFIG] Proxy configuration changed, rebuilding HTTP clients")
            await http_client.aclose()
            await http_client_chat.aclose()
            await http_client_auth.aclose()

            # 重新创建对话客户端
            http_client = httpx.AsyncClient(
                proxy=(PROXY_FOR_CHAT or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # 重新创建对话流式客户端
            http_client_chat = httpx.AsyncClient(
                proxy=(PROXY_FOR_CHAT or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # 重新创建账户操作客户端
            http_client_auth = httpx.AsyncClient(
                proxy=(PROXY_FOR_AUTH or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # 打印新的代理配置
            logger.info(f"[PROXY] Account operations (register/login/refresh): {PROXY_FOR_AUTH if PROXY_FOR_AUTH else 'disabled'}")
            logger.info(f"[PROXY] Chat operations (JWT/session/messages): {PROXY_FOR_CHAT if PROXY_FOR_CHAT else 'disabled'}")

            # 更新所有账户的 http_client 引用（对话用）
            multi_account_mgr.update_http_client(http_client)

            # 更新注册/登录服务的 http_client 引用（账户操作用）
            if register_service:
                register_service.http_client = http_client_auth
            if login_service:
                login_service.http_client = http_client_auth

        # 检查是否需要更新账户管理器配置（重试策略变化）
        retry_changed = (
            old_retry_config["text_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.text or
            old_retry_config["images_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.images or
            old_retry_config["videos_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.videos or
            old_retry_config["session_cache_ttl_seconds"] != SESSION_CACHE_TTL_SECONDS
        )

        if retry_changed:
            logger.info(f"[CONFIG] 重试策略已变化，更新账户管理器配置")
            # 更新所有账户管理器的配置
            multi_account_mgr.cache_ttl = SESSION_CACHE_TTL_SECONDS
            for account_id, account_mgr in multi_account_mgr.accounts.items():
                account_mgr.apply_retry_policy(RETRY_POLICY)
            if register_service:
                register_service.retry_policy = RETRY_POLICY
            if login_service:
                login_service.retry_policy = RETRY_POLICY

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

@app.get("/admin/task-history")
@require_login()
async def admin_get_task_history(request: Request, limit: int = 100):
    """获取任务历史记录"""
    _load_task_history()
    with task_history_lock:
        history = list(task_history)

    live_entries = []
    try:
        if register_service:
            current_register = register_service.get_current_task()
            if current_register and current_register.status in ("running", "pending"):
                live_entries.append(_build_history_entry("register", current_register.to_dict(), is_live=True))
        if login_service:
            current_login = login_service.get_current_task()
            if current_login and current_login.status in ("running", "pending"):
                live_entries.append(_build_history_entry("login", current_login.to_dict(), is_live=True))
    except Exception as exc:
        logger.warning(f"[HISTORY] build live entries failed: {exc}")

    merged = {}
    for entry in live_entries + history:
        entry_id = entry.get("id") or str(uuid.uuid4())
        if entry_id not in merged:
            merged[entry_id] = entry

    # 按创建时间倒序排序
    history = list(merged.values())
    history.sort(key=lambda x: x.get("created_at", 0), reverse=True)

    # 限制返回数量
    limit = min(limit, 100)
    return {
        "total": len(history),
        "limit": limit,
        "history": history[:limit]
    }

@app.delete("/admin/task-history")
@require_login()
async def admin_clear_task_history(request: Request, confirm: str = None):
    """清空任务历史记录"""
    if confirm != "yes":
        raise HTTPException(400, "需要 confirm=yes 参数确认清空操作")
    with task_history_lock:
        cleared_count = len(task_history)
        task_history.clear()
        _persist_task_history()
    logger.info("[HISTORY] 任务历史已清空")
    return {"status": "success", "message": "已清空任务历史", "cleared_count": cleared_count}

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

@app.post("/v1/chat/completions")
async def chat(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    # API Key 验证
    verify_api_key(API_KEY, authorization)
    # ... (保留原有的chat逻辑)
    return await chat_impl(req, request, authorization)

# chat实现函数
async def chat_impl(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str]
):
    # 生成请求ID（最优先，用于所有日志追踪）
    request_id = str(uuid.uuid4())[:6]

    start_ts = time.time()
    request.state.first_response_time = None
    message_count = len(req.messages)

    monitor_recorded = False
    account_manager: Optional[AccountManager] = None

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
            global_stats.setdefault("success_count", 0)
            global_stats.setdefault("failed_count", 0)
            global_stats.setdefault("account_conversations", {})
            global_stats.setdefault("account_failures", {})
            global_stats.setdefault("response_times", deque(maxlen=10000))

            # 记录响应时间（只记录成功的请求）
            if status == "success" and latency_ms is not None:
                # 记录首响时间和完成时间，按模型分类
                ttfb_ms = int((first_response_time - start_ts) * 1000) if first_response_time else latency_ms
                total_ms = int((time.time() - start_ts) * 1000)
                model_name = req.model if req else "unknown"

                global_stats["response_times"].append({
                    "timestamp": time.time(),
                    "ttfb_ms": ttfb_ms,  # 首响时间
                    "total_ms": total_ms,  # 完成时间
                    "model": model_name  # 模型名称
                })

                # 写入数据库
                asyncio.create_task(stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=ttfb_ms,
                    total_ms=total_ms,
                    status=status,
                    status_code=status_code
                ))
            elif status != "success":
                # 失败请求也记录到数据库
                model_name = req.model if req else "unknown"
                asyncio.create_task(stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=None,
                    total_ms=None,
                    status=status,
                    status_code=status_code
                ))

            if status != "success":
                global_stats["failed_count"] += 1
                global_stats["failure_timestamps"].append(time.time())
                if status_code == 429:
                    global_stats["rate_limit_timestamps"].append(time.time())
                failure_account_id = None
                if account_manager:
                    account_manager.failure_count += 1
                    failure_account_id = account_manager.config.account_id
                    global_stats["account_failures"][failure_account_id] = account_manager.failure_count
                else:
                    failure_account_id = getattr(request.state, "last_account_id", None)
                    if failure_account_id and failure_account_id in multi_account_mgr.accounts:
                        account_mgr = multi_account_mgr.accounts[failure_account_id]
                        account_mgr.failure_count += 1
                        global_stats["account_failures"][failure_account_id] = account_mgr.failure_count
                    elif failure_account_id:
                        global_stats["account_failures"][failure_account_id] = (
                            global_stats["account_failures"].get(failure_account_id, 0) + 1
                        )
            else:
                global_stats["success_count"] += 1
                if account_manager:
                    global_stats["account_conversations"][account_manager.config.account_id] = account_manager.conversation_count
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

    required_quota_types = get_required_quota_types(req.model)

    # 3. 生成会话指纹，获取Session锁（防止同一对话的并发请求冲突）
    conv_key = get_conversation_key([m.model_dump() for m in req.messages], client_ip)
    session_lock = await multi_account_mgr.acquire_session_lock(conv_key)

    # 4. 在锁的保护下检查缓存和处理Session（保证同一对话的请求串行化）
    async with session_lock:
        cached_session = multi_account_mgr.global_session_cache.get(conv_key)

        if cached_session:
            # 使用已绑定的账户
            account_id = cached_session["account_id"]
            try:
                account_manager = await multi_account_mgr.get_account(account_id, request_id, required_quota_types)
                google_session = cached_session["session_id"]
                is_new_conversation = False
                request.state.last_account_id = account_manager.config.account_id
                logger.info(f"[CHAT] [{account_id}] [req_{request_id}] 继续会话: {google_session[-12:]}")
            except HTTPException as e:
                logger.warning(
                    f"[CHAT] [req_{request_id}] 缓存会话账户不可用，切换新账户: {account_id} ({str(e.detail)})"
                )
                multi_account_mgr.global_session_cache.pop(conv_key, None)
                cached_session = None

        if not cached_session:
            # 新对话：尝试创建会话（遇到错误就切换账户）
            available_accounts = multi_account_mgr.get_available_accounts(required_quota_types)
            max_retries = min(MAX_ACCOUNT_SWITCH_TRIES, len(available_accounts))
            last_error = None

            for retry_idx in range(max_retries):
                try:
                    account_manager = await multi_account_mgr.get_account(None, request_id, required_quota_types)
                    google_session = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    # 线程安全地绑定账户到此对话
                    await multi_account_mgr.set_session_cache(
                        conv_key,
                        account_manager.config.account_id,
                        google_session
                    )
                    is_new_conversation = True
                    request.state.last_account_id = account_manager.config.account_id
                    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 新会话创建并绑定账户")
                    # 记录账号池状态（账户可用）
                    uptime_tracker.record_request("account_pool", True)
                    break
                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    # 安全获取账户ID
                    account_id = account_manager.config.account_id if 'account_manager' in locals() and account_manager else 'unknown'
                    logger.error(f"[CHAT] [req_{request_id}] 账户 {account_id} 创建会话失败 (尝试 {retry_idx + 1}/{max_retries}) - {error_type}: {str(e)}")
                    # 记录账号池状态（单个账户失败）
                    status_code = e.status_code if isinstance(e, HTTPException) else None
                    uptime_tracker.record_request("account_pool", False, status_code=status_code)

                    # 注意：会话创建失败不触发冷却，直接切换到下一个账户重试
                    # 网络抖动、超时等临时问题不应标记配额冷却

                    if retry_idx == max_retries - 1:
                        logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用")
                        status = classify_error_status(503, last_error if isinstance(last_error, Exception) else Exception("account_pool_unavailable"))
                        await finalize_result(status, 503, f"All accounts unavailable: {str(last_error)[:100]}")
                        raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")
                    # 继续尝试下一个账户

    # 确保 account_manager 已成功获取
    if account_manager is None:
        logger.error(f"[CHAT] [req_{request_id}] 无可用账户")
        await finalize_result("error", 503, "No available accounts")
        raise HTTPException(503, "No available accounts")

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

        # 单层重试循环：遇到错误就切换账户
        available_accounts = multi_account_mgr.get_available_accounts(required_quota_types)
        max_retries = min(MAX_ACCOUNT_SWITCH_TRIES, len(available_accounts))

        current_text = text_to_send
        current_retry_mode = is_retry_mode
        current_file_ids = []

        for retry_idx in range(max_retries):
            try:
                # 获取或创建 Session
                cached = multi_account_mgr.global_session_cache.get(conv_key)
                if not cached:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 缓存已清理，重建Session")
                    new_sess = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
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

                # 上传图片（如果需要）
                if current_images and not current_file_ids:
                    for img in current_images:
                        fid = await upload_context_file(current_session, img["mime"], img["data"], account_manager, http_client, USER_AGENT, request_id)
                        current_file_ids.append(fid)

                # 准备文本（重试模式下发全文）
                if current_retry_mode:
                    current_text = build_full_context_text(req.messages)

                # 发起对话
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

                if getattr(request.state, "first_response_time", None) is None:
                    # 空响应应该触发重试逻辑
                    raise HTTPException(status_code=502, detail="Empty response from upstream")

                # 请求成功（conversation_count 已在生成器内统计）
                uptime_tracker.record_request("account_pool", True)
                await finalize_result("success", 200, None)
                break

            except (httpx.HTTPError, ssl.SSLError, HTTPException) as e:
                # 提取错误信息
                is_http_exception = isinstance(e, HTTPException)
                status_code = e.status_code if is_http_exception else None
                error_detail = (
                    f"HTTP {e.status_code}: {e.detail}"
                    if is_http_exception
                    else f"{type(e).__name__}: {str(e)[:200]}"
                )

                # 记录账号池状态（请求失败）
                uptime_tracker.record_request("account_pool", False, status_code=status_code)

                # 判断请求类型以传递 quota_type
                quota_type = get_request_quota_type(req.model)

                # 使用统一的错误处理入口
                # 注意：502 空响应错误不触发冷却，只切换账户重试
                if is_http_exception:
                    if status_code == 502:
                        logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 上游 502 错误，切换账户重试（不触发冷却）")
                    else:
                        account_manager.handle_http_error(status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id, quota_type)
                else:
                    account_manager.handle_non_http_error("聊天请求", request_id, quota_type)

                # 检查是否还能继续重试
                if retry_idx < max_retries - 1:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 切换账户重试 ({retry_idx + 1}/{max_retries})")

                    # 尝试切换到其他账户
                    try:
                        new_account = await multi_account_mgr.get_account(None, request_id, required_quota_types)
                        logger.info(f"[CHAT] [req_{request_id}] 切换账户: {account_manager.config.account_id} -> {new_account.config.account_id}")

                        # 创建新 Session
                        new_sess = await create_google_session(new_account, http_client, USER_AGENT, request_id)

                        # 更新缓存绑定到新账户
                        await multi_account_mgr.set_session_cache(
                            conv_key,
                            new_account.config.account_id,
                            new_sess
                        )

                        # 更新账户管理器
                        account_manager = new_account
                        request.state.last_account_id = account_manager.config.account_id

                        # 设置重试模式（发送完整上下文）
                        current_retry_mode = True
                        current_file_ids = []  # 清空 ID，强制重新上传到新 Session

                    except Exception as create_err:
                        error_type = type(create_err).__name__
                        logger.error(f"[CHAT] [req_{request_id}] 账户切换失败 ({error_type}): {str(create_err)}")
                        # 记录账号池状态（账户切换失败）
                        status_code = create_err.status_code if isinstance(create_err, HTTPException) else None
                        uptime_tracker.record_request("account_pool", False, status_code=status_code)

                        status = classify_error_status(status_code, create_err)
                        await finalize_result(status, status_code, f"Account Failover Failed: {str(create_err)[:200]}")
                        if req.stream: yield f"data: {json.dumps({'error': {'message': 'Account Failover Failed'}})}\n\n"
                        return
                else:
                    # 已达到最大重试次数
                    logger.error(f"[CHAT] [req_{request_id}] 已达到最大重试次数 ({max_retries})，请求失败")
                    status = classify_error_status(status_code, e)
                    await finalize_result(status, status_code, error_detail)
                    if req.stream: yield f"data: {json.dumps({'error': {'message': f'Max retries ({max_retries}) exceeded: {error_detail}'}})}\n\n"
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

# ---------- 图片生成 API (OpenAI 兼容) ----------
@app.post("/v1/images/generations")
async def generate_images(
    req: ImageGenerationRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """OpenAI 兼容的图片生成接口

    将 /v1/images/generations 请求转换为内部格式处理，
    然后将响应转换回 OpenAI 图片生成格式
    """
    # API Key 验证
    verify_api_key(API_KEY, authorization)

    # 生成请求ID
    request_id = str(uuid.uuid4())[:6]

    # 转换为 ChatRequest 格式
    chat_req = ChatRequest(
        model=req.model,
        messages=[
            Message(role="user", content=req.prompt)
        ],
        stream=False  # 图片生成不支持流式
    )

    logger.info(f"[IMAGE-GEN] [req_{request_id}] 收到图片生成请求: model={req.model}, prompt={req.prompt[:100]}")

    try:
        # 调用 chat_impl 获取响应
        chat_response = await chat_impl(chat_req, request, authorization)

        # 从响应中提取图片
        message_content = chat_response["choices"][0]["message"]["content"]

        # 解析 markdown 中的图片
        import re
        b64_pattern = r'!\[.*?\]\(data:([^;]+);base64,([^\)]+)\)'
        b64_matches = re.findall(b64_pattern, message_content)
        url_pattern = r'!\[.*?\]\((https?://[^\)]+)\)'
        url_matches = re.findall(url_pattern, message_content)

        # 确定响应格式：始终使用系统配置
        system_format = config_manager.image_output_format
        response_format = "b64_json" if system_format == "base64" else "url"

        logger.info(f"[IMAGE-GEN] [req_{request_id}] 使用系统配置: {system_format} -> {response_format}")

        # 构建 OpenAI 格式的响应
        created_time = int(time.time())
        data_list = []

        if response_format == "b64_json":
            # 返回 base64 格式
            for mime, b64_data in b64_matches[:req.n]:
                data_list.append({"b64_json": b64_data, "revised_prompt": req.prompt})

            # 如果没有 base64 但有 URL，下载并转换
            if not data_list and url_matches:
                for url in url_matches[:req.n]:
                    try:
                        resp = await http_client.get(url)
                        if resp.status_code == 200:
                            b64_data = base64.b64encode(resp.content).decode()
                            data_list.append({"b64_json": b64_data, "revised_prompt": req.prompt})
                    except Exception as e:
                        logger.error(f"[IMAGE-GEN] [req_{request_id}] 下载图片失败: {url}, {str(e)}")
        else:
            # 返回 URL 格式
            for url in url_matches[:req.n]:
                data_list.append({"url": url, "revised_prompt": req.prompt})

            # 如果没有 URL 但有 base64，保存并生成 URL
            if not data_list and b64_matches:
                base_url = get_base_url(request)
                chat_id = f"img-{uuid.uuid4()}"
                for idx, (mime, b64_data) in enumerate(b64_matches[:req.n], 1):
                    try:
                        img_data = base64.b64decode(b64_data)
                        file_id = f"gen-{uuid.uuid4()}"
                        url = save_image_to_hf(img_data, chat_id, file_id, mime, base_url, IMAGE_DIR)
                        data_list.append({"url": url, "revised_prompt": req.prompt})
                    except Exception as e:
                        logger.error(f"[IMAGE-GEN] [req_{request_id}] 保存图片失败: {str(e)}")

        logger.info(f"[IMAGE-GEN] [req_{request_id}] 图片生成完成: {len(data_list)}张")

        return {"created": created_time, "data": data_list}

    except Exception as e:
        logger.error(f"[IMAGE-GEN] [req_{request_id}] 图片生成失败: {type(e).__name__}: {str(e)}")
        raise

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
        timeout=300.0,
    ) as r:
        if r.status_code != 200:
            error_text = await r.aread()
            uptime_tracker.record_request(model_name, False, status_code=r.status_code)
            raise HTTPException(status_code=r.status_code, detail=f"Upstream Error {error_text.decode()}")

        # 使用异步解析器处理 JSON 数组流
        try:
            response_count = 0
            async for json_obj in parse_json_array_stream_async(r.aiter_lines()):
                response_count += 1
                json_objects.append(json_obj)  # 收集响应

                # 记录原始响应结构（用于调试空响应）
                logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 收到响应#{response_count}: {json.dumps(json_obj, ensure_ascii=False)[:1000]}")

                # 检查是否有错误或政策违规信息
                if "error" in json_obj:
                    error_info = json_obj.get("error", {})
                    error_code = error_info.get("code", 0)
                    error_message = error_info.get("message", "")
                    logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 上游返回错误: {json.dumps(error_info, ensure_ascii=False)}")

                    # 上游 429 配额耗尽：立即标记冷却并抛异常，触发切换账户
                    if error_code == 429 or "RESOURCE_EXHAUSTED" in error_info.get("status", ""):
                        quota_type = get_request_quota_type(model_name)
                        account_manager.handle_http_error(429, error_message[:200], request_id, quota_type)
                        raise HTTPException(status_code=429, detail=f"Upstream quota exhausted: {error_message[:200]}")

                stream_response = json_obj.get("streamAssistResponse", {})
                answer = stream_response.get("answer", {})

                # 检查是否被政策阻止
                answer_state = answer.get("state", "")
                if answer_state == "SKIPPED":
                    skip_reasons = answer.get("assistSkippedReasons", [])
                    policy_result = answer.get("customerPolicyEnforcementResult", {})

                    if "CUSTOMER_POLICY_VIOLATION" in skip_reasons:
                        # 提取具体的违规信息（用于日志）
                        policy_results = policy_result.get("policyResults", [])
                        violation_detail = ""

                        for policy in policy_results:
                            armor_result = policy.get("modelArmorEnforcementResult", {})
                            if armor_result:
                                violation_detail = armor_result.get("modelArmorViolation", "")
                                if violation_detail:
                                    break

                        logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 内容被安全策略阻止: {violation_detail or 'CUSTOMER_POLICY_VIOLATION'}")

                        # 向用户返回官方风格的错误信息
                        error_text = "\n⚠️ 违反政策\n\n由于提示违反了 Google 定义的安全政策，因此 Gemini 无法回复。\n\n请修改提示以符合安全政策。\n"

                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time

                        full_content += error_text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                        yield f"data: {chunk}\n\n"
                        continue
                    elif skip_reasons:
                        # 处理其他跳过原因
                        reason_text = ", ".join(skip_reasons)
                        logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应被跳过: {reason_text}")

                        error_text = f"\n⚠️ 抱歉，无法生成响应。\n\n原因：{reason_text}\n\n请稍后重试或联系管理员。\n"

                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time

                        full_content += error_text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                        yield f"data: {chunk}\n\n"
                        continue

                replies = answer.get("replies", [])

                # 记录replies数量
                if not replies:
                    logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应#{response_count}无replies，完整answer结构: {json.dumps(answer, ensure_ascii=False)[:500]}")
                else:
                    logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 响应#{response_count}包含{len(replies)}个replies")

                # 提取文本内容
                for idx, reply in enumerate(replies):
                    content_obj = reply.get("groundedContent", {}).get("content", {})
                    text = content_obj.get("text", "")

                    if not text:
                        # 记录为什么没有text
                        logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] Reply#{idx}无text，content_obj结构: {json.dumps(content_obj, ensure_ascii=False)[:300]}")
                        continue

                    # 区分思考过程和正常内容
                    if content_obj.get("thought"):
                        # 思考过程使用 reasoning_content 字段（类似 OpenAI o1）
                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time
                        chunk = create_chunk(chat_id, created_time, model_name, {"reasoning_content": text}, None)
                        yield f"data: {chunk}\n\n"
                    else:
                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time
                            # 第一次响应时统计成功次数
                            account_manager.conversation_count += 1
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

            # 记录流处理总结
            logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 流处理完成: 收到{response_count}个响应对象, 累计内容长度{len(full_content)}字符")
            if response_count > 0 and len(full_content) == 0:
                # 画图/视频请求不产生文本内容，空响应是正常的
                quota_type = get_request_quota_type(model_name)
                if quota_type in ("images", "videos"):
                    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 媒体生成请求，无文本内容属正常情况")
                else:
                    logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] ⚠️ 空响应警告: 收到{response_count}个响应但无文本内容，可能是思考模型未生成最终回答或上游错误")
                    # 打印第一个响应对象的完整结构用于调试
                    if json_objects:
                        logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 第一个响应完整结构: {json.dumps(json_objects[0], ensure_ascii=False)}")

                    # 重置 first_response_time 并抛异常，触发调用方切换账号重试
                    if request is not None:
                        request.state.first_response_time = None
                    raise HTTPException(status_code=502, detail="Thinking model produced thoughts but no final content")


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
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"
                    continue

                try:
                    markdown = process_media(result, mime, chat_id, fid, base_url, idx, request_id, account_manager.config.account_id)
                    success_count += 1
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                    yield f"data: {chunk}\n\n"
                except Exception as save_error:
                    logger.error(f"[MEDIA] [{account_manager.config.account_id}] [req_{request_id}] 媒体{idx}处理失败: {str(save_error)[:100]}")
                    error_msg = f"\n\n⚠️ 媒体 {idx} 处理失败\n\n"
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"

            logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片处理完成: {success_count}/{len(file_ids)} 成功")

        except Exception as e:
            logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片处理失败: {type(e).__name__}: {str(e)[:100]}")
            # 降级处理：通知用户图片处理失败
            error_msg = f"\n\n⚠️ 图片处理失败: {type(e).__name__}\n\n"
            if first_response_time is None:
                first_response_time = time.time()
                if request is not None:
                    request.state.first_response_time = first_response_time
            chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
            yield f"data: {chunk}\n\n"

    if full_content:
        response_preview = full_content[:500] + "...(已截断)" if len(full_content) > 500 else full_content
        logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] AI响应: {response_preview}")
    else:
        # 画图/视频请求不产生文本内容，空响应是正常的
        quota_type = get_request_quota_type(model_name)
        if quota_type in ("images", "videos"):
            logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 媒体生成请求，文本响应为空属正常情况")
        else:
            logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] ⚠️ 最终响应为空，请检查上游日志")


    if first_response_time:
        latency_ms = int((first_response_time - start_time) * 1000)
        uptime_tracker.record_request(model_name, True, latency_ms)
    else:
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
