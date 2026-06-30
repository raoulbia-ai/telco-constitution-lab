"""Recoverability mediator — the commit wrapper / PEP+PDP boundary (Phase 1).

The mediator is the ONLY sanctioned path to `commit`. For each proposed
transaction it:
  1. ensures candidate == running (discard any stale candidate),
  2. captures the running "before" state,
  3. stages the proposed edit into candidate,
  4. computes the model-aware delta and asks OPA (the PDP) to decide,
  5. commits on permit, discards on deny,
  6. appends a per-action decision-log record (JSONL).

In Stage two this same mediator backs the agent's "apply config" tool, so the
deterministic floor is identical across both A/B arms (HANDOVER §2, §6).
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from ncclient import manager

from .state import build_pdp_input, parse_state

TH_NS = "urn:telco-constitution-ai:track1:telco-hardening"
HARDENING_FILTER = f'<hardening xmlns="{TH_NS}"/>'


class RecoverabilityMediator:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 830,
        user: str = "root",
        key_path: str | None = None,
        opa_url: str = "http://127.0.0.1:8181/v1/data/telco/recoverability/decision",
        log_path: str | Path = "logs/decisions/phase1.jsonl",
    ):
        self.host, self.port, self.user, self.key_path = host, port, user, key_path
        self.opa_url = opa_url
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.m = None

    # -- connection --
    def connect(self) -> "RecoverabilityMediator":
        self.m = manager.connect(
            host=self.host, port=self.port, username=self.user,
            key_filename=self.key_path, hostkey_verify=False,
            allow_agent=False, look_for_keys=False, timeout=30,
        )
        return self

    def close(self) -> None:
        if self.m is not None:
            self.m.close_session()

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # -- datastore helpers --
    def get_state(self, source: str, with_defaults: str | None = None) -> dict:
        """Parse a datastore snapshot.

        with_defaults=None (the PDP default): defaults are trimmed, so a deleted
        non-presence container (e.g. /hardening) genuinely reads as absent —
        essential for the delete-everything detector. Without this, report-all
        would re-materialise the container from its default leaves and mask the
        deletion.

        with_defaults="report-all": include default-valued leaves. Used only for
        restorability comparisons in the replay harness, where two snapshots must
        compare equal regardless of whether a leaf was ever explicitly set.
        """
        kwargs = {"source": source, "filter": ("subtree", HARDENING_FILTER)}
        if with_defaults is not None:
            kwargs["with_defaults"] = with_defaults
        reply = self.m.get_config(**kwargs)
        return parse_state(reply.data_xml)

    def reset_to_baseline(self, baseline_edit: str) -> None:
        """Direct (UN-mediated) restore of the hardening subtree to baseline.

        Used only for test setup / reset-between-actions. The baseline_edit must
        carry nc:operation="replace" on <hardening> so only that subtree is
        replaced (never the whole datastore — that would wipe the server's own
        netconf-server config and kill access).
        """
        self.m.discard_changes()
        self.m.edit_config(target="candidate", config=baseline_edit)
        self.m.commit()

    # -- PDP query --
    def opa_decide(self, pdp_input: dict) -> dict:
        body = json.dumps({"input": pdp_input}).encode()
        req = urllib.request.Request(
            self.opa_url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.load(resp)
        # Fail CLOSED: if OPA returns no decision, treat as deny.
        return payload.get(
            "result",
            {"permit": False, "denies": [{"rule": "pdp-error", "reason": "OPA returned no result"}]},
        )

    # -- the wrapped commit --
    def propose(self, action: dict) -> dict:
        """Stage `action['edit']`, decide, commit-or-discard, log, return record."""
        self.m.discard_changes()
        before = self.get_state("running")

        self.m.edit_config(target="candidate", config=action["edit"])
        after = self.get_state("candidate")

        pdp_input = build_pdp_input(before, after)
        decision = self.opa_decide(pdp_input)
        permit = bool(decision.get("permit", False))

        if permit:
            self.m.commit()
            outcome = "committed"
        else:
            self.m.discard_changes()
            outcome = "discarded"

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action_id": action.get("id"),
            "description": action.get("desc"),
            "class": action.get("class"),
            "expected": action.get("expect"),
            "pdp_input": pdp_input,
            "decision": decision,
            "outcome": outcome,
        }
        with self.log_path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        return record
