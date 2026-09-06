"""
policy.py
This is the agent's "brain": a table of estimated action-success-rates per
symptom signature, seeded with plausible (but imperfect) priors and updated
online from real outcomes -- classic bandit-style reinforcement.

It also demonstrates graceful degradation: if an Anthropic API key is
available it can call an LLM to reason through ambiguous/ novel cases;
if not (or the call fails), it falls back to the learned table without
crashing. This is the "robustness" piece.
"""
import os
import json

ACTIONS = [
    "restart_service", "scale_up", "clear_cache", "rollback_deploy",
    "block_ip", "isolate_host", "rotate_credentials", "cleanup_logs",
    "escalate_to_human",
]

SIGNATURE_LABELS = ["cpu_high", "mem_high", "latency_high", "error_high", "disk_high", "security_alert"]

# Heuristic priors: plausible first guesses an SRE playbook might encode.
# Deliberately imperfect / incomplete -- the agent has to learn the rest,
# and has NO prior at all for symptom signatures it has never seen
# (e.g. the novel cascading-failure signature).
PRIOR_HINTS = {
    ("F", "F", "T", "T", "F", "F"): {"rollback_deploy": 0.6, "restart_service": 0.5, "clear_cache": 0.3},
    ("F", "T", "T", "F", "F", "F"): {"restart_service": 0.5, "scale_up": 0.3},
    ("T", "F", "T", "T", "F", "T"): {"block_ip": 0.6, "isolate_host": 0.5, "scale_up": 0.3},
    ("F", "F", "F", "T", "F", "T"): {"rotate_credentials": 0.6, "block_ip": 0.4},
    ("F", "F", "F", "T", "T", "F"): {"cleanup_logs": 0.7},
    ("T", "T", "T", "F", "F", "F"): {"scale_up": 0.6, "clear_cache": 0.35},
}


def sig_key(signature_bools):
    return tuple("T" if b else "F" for b in signature_bools)


class AdaptivePolicy:
    def __init__(self, alpha=0.35, default_prior=0.15):
        self.alpha = alpha
        self.default_prior = default_prior
        self.q = {}  # (sig_key, action) -> estimated success rate
        self.calls = 0
        self.use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self._client = None
        if self.use_llm:
            try:
                import anthropic  # noqa
                self._client = anthropic.Anthropic()
            except Exception:
                self.use_llm = False  # graceful degrade if SDK missing

    def _get_q(self, sig, action):
        if (sig, action) not in self.q:
            self.q[(sig, action)] = PRIOR_HINTS.get(sig, {}).get(action, self.default_prior)
        return self.q[(sig, action)]

    def rank_actions(self, sig, exclude=()):
        candidates = [a for a in ACTIONS if a not in exclude and a != "escalate_to_human"]
        scored = sorted(candidates, key=lambda a: self._get_q(sig, a), reverse=True)
        return [(a, self._get_q(sig, a)) for a in scored]

    def decide(self, sig, exclude, rng, incident_history_text=""):
        """Dynamic action selection: epsilon-greedy over learned Q-values,
        with an optional LLM consult when the top choices are essentially
        tied (genuine uncertainty) -- otherwise pure learned policy."""
        ranked = self.rank_actions(sig, exclude=exclude)
        if not ranked:
            return "escalate_to_human", "no untried actions remain"

        top_action, top_q = ranked[0]
        runner_up_q = ranked[1][1] if len(ranked) > 1 else -1

        # Exploration for continued learning
        if rng.random() < 0.12:
            explore_action = rng.choice([a for a, _ in ranked])
            return explore_action, "exploring to improve estimate"

        # Ambiguous case -> consult LLM if available, else just go with top Q
        if self.use_llm and abs(top_q - runner_up_q) < 0.08 and len(ranked) > 1:
            choice = self._llm_decide(sig, ranked, incident_history_text)
            if choice:
                return choice, "LLM tie-break under uncertainty"

        return top_action, f"highest learned success rate ({top_q:.2f})"

    def _llm_decide(self, sig, ranked, incident_history_text):
        try:
            candidates = [a for a, _ in ranked[:4]]
            prompt = (
                "You are an SRE incident-response reasoning module. "
                f"Symptoms observed (signature order {SIGNATURE_LABELS}): {sig}. "
                f"Candidate remediation actions with current learned success rates: {ranked[:4]}. "
                f"Recent attempt history for this incident: {incident_history_text or 'none'}. "
                "Reply with strict JSON only: {\"action\": \"<one of the candidate actions>\"}"
            )
            resp = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            data = json.loads(text.strip().strip("`").replace("json\n", ""))
            action = data.get("action")
            return action if action in candidates else None
        except Exception:
            return None  # robust fallback -- never crash the loop on an API hiccup

    def update(self, sig, action, reward):
        old = self._get_q(sig, action)
        self.q[(sig, action)] = old + self.alpha * (reward - old)
