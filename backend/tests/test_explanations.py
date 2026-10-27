"""AI explanation texts: facts, template, validation, cache, budget and endpoints (Claude via MockTransport)."""
import httpx
import pytest
from sqlalchemy import select

from app.adapters import registry
from app.config import get_settings
from app.db import SessionLocal
from app.explain_facts import forecast_facts_text, forecast_template, pattern_facts_text, pattern_template, validate
from app.explain_service import MODEL, ClaudeExplainSource
from app.models import AiExplanation, LlmUsage, PatternDetection
from tests.conftest import login
from tests.test_forecast_api import run as run_forecast
from tests.test_forecast_api import seed as seed_forecast
from tests.test_pattern_api import run_scan, seed


@pytest.fixture()
def claude(monkeypatch):
    """Registers the explanation source with a key; handler(request) -> text. Returns (calls, set_handler)."""
    state = {"calls": [], "text": None}

    def install(text_fn=None, budget="10", tin=1500, tout=300, stop_reason="end_turn"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("CLAUDE_MONTHLY_BUDGET_USD", budget)
        get_settings.cache_clear()

        def handler(req: httpx.Request) -> httpx.Response:
            state["calls"].append(req.read().decode())
            facts = state["calls"][-1]
            text = text_fn(facts) if text_fn else ""
            return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
                                             "usage": {"input_tokens": tin, "output_tokens": tout}})

        registry.clear()
        registry.register(ClaudeExplainSource(transport=httpx.MockTransport(handler), sleep=lambda _s: None))

    yield state, install
    registry.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()


def setup_pattern(client):
    iid, _ = seed()
    run_scan(iid)
    login(client)
    body = client.get(f"/api/instruments/{iid}/patterns").json()
    det = next(d for d in body["detections"] if d["pattern_type"] == "doppelboden")
    return iid, det


def test_template_passes_own_validation_and_is_neutral(client):
    _, det = setup_pattern(client)
    facts = pattern_facts_text(det)
    tpl = pattern_template(det)
    assert validate(tpl, facts) is None
    assert "Double bottom" in tpl and "investment advice" in tpl
    assert det["backtest"]["status"] == "nicht_berechnet" and "not calculated" in facts


def test_symmetric_triangle_levels_are_breakouts_not_invalidation(client):
    _, det = setup_pattern(client)
    det = {**det, "pattern_type": "dreieck_symmetrisch", "name": "Symmetrical triangle",
           "direction_if_confirmed": "offen"}
    facts, tpl = pattern_facts_text(det), pattern_template(det)
    assert "Upper breakout level" in facts and "Lower breakout level" in facts
    assert "\nInvalidation level:" not in facts and "Invalidation level" not in tpl
    assert "breakout to the downside" in tpl
    assert validate(tpl, facts) is None


def test_validate_rejects_invented_numbers_dates_and_advice():
    facts = "Low 1: 142.10 on 2026-09-03, confidence 74%, sample 41 cases"
    ok = ("The first low was at 142.10 on 2026-09-03, the confidence is 74% over 41 historical cases. "
          "Whether the pattern is confirmed is open and subject to uncertainty; there are two possible scenarios.")
    assert validate(ok, facts) is None
    assert "number 143.50" in validate(ok.replace("142.10", "143.50"), facts)
    assert "date" in validate(ok.replace("2026-09-03", "2026-09-04"), facts)
    assert validate(ok.replace("open", "a clear buy signal"), facts) == "contains inadmissible language"
    assert validate(ok + " We recommend acting now.", facts) == "contains inadmissible language"
    assert validate(ok + " Mehr: https://example.org", facts) == "contains a link"
    assert validate("Zu kurz.", facts) == "length outside the permitted range"
    # Number words as digits (up to 10) are free, large foreign numbers are not
    assert validate(ok.replace("two", "999"), facts).startswith("number 999")


def test_without_key_returns_labeled_template_and_stores_nothing(client, claude):
    _, det = setup_pattern(client)
    r = client.get(f"/api/patterns/{det['id']}/explanation")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "vorlage" and "no AI" in body["label"]
    assert body["fallback_reason"] == "No API key set" and body["model_name"] is None
    assert body["text"] == pattern_template(client.get(f"/api/patterns/{det['id']}").json())
    with SessionLocal() as db:
        assert db.scalars(select(AiExplanation)).all() == []


