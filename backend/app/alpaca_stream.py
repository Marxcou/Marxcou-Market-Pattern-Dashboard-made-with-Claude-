"""Live prices via Alpaca WebSocket (IEX feed). Runs in the worker in its own thread.
At most 30 symbols (limit of the free tier); the order of the watchlist decides."""
import asyncio
import json
import logging
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.adapters.base import QuoteRecord
from app.adapters.registry import all_adapters
from app.config import get_settings
from app.db import SessionLocal
from app.models import Instrument, PriceBar
from app.price_service import store_quote, watched_instruments

log = logging.getLogger("alpaca-stream")
MAX_SYMBOLS = 30
MIN_SECONDS_BETWEEN_QUOTES = 2.0  # per symbol, so the database and the interface are not flooded
URL = "wss://stream.data.alpaca.markets/v2/iex"


def parse_trades(raw: str) -> list[tuple[str, float, datetime]]:
    """Trade messages ('T': 't') -> (symbol, price, time UTC). Other message types are ignored."""
    try:
        msgs = json.loads(raw)
    except ValueError:
        return []
    out = []
    for m in msgs if isinstance(msgs, list) else []:
        if isinstance(m, dict) and m.get("T") == "t" and "S" in m and "p" in m and "t" in m:
            ts = datetime.fromisoformat(str(m["t"]).replace("Z", "+00:00")).astimezone(UTC)
            out.append((str(m["S"]), float(m["p"]), ts))
    return out


def _prev_close(symbol_id: int) -> float | None:
    with SessionLocal() as db:
        rows = db.execute(select(PriceBar.close).where(PriceBar.instrument_id == symbol_id, PriceBar.timeframe == "1d")
                          .order_by(PriceBar.ts_utc.desc()).limit(2)).scalars().all()
    return rows[1] if len(rows) > 1 else None


def handle_trade(inst_id: int, symbol: str, exchange: str, price: float, ts: datetime) -> None:
    prev = _prev_close(inst_id)
    q = QuoteRecord(symbol=symbol, exchange=exchange, price=price, ts_utc=ts, source_key="alpaca",
                    fetched_at=datetime.now(UTC), change_abs=price - prev if prev else None,
                    change_pct=(price / prev - 1) * 100 if prev else None, delay_seconds=0)
    with SessionLocal() as db:
        inst = db.get(Instrument, inst_id)
        if inst is not None:
            store_quote(db, inst, q)


async def _run_once(symbols: dict[str, tuple[int, str]]) -> None:
    import websockets

    s = get_settings()
    last_sent: dict[str, float] = {}
    async with websockets.connect(URL, open_timeout=15, ping_interval=20) as ws:
        await ws.send(json.dumps({"action": "auth", "key": s.alpaca_api_key_id, "secret": s.alpaca_api_secret_key}))
        await ws.send(json.dumps({"action": "subscribe", "trades": list(symbols)}))
        async for raw in ws:
            for sym, price, ts in parse_trades(raw if isinstance(raw, str) else raw.decode()):
                now = time.monotonic()
                if sym not in symbols or now - last_sent.get(sym, 0) < MIN_SECONDS_BETWEEN_QUOTES:
                    continue
                last_sent[sym] = now
                inst_id, exchange = symbols[sym]
                await asyncio.to_thread(handle_trade, inst_id, sym, exchange, price, ts)


def _current_symbols() -> dict[str, tuple[int, str]]:
    with SessionLocal() as db:
        insts = [i for i in watched_instruments(db) if i.exchange in ("XNYS", "XNAS")]
    return {i.symbol: (i.id, i.exchange) for i in insts[:MAX_SYMBOLS]}


def stream_forever() -> None:
    """Reconnects (with backoff) until the process ends. Without a key or watchlist nothing happens."""
    delay = 5.0
    while True:
        adapter = next((a for a in all_adapters() if a.metadata().key == "alpaca"), None)
        symbols = _current_symbols() if adapter and adapter.is_configured() else {}
        if not symbols:
            time.sleep(60)
            continue
        try:
            asyncio.run(asyncio.wait_for(_run_once(symbols), timeout=900))  # renew the symbol list every 15 min.
            delay = 5.0
        except TimeoutError:
            delay = 5.0
        except Exception as exc:  # connection drop, auth error, limit: live feed pauses, polling continues
            log.warning("Alpaca stream interrupted: %s", exc)
            time.sleep(delay)
            delay = min(delay * 2, 300.0)


def start_stream_thread() -> threading.Thread:
    t = threading.Thread(target=stream_forever, name="alpaca-stream", daemon=True)
    t.start()
    return t
