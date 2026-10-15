#!/usr/bin/env python3
"""OpenAI-compatible mock model for the OpenCode end-to-end tests: scripted tool calls by keyword, no network.
Usage: mock_llm.py LOG. Binds 127.0.0.1 on a free port, prints the port as the first stdout line, logs each request
as one JSON line in LOG (model, tool names, system prompts, plan)."""
import hashlib
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RESET = {"command": "git reset --hard", "description": "reset"}
RESET_CODE = hashlib.sha1(("bash\n" + json.dumps(RESET, separators=(",", ":"))).encode()).hexdigest()[:4]
SCRIPT = (
    ("DELEGATE_APPROVE", "task", {"description": "probe", "prompt": "dryas allow %s RESET" % RESET_CODE,
                                  "subagent_type": "dryas-executor-fast"}),
    ("DELEGATE", "task", {"description": "probe", "prompt": "WRITE_OUT", "subagent_type": "dryas-executor-fast"}),
    ("WRITE_OUT", "write", {"filePath": "out.txt", "content": "x"}),
    ("WRITE_ALLOWED", "write", {"filePath": "allowed.txt", "content": "x"}),
    ("dryas allow", "bash", RESET),
    ("RESET", "bash", RESET),
    ("ECHO", "bash", {"command": "echo hi; sleep 0.5", "description": "echo"}),
    ("LS", "bash", {"command": "ls", "description": "list"}),
    ("MEMSEARCH", "jev_memory_search", {"query": "opencode"}),
)
USAGE = {"prompt_tokens": 1234, "completion_tokens": 5, "total_tokens": 1239}


def plan(messages, tools):
    last = messages[-1] if messages else {}
    if last.get("role") == "tool":
        return ("text", "done: " + str(last.get("content"))[:300])
    users = [m for m in messages if m.get("role") == "user"]
    text = json.dumps(users[-1].get("content")) if users else ""
    names = {t.get("function", {}).get("name") for t in tools or []}
    if "NO_RETRY" in text:
        return ("text", "ok")
    if "BIGUSAGE" in text:
        return ("text", "big")
    for key, tool, args in SCRIPT:
        if key in text and tool in names:
            return ("tool", tool, args)
    return ("text", "ok")


class Handler(BaseHTTPRequestHandler):
    log_path = ""

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "m1", "object": "model"}, {"id": "m2", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        msgs = body.get("messages") or []
        p = plan(msgs, body.get("tools"))
        users = [m for m in msgs if m.get("role") == "user"]
        text = json.dumps(users[-1].get("content")) if users else ""
        usage = dict(USAGE, prompt_tokens=190000, total_tokens=190005) if p == ("text", "big") else USAGE
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"model": body.get("model"),
                                "tools": sorted(t.get("function", {}).get("name") for t in body.get("tools") or []),
                                "system": [m.get("content") for m in msgs if m.get("role") == "system"],
                                "plan": list(p[:2]), "user": text[:20000]}) + "\n")

        def chunk(delta, finish=None):
            c = {"id": "mock", "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model"),
                 "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            if finish:
                c["usage"] = usage
            return c
        if p[0] == "text":
            chunks = [chunk({"role": "assistant", "content": p[1]}), chunk({}, "stop")]
        else:
            call = {"index": 0, "id": "call_%d" % time.time_ns(), "type": "function",
                    "function": {"name": p[1], "arguments": json.dumps(p[2])}}
            chunks = [chunk({"role": "assistant", "tool_calls": [call]}), chunk({}, "tool_calls")]
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for c in chunks:
            self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


def main(argv):
    Handler.log_path = argv[1]
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(srv.server_address[1], flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main(sys.argv)
