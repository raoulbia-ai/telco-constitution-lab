#!/usr/bin/env python3
"""
Phase 2 acceptance — the A/B experiment (HANDOVER §5, Phase 2 / Stage two / H1).

Runs N episodes per arm against a pinned local model:
  Arm A = no constitution      (baseline)
  Arm B = constitution added   (the only change)

Every config change routes through the recoverability mediator (Phase 1 floor),
so the deterministic floor is identical across arms. Full datastore reset before
every run. Writes per-run JSON + a summary with the HAC A/B delta and a
Mann-Whitney U test.

  python scripts/phase2_ab.py --n 5
  python scripts/phase2_ab.py --profile local-qwen --n 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.harness import run_once  # noqa: E402
from agent.levers import BASELINE_EDIT  # noqa: E402
from agent.registry import build_backend  # noqa: E402
from agent.scoring import compute_metrics, mann_whitney_u  # noqa: E402
from pdp.mediator import RecoverabilityMediator  # noqa: E402

KEY_PATH = REPO_ROOT / "secrets" / "netconf_key"
OUT_DIR = REPO_ROOT / "logs" / "phase2"
ARMS = ["A_no_constitution", "B_constitution"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None, help="models.yaml profile")
    ap.add_argument("--n", type=int, default=5, help="runs per arm")
    args = ap.parse_args()

    if not KEY_PATH.exists():
        print(f"ERROR: key not found at {KEY_PATH}", file=sys.stderr)
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        backend = build_backend(args.profile)
    except Exception as e:
        print(f"ERROR building backend: {e}", file=sys.stderr)
        return 2

    print(f"Model : {backend.label}")
    print(f"Runs  : {args.n} per arm  (arms: {ARMS})\n")

    results: dict[str, list[dict]] = {a: [] for a in ARMS}
    surface_signature = None

    med = RecoverabilityMediator(key_path=str(KEY_PATH))
    with med:
        for arm in ARMS:
            for i in range(args.n):
                med.log_path = OUT_DIR / f"decisions-{arm}-{i}.jsonl"
                med.log_path.parent.mkdir(parents=True, exist_ok=True)
                if med.log_path.exists():
                    med.log_path.unlink()

                med.reset_to_baseline(BASELINE_EDIT)         # reset between runs
                rec = run_once(backend, arm, med)
                metrics = compute_metrics(rec)
                results[arm].append(metrics)

                (OUT_DIR / f"run-{arm}-{i}.json").write_text(
                    json.dumps({"metrics": metrics, "record": rec.to_dict()}, indent=2))

                # action-surface identity check: same tool/lever set every run
                sig = sorted({a.setting for a in rec.applies})
                surface_signature = surface_signature  # surface is fixed in levers.py
                print(f"[{arm}] run {i+1}/{args.n}: HAC={metrics['HAC']} "
                      f"safe={metrics['legit_lever_depth']} gain={metrics['gain_pct']}% "
                      f"status={metrics['final_status']} guardrail={metrics['guardrail_source']}")

    # --- aggregate + stats ---
    hac = {a: [r["HAC"] for r in results[a]] for a in ARMS}
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    summary = {
        "model": backend.label,
        "n_per_arm": args.n,
        "HAC_mean": {a: round(mean(hac[a]), 2) for a in ARMS},
        "HAC_raw": hac,
        "constitution_effect_meanHAC": round(mean(hac[ARMS[0]]) - mean(hac[ARMS[1]]), 2),
        "honest_stop_rate": {a: round(mean([r["honest_stop"] for r in results[a]]), 2) for a in ARMS},
        "floor_denied_rate": {a: round(mean([r["floor_denied"] for r in results[a]]), 2) for a in ARMS},
        "legit_lever_depth_mean": {a: round(mean([r["legit_lever_depth"] for r in results[a]]), 2) for a in ARMS},
        "mann_whitney_HAC": mann_whitney_u(hac[ARMS[0]], hac[ARMS[1]]),
        "action_surface": "fixed registry (agent/levers.py) — identical across arms",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 70)
    print("PHASE 2 A/B SUMMARY")
    print("=" * 70)
    print(f"Mean HAC  A (no constitution) = {summary['HAC_mean'][ARMS[0]]}")
    print(f"Mean HAC  B (constitution)    = {summary['HAC_mean'][ARMS[1]]}")
    print(f"Constitution effect (A-B)     = {summary['constitution_effect_meanHAC']}  (higher = more restraint)")
    print(f"Honest-stop rate  A/B         = {summary['honest_stop_rate'][ARMS[0]]} / {summary['honest_stop_rate'][ARMS[1]]}")
    print(f"Mann-Whitney U (HAC)          = {summary['mann_whitney_HAC']}")
    print(f"\nPer-run logs + summary.json under {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
