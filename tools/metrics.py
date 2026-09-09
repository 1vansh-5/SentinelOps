def get_metrics(environment):

    return {
        "cpu": environment.cpu,
        "memory": environment.memory,
        "latency": environment.latency,
        "error_rate": environment.error_rate
    }