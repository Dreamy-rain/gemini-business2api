"""
子进程调用包装（主进程侧）

通过 subprocess.Popen 启动 browser_task_runner.py，
传递 JSON 参数，接收日志和结果。
子进程退出后 OS 回收全部浏览器相关内存。
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Callable, Deque, Optional

logger = logging.getLogger("gemini.subprocess_worker")

# 子进程脚本路径
_RUNNER_SCRIPT = os.path.join(os.path.dirname(__file__), "browser_task_runner.py")
# 默认超时（秒）
_DEFAULT_TIMEOUT = 300


def run_browser_in_subprocess(
    task_params: dict,
    log_callback: Callable[[str, str], None],
    timeout: int = _DEFAULT_TIMEOUT,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    在独立子进程中执行浏览器自动化任务。

    Args:
        task_params: 任务参数字典（会被序列化为 JSON 传给子进程）
        log_callback: 日志回调 (level, message)
        timeout: 超时秒数
        cancel_check: 取消检查回调，返回 True 表示应取消

    Returns:
        结果字典，至少包含 {"success": bool, ...}
    """
    # 序列化参数
    try:
        params_json = json.dumps(task_params, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": f"参数序列化失败: {exc}"}

    # 启动子进程
    python_exe = sys.executable
    try:
        proc = subprocess.Popen(
            [python_exe, "-u", _RUNNER_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(os.path.dirname(__file__)),  # 项目根目录
            env=os.environ.copy(),
        )
    except Exception as exc:
        return {"success": False, "error": f"子进程启动失败: {exc}"}

    child_pid = proc.pid
    logger.info(f"[SUBPROCESS] 子进程已启动 (PID={child_pid})")

    # 写入参数到 stdin
    try:
        proc.stdin.write(params_json.encode("utf-8"))
        proc.stdin.close()
    except Exception as exc:
        _kill_proc(proc)
        return {"success": False, "error": f"参数写入失败: {exc}"}

    # 后台线程：实时读取 stderr 日志
    stderr_lines: Deque[str] = deque(maxlen=300)
    log_thread = threading.Thread(
        target=_read_stderr_logs,
        args=(proc, log_callback, stderr_lines),
        daemon=True,
    )
    log_thread.start()

    # 后台线程：实时读取 stdout，防止 Linux 下超出 64KB 管道导致死锁挂起。
    # 仅保留 RESULT 行及少量尾部上下文，避免全量累积导致内存峰值抬升。
    stdout_result_payload: list[str] = []
    stdout_tail: Deque[str] = deque(maxlen=50)
    out_thread = threading.Thread(
        target=_read_stdout_worker,
        args=(proc, stdout_result_payload, stdout_tail),
        daemon=True,
    )
    out_thread.start()

    # 等待子进程完成（带超时和取消检查）
    start_time = time.monotonic()
    result = None

    try:
        while True:
            elapsed = time.monotonic() - start_time

            # 检查超时
            if elapsed > timeout:
                log_callback("error", f"⏰ 浏览器子进程超时 ({timeout}s)，正在终止...")
                _kill_proc(proc)
                return {"success": False, "error": f"浏览器操作超时 ({timeout}s)"}

            # 检查取消
            if cancel_check and cancel_check():
                log_callback("warning", "🚫 收到取消请求，正在终止浏览器子进程...")
                _kill_proc(proc)
                return {"success": False, "error": "任务已取消"}

            # 检查子进程是否结束
            retcode = proc.poll()
            if retcode is not None:
                break

            # 短暂等待
            time.sleep(0.3)

    except Exception as exc:
        _kill_proc(proc)
        return {"success": False, "error": f"子进程管理异常: {exc}"}

    # 等待各个 IO 线程结束
    log_thread.join(timeout=5)
    out_thread.join(timeout=5)

    logger.info(f"[SUBPROCESS] 子进程已结束 (PID={child_pid}, exitcode={proc.returncode})")

    # 解析 RESULT: 行（由 stdout 线程捕获）
    if stdout_result_payload:
        try:
            result = json.loads(stdout_result_payload[-1])
            return result
        except json.JSONDecodeError as exc:
            return {"success": False, "error": f"结果解析失败: {exc}"}

    # 没有找到 RESULT 行
    if proc.returncode != 0:
        # 收集 stderr 中非 LOG: 开头的行作为错误信息
        error_lines = list(stderr_lines)
        if not error_lines and stdout_tail:
            # 有些运行时会把错误写到 stdout，这里保留少量上下文辅助定位问题。
            error_lines = list(stdout_tail)
        error_msg = "\n".join(error_lines[-10:]) if error_lines else f"exitcode={proc.returncode}"

        return {"success": False, "error": f"子进程异常退出: {error_msg}"}

    return {"success": False, "error": "子进程未返回结果"}


def _read_stderr_logs(
    proc: subprocess.Popen,
    log_callback: Callable[[str, str], None],
    stderr_lines: Deque[str],
) -> None:
    """后台线程：实时读取 stderr，解析 LOG: 前缀转发给回调。"""
    try:
        for raw_line in proc.stderr:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            except Exception:
                continue

            if line.startswith("LOG:"):
                # 格式: LOG:level:message
                parts = line[4:].split(":", 1)
                if len(parts) == 2:
                    level, message = parts
                    try:
                        log_callback(level, message)
                    except Exception:
                        pass
            else:
                stderr_lines.append(line)
    except Exception:
        pass


def _read_stdout_worker(
    proc: subprocess.Popen,
    stdout_result_payload: list[str],
    stdout_tail: Deque[str],
) -> None:
    """后台线程：实时提取 stdout 缓冲，避免管道堵塞死锁。"""
    try:
        for raw_line in proc.stdout:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            except Exception:
                continue

            if line.startswith("RESULT:"):
                payload = line[7:]
                if stdout_result_payload:
                    stdout_result_payload[0] = payload
                else:
                    stdout_result_payload.append(payload)
            elif line:
                stdout_tail.append(line[:1000])
    except Exception:
        pass


def _kill_proc(proc: subprocess.Popen) -> None:
    """终止子进程及其衍生的所有孙子进程（如 Chrome 等），避免僵尸进程导致内存狂飙。"""
    try:
        import psutil
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
        except Exception:
            pass
            
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass
