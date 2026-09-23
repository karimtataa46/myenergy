"""
T3 — API tests.

Drive the real FastAPI app through its HTTP surface with TestClient. The `client`
fixture runs the app's lifespan with the network mocked. We check both happy
paths and error/validation paths (negative testing), which is where wiring bugs
and bad error handling show up.
"""
import pytest


class TestPages:
    @pytest.mark.parametrize("path", ["/", "/estimate", "/facility", "/sim"])
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
