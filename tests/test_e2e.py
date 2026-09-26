"""
T4 — end-to-end browser tests with Playwright.

Unlike the API tests (in-process TestClient), these drive a REAL headless browser
against a REAL running server (the `live_server` fixture), exercising the whole
stack at once: HTML + JavaScript + the API + the engine. This is the narrow top
of the test pyramid — highest fidelity, slowest, so we keep it to a few.
"""
import re

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_estimate_flow_opens_live_dashboard(page, live_server):
    # 1. open the estimate page
    page.goto(live_server + "/estimate")
    submit = page.get_by_role("button", name="See my facility live")
    expect(submit).to_be_visible()

    # 2. submit the prefilled form (Munich / 100 kWp / 200 kWh / 46,920 kWh)
    submit.click()

    # 3. it should navigate to the live facility dashboard
    page.wait_for_url("**/facility**", timeout=15000)

    # 4. the dashboard fills with live data: the hero % goes from "—" to a number,
    #    which proves the whole pipeline ran (session -> live poll -> render)
    expect(page.locator("#hero-pct")).to_have_text(re.compile(r"\d"), timeout=20000)


@pytest.mark.e2e
def test_city_autocomplete_shows_suggestions(page, live_server):
    page.goto(live_server + "/estimate")
    box = page.locator("#city")
    box.click()
    box.fill("")
    box.type("Mun", delay=60)          # typing triggers the debounced /api/cities call
    expect(page.locator("#cities")).to_contain_text("Munich", timeout=10000)


# ── /plan: the plan dashboard (#17) ───────────────────────────────────────────

@pytest.mark.e2e
def test_plan_page_shows_the_plan_the_api_computed(page, live_server):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    api = page.request.get(live_server + "/api/plan").json()

    page.goto(live_server + "/plan")
    expect(page.locator("#story-headline")).to_have_text(api["story"]["headline"], timeout=15000)
    expect(page.locator("#story-detail")).to_have_text(api["story"]["detail"])
    expect(page.locator("#k-buy")).to_have_text(f"{api['summary']['buy_tonight_kwh']} kWh")
    expect(page.locator("#k-full")).to_have_text(f"{api['summary']['fullest_battery_pct']}%")
    expect(page.locator("#plan-chart")).to_be_visible()
    expect(page.locator("#chart-title")).to_have_text(f"The next {len(api['hours'])} hours")
    assert errors == [], f"console errors: {errors}"


@pytest.mark.e2e
def test_plan_page_explains_when_there_is_no_forecast(page, live_server, monkeypatch):
    import main
    monkeypatch.setattr(main, "forecast_cache", [])      # the server has no forecast yet
    page.goto(live_server + "/plan")
    expect(page.locator("#status")).to_contain_text("safe rules", timeout=15000)
    expect(page.get_by_role("button", name="Check again")).to_be_visible()
    expect(page.locator("#content")).to_be_hidden()


@pytest.mark.e2e
def test_plan_page_keeps_the_last_plan_when_the_connection_drops(page, live_server):
    page.goto(live_server + "/plan")
    expect(page.locator("#story-headline")).not_to_be_empty(timeout=15000)

    page.route("**/api/plan", lambda route: route.abort())   # the server becomes unreachable
    page.evaluate("loadPlan()")
    expect(page.locator("#conn")).to_contain_text("Showing the last plan", timeout=10000)
    expect(page.locator("#content")).to_be_visible()        # the plan stays on screen
