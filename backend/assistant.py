"""
The bridge between the operator interface and the AI agent ("Frag deine Anlage" in n8n).

The browser only ever talks to myEnergy: POST /api/ask lands here, and this module passes
the question on to the agent's chat webhook. That keeps n8n off the internet, and gives
one place to limit how often people ask, since every question uses model quota.

With AGENT_URL unset (the public demo has no n8n) the assistant is unavailable and the
interface hides its button.
"""
import json
import os
import socket
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque

# In Docker Compose: http://n8n:5678/webhook/<chat trigger id>/chat
AGENT_URL = os.environ.get("AGENT_URL", "")
TIMEOUT_S = 90            # an answer takes about 20 s; a busy model can take longer
MAX_PER_MINUTE = 5        # questions per visitor
CHECK_EVERY_S = 30        # how long "is the agent running?" is remembered

_last_check = (float("-inf"), False)     # (when, reachable)
_TIMEOUTS = (TimeoutError, socket.timeout)  # the same class from Python 3.10 on


class AgentError(Exception):
    """The agent could not answer. The message is written for the operator."""


class AgentTimeout(AgentError):
    pass


def configured() -> bool:
    return bool(AGENT_URL)


def available() -> bool:
    """Configured, and the agent's chat page answers (a GET, which costs no model call)."""
    global _last_check
    if not AGENT_URL:
        return False
    checked_at, reachable = _last_check
    if time.monotonic() - checked_at < CHECK_EVERY_S:
        return reachable
    try:
        urllib.request.urlopen(AGENT_URL, timeout=3).close()
        reachable = True
    except (urllib.error.URLError, OSError):
        reachable = False
    _last_check = (time.monotonic(), reachable)
    return reachable


def _post(payload: dict) -> dict:
    req = urllib.request.Request(AGENT_URL, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read())


def ask(question: str, session_id: str) -> str:
    """The agent's answer to one question. The session id lets it remember the conversation."""
    try:
        reply = _post({"action": "sendMessage", "sessionId": f"web-{session_id}",
                       "chatInput": question})
    except _TIMEOUTS:
        raise AgentTimeout("The assistant took too long to answer. Please try again.")
    except urllib.error.URLError as e:
        if isinstance(e.reason, _TIMEOUTS):
            raise AgentTimeout("The assistant took too long to answer. Please try again.")
        raise AgentError("The assistant can't answer right now. Please try again later.")
    except (ValueError, OSError):
        raise AgentError("The assistant can't answer right now. Please try again later.")
    answer = (reply.get("output") or "").strip() if isinstance(reply, dict) else ""
    if not answer:
        raise AgentError("The assistant had no answer. Try asking in a different way.")
    return answer


class RateLimiter:
    """At most `limit` questions per `window` seconds for each visitor."""

    def __init__(self, limit: int = MAX_PER_MINUTE, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._asked = defaultdict(deque)

    def allow(self, visitor: str) -> bool:
        now = self.clock()
        times = self._asked[visitor]
        while times and now - times[0] >= self.window:
            times.popleft()
        if len(times) >= self.limit:
            return False
        times.append(now)
        return True
