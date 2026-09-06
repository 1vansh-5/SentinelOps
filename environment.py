"""
environment.py
Simulates a small fleet of microservices with metrics that drift, and
occasionally injects incidents. Ground-truth incident identity and the
"correct" fix are hidden from the agent -- the agent only ever sees
symptoms (metric readings), exactly like a real ops environment.
"""
import random

THRESHOLDS = {
    "cpu": 85,
    "mem": 85,
    "latency": 300,   # ms
    "error_rate": 2,  # %
    "disk": 90,
    "security_alert": 0,
}

# Ground truth: which actions actually fix which incident, and how well.
# The agent NEVER reads this dict -- it's used only by the environment to
# decide how the world responds to an action.
INCIDENTS = {
    "crashed_service": {
        "effect": {"latency": 900, "error_rate": 40},
        "fixes": {"restart_service": 0.9, "rollback_deploy": 0.55},
    },
    "memory_leak": {
        "effect": {"mem": 96, "latency": 400},
        "fixes": {"restart_service": 0.85, "scale_up": 0.4},
    },
    "ddos_attack": {
        "effect": {"latency": 950, "error_rate": 30, "cpu": 97, "security_alert": 1},
        "fixes": {"block_ip": 0.85, "isolate_host": 0.7, "scale_up": 0.25},
    },
    "credential_stuffing": {
        "effect": {"error_rate": 15, "security_alert": 1},
        "fixes": {"rotate_credentials": 0.9, "block_ip": 0.6},
    },
    "disk_full": {
        "effect": {"disk": 99, "error_rate": 20},
        "fixes": {"cleanup_logs": 0.95},
    },
    "config_drift": {
        "effect": {"error_rate": 25, "latency": 350},
        "fixes": {"rollback_deploy": 0.9, "restart_service": 0.3},
    },
    "latency_spike_load": {
        "effect": {"latency": 500, "cpu": 90, "mem": 80},
        "fixes": {"scale_up": 0.85, "clear_cache": 0.5},
    },
    # A deliberately NOVEL / unseen incident, not in any prior knowledge the
    # agent starts with. Used to test robustness against the unknown.
    "cascading_dependency_failure": {
        "effect": {"latency": 700, "error_rate": 35, "cpu": 80, "mem": 85},
        "fixes": {"restart_service": 0.3, "rollback_deploy": 0.3, "scale_up": 0.3, "isolate_host": 0.2},
    },
}

ACTIONS = [
    "restart_service", "scale_up", "clear_cache", "rollback_deploy",
    "block_ip", "isolate_host", "rotate_credentials", "cleanup_logs",
    "escalate_to_human", "no_op",
]

BASELINE = {"cpu": 35, "mem": 40, "latency": 120, "error_rate": 0.3, "disk": 45, "security_alert": 0}


class Service:
    def __init__(self, name):
        self.name = name
        self.metrics = dict(BASELINE)
        self.active_incident = None
        self.ticks_with_incident = 0

    def is_healthy(self):
        m = self.metrics
        return (m["cpu"] < THRESHOLDS["cpu"] and m["mem"] < THRESHOLDS["mem"] and
                m["latency"] < THRESHOLDS["latency"] and m["error_rate"] < THRESHOLDS["error_rate"] and
                m["disk"] < THRESHOLDS["disk"] and m["security_alert"] <= THRESHOLDS["security_alert"])

    def symptom_signature(self):
        m = self.metrics
        return (
            m["cpu"] >= THRESHOLDS["cpu"],
            m["mem"] >= THRESHOLDS["mem"],
            m["latency"] >= THRESHOLDS["latency"],
            m["error_rate"] >= THRESHOLDS["error_rate"],
            m["disk"] >= THRESHOLDS["disk"],
            m["security_alert"] > THRESHOLDS["security_alert"],
        )


class Environment:
    """Deterministic-given-seed simulation so adaptive vs baseline agents
    can be compared fairly on the *same* sequence of incidents."""

    def __init__(self, service_names, seed=42, incident_prob=0.22, flaky_exec_prob=0.10):
        self.rng = random.Random(seed)
        self.services = {n: Service(n) for n in service_names}
        self.incident_prob = incident_prob
        self.flaky_exec_prob = flaky_exec_prob
        self.tick_num = 0
        self.log = []

    def drift(self):
        """Idle metrics wobble slightly even when healthy."""
        for svc in self.services.values():
            if svc.active_incident is None:
                for k in ("cpu", "mem", "latency", "error_rate", "disk"):
                    base = BASELINE[k]
                    svc.metrics[k] = max(0, base + self.rng.uniform(-5, 5))
                svc.metrics["security_alert"] = 0

    def maybe_inject_incident(self):
        for svc in self.services.values():
            if svc.active_incident is None and self.rng.random() < self.incident_prob:
                incident = self.rng.choice(list(INCIDENTS.keys()))
                svc.active_incident = incident
                svc.ticks_with_incident = 0
                for k, v in INCIDENTS[incident]["effect"].items():
                    svc.metrics[k] = v
                self.log.append(f"[env] incident '{incident}' injected on {svc.name}")

    def escalate_severity_if_unresolved(self, svc):
        """Real incidents get worse the longer they're left untreated --
        this is what makes speed/efficiency of the agent loop matter."""
        if svc.active_incident:
            svc.ticks_with_incident += 1
            if svc.ticks_with_incident > 3:
                for k in ("latency", "error_rate", "cpu"):
                    if k in svc.metrics:
                        svc.metrics[k] *= 1.08

    def apply_action(self, service_name, action):
        """Returns True if the action executed at all (it may still have
        been the *wrong* fix). Randomly injects tool/infra flakiness so the
        agent cannot assume an action call = an action effect."""
        svc = self.services[service_name]

        if self.rng.random() < self.flaky_exec_prob:
            self.log.append(f"[env] action '{action}' on {svc.name} FAILED TO EXECUTE (infra flakiness)")
            return False  # the call itself failed -- world unchanged

        if action == "no_op" or action == "escalate_to_human":
            return True

        incident = svc.active_incident
        if incident is None:
            return True  # acting on a healthy service does nothing bad

        fix_table = INCIDENTS[incident]["fixes"]
        success_prob = fix_table.get(action, 0.03)  # wrong action rarely helps by luck
        roll = self.rng.random()
        if roll < success_prob:
            # Resolves the incident
            svc.active_incident = None
            svc.ticks_with_incident = 0
            for k in svc.metrics:
                svc.metrics[k] = BASELINE[k] + self.rng.uniform(-3, 3)
            svc.metrics["security_alert"] = 0
        elif roll < success_prob + 0.15:
            # Partial improvement, not fully resolved
            for k, v in INCIDENTS[incident]["effect"].items():
                svc.metrics[k] = max(BASELINE.get(k, 0), v * 0.6)
        elif action not in fix_table and self.rng.random() < 0.2:
            # Wrong action makes things mildly worse (e.g. restarting the
            # wrong component causes a brief additional blip)
            for k in svc.metrics:
                if k in INCIDENTS[incident]["effect"]:
                    svc.metrics[k] *= 1.1
        return True

    def tick(self):
        self.tick_num += 1
        self.drift()
        self.maybe_inject_incident()
        for svc in self.services.values():
            self.escalate_severity_if_unresolved(svc)
