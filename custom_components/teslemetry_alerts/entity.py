"""Base entity for Teslemetry Alerts."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import SIGNAL_UPDATE
from .coordinator import AlertManager, VehicleAlerts


class TeslemetryAlertsEntity(Entity):
    """An entity for one vehicle, updated from the alert stream."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AlertManager, vin: str, key: str) -> None:
        """Initialise the entity."""
        self.manager = manager
        self.vin = vin
        self._attr_unique_id = f"{vin}-{key}"
        self._attr_translation_key = key
        # Join the Teslemetry integration's vehicle device the way helpers
        # do (device_entry, not device_info): device_info would make Home
        # Assistant create a device of our own instead.
        if device := manager.teslemetry_device(vin):
            self.device_entry = device
        else:
            self._attr_device_info = manager.device_info(vin)
        self._update_attrs()

    @property
    def vehicle(self) -> VehicleAlerts:
        """Return this vehicle's alert state."""
        return self.manager.vehicles[self.vin]

    async def async_added_to_hass(self) -> None:
        """Subscribe to state updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(
                    entry_id=self.manager.entry.entry_id, vin=self.vin
                ),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self._update_attrs()
        self.async_write_ha_state()

    def _update_attrs(self) -> None:
        """Refresh the entity's attributes from the vehicle state."""
