# SentinelOps — Autonomous Incident Response Agent

**Domain:** Business Operations / Cybersecurity (IT incident response & self-healing infrastructure)

## The problem

Production services fail in messy, ambiguous ways. A spike in latency could
mean an overloaded box, a bad deploy, a DDoS attack, or a memory leak —
the *symptoms* often look alike, the *right fix* doesn't, and the first fix
you try might not work, might partially work, or might make things worse.
A human on-call engineer reasons through this iteratively: look at the
signals, form a hypothesis, try something, check whether it worked, and
change approach if it didn't — all under time pressure, since unresolved
incidents get worse the longer they sit.

That loop — not a single classification step — is the actual job. This is
why it's an agentic problem rather than a scripting problem.

## Why a static script is not enough (and how the demo proves it)

`agent.py` includes two systems that run against **the exact same injected
incident schedule** (same random seed) so the comparison is apples-to-apples:

| | Adaptive Agent | Static Runbook (baseline) |
|---|---|---|
| Diagnosis | Same symptom→signature classifier | Same symptom→signature classifier |
| Action choice | Learned success-rate table, updated online | One fixed lookup table |
| On failure | Retries a *different* action (never repeats a proven failure), up to a budget | Escalates immediately, no retry |
| Handles novel incidents | Yes — no-prior signatures start at a default score and get learned from outcomes | No — falls through to a generic guess, no way to recover if wrong |
| Result (60-tick run, seed=7) | **93.8%** self-resolved, 1.48 avg actions/incident | **60.0%** self-resolved, escalates 40% of the time |

Run it yourself:

```bash
python3 run_demo.py --trace
```

The static baseline is not a strawman — it's exactly what a well-intentioned
`if symptom_pattern == X: run_fix(Y)` runbook looks like. It's deterministic,
fast, and cheap to build. It also can't get better with experience, can't
recover from being wrong, and breaks down precisely on the cases that matter
most (novel or compound failures). The agent loop is what buys resilience.

## Architecture: Observe → Decide → Act → Evaluate → Adapt

```
 ┌────────────┐   symptom signature    ┌─────────────┐
 │ Environment │ ───────────────────▶  │   OBSERVE   │
 │ (simulated  │                        └──────┬──────┘
 │  services,  │                               ▼
 │  metrics,   │                        ┌─────────────┐   learned Q-table +
 │  incidents) │◀── action ─────────────│   DECIDE    │◀─ optional LLM tie-break
 │             │                        └──────┬──────┘   on genuine uncertainty
 │             │                               ▼
 │             │                        ┌─────────────┐
 │             │──── executes action ──▶│    ACT      │
 │             │                        └──────┬──────┘
 │             │   new metrics                 ▼
 │             │◀───────────────────────┌─────────────┐
 └────────────┘                         │  EVALUATE   │
                                         └──────┬──────┘
                                                ▼
                                         ┌─────────────┐
                                         │   ADAPT     │─▶ updates Q-table,
                                         └─────────────┘   tabu list, retry count
```

* **`environment.py`** — the world. Services drift, incidents get injected
  with hidden ground-truth causes, actions succeed/partially-succeed/fail
  stochastically, and 10% of the time an action call fails to execute at
  all (simulating a flaky API/infra call the agent must not blindly trust).
* **`policy.py`** — the learned brain. A table of
  `(symptom signature, action) → estimated success rate`, seeded with
  imperfect heuristic priors and updated with a simple exponential-moving-
  average reward signal after every attempt (lightweight, dependency-free
  reinforcement learning — no framework required). When two actions are
  essentially tied, and an `ANTHROPIC_API_KEY` is available, it optionally
  asks an LLM to reason through the tie using the attempt history; if the
  key or SDK isn't available, it silently falls back to the learned table.
* **`agent.py`** — the loop itself (`AdaptiveAgent`), plus the
  `BaselineAgent` used for comparison.
* **`run_demo.py`** — runs both agents on identical conditions and reports
  the comparison.

## How each required characteristic shows up

- **Goal-Driven Execution** — the agent's objective is fixed and explicit
  (keep every service inside SLA, minimize escalations and time-to-fix);
  every decision is judged against that goal, not against a single-shot
  correctness check.
- **Dynamic Action Selection** — the action chosen depends on the current
  learned success-rate table *and* what's already been tried on this
  specific incident; the same symptom signature can lead to different
  actions over time as the policy learns, and to an LLM consult only when
  genuinely ambiguous.
- **Multi-Step Execution** — a single incident is not "one classify, one
  fix." The agent retries with a different action if the first doesn't
  work, up to a bounded retry budget, tracking a per-incident tabu list of
  what's already failed.
- **Adaptation** — success/failure of every action updates the policy
  (`policy.update`) via online reward averaging, so future decisions on
  similar symptoms shift toward what has actually worked — including on
  the deliberately novel `cascading_dependency_failure` incident type that
  has *no* hand-written prior at all.
- **Robustness** — the loop tolerates: actions that silently fail to
  execute (flaky infra), incidents that get worse the longer they're left
  untreated, symptom signatures never seen before, and an unavailable/failed
  LLM call (never crashes — always degrades to the learned heuristic table
  and, as a last resort, escalation to a human rather than looping forever).

## Files

- `environment.py` — simulated infrastructure and incident ground truth
- `policy.py` — adaptive decision policy (+ optional LLM tie-break)
- `agent.py` — AdaptiveAgent (observe/decide/act/evaluate/adapt) and BaselineAgent
- `run_demo.py` — comparison runner
- `sample_run.log` — example output from `python3 run_demo.py --trace`
- `docs/index.html` — **browser demo**, a self-contained port of the same
  simulation to vanilla HTML/CSS/JS (no build step, no server, no API keys).
  Deploy it with GitHub Pages: push this repo, then in
  **Settings → Pages → Build and deployment**, set the source branch and
  `/docs` as the folder. The demo will be live at
  `https://<username>.github.io/<repo>/` a minute or two later.

  This file only mirrors the *reference* Python implementation for a
  zero-infrastructure, clickable demo — the canonical logic lives in the
  `.py` files above. It intentionally leaves out the optional LLM tie-break
  from `policy.py`: shipping an API key in client-side JS on a public page
  isn't safe, so the browser version runs on the learned heuristic policy
  alone. A server-side deployment (e.g. the Streamlit or Flask route) is
  the place to wire the LLM piece back in.
