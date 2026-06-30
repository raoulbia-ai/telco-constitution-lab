"""Model-aware state parsing + PDP-input construction for telco-hardening.

Deliberately specific to the illustrative `telco-hardening` YANG model (not a
generic YANG differ) — see HANDOVER §7. It reduces a NETCONF datastore snapshot
to the handful of facts the recoverability rails care about, then diffs two
snapshots (running "before" vs candidate "after") into the flat JSON `input`
the Rego policy consumes.
"""
from __future__ import annotations

from lxml import etree

TH_NS = "urn:telco-constitution-ai:track1:telco-hardening"


def _q(tag: str) -> str:
    return f"{{{TH_NS}}}{tag}"


def parse_state(xml: str | bytes) -> dict:
    """Reduce a get-config reply (subtree-filtered to hardening) to a dict."""
    if isinstance(xml, str):
        xml = xml.encode()
    root = etree.fromstring(xml)

    state = {
        "hardening_present": False,
        "management_interface_present": False,
        "management_interface_enabled": None,
        "audit_log_enabled": None,
        "tls_min_version": None,
        "managed_functions": {},  # name -> admin-state
    }

    hardening = root.find(f".//{_q('hardening')}")
    if hardening is None:
        return state
    state["hardening_present"] = True

    mi = hardening.find(_q("management-interface"))
    if mi is not None:
        state["management_interface_present"] = True
        en = mi.findtext(_q("enabled"))
        if en is not None:
            state["management_interface_enabled"] = en == "true"

    al = hardening.find(_q("audit-log"))
    if al is not None:
        en = al.findtext(_q("enabled"))
        if en is not None:
            state["audit_log_enabled"] = en == "true"

    tls = hardening.find(_q("tls"))
    if tls is not None:
        state["tls_min_version"] = tls.findtext(_q("min-version"))

    for mf in hardening.findall(_q("managed-function")):
        name = mf.findtext(_q("name"))
        if name is None:
            continue
        state["managed_functions"][name] = mf.findtext(_q("admin-state")) or "unlocked"

    return state


def build_pdp_input(before: dict, after: dict) -> dict:
    """Diff two parsed states into the flat input expected by recoverability.rego."""
    mf_b = before["managed_functions"]
    mf_a = after["managed_functions"]

    deleted = sorted(n for n in mf_b if n not in mf_a)
    locked_after = sorted(n for n, s in mf_a.items() if s == "locked")
    newly_locked = sorted(
        n for n, s in mf_a.items()
        if s == "locked" and mf_b.get(n) != "locked"
    )

    return {
        "hardening_deleted": before["hardening_present"] and not after["hardening_present"],
        "management_interface_deleted": (
            before["management_interface_present"]
            and not after["management_interface_present"]
        ),
        # informational (no deny rule — flagged open question, see journal)
        "audit_log_turned_off": (
            before["audit_log_enabled"] in (True, None)
            and after["audit_log_enabled"] is False
        ),
        "managed_function": {
            "total_before": len(mf_b),
            "total_after": len(mf_a),
            "deleted_count": len(deleted),
            "deleted": deleted,
            "locked_after_total": len(locked_after),
            "newly_locked_count": len(newly_locked),
            "newly_locked": newly_locked,
        },
    }
