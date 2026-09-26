"""
T3 — API tests.

Drive the real FastAPI app through its HTTP surface with TestClient. The `client`
fixture runs the app's lifespan with the network mocked. We check both happy
paths and error/validation paths (negative testing), which is where wiring bugs
and bad error handling show up.
"""
import pytest


class TestPages:
    @pytest.mark.parametrize("path", ["/", "/estimate", "/facility", "/sim", "/plan"])
    def test_html_pages_load(self, client, path):
        r = client.get(path)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


class TestReadEndpoints:
    def test_live_returns_dict(self, client):
        r = client.get("/api/live")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_history_returns_list(self, client):
        r = client.get("/api/history?minutes=60")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_forecast_returns_list(self, client):
        r = client.get("/api/forecast")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_savings_returns_dict(self, client):
        r = client.get("/api/savings")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


class TestCities:
    def test_returns_matches_for_a_query(self, client):
        r = client.get("/api/cities", params={"q": "Munich"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 1
        assert data[0]["name"] == "Munich"
        assert data[0]["priced"] is True

    def test_short_query_returns_empty(self, client):
        r = client.get("/api/cities", params={"q": "M"})
        assert r.status_code == 200
        assert r.json() == []


class TestEstimateEndpoint:
    def test_happy_path(self, client):
        r = client.post("/api/estimate", json={
            "city": "Munich", "solar_kwp": 100, "battery_kwh": 200, "monthly_kwh": 46920})
        assert r.status_code == 200
        data = r.json()
        assert data["city"] == "Munich"
        assert data["country"] == "Germany"
        assert "saved_eur" in data

    def test_blank_city_returns_error_body(self, client):
        r = client.post("/api/estimate", json={
            "city": "   ", "solar_kwp": 100, "battery_kwh": 200, "monthly_kwh": 46920})
        assert r.status_code == 200
        assert "error" in r.json()

    def test_invalid_type_is_rejected_422(self, client):
        r = client.post("/api/estimate", json={"city": "Munich", "solar_kwp": "not-a-number"})
        assert r.status_code == 422        # pydantic validation


class TestFacilitySession:
    def test_start_then_live(self, client):
        r = client.post("/api/facility/start", json={
            "city": "Munich", "solar_kwp": 100, "battery_kwh": 200, "monthly_kwh": 46920})
        assert r.status_code == 200
        sid = r.json().get("session")
        assert sid

        r2 = client.get("/api/facility/live", params={"session": sid})
        assert r2.status_code == 200
        state = r2.json()
        assert state["facility"] == "Munich"
        assert "battery_soc" in state

    def test_unknown_session_returns_error(self, client):
        r = client.get("/api/facility/live", params={"session": "nope"})
        assert r.status_code == 200
        assert "error" in r.json()

    def test_blank_city_returns_error(self, client):
        r = client.post("/api/facility/start", json={
            "city": "   ", "solar_kwp": 100, "battery_kwh": 200, "monthly_kwh": 46920})
        assert r.status_code == 200
        assert "error" in r.json()


class TestSimSession:
    """The /sim page's accelerated savings session endpoints."""

    def test_reset_then_live(self, client):
        r = client.post("/api/sim/reset", params={"session": "sim-test-1"})
        assert r.status_code == 200
        assert r.json().get("ok") is True

        r2 = client.get("/api/sim/live", params={"session": "sim-test-1", "speed": 1.0})
        assert r2.status_code == 200
        assert isinstance(r2.json(), dict)


class TestPlanEndpoint:
    """GET /api/plan: the planner's timeline, summary and story (#16)."""

    def test_returns_a_full_plan(self, client):
        d = client.get("/api/plan").json()
        assert d["available"] is True
        assert d["story"]["tone"] in ("sun", "buy", "hold")
        assert d["story"]["headline"] and d["story"]["detail"]
        assert {"buy_tonight_kwh", "buy_without_sun_kwh", "buy_from", "buy_until", "solar_to_battery_kwh",
                "fullest_battery_pct", "fullest_at"} <= d["summary"].keys()
        assert len(d["hours"]) > 0
        h = d["hours"][0]
        assert {"time", "label", "solar_kw", "load_kw", "grid_buy_kw", "battery_pct",
                "price", "cheap"} <= h.keys()
        assert all(len(x["label"]) == 5 and x["label"][2] == ":" for x in d["hours"])  # HH:MM
        assert d["site"]["timezone"] == "Europe/Berlin"

    def test_without_a_forecast_says_so_instead_of_failing(self, client, monkeypatch):
        import main
        monkeypatch.setattr(main, "forecast_cache", [])
        r = client.get("/api/plan")
        assert r.status_code == 200
        assert r.json()["available"] is False
        assert "safe rules" in r.json()["message"]

    def test_timeline_matches_the_cards(self, client):
        # The chart point at the "fullest" time must show the same level as the card,
        # and the first point is the battery level right now (values sit AT their label).
        import main
        d = client.get("/api/plan").json()
        at = {h["label"]: h for h in d["hours"]}
        s = d["summary"]
        assert round(at[s["fullest_at"]]["battery_pct"]) == s["fullest_battery_pct"]
        assert abs(d["hours"][0]["battery_pct"] - main.facility.battery_soc) < 1.0
