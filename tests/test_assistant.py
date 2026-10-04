"""
Tests for the AI assistant behind "Ask your plant": GET /api/assistant, POST /api/ask
and backend/assistant.py.

The agent itself (n8n + the model) is replaced by a fake, so these run in CI with no
model call. What is tested is myEnergy's side: it passes the question on, turns every
failure into a message for the operator, and limits how often people can ask.
"""
import socket
import urllib.error

import pytest

import assistant
import main

URL = "http://agent.test/webhook/chat"
SESSION = "3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(assistant, "AGENT_URL", "")
    monkeypatch.setattr(assistant, "_last_check", (float("-inf"), False))
    monkeypatch.setattr(main, "ask_limiter", assistant.RateLimiter())


@pytest.fixture
def agent(monkeypatch):
    """A configured assistant whose agent answers with whatever the test sets."""
    sent = []
    reply = {"output": "Die Batterie ist zu 61 % voll."}

    def fake_post(payload):
        sent.append(payload)
        if isinstance(reply.get("raise"), Exception):
            raise reply["raise"]
        return reply

    monkeypatch.setattr(assistant, "AGENT_URL", URL)
    monkeypatch.setattr(assistant, "_post", fake_post)
    return sent, reply


def ask(client, question="Wie voll ist die Batterie?", session=SESSION):
    return client.post("/api/ask", json={"question": question, "session_id": session})


class TestNotSetUp:
    def test_the_interface_is_told_it_is_unavailable(self, client):
        assert client.get("/api/assistant").json() == {"available": False}

    def test_asking_says_so_instead_of_failing(self, client):
        r = ask(client)
        assert r.status_code == 503
        assert "isn't set up" in r.json()["error"]


class TestAsking:
    def test_returns_the_agents_answer(self, client, agent):
        r = ask(client)
        assert r.status_code == 200
        assert r.json() == {"answer": "Die Batterie ist zu 61 % voll."}

    def test_passes_the_question_and_the_conversation_on(self, client, agent):
        sent, _ = agent
        ask(client, "  Und um Mitternacht?  ")
        assert sent == [{"action": "sendMessage", "sessionId": f"web-{SESSION}",
                         "chatInput": "Und um Mitternacht?"}]

    @pytest.mark.parametrize("failure, status, words", [
        (TimeoutError(), 504, "took too long"),
        (socket.timeout(), 504, "took too long"),     # a different class before Python 3.10
        (urllib.error.URLError(TimeoutError()), 504, "took too long"),
        (urllib.error.HTTPError(URL, 500, "Error in workflow", {}, None), 503, "can't answer right now"),
        (urllib.error.URLError("connection refused"), 503, "can't answer right now"),
        (ValueError("not JSON"), 503, "can't answer right now"),
    ], ids=["timeout", "socket-timeout", "timeout-while-connecting", "workflow-error", "n8n-down", "not-json"])
    def test_every_failure_becomes_a_message_for_the_operator(self, client, agent, failure, status, words):
        agent[1]["raise"] = failure
        r = ask(client)
        assert r.status_code == status
        assert words in r.json()["error"]

    def test_an_empty_answer_is_not_shown_as_an_answer(self, client, agent):
        agent[1]["output"] = "   "
        r = ask(client)
        assert r.status_code == 503
        assert "no answer" in r.json()["error"]

    @pytest.mark.parametrize("question, session", [
        ("", SESSION),                    # nothing asked
        ("   ", SESSION),                 # only spaces
        ("x" * 501, SESSION),             # too long
        ("Hallo?", "short"),              # not a session id
        ("Hallo?", "a" * 8 + "<script>"), # characters a session id never has
    ])
    def test_rejects_bad_input_without_calling_the_agent(self, client, agent, question, session):
        sent, _ = agent
        assert ask(client, question, session).status_code == 422
        assert sent == []


class TestLimits:
    def test_a_sixth_question_within_a_minute_is_refused(self, client, agent):
        codes = [ask(client).status_code for _ in range(6)]
        assert codes == [200] * 5 + [429]
        assert len(agent[0]) == 5                      # the refused one never reached the agent

    def test_the_limit_frees_up_after_the_window(self):
        now = [0.0]
        limiter = assistant.RateLimiter(limit=2, window=60, clock=lambda: now[0])
        assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
        assert limiter.allow("b")                      # each visitor has their own budget
        now[0] = 60.0
        assert limiter.allow("a")


class TestAvailability:
    def test_reachable_agent_is_available(self, monkeypatch):
        monkeypatch.setattr(assistant, "AGENT_URL", URL)
        monkeypatch.setattr(assistant.urllib.request, "urlopen", lambda *a, **k: _Closable())
        assert assistant.available() is True

    def test_unreachable_agent_is_not(self, monkeypatch):
        def refuse(*a, **k):
            raise urllib.error.URLError("connection refused")
        monkeypatch.setattr(assistant, "AGENT_URL", URL)
        monkeypatch.setattr(assistant.urllib.request, "urlopen", refuse)
        assert assistant.available() is False

    def test_the_answer_is_remembered_so_the_page_never_waits_on_n8n(self, monkeypatch):
        calls = []
        monkeypatch.setattr(assistant, "AGENT_URL", URL)
        monkeypatch.setattr(assistant.urllib.request, "urlopen",
                            lambda *a, **k: calls.append(1) or _Closable())
        assert assistant.available() and assistant.available()
        assert len(calls) == 1

    def test_the_endpoint_reports_it(self, client, monkeypatch):
        monkeypatch.setattr(assistant, "available", lambda: True)
        assert client.get("/api/assistant").json() == {"available": True}


class _Closable:
    def close(self):
        pass
