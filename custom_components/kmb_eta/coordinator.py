"""Data update coordinator."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import async_get_stop_eta, route_key
from .const import (
    CONF_POLES,
    CONF_ROUTES,
    CONF_STOP_ID,
    CONF_STOP_IDS,
    CONF_STOP_NAME,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class KmbCoordinator(DataUpdateCoordinator[dict[str, list[dict]]]):
    """Poll one or more poles of the same stop and group ETA rows by route."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_STOP_NAME, entry.data.get(CONF_STOP_ID))}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.entry = entry

    @property
    def stop_ids(self) -> list[str]:
        ids = self.entry.data.get(CONF_STOP_IDS)
        if ids:
            return list(ids)
        return [self.entry.data[CONF_STOP_ID]]

    @property
    def stop_id(self) -> str:
        return self.stop_ids[0]

    @property
    def poles(self) -> list[str]:
        return list(self.entry.data.get(CONF_POLES) or [])

    @property
    def stop_name(self) -> str:
        return self.entry.data.get(CONF_STOP_NAME) or self.stop_id

    @property
    def selected_keys(self) -> list[str]:
        return list(self.entry.options.get(CONF_ROUTES) or self.entry.data.get(CONF_ROUTES) or [])

    async def _async_update_data(self) -> dict[str, list[dict]]:
        session = async_get_clientsession(self.hass)
        ids = self.stop_ids
        poles = self.poles
        multi = len(ids) > 1

        async def _one(stop_id: str) -> list[dict]:
            return await async_get_stop_eta(session, stop_id)

        results = await asyncio.gather(*(_one(stop_id) for stop_id in ids), return_exceptions=True)
        if all(isinstance(item, Exception) for item in results):
            raise UpdateFailed(f"無法取得九巴到站資料: {results[0]}")

        grouped: dict[str, list[dict]] = {}
        for index, item in enumerate(results):
            if isinstance(item, Exception):
                _LOGGER.warning("KMB ETA failed for %s: %s", ids[index], item)
                continue
            pole = poles[index] if index < len(poles) else ""
            for row in item:
                tagged = dict(row)
                if multi and pole:
                    tagged["_pole"] = pole
                key = route_key(tagged)
                grouped.setdefault(key, []).append(tagged)
        for items in grouped.values():
            items.sort(key=lambda r: (r.get("eta_seq") or 99, r.get("eta") or ""))
        return grouped
