"""
A fake Anthropic Messages API for testing the n8n workflows without an API key
and without spending money. It is not a model: it logs every request n8n sends
and replies with a script.

  - a request with tools (the chat agent): first it calls get_plan, then it
    answers with the start of what the tool returned
  - a request without tools (the daily briefing): it echoes the start of the prompt

That proves the wiring (trigger, agent, tools, the API, the reply) and shows the
exact request n8n would send to Claude, in requests.jsonl. See automation/README.md
for how to point n8n at it.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = os.environ.get("FAKE_LOG", "requests.jsonl")
PORT = int(os.environ.get("PORT", "9100"))


def reply_for(body):
    last = body["messages"][-1]
    content = last["content"] if isinstance(last["content"], list) else []
    results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
    if not body.get("tools"):
        prompt = last["content"] if isinstance(last["content"], str) else json.dumps(last["content"])
        return [{"type": "text", "text": "## FAKE BRIEFING\n- prompt began: " + prompt[:300]}], "end_turn"
    if not results:
        return [{"type": "tool_use", "id": "toolu_fake_1", "name": "get_plan", "input": {}}], "tool_use"
    raw = results[0].get("content")
    text = raw if isinstance(raw, str) else json.dumps(raw)
    return [{"type": "text", "text": "FAKE ANSWER. The tool returned: " + text[:160]}], "end_turn"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        headers = {k: v for k, v in self.headers.items() if k.lower() != "x-api-key"}
        with open(LOG, "a") as f:
            f.write(json.dumps({"path": self.path, "headers": headers, "body": body}) + "\n")
        content, stop = reply_for(body)
        if body.get("stream"):
            self.send_error(501, "streaming is not supported by the fake; turn streaming off")
            return
        out = json.dumps({"id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                          "content": content, "stop_reason": stop, "stop_sequence": None,
                          "usage": {"input_tokens": 0, "output_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


if __name__ == "__main__":
    print(f"fake Anthropic API on :{PORT}, logging to {LOG}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
