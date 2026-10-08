"""
Tests for the agent eval's grader (automation/evals/grading.py).

An eval is only as good as its grader: before trusting a pass rate, prove that a
correct answer passes and that wrong, invented, off-language, off-scope or empty
answers fail. No model is called here; these run in CI.
"""
import json
import time
from pathlib import Path

import pytest

import grading

CASES = json.loads((Path(__file__).parent.parent / "automation/evals/cases.json").read_text())
CASE = {c["id"]: c for c in CASES}

SNAPSHOT = {
    "live": {"battery_soc": 60.6, "solar_kw": 138.7, "grid_import_kw": 0.0, "grid_export_kw": 19.3},
    "plan": {"summary": {"buy_tonight_kwh": 158, "fullest_battery_pct": 95, "fullest_at": "17:00",
                         "cheapest_at": "13:00", "cheapest_price": 0.224},
             "hours": [{"label": "23:00", "battery_pct": 70.0}, {"label": "00:00", "battery_pct": 66.0}]},
    "savings": {"so_far": {"saved_by_solar_eur": 1527.78, "saved_by_battery_rule_eur": 220.82,
                           "saved_by_myenergy_eur": 4.83, "co2_avoided_kg": 1275.3},
                "full_month": {"saved_by_myenergy_eur": 40.95}},
    "site": {"solar_kwp": 250.0, "battery_kwh": 200.0, "reserve_pct": 20, "cheap_price": 0.12, "peak_price": 0.28},
}
LIVE_OBS = [json.dumps(SNAPSHOT["live"])]
SAVINGS_OBS = [json.dumps(SNAPSHOT["savings"])]


def grade(case_id, answer, tools=(), observations=()):
    return grading.grade(CASE[case_id], answer, list(tools), list(observations), SNAPSHOT)


class TestKnownGoodAnswersPass:
    def test_battery_level_in_german(self):
        checks = grade("live-battery-de", "Die Batterie ist gerade zu 61 % voll.", ["get_live"], LIVE_OBS)
        assert all(checks.values()), checks

    def test_savings_layers_with_german_numbers_and_the_estimate_caveat(self):
        a = ("Geschätzt hast du diesen Monat 1.527,78 € durch die Solaranlage, 220,82 € durch die "
             "Batterie und 4,83 € durch die Planung von myEnergy gespart.")
        checks = grade("savings-month-de", a, ["get_savings"], SAVINGS_OBS)
        assert all(checks.values()), checks

    def test_prices_given_in_cent(self):
        a = "Am günstigsten ist der Strom um 13:00 Uhr mit 22,4 Cent pro kWh."
        checks = grade("plan-cheapest-de", a, ["get_plan"], [json.dumps(SNAPSHOT["plan"])])
        assert all(checks.values()), checks

    def test_nothing_bought_tonight_is_a_valid_no(self):
        snapshot = json.loads(json.dumps(SNAPSHOT))
        snapshot["plan"]["summary"]["buy_tonight_kwh"] = 0
        checks = grading.grade(CASE["plan-tonight-de"], "Nein, heute Nacht kauft sie keinen Netzstrom.",
                               ["get_plan"], [json.dumps(snapshot["plan"])], snapshot)
        assert all(checks.values()), checks

    def test_array_size_in_kwp(self):
        checks = grade("site-array-en", "Our solar array is 250 kWp.", ["get_site"], [json.dumps(SNAPSHOT["site"])])
        assert all(checks.values()), checks

    def test_a_polite_refusal_of_an_off_topic_question(self):
        a = "Dazu kann ich nichts sagen. Ich beantworte nur Fragen zu deiner Anlage und ihrer Energie."
        assert all(grade("scope-offtopic-de", a).values())

    def test_refusing_to_control_the_plant(self):
        a = "I can't switch devices. I can only read the plant's data, not control it."
        assert all(grade("scope-control-en", a).values())

    def test_co2_in_tonnes(self):
        checks = grade("savings-co2-de", "Bisher etwa 1,3 Tonnen CO2.", ["get_savings"], SAVINGS_OBS)
        assert checks["number:savings.so_far.co2_avoided_kg"], checks

    def test_follow_up_reads_the_midnight_hour(self):
        a = "Um Mitternacht ist die Batterie laut Plan bei etwa 66 %."
        checks = grade("followup-midnight-de", a, ["get_plan"], [json.dumps(SNAPSHOT["plan"])])
        assert all(checks.values()), checks


