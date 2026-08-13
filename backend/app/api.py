from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import agent
from app.clock import market_session
from app.config import settings
from app.engine import engine
from app.universe import PAIRS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


class ChatIn(BaseModel):
    message: str


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.info("Pair Trading Tester listening")
        engine.log("API online — starting AI operator")
        engine.start()
        yield
        engine.stop()

    app = FastAPI(title="Pair Trading Tester", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"ok": True, "account": settings.account_name}

    def _state_payload() -> dict:
        cycle = engine.last_cycle or {
            "session": market_session(),
            "account": {
                "name": settings.account_name,
                "broker": settings.broker,
                "cash": engine.broker.cash(),
                "equity": engine.broker.cash(),
                "gross_exposure": 0,
                "positions": [],
            },
            "pairs": [],
            "pair_positions": engine.store.pair_positions(),
            "actions": [],
            "loading": True,
        }
        return {
            **cycle,
            "logs": engine.store.recent_logs(80),
            "trades": engine.store.recent_trades(50),
            "equity_curve": engine.store.equity_curve(400),
            "universe_meta": [
                {
                    "id": p.id,
                    "sector": p.sector,
                    "symbol_a": p.symbol_a,
                    "symbol_b": p.symbol_b,
                    "name_a": p.name_a,
                    "name_b": p.name_b,
                    "active": p.active,
                    "notes": p.notes,
                }
                for p in PAIRS
            ],
            "running": engine.running,
            "loading": cycle.get("loading", engine.last_cycle is None),
            "config": {
                "z_entry": settings.z_entry,
                "z_stop": settings.z_stop,
                "z_lookback": settings.z_lookback,
                "coint_pvalue": settings.coint_pvalue,
                "max_hold_days": settings.max_hold_days,
                "max_notional_per_pair": settings.max_notional_per_pair,
                "max_open_pairs": settings.max_open_pairs,
            },
        }

    @app.get("/api/state")
    async def state():
        return _state_payload()

    @app.get("/api/quote/{symbol}")
    def quote(symbol: str):
        return engine.data.quote(symbol)

    @app.post("/api/chat")
    def chat(body: ChatIn):
        reply = agent.chat(body.message)
        engine.log(f"USER: {body.message}")
        engine.log(f"AI: {reply}")
        return {"reply": reply}

    @app.post("/api/engine/start")
    def start():
        engine.start()
        return {"running": True}

    @app.post("/api/engine/stop")
    def stop():
        engine.stop()
        return {"running": False}

    @app.post("/api/engine/cycle")
    def force_cycle():
        return engine.cycle()

    @app.post("/api/engine/flatten")
    def flatten():
        engine.flatten_all()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        try:
            while True:
                await socket.receive_text()
                await socket.send_json({"logs": engine.store.recent_logs(20), "running": engine.running})
        except WebSocketDisconnect:
            return

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
