"""
Static checks on the n8n workflows in automation/workflows/.

The workflows are code that n8n runs, so they get tests like any other code. These
catch drift between the agents and the API (a renamed endpoint, a tool the prompt
no longer mentions) and model settings that break answers, without starting n8n
or calling a model.
"""
import json
import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).parent.parent / "automation/workflows").glob("*.json"))
TRIGGERS = ("chatTrigger", "scheduleTrigger", "webhook")


def load(path):
    return json.loads(path.read_text())


def urls(wf):
    return [n["parameters"]["url"] for n in wf["nodes"] if "url" in n.get("parameters", {})]


@pytest.fixture(scope="module")
def api_paths():
    import main
    return {r.path for r in main.app.routes if "GET" in getattr(r, "methods", set())}


def test_both_workflows_exist():
    assert {p.name for p in WORKFLOWS} == {"chat-agent.json", "daily-briefing.json"}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
class TestEveryWorkflow:
    def test_every_api_call_hits_a_real_endpoint(self, path, api_paths):
        for url in urls(load(path)):
            assert url.startswith("={{ $env.MYENERGY_URL }}"), url      # no hard-coded host
            assert url.split("}}", 1)[1] in api_paths, url

    def test_connections_only_name_existing_nodes(self, path):
        wf = load(path)
        names = {n["name"] for n in wf["nodes"]}
        for source, outputs in wf["connections"].items():
            assert source in names
            for links in outputs.values():
                assert all(link["node"] in names for group in links for link in group)

    def test_every_node_is_wired_in(self, path):
        wf = load(path)
        targets = {link["node"] for outs in wf["connections"].values()
                   for links in outs.values() for group in links for link in group}
        for n in wf["nodes"]:
            if n["type"].endswith(TRIGGERS):
                assert n["name"] in wf["connections"], n["name"]      # a trigger leads somewhere
            else:
                assert n["name"] in targets or n["name"] in wf["connections"], n["name"]

    def test_no_secrets_are_committed(self, path):
        # A credential *reference* (id and name, after an export from n8n) is fine;
        # the key itself stays encrypted inside n8n and must never land in the repo.
        text = path.read_text()
        assert "sk-ant" not in text and '"apiKey"' not in text

    def test_exactly_one_language_model(self, path):
        models = [n for n in load(path)["nodes"] if n["type"].split(".")[-1].startswith("lmChat")]
        assert len(models) == 1, [n["name"] for n in models]

    def test_model_settings_the_model_accepts(self, path):
        for n in load(path)["nodes"]:
            opts = n.get("parameters", {}).get("options", {})
            if n["type"].endswith("lmChatGoogleGemini"):
                assert n["parameters"]["modelName"].startswith("models/gemini-")
                # thinking counts toward the limit, so a small one cuts answers off
                assert opts.get("maxOutputTokens", 8192) >= 8192
            if n["type"].endswith("lmChatAnthropic"):                      # if switched back to Claude
                assert n["parameters"]["model"]["value"].startswith("claude-")
                assert not {"temperature", "topK", "topP"} & opts.keys()   # rejected by Opus 5.5
                assert opts.get("thinkingMode") not in ("disabled", "manual")


class TestChatAgent:
    wf = load(Path(__file__).parent.parent / "automation/workflows/chat-agent.json")

    def tools(self):
        return {n["name"]: n for n in self.wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequestTool"}

    def test_the_prompt_names_every_tool_and_every_tool_is_described(self):
        system = next(n for n in self.wf["nodes"] if n["type"].endswith(".agent"))
        prompt = system["parameters"]["options"]["systemMessage"]
        for name, node in self.tools().items():
            assert name in prompt, name
            # n8n drops "manual" when it saves (it's the default once a description exists)
            assert node["parameters"].get("descriptionType") != "auto"
            assert len(node["parameters"]["toolDescription"]) > 100, name

    def test_the_eval_only_expects_tools_the_agent_has(self):
        cases = json.loads((Path(__file__).parent.parent / "automation/evals/cases.json").read_text())
        expected = {t for c in cases for t in c.get("tools", []) + c.get("tools_any", [])}
        assert expected <= self.tools().keys()

    def test_returns_its_tool_calls_so_the_eval_can_grade_them(self):
        agent = next(n for n in self.wf["nodes"] if n["type"].endswith(".agent"))
        assert agent["parameters"]["options"]["returnIntermediateSteps"] is True

    def test_the_prompt_has_no_em_dashes(self):
        agent = next(n for n in self.wf["nodes"] if n["type"].endswith(".agent"))
        assert not re.search("[—–]", agent["parameters"]["options"]["systemMessage"])
