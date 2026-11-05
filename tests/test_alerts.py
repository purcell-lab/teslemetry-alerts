"""Stream and entity tests."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from custom_components.teslemetry_alerts.const import API_URL, EVENT_ALERT

from .conftest import VIN, alert, sse

T1 = "2026-11-05T12:00:00.000Z"
T2 = "2026-11-05T12:30:00.000Z"
T3 = "2026-11-05T13:00:00.000Z"
T4 = "2026-11-05T13:05:00.000Z"

CACHED = sse(
    "alerts",
    {
        "vin": VIN,
        "isCache": True,
        "alerts": [
            alert("OLD_ended", T1, T2, "Old alert"),
            alert("OLD_active", T2, None, "Still active"),
        ],
    },
)
LIVE = (
    ": keep-alive\n\n"
    + sse(
        "errors",
        {
            "vin": VIN,
            "isCache": True,
            "errors": [
                {
                    "name": "unsupported_field",
                    "createdAt": T1,
                    "tags": {"field_name": "ScheduledDepartureTime"},
                    "body": "",
                }
            ],
        },
    )
    + sse(
        "alerts",
        {
            "vin": VIN,
            "alerts": [
                alert(
                    "BMS_a174_SW_Charge_Failure",
                    T3,
                    None,
                    "Unable to charge",
                    ("Customer", "ServiceFix"),
                )
            ],
        },
    )
    + sse(
        "alerts",
        {
            "vin": VIN,
            "alerts": [
                alert(
                    "BMS_a174_SW_Charge_Failure",
                    T3,
                    T4,
                    "Unable to charge",
                    ("Customer", "ServiceFix"),
                ),
                alert("OLD_active", T2, T4, "Still active"),
            ],
        },
    )
    + sse("alerts", {"vin": "SOMEONEELSE", "alerts": [alert("X", T4)]})
)


async def _wait_for(hass: HomeAssistant, entity_id: str, state: str) -> None:
    for _ in range(100):
        await hass.async_block_till_done()
        if (s := hass.states.get(entity_id)) and s.state == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"{entity_id} is {hass.states.get(entity_id)}")


async def test_stream(
    hass: HomeAssistant, mock_account, config_entry, entity_registry: er.EntityRegistry
) -> None:
    """Cached alerts fill the sensors silently; live ones fire events."""
    mock_account.get(f"{API_URL}/sse", text=CACHED + LIVE)
    events = []

    @callback
    def record(event):
        events.append(event)

    hass.bus.async_listen(EVENT_ALERT, record)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await _wait_for(hass, "sensor.betty_latest_alert", "Unable to charge")
    await _wait_for(hass, "sensor.betty_active_alerts", "0")

    latest = hass.states.get("sensor.betty_latest_alert")
    assert latest.attributes["name"] == "BMS_a174_SW_Charge_Failure"
    assert latest.attributes["audiences"] == ["Customer", "ServiceFix"]
    assert latest.attributes["ended_at"] == T4
    assert latest.attributes["active"] is False

    error = hass.states.get("sensor.betty_latest_telemetry_error")
    assert error.state == "unsupported_field"
    assert error.attributes["tags"] == {"field_name": "ScheduledDepartureTime"}

    # Nothing from the cached history; the live alert starts and ends, and
    # the cached active alert ends. A reconnect replaying the same body
    # must not fire them again. Within a batch, events go oldest alert first.
    fired = [(e.data["type"], e.data["name"]) for e in events]
    assert fired[:3] == [
        ("started", "BMS_a174_SW_Charge_Failure"),
        ("ended", "OLD_active"),
        ("ended", "BMS_a174_SW_Charge_Failure"),
    ], fired
    await asyncio.sleep(1.2)  # first reconnect backoff
    await hass.async_block_till_done()
    assert len(events) == 3
    assert events[0].data["vin"] == VIN and events[0].data["vehicle"] == "Betty"

    event_state = hass.states.get("event.betty_alert")
    assert event_state.attributes["event_type"] == "ended"
    assert event_state.attributes["name"] == "BMS_a174_SW_Charge_Failure"

    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_active_alerts(hass: HomeAssistant, mock_account, config_entry) -> None:
    """Active alerts are counted and listed newest first."""
    mock_account.get(
        f"{API_URL}/sse",
        text=sse(
            "alerts",
            {
                "vin": VIN,
                "isCache": True,
                "alerts": [
                    alert("A", T1, None, "First"),
                    alert("B", T2, T3, "Ended"),
                    alert("C", T3, None, None),
                ],
            },
        ),
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await _wait_for(hass, "sensor.betty_active_alerts", "2")
    active = hass.states.get("sensor.betty_active_alerts").attributes["alerts"]
    assert [a["name"] for a in active] == ["C", "A"]
    # No touchscreen message: the alert name is the state.
    await _wait_for(hass, "sensor.betty_latest_alert", "C")
    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_stream_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_account, config_entry
) -> None:
    """A rejected token on the stream starts reauth."""
    mock_account.get(f"{API_URL}/sse", status=401)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    for _ in range(50):
        await hass.async_block_till_done()
        if hass.config_entries.flow.async_progress():
            break
        await asyncio.sleep(0.01)
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"
    assert await hass.config_entries.async_unload(config_entry.entry_id)
