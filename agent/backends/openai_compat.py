"""OpenAI-compatible backend — Ollama (Track 1 default), vLLM, or any /v1 server.

Uses the official `openai` SDK pointed at the compatible base_url. This is the
correct use of the OpenAI SDK: the target is a genuinely OpenAI-compatible
server (Ollama), NOT a shim in front of Claude. (Claude goes through the
official anthropic SDK — see anthropic_backend.py.)
"""
from __future__ import annotations

import json

from .base import AssistantTurn, ModelBackend, ToolCall, ToolSpec


class OpenAICompatBackend(ModelBackend):
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434/v1",
        api_key: str = "ollama",  # Ollama ignores it; required to satisfy the SDK
        max_tokens: int = 2048,
        temperature: float | None = None,
    ):
        from openai import OpenAI  # lazy import

        self.model_id = model
        self.label = f"openai_compat:{model}"
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def _to_wire(self, system: str, messages: list[dict]) -> list[dict]:
        wire: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            role = m["role"]
            if role == "assistant":
                msg: dict = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m["tool_calls"]
                    ]
                wire.append(msg)
            elif role == "tool":
                wire.append({
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content": m["content"],
                })
            else:  # user
                wire.append({"role": "user", "content": m["content"]})
        return wire

    @staticmethod
    def _tools_to_wire(tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def chat(self, system, messages, tools=None) -> AssistantTurn:
        kwargs: dict = {
            "model": self.model_id,
            "messages": self._to_wire(system, messages),
            "max_tokens": self._max_tokens,
        }
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        wire_tools = self._tools_to_wire(tools)
        if wire_tools:
            kwargs["tools"] = wire_tools
            kwargs["tool_choice"] = "auto"

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return AssistantTurn(
            text=msg.content,
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
            raw=resp,
        )