def test_ai_text_generated_once_cached_labeled_and_cost_counted(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " This statement is uncertain and only describes the calculation.")
    first = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert first["source"] == "ki" and first["label"] == "AI-generated (Claude Sonnet 5.5)"
    assert first["model_version"] == MODEL and first["fallback_reason"] is None
    assert first["cost_usd"] == pytest.approx((1500 * 2 + 300 * 10) / 1e6)
    assert first["budget"]["spent_usd"] == pytest.approx(first["cost_usd"], abs=1e-4)
    second = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert second["text"] == first["text"] and second["generated_at"] == first["generated_at"]
    assert len(state["calls"]) == 1  # only once per data state
    assert MODEL in state["calls"][0] and "Facts of the automatic analysis" in state["calls"][0]
    with SessionLocal() as db:
        assert len(db.scalars(select(AiExplanation)).all()) == 1
        assert db.get(LlmUsage, first["budget"]["month"]).cost_usd > 0


def test_new_data_state_gets_new_text(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " This statement is uncertain and only describes the calculation.")
    client.get(f"/api/patterns/{det['id']}/explanation")
    with SessionLocal() as db:
        d = db.get(PatternDetection, det["id"])
        d.status_reason = d.status_reason + " Zusatz"
        db.commit()
    client.get(f"/api/patterns/{det['id']}/explanation")
    assert len(state["calls"]) == 2


def test_forbidden_or_invented_ai_text_falls_back_to_template_and_is_cached(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " This is a clear buy signal with price target 200.")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "rejected" in body["fallback_reason"]
    assert "buy signal" not in body["text"] and body["cost_usd"] > 0
    client.get(f"/api/patterns/{det['id']}/explanation")
    assert len(state["calls"]) == 1  # a discarded text is not paid for again

    with SessionLocal() as db:
        d = db.get(PatternDetection, det["id"])
        d.status_reason += " Zweiter Stand"
        db.commit()
    install(lambda body: pattern_template(det) + " The price then rises to 999.99.")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "999.99" in body["fallback_reason"]


def test_truncated_ai_text_falls_back_to_template(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    # A text cut off at max_tokens can pass validation but ends mid-sentence.
    install(lambda body: pattern_template(det)[:400], stop_reason="max_tokens")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "max_tokens" in body["fallback_reason"]
    assert body["text"].endswith("investment advice.") and body["cost_usd"] > 0


def test_budget_exhausted_uses_template_without_calling_api(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: "x", budget="0.001")
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and body["fallback_reason"] == "Monthly limit reached"
    assert state["calls"] == []
    assert registry.get_adapter("claude_explain").budget_exhausted is True
    assert registry.get_adapter("claude_explain").health().status == "degraded"


def test_api_error_falls_back_and_is_retried_next_time(client, claude, monkeypatch):
    state, install = claude
    _, det = setup_pattern(client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    get_settings.cache_clear()
    registry.clear()
    registry.register(ClaudeExplainSource(transport=httpx.MockTransport(lambda r: httpx.Response(500)),
                                          sleep=lambda _s: None))
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and body["fallback_reason"] == "AI service currently unreachable"
    with SessionLocal() as db:
        assert db.scalars(select(AiExplanation)).all() == []


def test_pattern_explanation_404_and_login(client):
    assert client.get("/api/patterns/1/explanation").status_code == 401
    login(client)
    assert client.get("/api/patterns/999/explanation").status_code == 404
    assert client.get("/api/instruments/999/forecast/explanation").status_code == 404


def test_forecast_explanation(client, claude):
    state, install = claude
    iid, _ = seed_forecast()
    login(client)
    assert client.get(f"/api/instruments/{iid}/forecast/explanation").status_code == 404  # not calculated yet
    run_forecast(iid)
    f = client.get(f"/api/instruments/{iid}/forecast").json()
    facts = forecast_facts_text({**f, "steps": f["steps"]}, "SAP")
    tpl = forecast_template(f, "SAP")
    assert validate(tpl, facts) is None
    assert "probability ranges" in facts and "single forecast" in tpl
    body = client.get(f"/api/instruments/{iid}/forecast/explanation").json()
    assert body["source"] == "vorlage" and body["text"] == tpl
    install(lambda b: tpl + " The values are uncertain.")
    body = client.get(f"/api/instruments/{iid}/forecast/explanation").json()
    assert body["source"] == "ki" and body["label"].startswith("AI-generated")
    client.get(f"/api/instruments/{iid}/forecast/explanation")
    assert len(state["calls"]) == 1


def test_demo_data_never_uses_ai(client, claude):
    state, install = claude
    _, det = setup_pattern(client)
    install(lambda body: pattern_template(det) + " This statement is uncertain and only describes the calculation.")
    with SessionLocal() as db:
        db.get(PatternDetection, det["id"]).is_demo = True
        db.commit()
    body = client.get(f"/api/patterns/{det['id']}/explanation").json()
    assert body["source"] == "vorlage" and "demo mode" in body["fallback_reason"] and state["calls"] == []
