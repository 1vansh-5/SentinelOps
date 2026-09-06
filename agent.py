"""
agent.py
SentinelOps adaptive agent: implements the observe -> decide -> act ->
evaluate -> adapt loop against the simulated Environment.

Also implements a BaselineAgent representing a traditional static runbook
(if/elif script) so we can prove, with numbers, that the agentic loop is
doing real work -- not just automating what a script already could.
"""
from policy import AdaptivePolicy, sig_key

MAX_ATTEMPTS_PER_INCIDENT = 4
GOAL = "Keep every service within SLA (low latency/error/cpu/mem/disk, no security alerts) with minimal escalations and minimal time-to-resolution."


class IncidentAttemptState:
    """Per-service memory of the CURRENT incident episode: what's been
    tried and failed already (a 'tabu list'), so the agent never repeats
    a known-bad move on the same incident -- this is the multi-step /
    adaptation mechanic."""
    def __init__(self):
        self.tried_and_failed = set()
        self.attempts = 0
        self.history_text = []


class AdaptiveAgent:
    def __init__(self, env, name="SentinelOps-Adaptive"):
        self.env = env
        self.name = name
        self.policy = AdaptivePolicy()
        self.state_per_service = {s: IncidentAttemptState() for s in env.services}
        self.trace = []
        self.stats = {
            "incidents_seen": 0, "resolved_by_agent": 0, "escalations": 0,
            "sla_violation_ticks": 0, "steps_taken": [],
        }

    def run(self, ticks):
        for _ in range(ticks):
            self.env.tick()
            for name, svc in self.env.services.items():
                self._handle_service(name, svc)
        return self.stats, self.trace

    def _handle_service(self, name, svc):
        st = self.state_per_service[name]

        if not svc.is_healthy():
            self.stats["sla_violation_ticks"] += 1

        # --- OBSERVE ---
        sig = sig_key(svc.symptom_signature())
        if svc.active_incident is None:
            st.tried_and_failed.clear()
            st.attempts = 0
            st.history_text.clear()
            return  # nothing to do

        if st.attempts == 0:
            self.stats["incidents_seen"] += 1

        if st.attempts >= MAX_ATTEMPTS_PER_INCIDENT:
            action = "escalate_to_human"
            reason = "retry budget exhausted"
        else:
            # --- DECIDE (dynamic action selection) ---
            action, reason = self.policy.decide(
                sig, exclude=st.tried_and_failed, rng=self.env.rng,
                incident_history_text="; ".join(st.history_text[-3:]),
            )

        self.trace.append(f"t={self.env.tick_num} [{name}] OBSERVE sig={sig} incident~'{svc.active_incident}' "
                           f"-> DECIDE '{action}' ({reason})")

        if action == "escalate_to_human":
            self.stats["escalations"] += 1
            self.stats["steps_taken"].append(st.attempts)
            self.trace.append(f"t={self.env.tick_num} [{name}] ESCALATE to human after {st.attempts} attempt(s)")
            svc.active_incident = None  # human resolves it out-of-band
            st.tried_and_failed.clear(); st.attempts = 0; st.history_text.clear()
            return

        # --- ACT ---
        st.attempts += 1
        executed = self.env.apply_action(name, action)

        # --- EVALUATE ---
        if not executed:
            reward, outcome = 0.0, "tool call failed to execute"
        elif svc.active_incident is None:
            reward, outcome = 1.0, "RESOLVED"
        elif svc.is_healthy():
            reward, outcome = 1.0, "RESOLVED"
        else:
            still_bad_sig = sig_key(svc.symptom_signature())
            reward = 0.35 if still_bad_sig != sig else 0.0
            outcome = "partial improvement" if reward > 0 else "no improvement"

        self.trace.append(f"t={self.env.tick_num} [{name}] ACT '{action}' executed={executed} -> EVALUATE: {outcome}")

        # --- ADAPT ---
        self.policy.update(sig, action, reward)
        st.history_text.append(f"tried {action} -> {outcome}")
        if reward == 0.0:
            st.tried_and_failed.add(action)  # never blindly repeat a proven failure

        if outcome == "RESOLVED":
            self.stats["resolved_by_agent"] += 1
            self.stats["steps_taken"].append(st.attempts)
            st.tried_and_failed.clear(); st.attempts = 0; st.history_text.clear()


# ----------------------------------------------------------------------
# Non-agentic baseline: a static runbook script. One fixed lookup table,
# one attempt, no memory of what already failed, no learning, immediate
# escalation on failure. This is what "just automate the obvious rule"
# looks like -- included to prove the agent loop is earning its keep.
# ----------------------------------------------------------------------
STATIC_RUNBOOK = {
    ("F", "F", "T", "T", "F", "F"): "restart_service",
    ("F", "T", "T", "F", "F", "F"): "restart_service",
    ("T", "F", "T", "T", "F", "T"): "block_ip",
    ("F", "F", "F", "T", "F", "T"): "rotate_credentials",
    ("F", "F", "F", "T", "T", "F"): "cleanup_logs",
    ("T", "T", "T", "F", "F", "F"): "scale_up",
    # no entry at all for novel signatures -> falls through to a generic guess
}


class BaselineAgent:
    def __init__(self, env, name="Static-Runbook-Baseline"):
        self.env = env
        self.name = name
        self.trace = []
        self.stats = {
            "incidents_seen": 0, "resolved_by_agent": 0, "escalations": 0,
            "sla_violation_ticks": 0, "steps_taken": [],
        }
        self._active = set()

    def run(self, ticks):
        for _ in range(ticks):
            self.env.tick()
            for name, svc in self.env.services.items():
                self._handle_service(name, svc)
        return self.stats, self.trace

    def _handle_service(self, name, svc):
        if not svc.is_healthy():
            self.stats["sla_violation_ticks"] += 1
        if svc.active_incident is None:
            self._active.discard(name)
            return
        if name in self._active:
            return  # already acted once this incident; static script does not retry
        self._active.add(name)
        self.stats["incidents_seen"] += 1

        sig = sig_key(svc.symptom_signature())
        action = STATIC_RUNBOOK.get(sig, "restart_service")  # generic default guess
        self.trace.append(f"t={self.env.tick_num} [{name}] RUNBOOK sig={sig} -> single fixed action '{action}'")

        self.env.apply_action(name, action)

        if svc.active_incident is None:
            self.stats["resolved_by_agent"] += 1
            self.stats["steps_taken"].append(1)
        else:
            self.stats["escalations"] += 1
            self.stats["steps_taken"].append(1)
            svc.active_incident = None  # escalate immediately, no retry logic at all
