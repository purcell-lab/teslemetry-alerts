"""Config flow tests."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.teslemetry_alerts.api import AuthError
from custom_components.teslemetry_alerts.const import API_URL, DOMAIN

from .conftest import TOKEN, UID

SETUP = "custom_components.teslemetry_alerts.async_setup_entry"


async def test_user_flow(hass: HomeAssistant, mock_account) -> None:
    """A valid token creates an entry for the account."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCESS_TOKEN: TOKEN}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == UID
    assert result["data"] == {CONF_ACCESS_TOKEN: TOKEN}


async def test_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    """A rejected token shows an error."""
    aioclient_mock.get(f"{API_URL}/api/metadata", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_already_configured(
    hass: HomeAssistant, mock_account, config_entry
) -> None:
    """The same account cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, mock_account, config_entry) -> None:
    """Reauth stores the new token."""
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.teslemetry_alerts.async_get_account",
        side_effect=AuthError,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1 and flows[0]["step_id"] == "reauth_confirm"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            flows[0]["flow_id"], {CONF_ACCESS_TOKEN: "new"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_ACCESS_TOKEN] == "new"
