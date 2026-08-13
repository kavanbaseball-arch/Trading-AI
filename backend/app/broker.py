from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.config import settings
from app.store import Store


class Broker(ABC):
    @abstractmethod
    def cash(self) -> float: ...

    @abstractmethod
    def positions(self) -> dict[str, dict]: ...

    @abstractmethod
    def submit_market(self, symbol: str, qty: float, price: float) -> dict: ...


class SimBroker(Broker):
    """Internal paper ledger for the Pair Trading Tester account."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def cash(self) -> float:
        return float(self.store.get_account()["cash"])

    def positions(self) -> dict[str, dict]:
        return self.store.positions()

    def submit_market(self, symbol: str, qty: float, price: float) -> dict:
        slip = price * (settings.slippage_bps / 10_000.0)
        fill = price + slip if qty > 0 else price - slip
        pos = self.store.positions().get(symbol, {"qty": 0.0, "avg_price": 0.0})
        old_qty = float(pos["qty"])
        new_qty = old_qty + qty
        cash = self.cash() - qty * fill
        if abs(new_qty) < 1e-8:
            avg = 0.0
        elif old_qty == 0 or (old_qty > 0) != (new_qty > 0) and abs(old_qty) < abs(qty):
            avg = fill
        elif (old_qty > 0 and qty > 0) or (old_qty < 0 and qty < 0):
            avg = (abs(old_qty) * float(pos["avg_price"]) + abs(qty) * fill) / abs(new_qty)
        else:
            avg = float(pos["avg_price"])
        self.store.upsert_position(symbol, new_qty, avg)
        self.store.set_cash(cash)
        return {
            "symbol": symbol,
            "qty": qty,
            "fill": fill,
            "ts": datetime.now(timezone.utc).isoformat(),
            "broker": "sim",
        }


class AlpacaBroker(Broker):
    def __init__(self, store: Store) -> None:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        self.store = store
        self._OrderSide = OrderSide
        self._TimeInForce = TimeInForce
        self._MarketOrderRequest = MarketOrderRequest
        self.client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_api_secret,
            paper=settings.alpaca_paper,
        )

    def cash(self) -> float:
        acct = self.client.get_account()
        cash = float(acct.cash)
        self.store.set_cash(cash)
        return cash

    def positions(self) -> dict[str, dict]:
        out = {}
        for p in self.client.get_all_positions():
            out[p.symbol] = {"symbol": p.symbol, "qty": float(p.qty), "avg_price": float(p.avg_entry_price)}
            self.store.upsert_position(p.symbol, float(p.qty), float(p.avg_entry_price))
        return out

    def submit_market(self, symbol: str, qty: float, price: float) -> dict:
        side = self._OrderSide.BUY if qty > 0 else self._OrderSide.SELL
        req = self._MarketOrderRequest(
            symbol=symbol,
            qty=abs(round(qty, 4)),
            side=side,
            time_in_force=self._TimeInForce.DAY,
        )
        order = self.client.submit_order(req)
        return {
            "symbol": symbol,
            "qty": qty,
            "fill": price,
            "order_id": str(order.id),
            "ts": datetime.now(timezone.utc).isoformat(),
            "broker": "alpaca",
        }


def make_broker(store: Store) -> Broker:
    if settings.broker.lower() == "alpaca" and settings.alpaca_api_key:
        return AlpacaBroker(store)
    return SimBroker(store)
