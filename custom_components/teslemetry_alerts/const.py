"""Constants for Teslemetry Alerts."""

from __future__ import annotations

import logging

DOMAIN = "teslemetry_alerts"
LOGGER = logging.getLogger(__package__)

# The core Teslemetry integration's domain: its vehicle devices are identified
# by (TESLEMETRY_DOMAIN, vin), so our entities join those devices.
TESLEMETRY_DOMAIN = "teslemetry"

API_URL = "https://api.teslemetry.com"
# Only the alert and error topics: this connection adds no telemetry fields,
# so it does not touch the vehicles' streaming allowance.
SSE_TOPICS = "alerts,errors"

# Bus event fired for each alert that starts or ends while connected.
EVENT_ALERT = "teslemetry_alert"

EVENT_STARTED = "started"
EVENT_ENDED = "ended"

# Alerts kept per vehicle; the oldest are dropped first.
MAX_ALERTS = 100

SIGNAL_UPDATE = f"{DOMAIN}_update_{{entry_id}}_{{vin}}"
SIGNAL_ALERT = f"{DOMAIN}_alert_{{entry_id}}_{{vin}}"