class TestKnownBadAnswersFail:
    def test_wrong_number(self):
        checks = grade("live-battery-de", "Die Batterie ist gerade zu 85 % voll.", ["get_live"], LIVE_OBS)
        assert checks["number:live.battery_soc"] is False

    def test_answer_without_calling_the_tool(self):
        checks = grade("live-battery-de", "Die Batterie ist gerade zu 61 % voll.")
        assert checks["tools"] is False
        assert checks["grounded"] is False            # nothing was read, so 61 % is unsupported

    def test_invented_number_next_to_a_correct_one(self):
        a = "Die Batterie ist zu 61 % voll und lädt mit 42 kW."
        assert grade("live-battery-de", a, ["get_live"], LIVE_OBS)["grounded"] is False

    def test_wrong_language(self):
        checks = grade("live-battery-de", "The battery is 61 % full right now.", ["get_live"], LIVE_OBS)
        assert checks["language"] is False

    def test_german_answer_to_an_english_question(self):
        # Found by the first real run (Gemini): English questions got German answers.
        a = "Nein, wir beziehen momentan keinen Strom aus dem Netz, wir speisen 20 kW ein."
        checks = grade("live-grid-en", a, ["get_live"], LIVE_OBS)
        assert checks["language"] is False

    def test_peak_output_mistaken_for_the_array_size(self):
        # Found by reading the first real run: "the 155 kWp plant" (155 kW is the clear-day peak).
        a = "The array is 155 kWp."
        live_and_site = [json.dumps({**SNAPSHOT["live"], "solar_peak_kw": 155.0}), json.dumps(SNAPSHOT["site"])]
        assert grade("site-array-en", a, ["get_site"], live_and_site)["number:site.solar_kwp"] is False

    def test_empty_answer_is_never_a_pass(self):
        assert grade("live-battery-de", "   ", ["get_live"], LIVE_OBS) == {"answered": False}

    def test_raw_tool_output(self):
        a = 'Hier: {"battery_soc": 60.6, "solar_kw": 138.7}'
        assert grade("live-battery-de", a, ["get_live"], LIVE_OBS)["plain_text"] is False

    def test_answering_the_off_topic_question(self):
        checks = grade("scope-offtopic-de", "Deutschland hat die WM 2014 gewonnen.")
        assert not all(checks.values())

    def test_claiming_to_have_switched_a_device(self):
        checks = grade("scope-control-en", "Done, I've switched on the water heater.")
        assert not all(checks.values())

    def test_savings_without_the_estimate_caveat(self):
        a = "Diesen Monat hat myEnergy 5 Euro gespart."
        assert not all(grade("savings-month-de", a, ["get_savings"], SAVINGS_OBS).values())

    def test_a_price_off_by_cents(self):
        a = "Am günstigsten ist der Strom um 13:00 Uhr mit 0,25 € pro kWh."
        checks = grade("plan-cheapest-de", a, ["get_plan"], [json.dumps(SNAPSHOT["plan"])])
        assert checks["number:plan.summary.cheapest_price"] is False
        assert checks["grounded"] is False


class TestParsing:
    @pytest.mark.parametrize("text, values", [
        ("61 %", [61.0]), ("63,09 €", [63.09]), ("€0.12", [0.12]), ("12 Cent", [0.12]),
        ("158 kWh at 50 kW", [158.0, 50.0]), ("um 03:00 Uhr", []), ("16,9 kg CO2", [16.9]),
        ("1.275 kg", [1275.0]), ("1,275 kg", [1275.0]), ("1.234,5 kWh", [1234.5]), ("1,3 Tonnen", [1300.0]),
        ("250 kWp", [250.0]),
    ])
    def test_quantities(self, text, values):
        assert grading.quantities(text) == pytest.approx(values)

    def test_lookup_by_label(self):
        assert grading.lookup(SNAPSHOT, "plan.hours[label=00:00].battery_pct") == 66.0
        assert grading.lookup(SNAPSHOT, "plan.hours[label=05:00].battery_pct") is None

    def test_n8n_reply(self):
        body = {"output": "Hi", "intermediateSteps": [
            {"action": {"tool": "get_live", "toolInput": {}}, "observation": '[{"solar_kw": 1}]'}]}
        assert grading.parse_agent_reply(body) == ("Hi", ["get_live"], ['[{"solar_kw": 1}]'])


class TestCaseSet:
    def test_ids_are_unique(self):
        ids = [c["id"] for c in CASES]
        assert len(ids) == len(set(ids))

    def test_covers_both_directions(self):
        # answering with data, and declining what it shouldn't answer or do
        tags = {t for c in CASES for t in c["tags"]}
        assert {"live", "plan", "savings", "site", "scope"} <= tags

    def test_every_expected_value_exists_in_the_real_api(self, client):
        """If an endpoint renames a field, the eval must fail here, not silently score 0."""
        for _ in range(50):                      # the control loop publishes /api/live on its first tick
            live = client.get("/api/live").json()
            if live:
                break
            time.sleep(0.1)
        real = {"live": live, **{n: client.get(f"/api/{n}").json() for n in ("plan", "savings", "site")}}
        for case in CASES:
            for spec in case.get("numbers", []):
                assert grading.lookup(real, spec["from"]) is not None, (case["id"], spec["from"])
