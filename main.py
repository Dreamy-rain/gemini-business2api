import json, time, os, asyncio, uuid, ssl, re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any
from dataclasses import dataclass  # 保留用于类型注解兼容性
import logging
from dotenv import load_dotenv

import httpx
import aiofiles
from fastapi import FastAPI, HTTPException, Header, Request, Body
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from util.streaming_parser import parse_json_array_stream_async
from collections import deque
from threading import Lock
from functools import wraps

# 导入认证装饰器
from core.auth import require_path_prefix, require_admin_auth, require_path_and_admin

# 导入核心模块
from core.jwt import JWTManager
from core.message import (
    get_conversation_key,
    extract_text_from_content,
    parse_last_message,
    build_full_context_text
)
from core.google_api import (
    get_common_headers,
    make_request_with_jwt_retry,
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
    save_accounts_to_file,
    get_account_id
)

# 导入 Uptime 追踪器
import uptime_tracker

# ---------- 日志配置 ----------

# 内存日志缓冲区 (保留最近 3000 条日志，重启后清空)
log_buffer = deque(maxlen=3000)
log_lock = Lock()

# 统计数据持久化
STATS_FILE = "data/stats.json"
stats_lock = asyncio.Lock()  # 改为异步锁

async def load_stats():
    """加载统计数据（异步）"""
    try:
        if os.path.exists(STATS_FILE):
            async with aiofiles.open(STATS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
    except Exception:
        pass
    return {
        "total_visitors": 0,
        "total_requests": 0,
        "request_timestamps": [],  # 最近1小时的请求时间戳
        "visitor_ips": {},  # {ip: timestamp} 记录访问IP和时间
        "account_conversations": {}  # {account_id: conversation_count} 账户对话次数
    }

async def save_stats(stats):
    """保存统计数据（异步，避免阻塞事件循环）"""
    try:
        async with aiofiles.open(STATS_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(stats, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"[STATS] 保存统计数据失败: {str(e)[:50]}")

# 初始化统计数据（需要在启动时异步加载）
global_stats = {
    "total_visitors": 0,
    "total_requests": 0,
    "request_timestamps": [],
    "visitor_ips": {},
    "account_conversations": {}
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

# 添加内存日志处理器
memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(memory_handler)

load_dotenv()
# ---------- 配置 ----------
PROXY        = os.getenv("PROXY", "")
TIMEOUT_SECONDS = 600
API_KEY      = os.getenv("API_KEY", "")  # API 访问密钥（可选）
PATH_PREFIX  = os.getenv("PATH_PREFIX")      # 路径前缀（必需，用于隐藏端点）
ADMIN_KEY    = os.getenv("ADMIN_KEY")        # 管理员密钥（必需，用于访问管理端点）
BASE_URL     = os.getenv("BASE_URL", "")         # 服务器完整URL（可选，用于图片URL生成）

# ---------- 公开展示配置 ----------
LOGO_URL     = os.getenv("LOGO_URL", "")  # Logo URL（公开，为空则不显示）
CHAT_URL     = os.getenv("CHAT_URL", "")  # 开始对话链接（公开，为空则不显示）
MODEL_NAME   = os.getenv("MODEL_NAME", "gemini-business")  # 模型名称（公开）
HIDE_HOME_PAGE = os.getenv("HIDE_HOME_PAGE", "").lower() == "true"  # 是否隐藏首页（默认不隐藏）

# ---------- 图片存储配置 ----------
if os.path.exists("/data"):
    IMAGE_DIR = "/data/images"  # HF Pro持久化存储
else:
    IMAGE_DIR = "./data/images"  # 本地持久化存储

# ---------- 重试配置 ----------
MAX_NEW_SESSION_TRIES = int(os.getenv("MAX_NEW_SESSION_TRIES", "5"))  # 新会话创建最多尝试账户数（默认5）
MAX_REQUEST_RETRIES = int(os.getenv("MAX_REQUEST_RETRIES", "3"))      # 请求失败最多重试次数（默认3）
MAX_ACCOUNT_SWITCH_TRIES = int(os.getenv("MAX_ACCOUNT_SWITCH_TRIES", "5"))  # 每次重试找账户的最大尝试次数（默认5）
ACCOUNT_FAILURE_THRESHOLD = int(os.getenv("ACCOUNT_FAILURE_THRESHOLD", "3"))  # 账户连续失败阈值（默认3次）
RATE_LIMIT_COOLDOWN_SECONDS = int(os.getenv("RATE_LIMIT_COOLDOWN_SECONDS", "600"))  # 429错误冷却时间（默认600秒=10分钟）
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
    proxy=PROXY or None,
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,  # 增加5倍：20 -> 100
        max_connections=200              # 增加4倍：50 -> 200
    )
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

# ---------- 配置文件管理 ----------
# (MultiAccountManager和配置管理函数已移至 core/account.py)

def reload_accounts():
    """重新加载账户配置（清空缓存并重新加载）"""
    global multi_account_mgr
    multi_account_mgr.global_session_cache.clear()
    multi_account_mgr = load_multi_account_config()
    logger.info(f"[CONFIG] 配置已重载，当前账户数: {len(multi_account_mgr.accounts)}")

def update_accounts_config(accounts_data: list):
    """更新账户配置（保存到文件并重新加载）"""
    save_accounts_to_file(accounts_data)
    reload_accounts()

def delete_account(account_id: str):
    """删除单个账户"""
    accounts_data = load_accounts_from_source()

    # 过滤掉要删除的账户
    filtered = [
        acc for i, acc in enumerate(accounts_data, 1)
        if get_account_id(acc, i) != account_id
    ]

    if len(filtered) == len(accounts_data):
        raise ValueError(f"账户 {account_id} 不存在")

    save_accounts_to_file(filtered)
    reload_accounts()

def update_account_disabled_status(account_id: str, disabled: bool):
    """更新账户的禁用状态"""
    accounts_data = load_accounts_from_source()

    # 查找并更新账户
    found = False
    for i, acc in enumerate(accounts_data, 1):
        if get_account_id(acc, i) == account_id:
            acc["disabled"] = disabled
            found = True
            break

    if not found:
        raise ValueError(f"账户 {account_id} 不存在")

    save_accounts_to_file(accounts_data)
    reload_accounts()

    status_text = "已禁用" if disabled else "已启用"
    logger.info(f"[CONFIG] 账户 {account_id} {status_text}")

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
# (JWTManager已移至 core/jwt.py)

# ---------- Session & File 管理 ----------
# (Google API函数已移至 core/google_api.py)

# ---------- 消息处理逻辑 ----------
# (消息处理函数已移至 core/message.py)

# ---------- OpenAI 兼容接口 ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway")

# ---------- Uptime 追踪中间件 ----------
@app.middleware("http")
async def track_uptime_middleware(request: Request, call_next):
    """追踪每个请求的成功/失败状态，用于 Uptime 监控"""
    # 只追踪 API 请求（排除静态文件、管理端点等）
    path = request.url.path
    if path.startswith("/images/") or path.startswith("/public/") or path.startswith("/favicon"):
        return await call_next(request)

    start_time = time.time()
    success = False
    model = None

    try:
        response = await call_next(request)
        success = response.status_code < 400

        # 尝试从请求中提取模型信息
        if hasattr(request.state, "model"):
            model = request.state.model

        # 记录 API 主服务状态
        uptime_tracker.record_request("api_service", success)

        # 如果有模型信息，记录模型状态
        if model and model in uptime_tracker.SUPPORTED_MODELS:
            uptime_tracker.record_request(model, success)

        return response

    except Exception as e:
        # 请求失败 - 尝试提取模型信息（可能在异常前已设置）
        if hasattr(request.state, "model"):
            model = request.state.model

        uptime_tracker.record_request("api_service", False)
        if model and model in uptime_tracker.SUPPORTED_MODELS:
            uptime_tracker.record_request(model, False)
        raise

# ---------- 图片静态服务初始化 ----------
os.makedirs(IMAGE_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
if IMAGE_DIR == "/data/images":
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (HF Pro持久化)")
else:
    logger.info(f"[SYSTEM] 图片静态服务已启用: /images/ -> {IMAGE_DIR} (本地持久化)")

# ---------- 后台任务启动 ----------
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化后台任务"""
    global global_stats

    # 加载统计数据
    global_stats = await load_stats()
    logger.info(f"[SYSTEM] 统计数据已加载: {global_stats['total_requests']} 次请求, {global_stats['total_visitors']} 位访客")

    # 启动缓存清理任务
    asyncio.create_task(multi_account_mgr.start_background_cleanup())
    logger.info("[SYSTEM] 后台缓存清理任务已启动（间隔: 5分钟）")

    # 启动 Uptime 数据聚合任务
    asyncio.create_task(uptime_tracker.uptime_aggregation_task())
    logger.info("[SYSTEM] Uptime 数据聚合任务已启动（间隔: 240秒）")

# ---------- 导入模板模块 ----------
# 注意：必须在所有全局变量初始化之后导入，避免循环依赖
from core import templates

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
    if not API_KEY:
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

@app.get("/")
async def home(request: Request):
    """首页 - 默认显示管理面板（可通过环境变量隐藏）"""
    # 检查是否隐藏首页
    if HIDE_HOME_PAGE:
        raise HTTPException(404, "Not Found")

    # 显示管理页面（带隐藏提示）
    html_content = templates.generate_admin_html(request, multi_account_mgr, show_hide_tip=True)
    return HTMLResponse(content=html_content)

@app.get("/{path_prefix}/admin")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_home(path_prefix: str, request: Request, key: str = None, authorization: str = Header(None)):
    """管理首页 - 显示API信息和错误提醒"""
    # 显示管理页面（不显示隐藏提示）
    html_content = templates.generate_admin_html(request, multi_account_mgr, show_hide_tip=False)
    return HTMLResponse(content=html_content)

@app.get("/{path_prefix}/v1/models")
@require_path_prefix(PATH_PREFIX)
async def list_models(path_prefix: str, authorization: str = Header(None)):
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
@require_path_prefix(PATH_PREFIX)
async def get_model(path_prefix: str, model_id: str, authorization: str = Header(None)):
    # 验证 API Key
    verify_api_key(authorization)

    return {"id": model_id, "object": "model"}

@app.get("/{path_prefix}/admin/health")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_health(path_prefix: str, key: str = None, authorization: str = Header(None)):
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.get("/{path_prefix}/admin/accounts")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_get_accounts(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """获取所有账户的状态信息"""
    accounts_info = []
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()

        # 使用统一的格式化函数
        status, status_color, remaining_display = format_account_expiration(remaining_hours)

        # 使用AccountManager的方法获取冷却信息
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()

        accounts_info.append({
            "id": config.account_id,
            "status": status,
            "expires_at": config.expires_at or "未设置",
            "remaining_hours": remaining_hours,
            "remaining_display": remaining_display,
            "is_available": account_manager.is_available,
            "error_count": account_manager.error_count,
            "disabled": config.disabled,  # 添加手动禁用状态
            "cooldown_seconds": cooldown_seconds,  # 冷却剩余秒数
            "cooldown_reason": cooldown_reason,  # 冷却原因
            "conversation_count": account_manager.conversation_count  # 累计对话次数
        })

    return {
        "total": len(accounts_info),
        "accounts": accounts_info
    }

@app.get("/{path_prefix}/admin/accounts-config")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_get_config(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """获取完整账户配置"""
    try:
        accounts_data = load_accounts_from_source()
        return {"accounts": accounts_data}
    except Exception as e:
        logger.error(f"[CONFIG] 获取配置失败: {str(e)}")
        raise HTTPException(500, f"获取失败: {str(e)}")

@app.put("/{path_prefix}/admin/accounts-config")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_update_config(path_prefix: str, accounts_data: list = Body(...), key: str = None, authorization: str = Header(None)):
    """更新整个账户配置"""
    try:
        update_accounts_config(accounts_data)
        return {"status": "success", "message": "配置已更新", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 更新配置失败: {str(e)}")
        raise HTTPException(500, f"更新失败: {str(e)}")

@app.delete("/{path_prefix}/admin/accounts/{account_id}")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_delete_account(path_prefix: str, account_id: str, key: str = None, authorization: str = Header(None)):
    """删除单个账户"""
    try:
        delete_account(account_id)
        return {"status": "success", "message": f"账户 {account_id} 已删除", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 删除账户失败: {str(e)}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.put("/{path_prefix}/admin/accounts/{account_id}/disable")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_disable_account(path_prefix: str, account_id: str, key: str = None, authorization: str = Header(None)):
    """手动禁用账户"""
    try:
        update_account_disabled_status(account_id, True)
        return {"status": "success", "message": f"账户 {account_id} 已禁用", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 禁用账户失败: {str(e)}")
        raise HTTPException(500, f"禁用失败: {str(e)}")

@app.put("/{path_prefix}/admin/accounts/{account_id}/enable")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_enable_account(path_prefix: str, account_id: str, key: str = None, authorization: str = Header(None)):
    """启用账户"""
    try:
        update_account_disabled_status(account_id, False)
        return {"status": "success", "message": f"账户 {account_id} 已启用", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] 启用账户失败: {str(e)}")
        raise HTTPException(500, f"启用失败: {str(e)}")

@app.get("/{path_prefix}/admin/log")
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
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
@require_path_and_admin(PATH_PREFIX, ADMIN_KEY)
async def admin_clear_logs(path_prefix: str, confirm: str = None, key: str = None, authorization: str = Header(None)):
    """
    清空所有日志（内存缓冲 + 文件）

    参数:
    - confirm: 必须传入 "yes" 才能清空
    """
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
async def admin_logs_html_route(path_prefix: str, key: str = None, authorization: str = Header(None)):
    """返回美化的 HTML 日志查看界面"""
    return await templates.admin_logs_html(path_prefix, key, authorization)

@app.post("/{path_prefix}/v1/chat/completions")
@require_path_prefix(PATH_PREFIX)
async def chat(
    path_prefix: str,
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    # 1. API Key 验证
    verify_api_key(authorization)

    # 1. 生成请求ID（最优先，用于所有日志追踪）
    request_id = str(uuid.uuid4())[:6]

    # 获取客户端IP（用于会话隔离）
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # 记录请求统计
    async with stats_lock:
        global_stats["total_requests"] += 1
        global_stats["request_timestamps"].append(time.time())
        await save_stats(global_stats)

    # 2. 模型校验
    if req.model not in MODEL_MAPPING:
        logger.error(f"[CHAT] [req_{request_id}] 不支持的模型: {req.model}")
        raise HTTPException(
            status_code=404,
            detail=f"Model '{req.model}' not found. Available models: {list(MODEL_MAPPING.keys())}"
        )

    # 保存模型信息到 request.state（用于 Uptime 追踪）
    request.state.model = req.model

    # 3. 生成会话指纹，获取Session锁（防止同一对话的并发请求冲突）
    conv_key = get_conversation_key([m.dict() for m in req.messages], client_ip)
    session_lock = await multi_account_mgr.acquire_session_lock(conv_key)

    # 4. 在锁的保护下检查缓存和处理Session（保证同一对话的请求串行化）
    async with session_lock:
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
                    google_session = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    # 线程安全地绑定账户到此对话
                    await multi_account_mgr.set_session_cache(
                        conv_key,
                        account_manager.config.account_id,
                        google_session
                    )
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
                    uptime_tracker.record_request("account_pool", False)
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
    last_text, current_images = await parse_last_message(req.messages, http_client, request_id)

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

                # A. 如果有图片且还没上传到当前 Session，先上传
                # 注意：每次重试如果是新 Session，都需要重新上传图片
                if current_images and not current_file_ids:
                    for img in current_images:
                        fid = await upload_context_file(current_session, img["mime"], img["data"], account_manager, http_client, USER_AGENT, request_id)
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

                # 请求成功，重置账户失败计数
                account_manager.is_available = True
                account_manager.error_count = 0
                account_manager.conversation_count += 1  # 增加对话次数

                # 记录账号池状态（请求成功）
                uptime_tracker.record_request("account_pool", True)

                # 保存对话次数到统计数据
                async with stats_lock:
                    if "account_conversations" not in global_stats:
                        global_stats["account_conversations"] = {}
                    global_stats["account_conversations"][account_manager.config.account_id] = account_manager.conversation_count
                    await save_stats(global_stats)

                break

            except (httpx.HTTPError, ssl.SSLError, HTTPException) as e:
                # 记录当前失败的账户
                failed_accounts.add(account_manager.config.account_id)

                # 记录账号池状态（请求失败）
                uptime_tracker.record_request("account_pool", False)

                # 检查是否为429错误（Rate Limit）
                is_rate_limit = isinstance(e, HTTPException) and e.status_code == 429

                # 增加账户失败计数（触发熔断机制）
                account_manager.last_error_time = time.time()
                if is_rate_limit:
                    account_manager.last_429_time = time.time()

                account_manager.error_count += 1
                if account_manager.error_count >= ACCOUNT_FAILURE_THRESHOLD:
                    account_manager.is_available = False
                    if is_rate_limit:
                        logger.error(f"[ACCOUNT] [{account_manager.config.account_id}] [req_{request_id}] 遇到429错误{account_manager.error_count}次，账户已禁用（需休息{RATE_LIMIT_COOLDOWN_SECONDS}秒）")
                    else:
                        logger.error(f"[ACCOUNT] [{account_manager.config.account_id}] [req_{request_id}] 请求连续失败{account_manager.error_count}次，账户已永久禁用")

                retry_count += 1

                # 详细记录错误信息
                error_type = type(e).__name__
                error_detail = str(e)

                # 特殊处理HTTPException，提取状态码和详情
                if isinstance(e, HTTPException):
                    if is_rate_limit:
                        logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 遇到429限流错误，账户将休息{RATE_LIMIT_COOLDOWN_SECONDS}秒")
                    else:
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
                        new_sess = await create_google_session(new_account, http_client, USER_AGENT, request_id)

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
                        # 记录账号池状态（账户切换失败）
                        uptime_tracker.record_request("account_pool", False)
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
                file_ids.append({
                    "fileId": file_info["fileId"],
                    "mimeType": file_info.get("mimeType", "image/png")
                })

    return file_ids, session_name


async def stream_chat_generator(session: str, text_content: str, file_ids: List[str], model_name: str, chat_id: str, created_time: int, account_manager: AccountManager, is_stream: bool = True, request_id: str = "", request: Request = None):
    start_time = time.time()

    # 记录发送给API的内容
    text_preview = text_content[:500] + "...(已截断)" if len(text_content) > 500 else text_content
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 发送内容: {text_preview}")
    if file_ids:
        logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] 附带文件: {len(file_ids)}个")

    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, USER_AGENT)

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
                file_ids, session_name = parse_images_from_response(json_objects)

                if file_ids and session_name:
                    logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 检测到{len(file_ids)}张生成图片")

                    try:
                        base_url = get_base_url(request) if request else ""
                        file_metadata = await get_session_file_metadata(account_manager, session_name, http_client, USER_AGENT, request_id)

                        # 并行下载所有图片
                        download_tasks = []
                        for file_info in file_ids:
                            fid = file_info["fileId"]
                            mime = file_info["mimeType"]
                            meta = file_metadata.get(fid, {})
                            correct_session = meta.get("session") or session_name
                            task = download_image_with_jwt(account_manager, correct_session, fid, http_client, USER_AGENT, request_id)
                            download_tasks.append((fid, mime, task))

                        results = await asyncio.gather(*[task for _, _, task in download_tasks], return_exceptions=True)

                        # 处理下载结果
                        for idx, ((fid, mime, _), result) in enumerate(zip(download_tasks, results), 1):
                            if isinstance(result, Exception):
                                logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片{idx}下载失败: {type(result).__name__}")
                                continue

                            image_url = save_image_to_hf(result, chat_id, fid, mime, base_url, IMAGE_DIR)
                            logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] 图片{idx}已保存: {image_url}")

                            markdown = f"\n\n![生成的图片]({image_url})\n\n"
                            chunk = create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                            yield f"data: {chunk}\n\n"

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
@app.get("/public/uptime")
async def get_public_uptime(days: int = 90):
    """获取 Uptime 监控数据（JSON格式）"""
    if days < 1 or days > 90:
        days = 90
    return await uptime_tracker.get_uptime_summary(days)

@app.get("/public/uptime/html")
async def get_public_uptime_html():
    """Uptime 监控页面（类似 status.openai.com）"""
    return await templates.get_uptime_html()

@app.get("/public/stats")
async def get_public_stats():
    """获取公开统计信息"""
    async with stats_lock:
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
    try:
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

        async with stats_lock:
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

            # 同步访问者计数（清理后的实际数量）
            global_stats["total_visitors"] = len(global_stats["visitor_ips"])
            await save_stats(global_stats)

        sanitized_logs = get_sanitized_logs(limit=min(limit, 1000))
        return {
            "total": len(sanitized_logs),
            "logs": sanitized_logs
        }
    except Exception as e:
        logger.error(f"[LOG] 获取公开日志失败: {e}")
        return {"total": 0, "logs": [], "error": str(e)}

@app.get("/public/log/html")
async def get_public_logs_html():
    """公开的脱敏日志查看器"""
    return await templates.get_public_logs_html()

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