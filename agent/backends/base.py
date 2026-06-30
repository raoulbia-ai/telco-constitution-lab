"""Provider-agnostic model backend interface (Phase 2a).

The harness depends only on these types, never on a specific SDK. Swapping
models is a config change (see models.yaml + registry.py). This is the
plug-and-play seam requested for Track 1 development.

Message model (neutral, provider-independent):
  {"role": "user",      "content": "<text>"}
  {"role": "assistant", "content": "<text|None>", "tool_calls": [ToolCall, ...]}
  {"role": "tool",      "tool_call_id": "<id>", "name": "<tool>", "content": "<result>"}

Each backend translates this neutral form to/from its own wire format.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """A tool the model may call. `parameters` is a JSON Schema object."""
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    """A single tool invocation the model emitted."""
    id: str
    name: str
    arguments: dict


@dataclass
class AssistantTurn:
    """Normalized result of one model turn."""
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    raw: Any = None  # provider-native response, for debugging/logging

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


class ModelBackend(ABC):
    """One model, one OpenAI-compatible or Anthropic endpoint.

    Implementations must be stateless across `chat` calls (the harness owns the
    message history) so runs reset cleanly between A/B iterations.
    """

    #: stable identifier for logs (e.g. "openai_compat:qwen3.5:122b-a10b")
    label: str = "backend"
    #: the pinned model string actually sent on the wire
    model_id: str = ""

    #: nominal sampling temperature (for run-config reporting); None = backend default
    temperature: float | None = None

    @abstractmethod
    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        seed: int | None = None,
    ) -> AssistantTurn:
        """Run one model turn and return the normalized result.

        `seed` (where the backend supports it) makes a run reproducible while
        varying it across runs yields independent draws — so N runs are genuine
        samples, not one deterministic outcome replayed.
        """

    # -- neutral message-builder helpers (so the harness never hand-rolls roles) --

    @staticmethod
    def user(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant(turn: AssistantTurn) -> dict:
        return {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}

    @staticmethod
    def tool_result(call: ToolCall, content: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": content,
        }
