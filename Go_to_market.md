# SentinelOps — Go-to-Market & Deployment Plan

*One-page companion to the technical README — how this becomes a real product, not just a demo.*

## The problem, in business terms

Every company running a website or app eventually gets paged at 3am. Someone has to
figure out *why* something broke — from symptoms that often look identical across very
different root causes — and fix it before it costs revenue or trust. Today that's either
a tired human, or a static automation script that tries one fixed action and gives up.
Both are slow, and the script gets worse the longer it's wrong.

## What we sell

An incident-response agent that plugs into the monitoring and infrastructure tools a
company already uses, and closes the loop a static runbook can't: try a fix, check if it
actually worked, adapt if it didn't — before ever waking someone up.

## Target customer

Engineering teams at companies past the point of "one person watches the dashboard" but
before the size where they've built a large in-house SRE/automation team — roughly
seed-to-Series-C SaaS and e-commerce companies. They already pay for a monitoring tool
(Datadog, New Relic) and an alerting tool (PagerDuty) — SentinelOps sits between the two.

## How it connects to their real stack

The version demoed here runs against a *simulated* environment on purpose — it proves
the decision loop without needing production access. Turning it into a real product
means swapping that simulation for real connections; the agent logic itself doesn't change.

| Demo | Production |
|---|---|
| Simulated metrics | Datadog / Prometheus / CloudWatch API |
| Simulated security alerts | Existing SIEM / security tooling |
| Simulated actions (restart, scale, block IP) | Real API calls to AWS / Kubernetes / cloud provider |
| Simulated escalation | Real PagerDuty / Opsgenie / Slack alert |

No changes to the customer's website or app code — this integrates on the operations
side, the same way a monitoring tool does, not the product side.

## Rollout plan (this is the trust-building part)

No engineering team lets a new AI system take real production actions on day one — the
adoption path has to earn that, in stages:

1. **Connect, watch, say nothing.** Read-only access to metrics and logs. No actions.
2. **Shadow mode.** For every real incident, the agent logs what it *would* have done and
   whether it thinks that would have worked — visible to the team, zero real actions taken.
   This is how a team builds confidence in the model before risking anything.
3. **Approve-to-act.** The agent proposes an action; a human clicks approve. Fast for the
   team, still a human in the loop.
4. **Autonomous for low-risk actions.** Things like clearing a cache or restarting a
   known-safe service run automatically; higher-risk actions (blocking IPs, rotating
   credentials) still require approval.
5. **Full autonomy**, service by service, as the agent's real track record — the same
   learned success-rate table shown in the demo, now built from real outcomes instead of
   simulated ones — earns it.

## Business model

Usage-based pricing tied to value delivered, not seats: price per service monitored,
with the pitch being incidents auto-resolved without paging anyone. That ROI is easy to
show a customer directly — "SentinelOps resolved N incidents last month without waking
your team up."

## Why this rollout plan matters for the pitch

It's the difference between a demo and a product. A judge who sees only "the agent
works" can reasonably ask "would anyone actually trust this in production?" Answering
that with a concrete, staged trust-building path — not "just turn it on" — is what turns
a working prototype into something a real engineering team could actually adopt.

## What's proven vs. what's next

- **Proven today:** the decision loop itself — observe, decide, act, evaluate, adapt —
  against eight distinct simulated failure modes, benchmarked against a static baseline
  on identical conditions (94% vs 60% self-resolution).
- **Next steps to productize:** real integrations (start with one monitoring tool + one
  cloud provider), the shadow-mode logging/reporting layer, and a permissions model for
  the approve-to-act stage.
