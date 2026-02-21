"""浏览器进程识别与统计工具。"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

# 现有自动化标识：作为误杀保护的最高优先级条件
AUTOMATION_MARKERS = (
    "--gemini-business-automation",
    "gemini_chrome_",
    "uc-profile-",
)

# Chromium 常见关联进程关键词
CHROMIUM_PROCESS_KEYWORDS = (
    "chrom",
    "google-chrome",
    "chromium",
    "crashpad",
    "zygote",
    "gpu-process",
    "utility",
    "renderer",
)

# 命令行中的浏览器相关特征参数
CHROMIUM_CMDLINE_HINTS = (
    "--type=zygote",
    "--type=renderer",
    "--type=gpu-process",
    "--type=utility",
    "--type=crashpad-handler",
    "--enable-crash-reporter",
    "--remote-debugging-port",
    "--disable-gpu",
    "--user-data-dir",
    "--profile-directory",
)


def normalize_cmdline(cmdline: Optional[list[str] | tuple[str, ...] | str]) -> str:
    """将进程命令行统一转换为小写字符串。"""
    if isinstance(cmdline, (list, tuple)):
        return " ".join(cmdline).lower()
    if isinstance(cmdline, str):
        return cmdline.lower()
    return ""


def has_automation_marker(cmdline_str: str) -> bool:
    """是否包含自动化标识（优先用于误杀保护/识别）。"""
    return any(marker in cmdline_str for marker in AUTOMATION_MARKERS)


def is_browser_related_process(name: str, cmdline: Optional[list[str] | tuple[str, ...] | str] = None) -> tuple[bool, str]:
    """
    识别是否为 Chromium 相关进程。

    Returns:
        (matched, process_type)
        process_type: automation/chromium/chromium-helper/other
    """
    normalized_name = (name or "").lower()
    cmdline_str = normalize_cmdline(cmdline)

    # 误杀保护优先：带自动化标识则直接认定为目标浏览器进程
    if has_automation_marker(cmdline_str):
        return True, "automation"

    direct_name_match = any(keyword in normalized_name for keyword in CHROMIUM_PROCESS_KEYWORDS)
    direct_cmd_match = any(keyword in cmdline_str for keyword in CHROMIUM_PROCESS_KEYWORDS)
    has_hint = any(hint in cmdline_str for hint in CHROMIUM_CMDLINE_HINTS)

    if direct_name_match:
        return True, "chromium"

    # 对 helper 类型（如 utility/gpu/zygote/crashpad）采用“关键词 + 参数特征”双重约束
    helper_like = any(k in normalized_name for k in ("crashpad", "zygote", "gpu", "utility", "renderer"))
    if helper_like and (has_hint or direct_cmd_match):
        return True, "chromium-helper"

    if direct_cmd_match and has_hint:
        return True, "chromium-helper"

    return False, "other"


def init_cleanup_stats(reason: str) -> dict:
    """初始化清理统计结构。"""
    return {
        "reason": reason,
        "tracked_candidates": 0,
        "tracked_killed": 0,
        "fallback_candidates": 0,
        "fallback_killed": 0,
        "fallback_rounds": 0,
        "global_candidates": 0,
        "global_killed": 0,
        "remaining_after_cleanup": 0,
        "hits": defaultdict(lambda: {"candidates": 0, "killed": 0, "remaining": 0}),
    }


def bump_hit(stats: dict, scope: str, process_type: str, field: str) -> None:
    """按命中维度累积计数。"""
    key = f"{scope}:{process_type}"
    stats["hits"][key][field] += 1

