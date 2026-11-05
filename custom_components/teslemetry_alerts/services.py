"""The get_alerts action."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, MAX_ALERTS, TESLEMETRY_DOMAIN
from .coordinator import AlertManager, alert_attributes

SERVICE_GET_ALERTS = "get_alerts"
ATTR_DEVICE_ID = "device_id"
ATTR_ACTIVE_ONLY = "active_only"
ATTR_AUDIENCE = "audience"
ATTR_LIMIT = "limit"

AUDIENCES = ["Customer", "Service", "ServiceFix"]

GET_ALERTS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ACTIVE_ONLY, default=False): cv.boolean,
        vol.Optional(ATTR_AUDIENCE): vol.In(AUDIENCES),
        vol.Optional(ATTR_LIMIT, default=MAX_ALERTS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_ALERTS)
        ),
    }
)


def _vins_for_devices(hass: HomeAssistant, device_ids: list[str]) -> set[str]:
    dev_reg = dr.async_get(hass)
    vins: set[str] = set()
    for device_id in device_ids:
        if (device := dev_reg.async_get(device_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_device",
                translation_placeholders={"device_id": device_id},
            )
        vins.update(
            value
            for domain, value in device.identifiers
            if domain in (TESLEMETRY_DOMAIN, DOMAIN)
        )
    return vins


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def get_alerts(call: ServiceCall) -> ServiceResponse:
        managers: list[AlertManager] = [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not managers:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_loaded"
            )
        wanted = (
            _vins_for_devices(hass, call.data[ATTR_DEVICE_ID])
            if ATTR_DEVICE_ID in call.data
            else None
        )
        audience = call.data.get(ATTR_AUDIENCE)
        vehicles: list[dict[str, Any]] = []
        for manager in managers:
            for vin, vehicle in manager.vehicles.items():
                if wanted is not None and vin not in wanted:
                    continue
                alerts = sorted(
                    vehicle.alerts.values(),
                    key=lambda a: a.get("startedAt") or "",
                    reverse=True,
                )
                if call.data[ATTR_ACTIVE_ONLY]:
                    alerts = [a for a in alerts if not a.get("endedAt")]
                if audience:
                    alerts = [
                        a for a in alerts if audience in (a.get("audiences") or [])
                    ]
                error = vehicle.latest_error
                vehicles.append(
                    {
                        "vin": vin,
                        "name": manager.vehicle_name(vin),
                        "alerts": [
                            alert_attributes(a) for a in alerts[: call.data[ATTR_LIMIT]]
                        ],
                        "latest_error": {
                            "name": error.get("name"),
                            "created_at": error.get("createdAt"),
                            "tags": error.get("tags") or {},
                            "body": error.get("body"),
                        }
                        if error
                        else None,
                    }
                )
        return {"vehicles": vehicles}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ALERTS,
        get_alerts,
        schema=GET_ALERTS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
