"""Alert event entity for Teslemetry Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TeslemetryAlertsConfigEntry
from .const import EVENT_ENDED, EVENT_STARTED, SIGNAL_ALERT
from .entity import TeslemetryAlertsEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslemetryAlertsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event entities."""
    manager = entry.runtime_data
    async_add_entities(AlertEvent(manager, vin, "alert") for vin in manager.vehicles)


class AlertEvent(TeslemetryAlertsEntity, EventEntity):
    """Fires when an alert starts or ends."""

    _attr_event_types = [EVENT_STARTED, EVENT_ENDED]

    async def async_added_to_hass(self) -> None:
        """Subscribe to alerts."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ALERT.format(
                    entry_id=self.manager.entry.entry_id, vin=self.vin
                ),
                self._handle_alert,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """State only changes when an alert fires."""

    @callback
    def _handle_alert(self, event_type: str, data: dict[str, Any]) -> None:
        self._trigger_event(event_type, data)
        self.async_write_ha_state()
