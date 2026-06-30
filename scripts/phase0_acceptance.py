#!/usr/bin/env python3
"""
Phase 0 acceptance test (HANDOVER §5, Phase 0).

Proves the NETCONF candidate-datastore commit/discard machinery works against
the Track 1 stand-in server:

  Test A (commit):  edit-config -> candidate, commit
                    => the change IS reflected in the running datastore.
  Test B (discard): edit-config -> candidate, discard-changes
                    => the change is NOT reflected in the running datastore.

It prints the config delta at each step and exits non-zero if either invariant
fails. No agent / LLM involved — this is plain mechanism validation.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

from ncclient import manager
from ncclient.operations.rpc import RPCError

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = REPO_ROOT / "secrets" / "netconf_key"

HOST = "127.0.0.1"
PORT = 830
USER = "root"  # netopeer2 configured this user (install ran as root) w/ our pubkey

TH_NS = "urn:telco-constitution-ai:track1:telco-hardening"

# Subtree filter limiting get-config to our illustrative model.
HARDENING_FILTER = f'<hardening xmlns="{TH_NS}"/>'

# Test A payload: turn audit-log off (recoverable) + add a managed function.
EDIT_A = f"""
<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <hardening xmlns="{TH_NS}">
    <audit-log>
      <enabled>false</enabled>
    </audit-log>
    <managed-function>
      <name>amf-1</name>
      <admin-state>unlocked</admin-state>
    </managed-function>
  </hardening>
</config>
"""

# Test B payload: a DIFFERENT change we will discard (set audit level to debug).
EDIT_B = f"""
<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <hardening xmlns="{TH_NS}">
    <audit-log>
      <level>debug</level>
    </audit-log>
  </hardening>
</config>
"""


def banner(msg: str) -> None:
    print(f"\n{'=' * 70}\n{msg}\n{'=' * 70}")


def get_running(m) -> str:
    return m.get_config(source="running", filter=("subtree", HARDENING_FILTER)).data_xml


def get_candidate(m) -> str:
    return m.get_config(source="candidate", filter=("subtree", HARDENING_FILTER)).data_xml


def show_delta(label: str, before: str, after: str) -> None:
    diff = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile="before", tofile="after", lineterm="",
        )
    )
    print(f"\n--- delta: {label} ---")
    print("\n".join(diff) if diff else "(no change)")


def main() -> int:
    if not KEY_PATH.exists():
        print(f"ERROR: private key not found at {KEY_PATH}. Run scripts/gen_keys.sh "
              f"and build the image first.", file=sys.stderr)
        return 2

    print(f"Connecting to {USER}@{HOST}:{PORT} with key {KEY_PATH} ...")
    m = manager.connect(
        host=HOST,
        port=PORT,
        username=USER,
        key_filename=str(KEY_PATH),
        hostkey_verify=False,
        allow_agent=False,
        look_for_keys=False,
        timeout=30,
    )

    failures: list[str] = []
    with m:
        # Capability sanity check.
        caps = list(m.server_capabilities)
        has_candidate = any(":candidate" in c for c in caps)
        print(f"Server advertises :candidate capability -> {has_candidate}")
        if not has_candidate:
            failures.append("server does not advertise the :candidate capability")

        # ---- Test A: commit is reflected in running ----
        banner("TEST A — edit candidate -> commit (expect running to change)")
        run_before = get_running(m)
        print("running (before):")
        print(run_before)

        m.edit_config(target="candidate", config=EDIT_A)
        cand = get_candidate(m)
        show_delta("candidate after edit-config A", run_before, cand)

        m.commit()
        run_after = get_running(m)
        show_delta("running after commit", run_before, run_after)

        committed_ok = ("amf-1" in run_after) and ("<enabled>false</enabled>" in run_after)
        print(f"\n[A] commit reflected in running -> {committed_ok}")
        if not committed_ok:
            failures.append("Test A: committed change not found in running datastore")

        # ---- Test B: discard is NOT reflected in running ----
        banner("TEST B — edit candidate -> discard (expect running unchanged)")
        run_before_b = get_running(m)
        m.edit_config(target="candidate", config=EDIT_B)
        cand_b = get_candidate(m)
        show_delta("candidate after edit-config B (pending)", run_before_b, cand_b)

        pending_in_candidate = "<level>debug</level>" in cand_b
        print(f"\n[B] change is staged in candidate -> {pending_in_candidate}")
        if not pending_in_candidate:
            failures.append("Test B: change did not appear in candidate before discard")

        m.discard_changes()
        run_after_b = get_running(m)
        show_delta("running after discard", run_before_b, run_after_b)

        discarded_ok = "<level>debug</level>" not in run_after_b
        print(f"\n[B] discard kept running unchanged -> {discarded_ok}")
        if not discarded_ok:
            failures.append("Test B: discarded change leaked into running datastore")

    banner("RESULT")
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — candidate commit/discard semantics verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
