"""
Uptime 实时监控追踪器
类似 Uptime Kuma 的心跳监控，显示最近请求状态
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# 北京时区 UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))

# 每个服务保留最近 60 条心跳记录
MAX_HEARTBEATS = 60

# 服务配置
SERVICES = {
    "api_service": {"name": "API 服务", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "account_pool": {"name": "服务资源", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-2.5-flash": {"name": "Gemini 2.5 Flash", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-2.5-pro": {"name": "Gemini 2.5 Pro", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-3-flash-preview": {"name": "Gemini 3 Flash Preview", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
    "gemini-3-pro-preview": {"name": "Gemini 3 Pro Preview", "heartbeats": deque(maxlen=MAX_HEARTBEATS)},
}

SUPPORTED_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3-pro-preview"]


def record_request(service: str, success: bool):
    """记录请求心跳"""
    if service not in SERVICES:
        return

    SERVICES[service]["heartbeats"].append({
        "time": datetime.now(BEIJING_TZ).strftime("%H:%M:%S"),
        "success": success
    })


def get_realtime_status() -> Dict:
    """获取实时状态数据"""
    result = {"services": {}}

    for service_id, service_data in SERVICES.items():
        heartbeats = list(service_data["heartbeats"])
        total = len(heartbeats)
        success = sum(1 for h in heartbeats if h["success"])

        # 计算可用率
        uptime = (success / total * 100) if total > 0 else 100.0

        # 最近状态
        last_status = "unknown"
        if heartbeats:
            last_status = "up" if heartbeats[-1]["success"] else "down"

        result["services"][service_id] = {
            "name": service_data["name"],
            "status": last_status,
            "uptime": round(uptime, 1),
            "total": total,
            "success": success,
            "heartbeats": heartbeats[-MAX_HEARTBEATS:]  # 最近的心跳
        }

    result["updated_at"] = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return result


# 兼容旧接口
async def get_uptime_summary(days: int = 90) -> Dict:
    """兼容旧接口，返回实时数据"""
    return get_realtime_status()


async def uptime_aggregation_task():
    """后台任务（保留兼容性，实际不需要聚合）"""
    pass
