def get_recent_deployments(environment):
    return environment.deployments[-5:]