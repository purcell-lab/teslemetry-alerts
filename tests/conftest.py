"""Fixtures for Teslemetry Alerts tests."""

from __future__ import annotations

import json

import pytest
from homeassistant.const import CONF_ACCESS_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.teslemetry_alerts.const import API_URL, DOMAIN

VIN = "TESTVIN0000000001"
UID = "account-uid"
TOKEN = "token"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


def alert(name, started, ended=None, message=None, audiences=("Customer",)):
    """Build a stream alert record."""
    record = {
        "name": name,
        "audiences": list(audiences),
        "startedAt": started,
        "description": f"{name} description",
        "potentialImpact": "impact",
        "customerFacingMessage1": message,
        "customerFacingMessage2": "detail",
    }
    if ended:
        record["endedAt"] = ended
    return record


def sse(event, payload):
    """Encode one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@pytest.fixture
def mock_account(aioclient_mock: AiohttpClientMocker):
    """Mock the metadata and products endpoints."""
    aioclient_mock.get(
        f"{API_URL}/api/metadata", json={"uid": UID, "vins": [VIN], "region": "NA"}
    )
    aioclient_mock.get(
        f"{API_URL}/api/1/products",
        json={"response": [{"vin": VIN, "display_name": "Betty"}]},
    )
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=UID, data={CONF_ACCESS_TOKEN: TOKEN}
    )
