"""
ConfigScaler — adapts OrchestratorConfig thresholds to meeting duration.

For short meetings the default fixed-minute values are too coarse.
This class computes proportional replacements so every check fires
at a meaningful point in the meeting regardless of its length.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import OrchestratorConfig

logger = logging.getLogger("orchestrator.config_scaler")

# Meetings >= this duration use the original config unchanged.
_LONG_MEETING_THRESHOLD_MINUTES = 30


class ConfigScaler:
    """Scale time-sensitive config thresholds to a given meeting duration."""

    # (field_name, fraction_of_duration, minimum_value, unit)
    # unit is "seconds" or "minutes" — determines how fraction*duration is converted
    _RULES: list[tuple[str, float, int, str]] = [
        ("purpose_detection_delay_seconds",      0.20, 60,  "seconds"),
        ("purpose_drift_consecutive_minutes",    0.15,  1,  "minutes"),
        ("purpose_recheck_interval_minutes",     0.15,  1,  "minutes"),
        ("participation_pulse_interval_minutes", 0.20,  2,  "minutes"),
        ("silent_participant_threshold_minutes", 0.25,  2,  "minutes"),
        ("realtime_loop_start_delay_seconds",    0.15, 30,  "seconds"),
        ("time_remaining_alert_minutes",         0.15,  1,  "minutes"),
    ]

    def scale(
        self,
        cfg: OrchestratorConfig,
        end_time: Optional[datetime],
    ) -> OrchestratorConfig:
        """
        Return a scaled copy of cfg, or the original if end_time is unknown
        or the meeting is long enough that defaults are appropriate.
        """
        if not end_time:
            logger.debug("No end_time — using default config")
            return cfg

        now = datetime.now(timezone.utc)
        duration_minutes = max((end_time - now).total_seconds() / 60, 1)

        if duration_minutes >= cfg.config_scale_threshold_minutes:
            logger.debug("Long meeting (%.0f min) — using default config", duration_minutes)
            return cfg

        scaled = copy.copy(cfg)
        for field, fraction, minimum, unit in self._RULES:
            if unit == "seconds":
                value = max(minimum, int(duration_minutes * 60 * fraction))
            else:
                value = max(minimum, int(duration_minutes * fraction))
            setattr(scaled, field, value)

        logger.info(
            "Config scaled for %.0f-min meeting: "
            "purpose_delay=%ds drift=%dm pulse=%dm silent=%dm start_delay=%ds",
            duration_minutes,
            scaled.purpose_detection_delay_seconds,
            scaled.purpose_drift_consecutive_minutes,
            scaled.participation_pulse_interval_minutes,
            scaled.silent_participant_threshold_minutes,
            scaled.realtime_loop_start_delay_seconds,
        )
        return scaled
