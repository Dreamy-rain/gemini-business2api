#!/usr/bin/env python3
"""Seed local SQLite with demo data for frontend pages.

Usage:
  python scripts/seed_frontend_demo_data.py
  python scripts/seed_frontend_demo_data.py --replace-accounts --replace-logs
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sqlite3
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))


@dataclass
class SeedSummary:
    accounts_inserted: int = 0
    logs_inserted: int = 0


def _rand_token(prefix: str, n: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits
    return f"{prefix}{''.join(random.choice(alphabet) for _ in range(n))}"


def _ensure_tables(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                position INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                model TEXT NOT NULL,
                ttfb_ms INTEGER,
                total_ms INTEGER,
                status TEXT NOT NULL,
                status_code INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
def _build_demo_accounts() -> list[dict]:
    now = datetime.now(BEIJING_TZ)

    def exp(hours: int | None) -> str | None:
        if hours is None:
            return None
        return (now + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    providers = ["duckmail", "moemail", "freemail", "gptmail", "cfmail", "microsoft"]
    clusters = ["alpha", "beta", "gamma", "delta", "omega", "nova"]
    rows: list[dict] = []
    template_hours: list[int | None] = [240, 168, 96, 72, 48, 24, 12, 6, 3, -4, -12, None]

    for idx, hours in enumerate(template_hours, 1):
        provider = providers[(idx - 1) % len(providers)]
        cluster = clusters[(idx - 1) % len(clusters)]
        account_id = f"{cluster}-{200 + idx:03d}"
        is_disabled = idx in {10, 11}
        entry = {
            "id": account_id,
            "secure_c_ses": _rand_token("CSE.AXUaAj", 118),
            "host_c_oses": _rand_token("HOS.", 24),
            "csesidx": str(100000000 + idx * 7919),
            "config_id": str(uuid.uuid4()),
            "expires_at": exp(hours),
            "disabled": is_disabled,
            "disabled_reason": "manual_hold" if is_disabled else None,
            "mail_provider": provider,
            "mail_address": f"{account_id}@mailbox.local",
            "mail_password": _rand_token("mail-", 10),
            "mail_verify_ssl": True,
            "trial_end": (now + timedelta(days=max(0, 21 - idx))).strftime("%Y-%m-%d"),
        }
        if provider == "microsoft":
            entry["mail_client_id"] = "demo-client-id"
            entry["mail_refresh_token"] = _rand_token("demo-refresh-", 18)
            entry["mail_tenant"] = "consumers"
        rows.append(entry)

    return rows


def _seed_accounts(conn: sqlite3.Connection, replace: bool) -> int:
    current = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    if current > 0 and not replace:
        return 0

    rows = _build_demo_accounts()

    with conn:
        if replace:
            conn.execute("DELETE FROM accounts")
        for position, item in enumerate(rows, 1):
            conn.execute(
                """
                INSERT OR REPLACE INTO accounts (account_id, position, data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (item["id"], position, json.dumps(item, ensure_ascii=False)),
            )

    return len(rows)


