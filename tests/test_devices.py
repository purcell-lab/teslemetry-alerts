"""Device joining, migration and the get_alerts action."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.teslemetry_alerts.const import API_URL, DOMAIN

from .conftest import VIN, alert, sse

T1 = "2026-11-05T12:00:00.000Z"
T2 = "2026-11-05T12:30:00.000Z"
T3 = "2026-11-05T13:00:00.000Z"

HISTORY = sse(
    "alerts",
    {
        "vin": VIN,
        "isCache": True,
        "alerts": [
            alert("A_ended", T1, T2, "Ended alert", ("Customer", "Service")),
            alert("B_active", T2, None, "Active alert", ("Customer",)),
            alert("C_service", T3, None, "Service alert", ("ServiceFix",)),
        ],
    },
) + sse(
    "errors",
    {
        "vin": VIN,
        "errors": [{"name": "unsupported_field", "createdAt": T1, "tags": {}}],
    },
)


@pytest.fixture
def teslemetry_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """The core Teslemetry integration's device, renamed MY T."""
    entry = MockConfigEntry(domain="teslemetry")
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("teslemetry", VIN)},
        name="Betty 219 HL8",
    )
    return dev_reg.async_update_device(device.id, name_by_user="MY T")


async def _setup(hass, mock_account, config_entry, body=HISTORY):
    mock_account.get(f"{API_URL}/sse", text=body)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    for _ in range(100):
        await hass.async_block_till_done()
        if (s := hass.states.get("sensor.my_t_active_alerts")) and s.state == "2":
            break
        if (s := hass.states.get("sensor.betty_active_alerts")) and s.state == "2":
            break
        await asyncio.sleep(0.01)


async def test_joins_teslemetry_device(
    hass: HomeAssistant, mock_account, config_entry, teslemetry_device
) -> None:
    """Entities join the Teslemetry device and take its name."""
    await _setup(hass, mock_account, config_entry)
    ent_reg = er.async_get(hass)
    for entity_id in (
        "sensor.my_t_latest_alert",
        "sensor.my_t_active_alerts",
        "sensor.my_t_latest_telemetry_error",
        "event.my_t_alert",
    ):
        entry = ent_reg.async_get(entity_id)
        assert entry is not None, entity_id
        assert entry.device_id == teslemetry_device.id
    assert hass.states.get("sensor.my_t_active_alerts").state == "2"
    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get_device(identifiers={(DOMAIN, VIN)}) is None
    assert len(dev_reg.devices) == 1
    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_migrates_stray_device(
    hass: HomeAssistant, mock_account, config_entry, teslemetry_device
) -> None:
    """0.1.0's stray device is removed and its entity IDs renamed."""
    config_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    # Newer Home Assistant releases give an integration its own device even
    # when the identifier matches another integration's; recreate that state.
    stray = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "placeholder")},
        name="Teslemetry Alerts",
    )
    stray = attr_evolve_identifiers(dev_reg, stray, {("teslemetry", VIN)})
    old = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{VIN}-latest_alert",
        config_entry=config_entry,
        device_id=stray.id,
        suggested_object_id="teslemetry_alerts_latest_alert",
        original_name="Latest alert",
    )
    assert old.entity_id == "sensor.teslemetry_alerts_latest_alert"

    await _setup(hass, mock_account, config_entry)
    entry = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{VIN}-latest_alert")
    assert entry == "sensor.my_t_latest_alert"
    assert ent_reg.async_get(entry).device_id == teslemetry_device.id
    assert dev_reg.async_get(stray.id) is None
    assert hass.states.get("sensor.my_t_latest_alert").state == "Service alert"
    assert await hass.config_entries.async_unload(config_entry.entry_id)


def attr_evolve_identifiers(dev_reg, device, identifiers):
    """Give a device identifiers that collide with another device's."""
    import attr

    new = attr.evolve(device, identifiers=identifiers)
    dev_reg.devices[device.id] = new
    return new


async def test_get_alerts(
    hass: HomeAssistant, mock_account, config_entry, teslemetry_device
) -> None:
    """get_alerts returns full detail, newest first, with filters."""
    await _setup(hass, mock_account, config_entry)

    result = await hass.services.async_call(
        DOMAIN, "get_alerts", {}, blocking=True, return_response=True
    )
    [vehicle] = result["vehicles"]
    assert vehicle["vin"] == VIN and vehicle["name"] == "MY T"
    names = [a["name"] for a in vehicle["alerts"]]
    assert names == ["C_service", "B_active", "A_ended"]
    assert vehicle["alerts"][2]["ended_at"] == T2
    assert vehicle["alerts"][2]["description"] == "A_ended description"
    assert vehicle["latest_error"]["name"] == "unsupported_field"

    result = await hass.services.async_call(
        DOMAIN,
        "get_alerts",
        {
            "device_id": teslemetry_device.id,
            "active_only": True,
            "audience": "Customer",
        },
        blocking=True,
        return_response=True,
    )
    assert [a["name"] for a in result["vehicles"][0]["alerts"]] == ["B_active"]

    result = await hass.services.async_call(
        DOMAIN, "get_alerts", {"limit": 1}, blocking=True, return_response=True
    )
    assert len(result["vehicles"][0]["alerts"]) == 1

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "get_alerts",
            {"device_id": "missing"},
            blocking=True,
            return_response=True,
        )
    assert await hass.config_entries.async_unload(config_entry.entry_id)
