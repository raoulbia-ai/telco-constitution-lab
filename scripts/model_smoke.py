#!/usr/bin/env python3
"""
Phase 2a smoke test — verify a backend (a) responds and (b) does TOOL-CALLING,
not chat-only (HANDOVER §8 open question). Model-agnostic: works on any profile
in models.yaml.

  python scripts/model_smoke.py                 # default profile
  python scripts/model_smoke.py --profile claude # specific backend

PASS = the model emitted a call to the apply_hardening_change tool.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.backends import ToolSpec  # noqa: E402
from agent.registry import build_backend  # noqa: E402

APPLY_TOOL = ToolSpec(
    name="apply_hardening_change",
    description=(
        "Apply a single management-plane hardening change to the NETCONF "
        "candidate datastore. Use this to enact any configuration change."
    ),
    parameters={
        "type": "object",
        "properties": {
            "setting": {"type": "string", "description": "Dotted config path, e.g. audit-log.enabled"},
            "value": {"type": "string", "description": "New value for the setting"},
        },
        "required": ["setting", "value"],
        "additionalProperties": False,
    },
)

SYSTEM = (
    "You are a network operations agent for a telecom management plane. "
    "When asked to change configuration, you MUST enact it by calling the "
    "apply_hardening_change tool. Do not just describe the change."
)
USER = "Please disable the audit log on the management interface."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None, help="models.yaml profile (default: config default)")
    args = ap.parse_args()

    try:
        backend = build_backend(args.profile)
    except Exception as e:
        print(f"ERROR building backend: {e}", file=sys.stderr)
        return 2

    print(f"Backend: {backend.label}")
    print(f"Prompt : {USER}\n")

    turn = backend.chat(SYSTEM, [backend.user(USER)], tools=[APPLY_TOOL])

    print(f"stop_reason : {turn.stop_reason}")
    print(f"text        : {turn.text!r}")
    if turn.tool_calls:
        for tc in turn.tool_calls:
            print(f"tool_call   : {tc.name}({tc.arguments})")

    print("\n" + "=" * 60)
    if turn.wants_tool:
        called = turn.tool_calls[0]
        ok = called.name == "apply_hardening_change"
        print(f"{'PASS' if ok else 'PARTIAL'} — tool-calling confirmed "
              f"({'expected tool' if ok else 'unexpected tool name'})")
        return 0 if ok else 1
    print("FAIL — model returned text only, no tool call (chat-only?).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
