"""Request log statistics access layer backed by shared SQLite connection."""

import asyncio
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Tuple

from core.storage import _get_sqlite_conn, _sqlite_lock


class StatsDatabase:
    """Statistics manager for request_logs."""

    async def insert_request_log(
        self,
        timestamp: float,
        model: str,
        ttfb_ms: int = None,
        total_ms: int = None,
        status: str = "success",
        status_code: int = None,
    ):
        """Insert one request log."""

        def _insert():
            conn = _get_sqlite_conn()
            with _sqlite_lock:
                conn.execute(
                    """
                    INSERT INTO request_logs
                    (timestamp, model, ttfb_ms, total_ms, status, status_code)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (int(timestamp), model, ttfb_ms, total_ms, status, status_code),
                )
                conn.commit()

        await asyncio.to_thread(_insert)

    async def get_stats_by_time_range(self, time_range: str = "24h") -> Dict:
        """Aggregate stats by time bucket: 24h / 7d / 30d."""

        def _query():
            now = int(time.time())
            if time_range == "24h":
                bucket_size = 3600
                bucket_count = 24
                label_fmt = "%H:00"
            elif time_range == "7d":
                bucket_size = 6 * 3600
                bucket_count = 28
                label_fmt = "%m-%d %H:00"
            elif time_range == "30d":
                bucket_size = 24 * 3600
                bucket_count = 30
                label_fmt = "%m-%d"
            else:
                bucket_size = 3600
                bucket_count = 24
                label_fmt = "%H:00"

            aligned_end = ((now // bucket_size) + 1) * bucket_size
            start_time = aligned_end - bucket_size * bucket_count

            conn = _get_sqlite_conn()
            with _sqlite_lock:
                rows = conn.execute(
                    """
                    SELECT timestamp, model, ttfb_ms, total_ms, status, status_code
                    FROM request_logs
                    WHERE timestamp >= ? AND timestamp < ?
                    ORDER BY timestamp
                    """,
                    (int(start_time), int(aligned_end)),
                ).fetchall()

            buckets = defaultdict(
                lambda: {
                    "total": 0,
                    "failed": 0,
                    "rate_limited": 0,
                    "models": defaultdict(int),
                    "model_ttfb": defaultdict(list),
                    "model_total": defaultdict(list),
                }
            )

            for row in rows:
                ts, model, ttfb, total, status, status_code = row
                bucket_key = int((ts - start_time) // bucket_size)
                if bucket_key < 0 or bucket_key >= bucket_count:
                    continue
                bucket = buckets[bucket_key]

                bucket["total"] += 1
                bucket["models"][model] += 1

                if status != "success":
                    bucket["failed"] += 1
                    if status_code == 429:
                        bucket["rate_limited"] += 1

                if status == "success" and ttfb is not None and total is not None:
                    bucket["model_ttfb"][model].append(ttfb)
                    bucket["model_total"][model].append(total)

            labels = []
            total_requests = []
            failed_requests = []
            rate_limited_requests = []

            all_models = set()
            for bucket in buckets.values():
                all_models.update(bucket["models"].keys())
                all_models.update(bucket["model_ttfb"].keys())
                all_models.update(bucket["model_total"].keys())

            model_requests = {model: [] for model in all_models}
            model_ttfb_times = {model: [] for model in all_models}
            model_total_times = {model: [] for model in all_models}

            for i in range(bucket_count):
                bucket_time = start_time + i * bucket_size
                dt = datetime.fromtimestamp(bucket_time)
                labels.append(dt.strftime(label_fmt))

                bucket = buckets[i]
                total_requests.append(bucket["total"])
                failed_requests.append(bucket["failed"])
                rate_limited_requests.append(bucket["rate_limited"])

                for model in all_models:
                    model_requests[model].append(bucket["models"].get(model, 0))

                    if model in bucket["model_ttfb"] and bucket["model_ttfb"][model]:
                        avg_ttfb = sum(bucket["model_ttfb"][model]) / len(bucket["model_ttfb"][model])
                        model_ttfb_times[model].append(avg_ttfb)
                    else:
                        model_ttfb_times[model].append(0)

                    if model in bucket["model_total"] and bucket["model_total"][model]:
                        avg_total = sum(bucket["model_total"][model]) / len(bucket["model_total"][model])
                        model_total_times[model].append(avg_total)
                    else:
                        model_total_times[model].append(0)

            return {
                "labels": labels,
                "total_requests": total_requests,
                "failed_requests": failed_requests,
                "rate_limited_requests": rate_limited_requests,
                "model_requests": dict(model_requests),
                "model_ttfb_times": dict(model_ttfb_times),
                "model_total_times": dict(model_total_times),
            }

        return await asyncio.to_thread(_query)

    async def get_total_counts(self) -> Tuple[int, int]:
        """Return success and failed counts."""

        def _query():
            conn = _get_sqlite_conn()
            with _sqlite_lock:
                success = conn.execute("SELECT COUNT(*) FROM request_logs WHERE status = 'success'").fetchone()[0]
                failed = conn.execute("SELECT COUNT(*) FROM request_logs WHERE status != 'success'").fetchone()[0]
            return success, failed

        return await asyncio.to_thread(_query)

    async def cleanup_old_data(self, days: int = 30):
        """Delete request logs older than N days (default 30)."""

        def _cleanup():
            cutoff_time = int(time.time() - days * 24 * 3600)
            conn = _get_sqlite_conn()
            with _sqlite_lock:
                cursor = conn.execute("DELETE FROM request_logs WHERE timestamp < ?", (cutoff_time,))
                conn.commit()
                return cursor.rowcount

        return await asyncio.to_thread(_cleanup)


stats_db = StatsDatabase()
