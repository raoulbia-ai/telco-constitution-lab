"""Anthropic (Claude) backend — the CLEAN way to use a Claude model.

Uses the official `anthropic` SDK with OUR controlled system prompt and OUR
tools. This is NOT Claude Code / the `claude` CLI: §6 forbids that as the
scored harness because it injects an uncontrolled agentic system prompt. Here
the harness owns the entire prompt and tool surface, so the only Claude-specific
variable is the model weights.

Caveat (see BUILD-JOURNAL): Claude's strong built-in restraint training likely
produces a ceiling effect, making it a weak proxy for the production model used
in the real lab when measuring H1. Use for plumbing/dev smoke tests, not for directional
H1 signal — prefer a local open model for that.

Credentials resolve via the SDK default chain: ANTHROPIC_API_KEY, or
ANTHROPIC_AUTH_TOKEN, or an `ant auth login` OAuth profile. If none is present,
construction/calls raise — the registry surfaces a clear "needs credentials"
message.
"""
from __future__ import annotations

from .base import AssistantTurn, ModelBackend, ToolCall, ToolSpec


class AnthropicBackend(ModelBackend):
    def __init__(
        self,
        model: str = "claude-opus-4-8",
        max_tokens: int = 4096,
        effort: str = "high",
        thinking: bool = True,
    ):
        from anthropic import Anthropic  # lazy import

        self.model_id = model
        self.label = f"anthropic:{model}"
        self._max_tokens = max_tokens
        self._effort = effort
        self._thinking = thinking
        self._client = Anthropic()  # resolves env key or OAuth profile
        # The SDK defers auth resolution to request time; probe here so the
        # registry can surface a clear "needs credentials" message at build.
        if not getattr(self._client, "api_key", None) and not getattr(self._client, "auth_token", None):
            raise RuntimeError(
                "no Anthropic credentials resolved (set ANTHROPIC_API_KEY or run `ant auth login`)"
            )

    @staticmethod
    def _tools_to_wire(tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

    def _to_wire(self, messages: list[dict]) -> list[dict]:
        wire: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "assistant":
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls", []):
                    blocks.append({
                        "type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments,
                    })
                wire.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                wire.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }],
                })
            else:  # user
                wire.append({"role": "user", "content": m["content"]})
        return wire

    def chat(self, system, messages, tools=None, seed=None) -> AssistantTurn:
        # Claude has no seed parameter (and sampling params are removed on the
        # current Opus tier); `seed` is accepted for interface parity, ignored.
        kwargs: dict = {
            "model": self.model_id,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": self._to_wire(messages),
            "output_config": {"effort": self._effort},
        }
        if self._thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        wire_tools = self._tools_to_wire(tools)
        if wire_tools:
            kwargs["tools"] = wire_tools

        resp = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))

        return AssistantTurn(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason,
            raw=resp,
        )
