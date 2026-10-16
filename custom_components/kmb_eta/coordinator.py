"""Data update coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import async_get_stop_eta, route_key
from .const import CONF_ROUTES, CONF_STOP_ID, CONF_STOP_NAME, DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class KmbCoordinator(DataUpdateCoordinator[dict[str, list[dict]]]):
    """Poll one stop and group ETA rows by route key."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.data.get(CONF_STOP_NAME, entry.data[CONF_STOP_ID])}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.entry = entry

    @property
    def stop_id(self) -> str:
        return self.entry.data[CONF_STOP_ID]

    @property
    def stop_name(self) -> str:
        return self.entry.data.get(CONF_STOP_NAME) or self.stop_id

    @property
    def selected_keys(self) -> list[str]:
        return list(self.entry.options.get(CONF_ROUTES) or self.entry.data.get(CONF_ROUTES) or [])

    async def _async_update_data(self) -> dict[str, list[dict]]:
        session = async_get_clientsession(self.hass)
        try:
            rows = await async_get_stop_eta(session, self.stop_id)
        except Exception as err:
            raise UpdateFailed(f"無法取得九巴到站資料: {err}") from err

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            key = route_key(row)
            grouped.setdefault(key, []).append(row)
        for key, items in grouped.items():
            items.sort(key=lambda r: (r.get("eta_seq") or 99, r.get("eta") or ""))
        return grouped
