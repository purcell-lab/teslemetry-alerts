"""Per-vehicle alert state, fed by the alert stream."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    EVENT_ALERT,
    EVENT_ENDED,
    EVENT_STARTED,
    MAX_ALERTS,
    SIGNAL_ALERT,
    SIGNAL_UPDATE,
    TESLEMETRY_DOMAIN,
)


def alert_attributes(alert: dict[str, Any]) -> dict[str, Any]:
    """Map a stream alert record to Home Assistant attribute names."""
    return {
        "name": alert.get("name"),
        "message": alert.get("customerFacingMessage1"),
        "detail": alert.get("customerFacingMessage2"),
        "audiences": alert.get("audiences") or [],
        "started_at": alert.get("startedAt"),
        "ended_at": alert.get("endedAt"),
        "active": not alert.get("endedAt"),
        "description": alert.get("description"),
        "potential_impact": alert.get("potentialImpact"),
        "condition": alert.get("condition"),
        "clear_condition": alert.get("clearCondition"),
    }


def _started(alert: dict[str, Any]) -> str:
    return alert.get("startedAt") or ""


@dataclass
class VehicleAlerts:
    """Alert state for one vehicle."""

    name: str
    alerts: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    latest_error: dict[str, Any] | None = None
    # Set once the first alerts batch arrives. Until then a cached batch is
    # history, not news, so it fills the state without firing events.
    synced: bool = False

    @property
    def latest(self) -> dict[str, Any] | None:
        """Return the most recently started alert."""
        return max(self.alerts.values(), key=_started, default=None)

    @property
    def active(self) -> list[dict[str, Any]]:
        """Return the alerts that have not ended, newest first."""
        return sorted(
            (a for a in self.alerts.values() if not a.get("endedAt")),
            key=_started,
            reverse=True,
        )


class AlertManager:
    """Holds alert state for each vehicle and fans updates out to entities."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vehicles: dict[str, str]
    ) -> None:
        """Initialise the manager."""
        self.hass = hass
        self.entry = entry
        self.vehicles = {vin: VehicleAlerts(name) for vin, name in vehicles.items()}
        self.connected = False

    def device_info(self, vin: str) -> DeviceInfo:
        """Join the Teslemetry integration's device for this vehicle."""
        identifiers = {(TESLEMETRY_DOMAIN, vin)}
        if dr.async_get(self.hass).async_get_device(identifiers=identifiers):
            return DeviceInfo(identifiers=identifiers)
        return DeviceInfo(
            identifiers=identifiers,
            name=self.vehicles[vin].name,
            manufacturer="Tesla",
            serial_number=vin,
        )

    @callback
    def set_connected(self, connected: bool) -> None:
        """Record the stream's connection state."""
        self.connected = connected

    @callback
    def handle_event(self, event: str, payload: dict[str, Any]) -> None:
        """Handle one event from the stream."""
        vin = payload.get("vin")
        if (vehicle := self.vehicles.get(vin)) is None:
            return
        is_cache = bool(payload.get("isCache"))
        if event == "alerts" and isinstance(payload.get("alerts"), list):
            self._handle_alerts(vin, vehicle, payload["alerts"], is_cache)
        elif event == "errors" and isinstance(payload.get("errors"), list):
            for error in payload["errors"]:
                if not isinstance(error, dict):
                    continue
                current = vehicle.latest_error
                if current is None or (error.get("createdAt") or "") >= (
                    current.get("createdAt") or ""
                ):
                    vehicle.latest_error = error
        else:
            return
        async_dispatcher_send(
            self.hass, SIGNAL_UPDATE.format(entry_id=self.entry.entry_id, vin=vin)
        )

    def _handle_alerts(
        self,
        vin: str,
        vehicle: VehicleAlerts,
        alerts: list[Any],
        is_cache: bool,
    ) -> None:
        silent = is_cache and not vehicle.synced
        newest_before = max(map(_started, vehicle.alerts.values()), default="")
        records = [a for a in alerts if isinstance(a, dict) and a.get("name")]
        for alert in sorted(records, key=_started):
            key = (alert["name"], _started(alert))
            previous = vehicle.alerts.get(key)
            if previous and previous.get("endedAt") and not alert.get("endedAt"):
                # A stale copy of an alert that has already ended: keep the end.
                continue
            vehicle.alerts[key] = alert
            if silent:
                continue
            if previous is None:
                # A cached batch after a reconnect repeats history; only alerts
                # newer than anything already seen happened while disconnected.
                if is_cache and key[1] <= newest_before:
                    continue
                self._fire(vin, vehicle, EVENT_STARTED, alert)
                if alert.get("endedAt"):
                    self._fire(vin, vehicle, EVENT_ENDED, alert)
            elif alert.get("endedAt") and not previous.get("endedAt"):
                self._fire(vin, vehicle, EVENT_ENDED, alert)
        vehicle.synced = True
        if len(vehicle.alerts) > MAX_ALERTS:
            keep = sorted(vehicle.alerts.items(), key=lambda kv: _started(kv[1]))
            vehicle.alerts = dict(keep[-MAX_ALERTS:])

    def _fire(
        self, vin: str, vehicle: VehicleAlerts, event_type: str, alert: dict[str, Any]
    ) -> None:
        data = alert_attributes(alert)
        self.hass.bus.async_fire(
            EVENT_ALERT,
            {"vin": vin, "vehicle": vehicle.name, "type": event_type, **data},
        )
        async_dispatcher_send(
            self.hass,
            SIGNAL_ALERT.format(entry_id=self.entry.entry_id, vin=vin),
            event_type,
            data,
        )
