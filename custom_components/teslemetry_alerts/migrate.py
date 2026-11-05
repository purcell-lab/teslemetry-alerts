"""Move entities from stray devices onto the Teslemetry vehicle devices.

Version 0.1.0 gave its entities a device_info with the Teslemetry identifier,
which made Home Assistant create a second device per vehicle ("Teslemetry
Alerts") instead of joining the Teslemetry one, so the entity IDs came out as
sensor.teslemetry_alerts_*. This moves those entities onto the vehicle's
Teslemetry device, renames IDs that still have that generated prefix after
the vehicle's name (sensor.my_t_latest_alert), and removes the stray device.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import LOGGER, TESLEMETRY_DOMAIN
from .coordinator import AlertManager

OLD_PREFIX = "teslemetry_alerts"


@callback
def async_migrate_devices(
    hass: HomeAssistant, entry: ConfigEntry, manager: AlertManager
) -> None:
    """Re-home entities left on stray devices by version 0.1.0."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for vin in manager.vehicles:
        if (target := manager.teslemetry_device(vin)) is None:
            continue
        vehicle = target.name_by_user or target.name or vin
        stray = [
            device
            for device in dev_reg.devices.values()
            if device.id != target.id
            and (TESLEMETRY_DOMAIN, vin) in device.identifiers
            and device.config_entries == {entry.entry_id}
        ]
        for device in stray:
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            ):
                if ent.config_entry_id != entry.entry_id:
                    continue
                changes: dict = {"device_id": target.id}
                object_id = ent.entity_id.split(".", 1)[1]
                if object_id.startswith(OLD_PREFIX) and ent.original_name:
                    changes["new_entity_id"] = ent_reg.async_generate_entity_id(
                        ent.domain, slugify(f"{vehicle} {ent.original_name}")
                    )
                LOGGER.info(
                    "Moving %s to the %s device%s",
                    ent.entity_id,
                    vehicle,
                    f" as {changes['new_entity_id']}"
                    if "new_entity_id" in changes
                    else "",
                )
                ent_reg.async_update_entity(ent.entity_id, **changes)
            dev_reg.async_remove_device(device.id)
