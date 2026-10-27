"""Timestamps are UTC in the database and come back from the API with a time zone (Grundregel 2: correct
publication and fetch times). SQLite stores no time zone; without conversion an RSS time
with "+0200" ended up two hours too late in the database, and the API returned times without "Z",
which the browser read as local time."""
from datetime import UTC, datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Instrument, PriceBar, Quote, Source
from tests.conftest import login

BERLIN_SUMMER = timezone(timedelta(hours=2))


def test_offset_is_converted_to_utc_and_read_back_with_timezone(client):
    with SessionLocal() as db:
        src = Source(key="yahoo", name="Yahoo", kind="price")
        db.add(src)
        db.flush()
        inst = Instrument(symbol="AAPL", name="Apple", exchange="XNAS", currency="USD", source_id=src.id)
        db.add(inst)
        db.flush()
        local = datetime(2026, 9, 30, 10, 0, tzinfo=BERLIN_SUMMER)  # = 08:00 UTC
        db.add(Quote(instrument_id=inst.id, price=1.0, ts_utc=local, source_id=src.id, fetched_at=local))
        db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=datetime(2026, 9, 29, tzinfo=UTC),
                        source_id=src.id, open=1, high=1, low=1, close=1, fetched_at=local))
        db.commit()
        iid = inst.id
    with SessionLocal() as db:
        q = db.query(Quote).one()
        assert q.ts_utc == datetime(2026, 9, 30, 8, 0, tzinfo=UTC) and q.ts_utc.tzinfo is not None

    login(client)
    quote = client.get(f"/api/instruments/{iid}").json()["quote"]
    assert datetime.fromisoformat(quote["ts_utc"]) == datetime(2026, 9, 30, 8, 0, tzinfo=UTC)
    assert quote["ts_utc"].endswith("Z")
    bar = client.get(f"/api/instruments/{iid}/bars").json()["bars"][0]
    assert bar["ts_utc"] == "2026-09-29T00:00:00Z"
    # Filters with a time zone are converted to UTC before comparing (00:30 Berlin = 22:30 UTC the day before)
    start = datetime(2026, 9, 29, 0, 30, tzinfo=BERLIN_SUMMER).isoformat()
    assert len(client.get(f"/api/instruments/{iid}/bars", params={"start": start}).json()["bars"]) == 1