def _seed_logs(conn: sqlite3.Connection, replace: bool, count: int) -> int:
    if count <= 0:
        return 0

    model_pool: list[tuple[str, float]] = [
        ("gemini-3.1-fast", 0.35),
        ("gemini-3.1-thinking", 0.12),
        ("gemini-3.1-pro", 0.09),
        ("gemini-2.5-flash", 0.16),
        ("gemini-2.5-pro", 0.08),
        ("gemini-imagen", 0.15),
        ("nano-banana-2", 0.05),
    ]

    now = datetime.now(BEIJING_TZ)
    start_hour = (now - timedelta(days=30)).replace(minute=0, second=0, microsecond=0)
    total_hours = int((now - start_hour).total_seconds() // 3600) + 1

    slots: list[datetime] = []
    weights: list[float] = []
    for h in range(total_hours):
        slot = start_hour + timedelta(hours=h)
        hour = slot.hour
        weekday = slot.weekday()  # 0=Mon ... 6=Sun
        age_days = (now - slot).total_seconds() / (24 * 3600)
        recent_boost = 1.25 + 1.75 * math.exp(-age_days / 6.2)
        daytime_boost = 0.75 + max(0.0, math.sin((hour - 8) / 24 * math.pi * 2)) * 1.45
        weekday_boost = 1.08 if weekday < 5 else 0.82
        weight = max(0.15, recent_boost * daytime_boost * weekday_boost)
        slots.append(slot)
        weights.append(weight)

    chosen_slots = random.choices(slots, weights=weights, k=count)
    points: list[tuple[int, str, int | None, int | None, str, int]] = []

    models = [item[0] for item in model_pool]
    model_weights = [item[1] for item in model_pool]
    for slot in chosen_slots:
        ts = slot + timedelta(minutes=random.randint(0, 59), seconds=random.randint(0, 59))
        timestamp = int(ts.timestamp())

        model = random.choices(models, weights=model_weights, k=1)[0]
        image_model = model in {"gemini-imagen", "nano-banana-2"}
        roll = random.random()

        if image_model:
            success_rate = 0.82
            rate_limit_rate = 0.08
        else:
            success_rate = 0.9
            rate_limit_rate = 0.04

        if roll < success_rate:
            status = "success"
            status_code = 200
            if image_model:
                ttfb = random.randint(950, 4200)
                total = ttfb + random.randint(1500, 7800)
            elif "thinking" in model or "pro" in model:
                ttfb = random.randint(700, 3200)
                total = ttfb + random.randint(500, 4200)
            else:
                ttfb = random.randint(380, 1800)
                total = ttfb + random.randint(240, 2200)
        elif roll < success_rate + rate_limit_rate:
            status = "failed"
            status_code = 429
            ttfb = random.randint(350, 1600)
            total = ttfb + random.randint(180, 1900)
        else:
            status = "failed"
            status_code = random.choice([500, 502, 503])
            ttfb = random.randint(700, 3200)
            total = ttfb + random.randint(500, 5000)

        points.append((timestamp, model, ttfb, total, status, status_code))

    points.sort(key=lambda x: x[0])

    with conn:
        if replace:
            conn.execute("DELETE FROM request_logs")
        conn.executemany(
            """
            INSERT INTO request_logs (timestamp, model, ttfb_ms, total_ms, status, status_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            points,
        )

    return len(points)


def _backup_db(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    backup_dir = db_path.parent / "snapshots"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"data.db.seed-backup-{stamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed frontend demo data into SQLite")
    parser.add_argument("--db-path", default="data/data.db", help="SQLite db path")
    parser.add_argument("--replace-accounts", action="store_true", help="Replace existing accounts with demo accounts")
    parser.add_argument("--replace-logs", action="store_true", help="Replace existing request logs with demo logs")
    parser.add_argument("--logs-count", type=int, default=2400, help="How many demo request logs to generate")
    parser.add_argument("--seed", type=int, default=20260323, help="Random seed for reproducible demo data")
    parser.add_argument("--no-backup", action="store_true", help="Skip db backup before writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = None
    if not args.no_backup:
        backup_path = _backup_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        _ensure_tables(conn)

        summary = SeedSummary()
        summary.accounts_inserted = _seed_accounts(conn, replace=args.replace_accounts)
        summary.logs_inserted = _seed_logs(conn, replace=args.replace_logs, count=args.logs_count)

        print("[OK] Demo data seeding completed")
        print(f"   DB: {db_path.resolve()}")
        if backup_path:
            print(f"   Backup: {backup_path.resolve()}")
        print(f"   Accounts inserted: {summary.accounts_inserted}")
        print(f"   Request logs inserted: {summary.logs_inserted}")

        current_accounts = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        current_logs = conn.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0]
        print("   Current totals -> "
              f"accounts: {current_accounts}, request_logs: {current_logs}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
