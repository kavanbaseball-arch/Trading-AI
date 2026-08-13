from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "tester.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT,
                    cash REAL,
                    broker TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    qty REAL,
                    avg_price REAL
                );
                CREATE TABLE IF NOT EXISTS pair_positions (
                    pair_id TEXT PRIMARY KEY,
                    side TEXT,
                    shares_a REAL,
                    shares_b REAL,
                    entry_z REAL,
                    entry_spread REAL,
                    beta REAL,
                    opened_at TEXT,
                    holding_days INTEGER
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    pair_id TEXT,
                    action TEXT,
                    reason TEXT,
                    payload TEXT
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    level TEXT,
                    message TEXT
                );
                CREATE TABLE IF NOT EXISTS equity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    equity REAL,
                    cash REAL
                );
                CREATE TABLE IF NOT EXISTS pair_state (
                    pair_id TEXT PRIMARY KEY,
                    payload TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS kv (
                    k TEXT PRIMARY KEY,
                    v TEXT
                );
                """
            )
            row = conn.execute("SELECT id FROM account WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO account (id, name, cash, broker, updated_at) VALUES (1, ?, ?, ?, ?)",
                    (settings.account_name, settings.starting_cash, settings.broker, _now()),
                )

    def get_account(self) -> dict:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
            return dict(row)

    def set_cash(self, cash: float) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE account SET cash = ?, updated_at = ? WHERE id = 1",
                (cash, _now()),
            )

    def positions(self) -> dict[str, dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM positions").fetchall()
            return {r["symbol"]: dict(r) for r in rows}

    def upsert_position(self, symbol: str, qty: float, avg_price: float) -> None:
        with self._lock, self._conn() as conn:
            if abs(qty) < 1e-8:
                conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            else:
                conn.execute(
                    """
                    INSERT INTO positions (symbol, qty, avg_price)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET qty = excluded.qty, avg_price = excluded.avg_price
                    """,
                    (symbol, qty, avg_price),
                )

    def pair_positions(self) -> dict[str, dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM pair_positions").fetchall()
            return {r["pair_id"]: dict(r) for r in rows}

    def upsert_pair_position(self, payload: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO pair_positions (
                    pair_id, side, shares_a, shares_b, entry_z, entry_spread, beta, opened_at, holding_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pair_id) DO UPDATE SET
                    side=excluded.side, shares_a=excluded.shares_a, shares_b=excluded.shares_b,
                    entry_z=excluded.entry_z, entry_spread=excluded.entry_spread, beta=excluded.beta,
                    opened_at=excluded.opened_at, holding_days=excluded.holding_days
                """,
                (
                    payload["pair_id"],
                    payload["side"],
                    payload["shares_a"],
                    payload["shares_b"],
                    payload["entry_z"],
                    payload["entry_spread"],
                    payload["beta"],
                    payload["opened_at"],
                    payload.get("holding_days", 0),
                ),
            )

    def delete_pair_position(self, pair_id: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM pair_positions WHERE pair_id = ?", (pair_id,))

    def add_trade(self, pair_id: str, action: str, reason: str, payload: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO trades (ts, pair_id, action, reason, payload) VALUES (?, ?, ?, ?, ?)",
                (_now(), pair_id, action, reason, json.dumps(payload)),
            )

    def recent_trades(self, limit: int = 100) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                item = dict(r)
                item["payload"] = json.loads(item["payload"])
                out.append(item)
            return out

    def add_log(self, message: str, level: str = "info") -> dict:
        ts = _now()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO logs (ts, level, message) VALUES (?, ?, ?)",
                (ts, level, message),
            )
        return {"ts": ts, "level": level, "message": message}

    def recent_logs(self, limit: int = 200) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def snapshot_equity(self, equity: float, cash: float) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO equity (ts, equity, cash) VALUES (?, ?, ?)",
                (_now(), equity, cash),
            )

    def equity_curve(self, limit: int = 500) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM equity ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return list(reversed([dict(r) for r in rows]))

    def set_pair_state(self, pair_id: str, payload: dict) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO pair_state (pair_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(pair_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (pair_id, json.dumps(payload), _now()),
            )

    def all_pair_state(self) -> dict[str, dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM pair_state").fetchall()
            return {r["pair_id"]: json.loads(r["payload"]) for r in rows}

    def get_kv(self, key: str) -> Any:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
            return json.loads(row["v"]) if row else None

    def set_kv(self, key: str, value: Any) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                (key, json.dumps(value)),
            )
