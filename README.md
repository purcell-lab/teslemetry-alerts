# Teslemetry Alerts

A Home Assistant custom integration that streams Tesla vehicle alerts (the
warnings shown on the car's touchscreen, and service alerts) from
[Teslemetry](https://teslemetry.com).

The Teslemetry integration in Home Assistant connects to the same stream but
ignores its `alerts` and `errors` topics. This integration subscribes to only
those topics, so it adds no telemetry fields and does not use any of your
vehicles' streaming allowance. It runs alongside the Teslemetry integration
and adds its entities to the same vehicle devices.

## Install

1. In HACS, add `https://github.com/purcell-lab/teslemetry-alerts` as a custom
   repository (category: Integration) and install **Teslemetry Alerts**.
   Or copy `custom_components/teslemetry_alerts` into your `config/custom_components`.
2. Restart Home Assistant.
3. Create an access token in the [Teslemetry console](https://teslemetry.com/console).
4. Go to **Settings → Devices & services → Add integration → Teslemetry Alerts**
   and enter the token.

Every vehicle on the account is added. If the token stops working, Home
Assistant asks for a new one.

## Entities (per vehicle)

| Entity | State | Attributes |
|---|---|---|
| `sensor.<car>_latest_alert` | Touchscreen message of the most recently started alert (its name if it has none) | `name`, `message`, `detail`, `audiences`, `started_at`, `ended_at`, `active`, `description`, `potential_impact`, `condition`, `clear_condition` |
| `sensor.<car>_active_alerts` | Number of alerts that have not ended | `alerts`: list of `name`, `message`, `audiences`, `started_at`, newest first |
| `sensor.<car>_latest_telemetry_error` (diagnostic) | Name of the latest Teslemetry/telemetry error, e.g. `unsupported_field` | `created_at`, `tags`, `body` |
| `event.<car>_alert` | Fires `started` or `ended` for each alert | same attributes as the latest alert sensor |

`audiences` says who an alert is for: `Customer`, `Service` or `ServiceFix`.

Entities are named after the vehicle as Home Assistant names it: a car whose
Teslemetry device is renamed `MY T` gets `sensor.my_t_latest_alert`. Vehicles
the Teslemetry integration doesn't have get a device of their own, named as
Teslemetry reports them.

## Action: `teslemetry_alerts.get_alerts`

Returns the alerts held for each vehicle, newest first, with the same detail
as the attributes above. That includes the history Teslemetry sends on
connect (up to 100 alerts per vehicle), so it covers alerts from before the
last restart that never fired an event.

| Field | Meaning |
|---|---|
| `device_id` | Vehicles to return (default: all) |
| `active_only` | Only alerts that have not ended |
| `audience` | Only `Customer`, `Service` or `ServiceFix` alerts |
| `limit` | Maximum alerts per vehicle (1-100) |

```yaml
action: teslemetry_alerts.get_alerts
data:
  active_only: true
response_variable: alerts
```

The response is `{"vehicles": [{"vin", "name", "alerts": [...], "latest_error"}]}`.

## Events

Each alert that starts or ends also fires a `teslemetry_alert` event on the
bus, with `vin`, `vehicle`, `type` (`started`/`ended`) and the attributes above.
Use it to watch every car from one automation.

On connect, Teslemetry sends each car's recent alert history. That history
fills the sensors without firing events, so restarting Home Assistant does not
replay old alerts. After a reconnect, alerts that started while disconnected
do fire.

## Example automation

Notify when charging fails on any car:

```yaml
triggers:
  - trigger: event
    event_type: teslemetry_alert
    event_data:
      type: started
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.name.startswith(('BMS_', 'CP_')) }}"
actions:
  - action: notify.notify
    data:
      title: "{{ trigger.event.data.vehicle }}"
      message: "{{ trigger.event.data.message or trigger.event.data.name }}"
```

## Requirements

- Home Assistant 2025.1 or newer.
- Alerts must be enabled in each vehicle's Teslemetry streaming config
  (`alert_types`). Teslemetry enables `customer`, `service` and `service-fix` by
  default.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```
