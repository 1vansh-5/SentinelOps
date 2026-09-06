"""
run_demo.py
Runs SentinelOps' adaptive agent AND a static-runbook baseline against two
*identical* incident schedules (same random seed) so the comparison is
fair, then prints a report proving the agentic loop's value.
"""
import sys
from environment import Environment
from agent import AdaptiveAgent, BaselineAgent

TICKS = 60
SEED = 7
SERVICES = ["auth-api", "checkout-svc", "search-svc", "notifications-svc"]


def summarize(name, stats):
    steps = stats["steps_taken"]
    avg_steps = sum(steps) / len(steps) if steps else 0
    total = stats["incidents_seen"] or 1
    print(f"\n=== {name} ===")
    print(f"  Incidents encountered:       {stats['incidents_seen']}")
    print(f"  Resolved without escalation: {stats['resolved_by_agent']} "
          f"({100*stats['resolved_by_agent']/total:.1f}%)")
    print(f"  Escalated to a human:        {stats['escalations']} "
          f"({100*stats['escalations']/total:.1f}%)")
    print(f"  Avg. actions per incident:   {avg_steps:.2f}")
    print(f"  Ticks spent in SLA violation:{stats['sla_violation_ticks']}")


def main():
    verbose = "--trace" in sys.argv

    env_a = Environment(SERVICES, seed=SEED)
    adaptive = AdaptiveAgent(env_a)
    adaptive_stats, adaptive_trace = adaptive.run(TICKS)

    env_b = Environment(SERVICES, seed=SEED)  # identical incident schedule
    baseline = BaselineAgent(env_b)
    baseline_stats, baseline_trace = baseline.run(TICKS)

    print("SentinelOps Demo — Adaptive Agent vs Static Runbook")
    print(f"({TICKS} ticks, {len(SERVICES)} services, identical injected-incident schedule, seed={SEED})")

    summarize(adaptive.name, adaptive_stats)
    summarize(baseline.name, baseline_stats)

    a_rate = adaptive_stats["resolved_by_agent"] / (adaptive_stats["incidents_seen"] or 1)
    b_rate = baseline_stats["resolved_by_agent"] / (baseline_stats["incidents_seen"] or 1)
    print(f"\n>> Self-resolution rate improvement from agentic loop: "
          f"{100*(a_rate - b_rate):.1f} percentage points")
    print(f">> SLA-violation ticks avoided: {baseline_stats['sla_violation_ticks'] - adaptive_stats['sla_violation_ticks']}")

    if verbose:
        print("\n--- Adaptive agent trace (first 40 lines) ---")
        for line in adaptive_trace[:40]:
            print(" ", line)


if __name__ == "__main__":
    main()
