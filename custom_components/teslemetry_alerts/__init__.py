"""Teslemetry Alerts: Tesla vehicle alerts streamed from Teslemetry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import AlertStream, AuthError, CannotConnect, async_get_account
from .const import DOMAIN
from .coordinator import AlertManager
from .migrate import async_migrate_devices
from .services import async_setup_services

PLATFORMS = [Platform.EVENT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type TeslemetryAlertsConfigEntry = ConfigEntry[AlertManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: TeslemetryAlertsConfigEntry
) -> bool:
    """Set up Teslemetry Alerts from a config entry."""
    session = async_get_clientsession(hass)
    token = entry.data[CONF_ACCESS_TOKEN]
    try:
        _, vehicles = await async_get_account(session, token)
    except AuthError as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        raise ConfigEntryNotReady from err

    manager = AlertManager(hass, entry, vehicles)
    entry.runtime_data = manager
    async_migrate_devices(hass, entry, manager)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    stream = AlertStream(session, token, manager.handle_event, manager.set_connected)
    entry.async_create_background_task(
        hass,
        stream.run(lambda: entry.async_start_reauth(hass)),
        "teslemetry_alerts stream",
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: TeslemetryAlertsConfigEntry
) -> bool:
    """Unload a config entry; the stream task is cancelled with it."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
