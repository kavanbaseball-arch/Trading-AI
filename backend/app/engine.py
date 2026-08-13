from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

import numpy as np

from app.analyzer import PairAnalyzer, size_pair, spread_correlation
from app.broker import Broker, make_broker
from app.clock import market_session, now_et
from app.config import settings
from app.market_data import MarketData
from app.risk import RiskEngine
from app.store import Store
from app.strategy import evaluate_signal
from app.universe import PAIRS, active_pairs, all_symbols


class TradingEngine:
    def __init__(self) -> None:
        self.store = Store()
        self.broker: Broker = make_broker(self.store)
        self.data = MarketData()
        self.analyzer = PairAnalyzer()
        self.risk = RiskEngine()
        self.running = False
        self.last_cycle: dict | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def log(self, message: str, level: str = "info") -> None:
        self.store.add_log(message, level)

    def mark_to_market(self, prices: dict[str, float]) -> dict:
        cash = self.broker.cash()
        positions = self.broker.positions()
        mtm = 0.0
        gross = 0.0
        detailed = []
        for sym, pos in positions.items():
            qty = float(pos["qty"])
            px = prices.get(sym, float(pos.get("avg_price") or 0))
            value = qty * px
            mtm += value
            gross += abs(value)
            detailed.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "price": px,
                    "avg_price": float(pos.get("avg_price") or 0),
                    "value": value,
                    "unrealized": qty * (px - float(pos.get("avg_price") or px)),
                }
            )
        equity = cash + mtm
        self.store.snapshot_equity(equity, cash)
        return {
            "name": settings.account_name,
            "broker": settings.broker,
            "cash": cash,
            "equity": equity,
            "gross_exposure": gross,
            "positions": detailed,
        }

    def _holding_days(self, opened_at: str) -> int:
        opened = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        return int(np.busday_count(opened.date(), now_et().date()))

    def _execute_entry(self, pair, analysis: dict, side: str, prices: dict[str, float]) -> None:
        beta = analysis["beta"]
        if abs(beta) < 0.05:
            self.log(f"SKIP {pair.id} hedge β too small ({beta:.4f})", "warn")
            return
        shares_a, shares_b = size_pair(
            settings.max_notional_per_pair,
            analysis["price_a"],
            analysis["price_b"],
            beta,
        )
        if side == "short_a_long_b":
            qty_a, qty_b = -abs(shares_a), abs(shares_b)
        else:
            qty_a, qty_b = abs(shares_a), -abs(shares_b)

        fills = [
            self.broker.submit_market(pair.symbol_a, qty_a, prices[pair.symbol_a]),
            self.broker.submit_market(pair.symbol_b, qty_b, prices[pair.symbol_b]),
        ]
        payload = {
            "pair_id": pair.id,
            "side": side,
            "shares_a": qty_a,
            "shares_b": qty_b,
            "entry_z": analysis["zscore"],
            "entry_spread": analysis["spread"],
            "beta": analysis["beta"],
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "holding_days": 0,
        }
        self.store.upsert_pair_position(payload)
        self.store.add_trade(pair.id, "enter", side, {"fills": fills, **payload})
        self.log(
            f"ENTRY {pair.id} {side} | z={analysis['zscore']:.2f} β={analysis['beta']:.3f} "
            f"| {qty_a:+.2f} {pair.symbol_a} / {qty_b:+.2f} {pair.symbol_b} "
            f"| ADF p={analysis['adf_pvalue']:.3f}"
        )

    def _execute_exit(self, pair, pos: dict, reason: str, analysis: dict | None, prices: dict[str, float]) -> None:
        fills = [
            self.broker.submit_market(pair.symbol_a, -float(pos["shares_a"]), prices[pair.symbol_a]),
            self.broker.submit_market(pair.symbol_b, -float(pos["shares_b"]), prices[pair.symbol_b]),
        ]
        z = analysis["zscore"] if analysis else float("nan")
        self.store.delete_pair_position(pair.id)
        self.store.add_trade(pair.id, "exit", reason, {"fills": fills, "zscore": z})
        self.log(f"EXIT {pair.id} {reason} | z={z:.2f} | closed both legs")

    def cycle(self) -> dict:
        with self._lock:
            session = market_session()
            symbols = all_symbols()
            try:
                self.data.load_history(symbols)
            except Exception as exc:
                self.log(f"History load warning: {exc}", "warn")
            prices = self.data.last_prices(symbols)
            account = self.mark_to_market(prices)
            open_pairs = self.store.pair_positions()
            analyses: list[dict] = []

            for pair in PAIRS:
                if not pair.active:
                    state = {
                        "pair_id": pair.id,
                        "sector": pair.sector,
                        "symbol_a": pair.symbol_a,
                        "symbol_b": pair.symbol_b,
                        "name_a": pair.name_a,
                        "name_b": pair.name_b,
                        "active": False,
                        "tradable": False,
                        "notes": pair.notes,
                        "is_cointegrated": False,
                    }
                    analyses.append(state)
                    self.store.set_pair_state(pair.id, state)
                    continue

                pa = prices.get(pair.symbol_a)
                pb = prices.get(pair.symbol_b)
                if not pa or not pb:
                    state = {
                        "pair_id": pair.id,
                        "sector": pair.sector,
                        "symbol_a": pair.symbol_a,
                        "symbol_b": pair.symbol_b,
                        "error": "missing_price",
                        "tradable": False,
                    }
                    analyses.append(state)
                    self.store.set_pair_state(pair.id, state)
                    continue

                try:
                    analysis = self.analyzer.analyze(
                        pair,
                        self.data.history_for(pair.symbol_a),
                        self.data.history_for(pair.symbol_b),
                        pa,
                        pb,
                    )
                except Exception as exc:
                    analysis = {
                        "pair_id": pair.id,
                        "error": str(exc),
                        "is_cointegrated": False,
                        "tradable": False,
                    }
                analysis["active"] = True
                analysis["open"] = pair.id in open_pairs
                analyses.append(analysis)
                self.store.set_pair_state(pair.id, {k: v for k, v in analysis.items() if k not in ("spread_series", "z_series")})

            # Trading decisions — only route when the NYSE cash session is open.
            actions = []
            if session["is_open"] or settings.broker == "sim":
                overlapping = set()
                for pid, pos in open_pairs.items():
                    spec = next((p for p in active_pairs() if p.id == pid), None)
                    if spec:
                        overlapping.add(spec.symbol_a)
                        overlapping.add(spec.symbol_b)

                for pair in active_pairs():
                    analysis = next((a for a in analyses if a.get("pair_id") == pair.id), None)
                    if not analysis or analysis.get("error"):
                        continue
                    z = analysis.get("zscore")
                    if z is None or z != z:
                        continue
                    pos = open_pairs.get(pair.id)
                    holding = self._holding_days(pos["opened_at"]) if pos else 0
                    if pos:
                        force, why = self.risk.should_force_exit(
                            holding_days=holding,
                            zscore=z,
                            still_cointegrated=bool(analysis.get("is_cointegrated")),
                        )
                        if force:
                            self._execute_exit(pair, pos, why or "risk", analysis, prices)
                            actions.append({"pair_id": pair.id, "action": "exit", "reason": why})
                            continue
                    signal = evaluate_signal(
                        pair_id=pair.id,
                        zscore=z,
                        prev_z=analysis.get("prev_z"),
                        is_cointegrated=bool(analysis.get("is_cointegrated")),
                        has_position=bool(pos),
                        position_side=pos["side"] if pos else None,
                    )
                    if signal.action == "exit" and pos:
                        self._execute_exit(pair, pos, signal.reason, analysis, prices)
                        actions.append({"pair_id": pair.id, "action": "exit", "reason": signal.reason})
                    elif signal.action.startswith("enter") and not pos:
                        stacked = None
                        for open_id in open_pairs:
                            stacked = spread_correlation(analyses, pair.id, open_id)
                            if stacked is not None and abs(stacked) > settings.pair_spread_corr_limit:
                                break
                        ok, reason = self.risk.can_open(
                            pair,
                            open_pair_ids=list(open_pairs.keys()),
                            equity=account["equity"],
                            gross_exposure=account["gross_exposure"],
                            overlapping_tickers=overlapping,
                            stacked_corr=stacked,
                        )
                        if not ok:
                            self.log(f"SKIP {pair.id} {signal.action} blocked by {reason}", "warn")
                            continue
                        self._execute_entry(pair, analysis, signal.side or "short_a_long_b", prices)
                        overlapping.add(pair.symbol_a)
                        overlapping.add(pair.symbol_b)
                        open_pairs = self.store.pair_positions()
                        actions.append({"pair_id": pair.id, "action": signal.action, "reason": signal.reason})

            account = self.mark_to_market(prices)
            snapshot = {
                "session": session,
                "account": account,
                "pairs": analyses,
                "pair_positions": self.store.pair_positions(),
                "actions": actions,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            self.last_cycle = snapshot
            return snapshot

    def _loop(self) -> None:
        self.log(f"AI operator online for account '{settings.account_name}'")
        while self.running:
            try:
                self.cycle()
            except Exception:
                self.log(traceback.format_exc(), "error")
            for _ in range(settings.engine_interval_seconds):
                if not self.running:
                    break
                time.sleep(1)
        self.log("AI operator paused")

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="pair-operator")
        self._thread.start()

    def stop(self) -> None:
        self.running = False

    def flatten_all(self) -> None:
        prices = self.data.last_prices()
        for pair in active_pairs():
            pos = self.store.pair_positions().get(pair.id)
            if pos and pair.symbol_a in prices and pair.symbol_b in prices:
                self._execute_exit(pair, pos, "manual_flatten", None, prices)


engine = TradingEngine()
