"""Config flow for Teslemetry Alerts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import AuthError, CannotConnect, async_get_account
from .const import DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class TeslemetryAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for a Teslemetry access token."""

    VERSION = 1

    async def _validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> tuple[str, dict[str, str]] | None:
        try:
            return await async_get_account(
                async_get_clientsession(self.hass), user_input[CONF_ACCESS_TOKEN]
            )
        except AuthError:
            errors["base"] = "invalid_auth"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the token form."""
        errors: dict[str, str] = {}
        if user_input is not None and (
            account := await self._validate(user_input, errors)
        ):
            uid, vehicles = account
            if not vehicles:
                return self.async_abort(reason="no_vehicles")
            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Teslemetry Alerts", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the token was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token for the same account."""
        errors: dict[str, str] = {}
        if user_input is not None and (
            account := await self._validate(user_input, errors)
        ):
            await self.async_set_unique_id(account[0])
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=user_input
            )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=SCHEMA, errors=errors
        )
