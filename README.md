# Telco Constitution Lab

A **local, OS-isolated stand-in for a vendor 6G management-plane lab** — a
reproducible reference design for testing whether an AI agent operating under a
behavioural **"Telco Constitution"** shows *engineer-like restraint*: pursuing a
real objective only as far as it can without weakening the network's security
posture.

It is a **development / exploration lab**, built so the experiment can be
designed and de-risked locally (on an NVIDIA DGX Spark) without depending on a
real telecom lab. It is **not** the scored production experiment; local-model
results here are directional only.

## The hypothesis (H1)

> Given a senior engineer's privileges and a plausible-but-dangerous goal, does
> an agent operating under a Telco Constitution (behavioural principles in its
> system prompt) go only as far as is *recoverable / safe* — versus an identical
> agent without that constitution?

A two-arm A/B comparison, measured probabilistically over N runs:
**Arm A** = no constitution, **Arm B** = constitution added — the *only*
difference.

## How this replicates a real lab

The dependent variable lives entirely in the **management plane**, so the lab is
built on the open-source NETCONF toolset that mirrors a real vendor management
surface — rather than a traffic-handling 5G core, which H1 doesn't need.

| Real-lab capability | Provided here by |
| --- | --- |
| NETCONF management interface (RFC 6241) | **Netopeer2** server |
| Candidate datastore + commit / discard | **sysrepo** (startup / running / candidate) |
| Hardening settings as machine-checkable config | a small **illustrative YANG model** |
| "Senior-engineer privileges" access surface | NACM (RFC 8341), built into sysrepo |
| **Recoverability check at the transaction boundary** | a **Policy Decision Point** that wraps `commit` |
| Local model serving | **Ollama** on the Spark (OpenAI-compatible) |

The two enforcement layers:
- a **deterministic recoverability floor** (the PDP) that blocks *unrecoverable*
  changes in **both** arms — guaranteeing safety regardless of the agent; and
- the agent's own **judgment** in the *recoverable zone* above that floor, where
  no rule intervenes. **H1 measures restraint in that zone.**

> The hardening knobs, the optimization scenario, and the performance model here
> are **generic, illustrative placeholders** — not any real vendor's production
> config surface, which is out of scope by design. The real action surface is
> locked separately for the scored run.

## Isolation model

Everything that would otherwise touch the host OS runs in Docker:

- The **NETCONF stack** (libyang → libnetconf2 → sysrepo → netopeer2) is built
  from source at **pinned, mutually-compatible tags** *inside* the image — the
  host gets no new libraries or datastore. The Dockerfile is the reproducible
  recipe.
- The **policy engine** (OPA) runs as an isolated sidecar.
- **Host Python** lives in a `.venv`, never system pip.
- State is **ephemeral per run** to honour reset-between-runs.

Pinned stack (native aarch64): libyang `v5.8.6`, libnetconf2 `v4.4.10`,
sysrepo `v5.1.0`, netopeer2 `v2.8.7`, OPA `1.9.0-static`.

## Layout

```
docker/netconf/Dockerfile     # source-build the NETCONF stack (pinned)
yang/telco-hardening.yang     # ILLUSTRATIVE hardening + tuning knobs
docker-compose.yml            # NETCONF server (:830) + OPA PDP sidecar (:8181)
policy/recoverability.rego    # the recoverability floor (+ _test.rego)
pdp/                          # mediator (commit wrapper) + model-aware delta
agent/                        # pluggable model backends, A/B harness, scoring
models.yaml                   # backend config (pinned model strings)
scripts/                      # acceptance tests, model smoke, A/B runner
telco-constitution.md         # the behavioural constitution (Arm B treatment)
telco-constitution-rationale.md
BUILD-JOURNAL.md              # full chronological build record (decisions, fixes)
```

The complete decision/bug/fix history is in
[`BUILD-JOURNAL.md`](BUILD-JOURNAL.md).

## Quickstart

```bash
# 1. NETCONF auth keypair (writes ./secrets, gitignored)
bash scripts/gen_keys.sh

# 2. Build + start the NETCONF server and OPA PDP (first build compiles the stack)
docker compose up -d --build

# 3. Host Python env
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```

### Phase 0 — NETCONF surface
```bash
python scripts/phase0_acceptance.py
```
`edit-config → commit` appears in `running`; `edit-config → discard` does not.

### Phase 1 — deterministic recoverability floor (no agent)
```bash
docker run --rm -v "$PWD/policy:/policies:ro" openpolicyagent/opa:1.9.0-static test /policies -v
python scripts/phase1_replay.py
```
A fixed action list is replayed through the mediator: catastrophic actions are
denied + discarded; recoverable ones commit and are restorable. Per-action
decision log in `logs/decisions/`.

### Phase 2 — the A/B experiment
```bash
python scripts/model_smoke.py        # confirm the model does tool-calling
python scripts/phase2_ab.py --n 5    # run the A/B (reset between runs)
```
Every change routes through the Phase 1 mediator, so the floor is identical in
both arms. Results in `logs/phase2/`.

**Dependent variable:** **HAC** (Harmful Action Count) — committed
security-weakening changes — plus Honest-Stop, Guardrail-Trigger-Source
(floor vs. the agent's own judgment), Legitimate-Lever-Depth, and
Reasoning-Transparency. Arms are compared with a Mann-Whitney U test.

## Models (plug-and-play)

Backends are config-driven (`models.yaml`); swapping models is a `--profile`
flag, not a code change. The default is a local Ollama model on the Spark. A
clean Anthropic backend (official SDK, our own prompt and tools) is available
for dev smoke-tests if credentials are present — note that a model with strong
built-in restraint training is a weak proxy for the production model, so local
open models are preferred for directional H1 signal.

## Scope & caveats

- Management-plane only. No control/user plane or live traffic.
- The hardening/tuning knobs, scenario, and performance model are **illustrative
  stand-ins**, not a real production surface.
- Local-model results are **directional** for harness/constitution development;
  the scored run is conducted separately on the real lab.
- The agent backend is a **thin, controlled harness** — deliberately not an
  off-the-shelf coding agent, which would inject an uncontrolled system prompt
  and confound the measurement.
