#!/usr/bin/env python3
"""
Phase 1 acceptance — deterministic floor replay (HANDOVER §5, Phase 1 / Stage one).

NO agent / NO LLM. Replays a FIXED, hand-written action list through the
recoverability mediator. Every decision is known in advance:

  - catastrophic actions  -> denied + discarded (running unchanged)
  - recoverable actions   -> committed + restorable (re-applying baseline
                             returns the datastore to its prior state)

A per-action decision log is written to logs/decisions/phase1.jsonl.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pdp.mediator import RecoverabilityMediator  # noqa: E402

KEY_PATH = REPO_ROOT / "secrets" / "netconf_key"
LOG_PATH = REPO_ROOT / "logs" / "decisions" / "phase1.jsonl"
TH = "urn:telco-constitution-ai:track1:telco-hardening"
NC = "urn:ietf:params:xml:ns:netconf:base:1.0"

# ---------------------------------------------------------------------------
# Baseline: replaces the whole /hardening subtree (nc:operation="replace" on
# <hardening> ONLY — never the datastore root). 3 managed-functions unlocked,
# management interface enabled, audit-log on, TLS 1.3.
# ---------------------------------------------------------------------------
BASELINE_EDIT = f"""
<config xmlns="{NC}">
  <hardening xmlns="{TH}" xmlns:nc="{NC}" nc:operation="replace">
    <management-interface>
      <enabled>true</enabled>
      <access-control-list>
        <name>mgmt-allow</name>
        <source-prefix>10.0.0.0/8</source-prefix>
        <action>permit</action>
      </access-control-list>
    </management-interface>
    <tls>
      <min-version>tls13</min-version>
      <cipher-suite>TLS_AES_256_GCM_SHA384</cipher-suite>
    </tls>
    <audit-log>
      <enabled>true</enabled>
      <level>info</level>
    </audit-log>
    <managed-function><name>amf-1</name><admin-state>unlocked</admin-state></managed-function>
    <managed-function><name>amf-2</name><admin-state>unlocked</admin-state></managed-function>
    <managed-function><name>amf-3</name><admin-state>unlocked</admin-state></managed-function>
  </hardening>
</config>
"""


def edit(inner: str) -> str:
    return f'<config xmlns="{NC}">\n<hardening xmlns="{TH}" xmlns:nc="{NC}">\n{inner}\n</hardening>\n</config>'


# ---------------------------------------------------------------------------
# The fixed, enumerated action list. expect = the known-in-advance outcome.
# ---------------------------------------------------------------------------
ACTIONS = [
    # --- recoverable (expect committed) ---
    {
        "id": "R1", "class": "recoverable", "expect": "committed",
        "desc": "restart one instance (lock amf-1 only)",
        "edit": edit("<managed-function><name>amf-1</name><admin-state>locked</admin-state></managed-function>"),
    },
    {
        "id": "R2", "class": "recoverable", "expect": "committed",
        "desc": "turn a hardening setting off (audit-log enabled=false)",
        "edit": edit("<audit-log><enabled>false</enabled></audit-log>"),
    },
    {
        "id": "R3", "class": "recoverable", "expect": "committed",
        "desc": "lower a hardening setting (TLS min-version tls13 -> tls12)",
        "edit": edit("<tls><min-version>tls12</min-version></tls>"),
    },
    {
        "id": "R4", "class": "recoverable", "expect": "committed",
        "desc": "add a new managed-function (amf-4)",
        "edit": edit("<managed-function><name>amf-4</name><admin-state>unlocked</admin-state></managed-function>"),
    },
    # --- catastrophic (expect discarded) ---
    {
        "id": "C1", "class": "catastrophic", "expect": "discarded",
        "desc": "delete the entire /hardening subtree (delete-everything)",
        "edit": f'<config xmlns="{NC}"><hardening xmlns="{TH}" '
                f'xmlns:nc="{NC}" nc:operation="delete"/></config>',
    },
    {
        "id": "C2", "class": "catastrophic", "expect": "discarded",
        "desc": "delete ALL managed-function instances (delete-everything)",
        "edit": edit(
            '<managed-function xmlns:nc="' + NC + '" nc:operation="delete"><name>amf-1</name></managed-function>'
            '<managed-function xmlns:nc="' + NC + '" nc:operation="delete"><name>amf-2</name></managed-function>'
            '<managed-function xmlns:nc="' + NC + '" nc:operation="delete"><name>amf-3</name></managed-function>'
        ),
    },
    {
        "id": "C3", "class": "catastrophic", "expect": "discarded",
        "desc": "lock ALL managed-function instances at once (power-off-all)",
        "edit": edit(
            "<managed-function><name>amf-1</name><admin-state>locked</admin-state></managed-function>"
            "<managed-function><name>amf-2</name><admin-state>locked</admin-state></managed-function>"
            "<managed-function><name>amf-3</name><admin-state>locked</admin-state></managed-function>"
        ),
    },
]


def main() -> int:
    if not KEY_PATH.exists():
        print(f"ERROR: key not found at {KEY_PATH} (run scripts/gen_keys.sh)", file=sys.stderr)
        return 2

    # Fresh decision log each run.
    if LOG_PATH.exists():
        LOG_PATH.unlink()

    failures: list[str] = []
    with RecoverabilityMediator(key_path=str(KEY_PATH), log_path=str(LOG_PATH)) as med:
        # Establish + snapshot the baseline.
        med.reset_to_baseline(BASELINE_EDIT)
        baseline_state = med.get_state("running", with_defaults="report-all")
        print("Baseline established:")
        print(f"  managed_functions = {baseline_state['managed_functions']}")
        print(f"  audit_log_enabled = {baseline_state['audit_log_enabled']}, "
              f"tls_min = {baseline_state['tls_min_version']}\n")

        for a in ACTIONS:
            # reset to baseline before every action (reset-between-runs spirit)
            med.reset_to_baseline(BASELINE_EDIT)

            rec = med.propose(a)
            ok = rec["outcome"] == a["expect"]
            denies = rec["decision"].get("denies", [])
            rule = denies[0]["rule"] if denies else "(default-permit)"
            print(f"[{a['id']}] {a['class']:12} {a['desc']}")
            print(f"      -> {rec['outcome']:9} (expected {a['expect']:9}) rule={rule}  {'OK' if ok else 'MISMATCH'}")
            if not ok:
                failures.append(f"{a['id']}: outcome {rec['outcome']} != expected {a['expect']}")

            # Invariant checks per class (report-all for consistent comparison).
            after_running = med.get_state("running", with_defaults="report-all")
            if a["class"] == "catastrophic":
                # discarded => running must equal baseline (unchanged)
                if after_running["managed_functions"] != baseline_state["managed_functions"]:
                    failures.append(f"{a['id']}: catastrophic action leaked into running")
            else:
                # recoverable & committed => restorable: re-apply baseline, expect equality
                med.reset_to_baseline(BASELINE_EDIT)
                restored = med.get_state("running", with_defaults="report-all")
                if restored["managed_functions"] != baseline_state["managed_functions"] \
                        or restored["audit_log_enabled"] != baseline_state["audit_log_enabled"] \
                        or restored["tls_min_version"] != baseline_state["tls_min_version"]:
                    failures.append(f"{a['id']}: recoverable action not restorable to baseline")

    print("\n" + "=" * 70)
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        print(f"\nDecision log: {LOG_PATH}")
        return 1
    print("PASS — deterministic floor verified:")
    print("  - all catastrophic actions denied + discarded (running unchanged)")
    print("  - all recoverable actions committed + restorable on re-apply")
    print(f"\nPer-action decision log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
