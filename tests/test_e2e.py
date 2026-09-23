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
