"""
End-to-end browser tests with Playwright for the one operator interface (#21).

They drive a REAL headless browser against a REAL running server (the
`live_server` fixture, network mocked) and check what the operator sees:
each section answers its question, the numbers match the API, and the page
stays honest when there is no forecast or the plant can't be reached.
This is the narrow top of the test pyramid: slow and few.
"""
import pytest
from playwright.sync_api import expect

ELLIPSIS = "…"      # the loading placeholder; no value on screen should still show it

# Counts the chart's battery-line pixels (#15E6A0). "The canvas is visible" isn't
# enough: an empty chart is visible too, which is exactly the bug this guards.
BATTERY_PIXELS = """() => {
  const c = document.getElementById('plan-chart');
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4)
    if (Math.abs(d[i] - 0x15) < 40 && Math.abs(d[i + 1] - 0xE6) < 40 && Math.abs(d[i + 2] - 0xA0) < 40) n++;
  return n;
}"""


@pytest.mark.e2e
def test_the_plan_on_screen_is_what_the_api_computed(page, live_server):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))     # uncaught exceptions
    api = page.request.get(live_server + "/api/plan").json()

    page.goto(live_server + "/")
    expect(page.locator("#story-headline")).to_have_text(api["story"]["headline"], timeout=15000)
    expect(page.locator("#story-detail")).to_have_text(api["story"]["detail"])
    expect(page.locator("#k-buy")).to_have_text(f"{api['summary']['buy_tonight_kwh']} kWh")
    expect(page.locator("#k-full")).to_have_text(f"{api['summary']['fullest_battery_pct']}%")
    assert page.evaluate(BATTERY_PIXELS) > 100, "the chart didn't draw the battery line"
    assert errors == [], f"page errors: {errors}"


@pytest.mark.e2e
def test_right_now_shows_the_live_state(page, live_server):
    page.goto(live_server + "/")
    expect(page.locator("#status-text")).to_have_text("Running normally", timeout=15000)
    for tile in ("#t-solar", "#t-load", "#t-batt", "#t-grid"):
        expect(page.locator(tile)).not_to_have_text(ELLIPSIS)
    expect(page.locator("#now-reason")).not_to_have_text("Waiting for the first reading…")


@pytest.mark.e2e
def test_your_system_and_savings_are_filled_in(page, live_server):
    site = page.request.get(live_server + "/api/site").json()
    page.goto(live_server + "/")
    expect(page.locator("#plant-name")).to_have_text(site["name"], timeout=15000)
    facts = page.locator("#facts")
    expect(facts).to_contain_text(f"{round(site['solar_kwp'])} kWp")
    expect(facts).to_contain_text(f"never below {site['reserve_pct']}%")
    for device in site["devices"]:
        expect(facts).to_contain_text(device["name"])
    expect(page.locator("#s-saved")).not_to_have_text(ELLIPSIS, timeout=15000)


@pytest.mark.e2e
def test_without_a_forecast_it_says_it_runs_on_safe_rules(page, live_server, monkeypatch):
    import main
    monkeypatch.setattr(main, "forecast_cache", [])       # the server has no forecast yet
    page.goto(live_server + "/")
    expect(page.locator("#status-text")).to_have_text("No forecast: running on safe rules", timeout=15000)
    expect(page.locator("#plan-notice")).to_contain_text("safe rules")
    expect(page.locator("#plan-body")).to_be_hidden()


@pytest.mark.e2e
def test_when_the_plant_is_unreachable_it_says_so_and_keeps_the_last_plan(page, live_server):
    page.goto(live_server + "/")
    expect(page.locator("#story-headline")).not_to_be_empty(timeout=15000)

    page.route("**/api/**", lambda route: route.abort())   # the server becomes unreachable
    page.evaluate("Promise.all([loadLive(), loadPlan()])")
    expect(page.locator("#status-text")).to_have_text("Can't reach the plant", timeout=10000)
    expect(page.locator("#plan-body")).to_be_visible()     # the last plan stays on screen


# ── Ask your plant: the AI assistant ──────────────────────────────────────────
# The agent is faked inside the running server, so no model is called.

@pytest.fixture
def fake_agent(monkeypatch):
    import assistant
    import main
    replies = []
    monkeypatch.setattr(assistant, "AGENT_URL", "http://agent.test/chat")
    monkeypatch.setattr(assistant, "available", lambda: True)
    monkeypatch.setattr(assistant, "_post", lambda payload: replies.pop(0)())
    monkeypatch.setattr(main, "ask_limiter", assistant.RateLimiter())
    return replies


@pytest.mark.e2e
def test_the_assistant_stays_hidden_when_it_is_not_running(page, live_server):
    page.goto(live_server + "/")
    expect(page.locator("#status-text")).to_have_text("Running normally", timeout=15000)
    expect(page.locator("#ask-open")).to_be_hidden()


@pytest.mark.e2e
def test_asking_the_plant_a_question(page, live_server, fake_agent):
    fake_agent += [lambda: {"output": "Die Batterie ist zu 61 % voll."},
                   lambda: {"output": '<img src=x onerror="window.hacked=1"> stays text'}]
    page.goto(live_server + "/")
    page.locator("#ask-open").click(timeout=15000)
    page.get_by_role("button", name="Wie voll ist die Batterie gerade?").click()
    expect(page.locator(".msg.me").last).to_have_text("Wie voll ist die Batterie gerade?")
    expect(page.locator(".msg.bot").last).to_have_text("Die Batterie ist zu 61 % voll.")

    # The answer is model output: it must be shown as text, never run as HTML.
    page.locator("#ask-input").fill("Und morgen?")
    page.locator("#ask-input").press("Enter")
    expect(page.locator(".msg.bot").last).to_contain_text('<img src=x onerror="window.hacked=1">')
    assert page.evaluate("window.hacked") is None

    page.keyboard.press("Escape")
    expect(page.locator("#ask-panel")).to_be_hidden()
    expect(page.locator("#ask-open")).to_be_visible()


@pytest.mark.e2e
def test_when_the_assistant_fails_the_operator_reads_why(page, live_server, fake_agent):
    import urllib.error

    def n8n_down():
        raise urllib.error.URLError("connection refused")
    fake_agent.append(n8n_down)
    page.goto(live_server + "/")
    page.locator("#ask-open").click(timeout=15000)
    page.locator("#ask-input").fill("Wie voll ist die Batterie?")
    page.locator("#ask-send").click()
    expect(page.locator(".msg.bot.err")).to_contain_text("can't answer right now")
    expect(page.locator("#ask-send")).to_be_enabled()      # the operator can simply ask again
