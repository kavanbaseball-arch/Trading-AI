from __future__ import annotations

import json
import re

from app.config import settings
from app.engine import engine
from app.market_data import MarketData
from app.universe import get_pair


SYSTEM = """You are the AI operator of Pair Trading Tester, a market-neutral NYSE pairs-trading book.
You only describe facts from the provided account state and quotes. You never invent fills or prices.
Hard risk limits cannot be overridden: z-entry ±2, stop |z|≥3.5, max hold 20 days, dollar-neutral sizing,
cointegration required (ADF + Engle-Granger p<0.05), no stacking shared legs or highly correlated pair spreads.
Be concise, quantitative, and specific.
"""


class OperatorAgent:
    def __init__(self) -> None:
        self.data = MarketData()

    def _state_brief(self) -> str:
        cycle = engine.last_cycle or {}
        account = cycle.get("account") or engine.mark_to_market(engine.data.last_prices())
        pairs = cycle.get("pairs") or []
        open_pos = engine.store.pair_positions()
        tradable = [
            {
                "id": p.get("pair_id"),
                "z": p.get("zscore"),
                "adf_p": p.get("adf_pvalue"),
                "eg_p": p.get("engle_granger_pvalue"),
                "coint": p.get("is_cointegrated"),
                "beta": p.get("beta"),
                "px": [p.get("price_a"), p.get("price_b")],
            }
            for p in pairs
            if p.get("active")
        ]
        return json.dumps(
            {
                "account": {k: account.get(k) for k in ("name", "equity", "cash", "gross_exposure", "broker")},
                "session": cycle.get("session"),
                "open_pairs": open_pos,
                "universe": tradable,
            },
            default=str,
        )[:12000]

    def rule_based_reply(self, message: str) -> str:
        text = message.strip()
        lower = text.lower()
        quote_match = re.search(r"\b([A-Z]{1,5})\b", text.upper())
        if lower.startswith("quote") or lower.startswith("price") or "quote" in lower:
            if quote_match:
                q = self.data.quote(quote_match.group(1))
                chg = q.get("change_pct")
                chg_s = f"{chg*100:+.2f}%" if chg is not None else "n/a"
                return (
                    f"{q['symbol']} last {q['last']:.2f} ({chg_s} vs prior close) "
                    f"via {q['source']}."
                )
        if "position" in lower or "book" in lower or "exposure" in lower:
            pos = engine.store.pair_positions()
            if not pos:
                return "Pair Trading Tester has no open pair positions."
            lines = ["Open pair book:"]
            for pid, p in pos.items():
                lines.append(
                    f"- {pid} {p['side']}  A {p['shares_a']:+.2f} / B {p['shares_b']:+.2f}  "
                    f"entry z={p['entry_z']:.2f} β={p['beta']:.3f}"
                )
            return "\n".join(lines)
        pair = None
        for token in re.findall(r"[A-Z]{1,5}-[A-Z]{1,5}", text.upper()):
            pair = get_pair(token)
            if pair:
                break
        if pair or "why" in lower or "status" in lower:
            states = engine.store.all_pair_state()
            if pair and pair.id in states:
                s = states[pair.id]
                if not pair.active:
                    return f"{pair.id} is disabled: {pair.notes}"
                return (
                    f"{pair.id} ({pair.name_a} vs {pair.name_b})\n"
                    f"β={s.get('beta'):.3f}  z={s.get('zscore'):.2f}  spread={s.get('spread')}\n"
                    f"ADF p={s.get('adf_pvalue'):.4f}  Engle-Granger p={s.get('engle_granger_pvalue'):.4f}\n"
                    f"Cointegrated: {s.get('is_cointegrated')}  "
                    f"Px {pair.symbol_a} {s.get('price_a')} / {pair.symbol_b} {s.get('price_b')}"
                )
        acct = engine.store.get_account()
        n_open = len(engine.store.pair_positions())
        return (
            f"Pair Trading Tester | cash ${acct['cash']:,.0f} | broker {acct['broker']} | "
            f"{n_open} open pairs. Ask for a quote (e.g. 'quote NVDA'), a pair status "
            f"('AAPL-MSFT'), or 'positions'."
        )

    def chat(self, message: str) -> str:
        if not settings.openai_api_key:
            return self.rule_based_reply(message)
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            extra = ""
            m = re.search(r"\b([A-Z]{1,5})\b", message.upper())
            if m and len(m.group(1)) <= 5:
                try:
                    extra = "\nLive quote: " + json.dumps(self.data.quote(m.group(1)))
                except Exception:
                    extra = ""
            completion = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": f"BOOK STATE:\n{self._state_brief()}{extra}\n\nUSER:\n{message}",
                    },
                ],
            )
            return completion.choices[0].message.content or self.rule_based_reply(message)
        except Exception as exc:
            return f"{self.rule_based_reply(message)}\n\n(LLM unavailable: {exc})"


agent = OperatorAgent()
