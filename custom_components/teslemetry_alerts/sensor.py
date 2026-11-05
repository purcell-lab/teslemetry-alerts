"""Alert sensors for Teslemetry Alerts."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TeslemetryAlertsConfigEntry
from .coordinator import alert_attributes
from .entity import TeslemetryAlertsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslemetryAlertsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    manager = entry.runtime_data
    async_add_entities(
        entity
        for vin in manager.vehicles
        for entity in (
            LatestAlertSensor(manager, vin, "latest_alert"),
            ActiveAlertsSensor(manager, vin, "active_alerts"),
            LatestErrorSensor(manager, vin, "latest_error"),
        )
    )


class LatestAlertSensor(TeslemetryAlertsEntity, SensorEntity):
    """The most recent alert: its touchscreen message, details as attributes."""

    def _update_attrs(self) -> None:
        if (alert := self.vehicle.latest) is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        attrs = alert_attributes(alert)
        self._attr_native_value = (attrs["message"] or attrs["name"])[:255]
        self._attr_extra_state_attributes = attrs


class ActiveAlertsSensor(TeslemetryAlertsEntity, SensorEntity):
    """How many alerts are active, listed in the alerts attribute."""

    def _update_attrs(self) -> None:
        if not self.vehicle.synced:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        active = self.vehicle.active
        self._attr_native_value = len(active)
        self._attr_extra_state_attributes = {
            "alerts": [
                {
                    "name": a.get("name"),
                    "message": a.get("customerFacingMessage1"),
                    "audiences": a.get("audiences") or [],
                    "started_at": a.get("startedAt"),
                }
                for a in active
            ]
        }


class LatestErrorSensor(TeslemetryAlertsEntity, SensorEntity):
    """The most recent telemetry error Teslemetry reported for the vehicle."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _update_attrs(self) -> None:
        if (error := self.vehicle.latest_error) is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_native_value = str(error.get("name"))[:255]
        self._attr_extra_state_attributes = {
            "created_at": error.get("createdAt"),
            "tags": error.get("tags") or {},
            "body": error.get("body"),
        }
