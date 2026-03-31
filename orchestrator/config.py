from pydantic_settings import BaseSettings


class OrchestratorConfig(BaseSettings):
    # Azure AI Foundry
    azure_ai_project_endpoint: str = ""
    foundry_mode: str = "azure"  # "azure" | "mock"

    # MCP server
    mcp_server_url: str = "http://localhost:8000"
    mcp_retry_max_attempts: int = 3
    mcp_retry_backoff_seconds: list[int] = [1, 2, 4]

    # Loops
    transcript_capture_interval_seconds: int = 60
    realtime_loop_interval_seconds: int = 60
    realtime_loop_start_delay_seconds: int = 120

    # Agenda adherence
    similarity_window_seconds: int = 120
    off_track_consecutive_windows: int = 3
    off_track_similarity_threshold: float = 0.35
    agenda_unclear_threshold: float = 0.4
    agenda_unclear_trigger_minutes: int = 5
    agenda_unclear_second_alert_minutes: int = 8

    # Purpose detection
    purpose_detection_delay_seconds: int = 120
    purpose_drift_consecutive_minutes: int = 5
    purpose_recheck_interval_minutes: int = 5

    # Tone & participation
    tone_escalation_window_seconds: int = 180
    participation_pulse_interval_minutes: int = 5
    silent_participant_threshold_minutes: int = 10

    # Alerts & retries
    alert_throttle_window_seconds: int = 300
    specialist_agent_timeout_seconds: int = 120

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": "ORCH_", "case_sensitive": False}


config = OrchestratorConfig()
