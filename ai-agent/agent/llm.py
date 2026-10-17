"""LLM backends for the scheduling assistant.

The assistant only needs one call: chat(messages, tools) -> assistant message.
Any model that supports tool calling can sit behind that interface. Two are
provided:

- OllamaLLM: a local open-source model through Ollama (free, runs on the lab
  machines, no API key). Default model: qwen3:8b.
- ScriptedLLM: replays fixed responses, so the agent loop can be tested
  deterministically without a model.

Assistant messages are normalized to:
    {"role": "assistant", "content": str,
     "tool_calls": [{"name": str, "arguments": dict}, ...]}
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    async def chat(self, messages: list[dict], tools: list[dict]) -> dict: ...


def _normalize_tool_calls(raw: list[dict] | None) -> list[dict]:
    calls = []
    for call in raw or []:
        fn = call.get("function", call)
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"__unparseable__": args}
        calls.append({"name": fn.get("name", ""), "arguments": args})
    return calls


class OllamaLLM:
    def __init__(
        self,
        model: str = "qwen3:8b",
        host: str | None = None,
        timeout: float = 300,
        temperature: float = 0.0,
    ):
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.timeout = timeout
        self.temperature = temperature

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise LLMError(f"Ollama returned {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"Cannot reach Ollama at {self.host} ({e.reason}). Is it running?") from e

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        data = await asyncio.to_thread(self._post, payload)
        msg = data.get("message") or {}
        return {
            "role": "assistant",
            "content": _THINK.sub("", msg.get("content") or "").strip(),
            "tool_calls": _normalize_tool_calls(msg.get("tool_calls")),
        }


class ScriptedLLM:
    """Returns the given assistant messages in order; records what it was sent."""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.received: list[list[dict]] = []

    async def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.received.append([dict(m) for m in messages])
        if not self._responses:
            raise LLMError("ScriptedLLM ran out of responses")
        r = self._responses.pop(0)
        return {
            "role": "assistant",
            "content": r.get("content", ""),
            "tool_calls": _normalize_tool_calls(r.get("tool_calls")),
        }


def call(name: str, **arguments: Any) -> dict:
    """Helper for scripts/tests: a tool call in the normalized shape."""
    return {"name": name, "arguments": arguments}
