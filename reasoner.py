def analyze_incident(incident_data):

    response = ask_astra(
        "Analyze this production incident..."
    )

    return response