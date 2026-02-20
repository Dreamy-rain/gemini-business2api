"""
子进程调用包装（主进程侧）

通过 subprocess.Popen 启动 browser_task_runner.py，
传递 JSON 参数，接收日志和结果。
子进程退出后 OS 回收全部浏览器相关内存。
"""

import gc
import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("gemini.subprocess_worker")

# 子进程脚本路径
_RUNNER_SCRIPT = os.path.join(os.path.dirname(__file__), "browser_task_runner.py")
# 默认超时（秒）
_DEFAULT_TIMEOUT = 300


def _close_proc_pipes(proc: subprocess.Popen) -> None:
    """安全关闭子进程的所有管道，释放内核缓冲区内存。"""
    for pipe in (proc.stdin, proc.stdout, proc.stderr):
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass


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
        )
    except Exception as exc:
        return {"success": False, "error": f"子进程启动失败: {exc}"}

    child_pid = proc.pid
    logger.info(f"[SUBPROCESS] 子进程已启动 (PID={child_pid})")

    # 后台线程实时读取 stderr 日志用的缓冲区
    stderr_lines = []
    tracked_browser_pids = set()

    try:
        # 写入参数到 stdin
        try:
            proc.stdin.write(params_json.encode("utf-8"))
            proc.stdin.close()
        except Exception as exc:
            _kill_proc(proc)
            return {"success": False, "error": f"参数写入失败: {exc}"}

        # 后台线程：实时读取 stderr 日志
        log_thread = threading.Thread(
            target=_read_stderr_logs,
            args=(proc, log_callback, stderr_lines),
            daemon=True,
        )
        log_thread.start()

        # 等待子进程完成（带超时和取消检查）
        start_time = time.monotonic()
        last_scan = 0.0

        try:
            while True:
                elapsed = time.monotonic() - start_time

                # 定期采样子进程树中的浏览器 PID，便于子进程退出后兜底清理
                if elapsed - last_scan >= 0.5:
                    tracked_browser_pids.update(_collect_browser_descendants(child_pid))
                    last_scan = elapsed

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

        # 等待日志线程结束
        log_thread.join(timeout=5)

        # 子进程已退出，执行兜底清理（BROWSER_LOCK 保证同时只有一个浏览器任务，不会误杀）
        _cleanup_orphan_browsers(child_pid, tracked_browser_pids)

        # 读取 stdout 获取结果
        try:
            stdout_data = proc.stdout.read().decode("utf-8", errors="replace")
        except Exception:
            stdout_data = ""

        logger.info(f"[SUBPROCESS] 子进程已结束 (PID={child_pid}, exitcode={proc.returncode})")

        # 解析 RESULT: 行
        for line in stdout_data.splitlines():
            if line.startswith("RESULT:"):
                try:
                    return json.loads(line[7:])
                except json.JSONDecodeError as exc:
                    return {"success": False, "error": f"结果解析失败: {exc}"}

        # 没有找到 RESULT 行
        if proc.returncode != 0:
            error_lines = [l for l in stderr_lines if not l.startswith("LOG:")]
            error_msg = "\n".join(error_lines[-10:]) if error_lines else f"exitcode={proc.returncode}"
            return {"success": False, "error": f"子进程异常退出: {error_msg}"}

        return {"success": False, "error": "子进程未返回结果"}

    finally:
        # 【关键】无论何种返回路径，都必须关闭管道并释放内存
        _close_proc_pipes(proc)
        stderr_lines.clear()
        tracked_browser_pids.clear()
        # 强制垃圾回收，释放 Popen 对象、管道缓冲区等循环引用
        gc.collect()
        logger.debug(f"[SUBPROCESS] 管道已关闭，GC 已触发 (PID={child_pid})")


def _read_stderr_logs(
    proc: subprocess.Popen,
    log_callback: Callable[[str, str], None],
    stderr_lines: list,
) -> None:
    """后台线程：实时读取 stderr，解析 LOG: 前缀转发给回调。"""
    try:
        for raw_line in proc.stderr:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            except Exception:
                continue

            stderr_lines.append(line)
            if len(stderr_lines) > 200:
                del stderr_lines[:-200]

            if line.startswith("LOG:"):
                # 格式: LOG:level:message
                parts = line[4:].split(":", 1)
                if len(parts) == 2:
                    level, message = parts
                    try:
                        log_callback(level, message)
                    except Exception:
                        pass
    except Exception:
        pass


def _collect_browser_descendants(root_pid: int) -> set[int]:
    """采集指定进程树中的浏览器子孙 PID。"""
    try:
        import psutil

        root = psutil.Process(root_pid)
        descendants = root.children(recursive=True)
    except Exception:
        return set()

    browser_pids: set[int] = set()
    for proc in descendants:
        try:
            name = proc.name().lower()
            if "chrom" in name or "google-chrome" in name:
                browser_pids.add(proc.pid)
        except Exception:
            continue
    return browser_pids


def _cleanup_orphan_browsers(child_pid: int, tracked_browser_pids: Optional[set[int]] = None) -> None:
    """主进程侧兜底清理：子进程退出后扫除可能残留的浏览器进程。"""
    if tracked_browser_pids is None:
        tracked_browser_pids = set()

    try:
        import psutil

        killed = 0

        # 1) 精确清理：优先清理采样到的浏览器 PID（子进程退出后即使被系统接管也能清）
        for pid in list(tracked_browser_pids):
            try:
                proc = psutil.Process(pid)
                name = proc.name().lower()
                if "chrom" in name or "google-chrome" in name:
                    logger.info(
                        f"[SUBPROCESS] 🔪 清理残留浏览器进程(跟踪命中): PID={pid} Name={name}"
                    )
                    proc.kill()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        pass
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # 2) 回退清理：继续扫描当前主进程可见的子孙进程
        current = psutil.Process()
        children = current.children(recursive=True)
        for child in children:
            try:
                name = child.name().lower()
                if "chrom" in name or "google-chrome" in name:
                    logger.info(
                        f"[SUBPROCESS] 🔪 清理残留浏览器进程: PID={child.pid} Name={name}"
                    )
                    child.kill()
                    try:
                        child.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        pass
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if killed:
            logger.info(f"[SUBPROCESS] 兜底清理完成，共清理 {killed} 个残留浏览器进程")

    except Exception as e:
        logger.warning(f"[SUBPROCESS] 兜底清理异常: {e}")


def _kill_proc(proc: subprocess.Popen) -> None:
    """终止子进程（包括所有子孙进程）。"""
    try:
        import psutil
        
        # 1. 获取父进程对象
        try:
            parent = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return

        # 2. 获取所有子孙进程（需要在杀父进程之前获取）
        children = parent.children(recursive=True)

        if children:
            logger.info(f"[SUBPROCESS] 🧹 中止任务时清理了 {len(children)} 个子孙进程 (浏览器等)")

        # 3. 杀死所有子孙进程
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass

        # 4. 杀死相关子孙进程后，等待其终结（避免僵尸进程）
        psutil.wait_procs(children, timeout=3)

        # 5. 最后杀死父进程（Python Wrapper）
        proc.kill()
        proc.wait(timeout=5)

    except Exception as e:
        # 降级处理：直接尝试杀死父进程
        logger.warning(f"[SUBPROCESS] 进程树清理失败 ({e})，尝试直接 Kill")
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
