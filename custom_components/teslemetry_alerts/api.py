"""Teslemetry REST calls and the alert stream client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .const import API_URL, LOGGER, SSE_TOPICS


class AuthError(Exception):
    """The access token was rejected."""


class CannotConnect(Exception):
    """Teslemetry could not be reached."""


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _get(session: aiohttp.ClientSession, token: str, path: str) -> Any:
    try:
        async with session.get(
            f"{API_URL}{path}",
            headers=_headers(token),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status in (401, 403):
                raise AuthError
            resp.raise_for_status()
            return await resp.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect from err


async def async_get_account(
    session: aiohttp.ClientSession, token: str
) -> tuple[str, dict[str, str]]:
    """Return the account uid and {vin: vehicle name} for a token."""
    metadata = await _get(session, token, "/api/metadata")
    products = await _get(session, token, "/api/1/products")
    names = {
        p["vin"]: p.get("display_name") or p["vin"]
        for p in products.get("response", [])
        if p.get("vin")
    }
    vins = metadata.get("vins") or list(metadata.get("vehicles") or names)
    return str(metadata["uid"]), {vin: names.get(vin, vin) for vin in vins}


EventCallback = Callable[[str, dict[str, Any]], None]


class AlertStream:
    """Server-sent event client for the Teslemetry alerts and errors topics."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        on_event: EventCallback,
        on_connected: Callable[[bool], None] | None = None,
    ) -> None:
        """Initialise the stream."""
        self._session = session
        self._token = token
        self._on_event = on_event
        self._on_connected = on_connected or (lambda _: None)

    async def run(self, on_auth_error: Callable[[], Awaitable[None] | None]) -> None:
        """Stream until cancelled, reconnecting with backoff.

        A rejected token stops the stream and calls on_auth_error.
        """
        backoff = 1
        while True:
            try:
                await self._listen()
                backoff = 1  # clean end of stream (e.g. server deploy)
            except AuthError:
                LOGGER.error("Teslemetry rejected the access token")
                result = on_auth_error()
                if asyncio.iscoroutine(result):
                    await result
                return
            except (aiohttp.ClientError, TimeoutError) as err:
                LOGGER.debug("Alert stream disconnected: %s", err)
            finally:
                self._on_connected(False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _listen(self) -> None:
        async with self._session.get(
            f"{API_URL}/sse",
            params={"topics": SSE_TOPICS},
            headers={**_headers(self._token), "Accept": "text/event-stream"},
            # The server sends keep-alives every few seconds; 30s of silence
            # means the connection is dead.
            timeout=aiohttp.ClientTimeout(
                total=None, connect=10, sock_connect=10, sock_read=30
            ),
        ) as resp:
            if resp.status in (401, 403):
                raise AuthError
            resp.raise_for_status()
            LOGGER.debug("Alert stream connected")
            self._on_connected(True)
            event = "message"
            data: list[str] = []
            async for raw in resp.content:
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line:
                    if data:
                        self._dispatch(event, "\n".join(data))
                    event, data = "message", []
                elif line.startswith(":"):
                    continue
                else:
                    field, _, value = line.partition(":")
                    value = value.removeprefix(" ")
                    if field == "event":
                        event = value
                    elif field == "data":
                        data.append(value)
            if data:
                self._dispatch(event, "\n".join(data))

    def _dispatch(self, event: str, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except ValueError:
            LOGGER.debug("Ignoring non-JSON %s event: %s", event, raw[:200])
            return
        if isinstance(payload, dict):
            try:
                self._on_event(event, payload)
            except Exception:  # noqa: BLE001 - one bad event must not end the stream
                LOGGER.exception("Error handling %s event", event)
