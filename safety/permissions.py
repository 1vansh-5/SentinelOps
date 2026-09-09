SAFE_ACTIONS = [
    "get_metrics",
    "get_logs",
    "get_deployments"
]

DANGEROUS_ACTIONS = [
    "rollback",
    "restart_service",
    "scale_up"
]
def is_allowed(action):

    if action in SAFE_ACTIONS:
        return True

    return False