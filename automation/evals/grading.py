"""
Grades one answer from the "Frag deine Anlage" agent against one eval case.

Pure functions only (no network), so the grader itself is unit tested in
tests/test_eval_grading.py with known-good and known-bad answers.

Every check is scored separately, so a failing case says *why* it failed:

  tools      the agent called the tools that hold the answer
  numbers    the expected values (from a live API snapshot) appear in the answer
  grounded   every quantity in the answer (kW, kWh, %, EUR, kg) appears in what
             the tools returned, so nothing was invented
  language   the answer is in the language of the question
  must_match / must_not_match   case-specific patterns (scope, refusals, caveats)
  length     the answer stays short
  plain_text the answer is sentences, not raw JSON from a tool
"""
import json
import re

TOL_DEFAULT = 1.0

# A quantity with a unit: "61 %", "158 kWh", "250 kWp", "0,12 €", "12 Cent", "16,9 kg".
_UNIT = r"(kWh|kWp|kW|%|Prozent|percent|€|EUR|Euro|Cent|ct|kg|Tonnen|tonnes|tons|t)"
# 1.275 (German thousands), 1,275 (English thousands), 1 275, or a plain 61 / 0,12 / 16.9
_NUM = r"(\d{1,3}(?:[.,\u202f\u00a0 ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
_QTY_AFTER = re.compile(_NUM + r"\s*" + _UNIT + r"(?![A-Za-z])", re.IGNORECASE)
_QTY_BEFORE = re.compile(r"(€|EUR)\s*" + _NUM, re.IGNORECASE)
_ANY_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# Clock times and timestamps are not quantities: "03:00", "13.00 Uhr", "2026-10-04T10:00:00+00:00".
# (A dot alone is not a time: 0.12 is a price.)
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T[\d:.+-]+Z?|\b\d{1,2}:\d{2}\b|\b\d{1,2}\.\d{2}\s*Uhr\b")
_JSON = re.compile(r'[{\[]\s*"\w+"\s*:')            # raw tool output pasted into the answer

_DE = {"der", "die", "das", "und", "ist", "nicht", "gerade", "heute", "nacht", "wird", "du",
       "batterie", "strom", "aus", "mit", "noch", "bis", "um", "sie", "es", "wir", "ein", "eine"}
_EN = {"the", "and", "is", "not", "right", "now", "today", "tonight", "will", "you", "battery",
       "power", "from", "with", "still", "until", "at", "it", "we", "a", "an", "of", "are"}


def _to_float(s: str) -> float:
    """'61', '0,12', '16.9', and thousands written either way: '1.275', '1,275', '1 275'."""
    s = re.sub(r"[\u202f\u00a0 ]", "", s)
    groups = re.fullmatch(r"\d{1,3}([.,])\d{3}(?:\1\d{3})*(?:([.,])\d+)?", s)
    if groups and (groups.group(2) or len(s.split(groups.group(1))) > 2 or not s.startswith("0")):
        decimal = groups.group(2)
        whole, _, frac = s.rpartition(decimal) if decimal else (s, "", "")
        return float(whole.replace(".", "").replace(",", "") + ("." + frac if frac else ""))
    return float(s.replace(",", "."))


def quantities(text: str) -> list:
    """Every number written with a unit, as plain values (Cent converted to EUR)."""
    text = _TIME.sub(" ", text)                      # 03:00 is a time, not a quantity
    found = []
    for num, unit in _QTY_AFTER.findall(text):
        v = _to_float(num)
        unit = unit.lower()
        found.append(v / 100 if unit in ("cent", "ct") else v * 1000 if unit in ("t", "tonnen", "tonnes", "tons") else v)
    for _, num in _QTY_BEFORE.findall(text):
        found.append(_to_float(num))
    return found


def numbers_in(observations: list) -> list:
    """Every number in the tool results (JSON text)."""
    return [float(n) for obs in observations for n in _ANY_NUM.findall(_TIME.sub(" ", obs))]


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= max(tol, abs(b) * 0.02)


def _rounds_to(said: float, source: float) -> bool:
    """Could `said` be `source` rounded for a person? Prices keep their cents."""
    return _close(said, source, 0.005 if abs(source) < 1 else 0.6)


def lookup(snapshot: dict, path: str):
    """'live.battery_soc' or 'plan.hours[label=00:00].battery_pct' -> value."""
    node = snapshot
    for part in path.split("."):
        m = re.fullmatch(r"(\w+)\[(\w+)=([^\]]+)\]", part)
        if m:
            key, field, want = m.groups()
            node = next((x for x in node[key] if str(x.get(field)) == want), None)
            if node is None:
                return None
        else:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                return None
    return node


def detect_language(text: str) -> str:
    words = re.findall(r"[a-zäöüß]+", text.lower())
    de = sum(w in _DE for w in words) + 3 * sum(c in "äöüß" for c in text.lower())
    en = sum(w in _EN for w in words)
    return "de" if de > en else "en"


def grade(case: dict, answer: str, tools_called: list, observations: list, snapshot: dict) -> dict:
    """Return {check_name: True/False} for every check this case asks for."""
    checks = {}
    text = answer or ""

    if not text.strip():                       # no answer is never a pass
        return {"answered": False}
    checks["answered"] = True

    if "tools" in case:
        checks["tools"] = all(t in tools_called for t in case["tools"])
    if "tools_any" in case:
        checks["tools"] = any(t in tools_called for t in case["tools_any"])

    said = quantities(text)
    for spec in case.get("numbers", []):
        expected = lookup(snapshot, spec["from"])
        name = "number:" + spec["from"]
        if expected is None:
            checks[name] = False
        elif expected == 0 and spec.get("zero_means"):
            checks[name] = re.search(spec["zero_means"], text, re.IGNORECASE) is not None
        else:
            tol = spec.get("tol", TOL_DEFAULT)
            checks[name] = any(_close(v, float(expected), tol) for v in said)

    if case.get("grounded", True) and said:
        seen = numbers_in(observations) + [float(n) for n in _ANY_NUM.findall(case.get("question", ""))]
        checks["grounded"] = all(any(_rounds_to(v, s) for s in seen) for v in said)

    if "language" in case:
        checks["language"] = detect_language(text) == case["language"]

    for pattern in case.get("must_match", []):
        checks["must_match:" + pattern] = re.search(pattern, text, re.IGNORECASE) is not None
    for pattern in case.get("must_not_match", []):
        checks["must_not_match:" + pattern] = re.search(pattern, text, re.IGNORECASE) is None

    checks["length"] = len(text.split()) <= case.get("max_words", 120)
    checks["plain_text"] = _JSON.search(text) is None
    return checks


def parse_agent_reply(body: dict) -> tuple:
    """n8n chat reply -> (answer, tools called, tool results as text)."""
    steps = body.get("intermediateSteps") or []
    tools = [s.get("action", {}).get("tool") for s in steps]
    observations = [s["observation"] if isinstance(s.get("observation"), str)
                    else json.dumps(s.get("observation")) for s in steps]
    return body.get("output", ""), [t for t in tools if t], observations
