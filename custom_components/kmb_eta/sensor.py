"""Sensors: one entity per selected route, state is minutes until the next bus."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import route_key
from .const import (
    ATTR_DEST,
    ATTR_DIR,
    ATTR_ETA_1,
    ATTR_ETA_2,
    ATTR_ETA_3,
    ATTR_MINS_2,
    ATTR_MINS_3,
    ATTR_REMARK,
    DOMAIN,
)
from .coordinator import KmbCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: KmbCoordinator = hass.data[DOMAIN][entry.entry_id]
    keys = coordinator.selected_keys
    async_add_entities([KmbRouteSensor(coordinator, entry, key) for key in keys])


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    return dt_util.as_local(parsed)


def _minutes(when: datetime | None) -> int | None:
    if when is None:
        return None
    delta = (when - dt_util.now()).total_seconds() / 60
    if delta < -1:
        return None
    return max(0, int(round(delta)))


class KmbRouteSensor(CoordinatorEntity[KmbCoordinator], SensorEntity):
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bus-clock"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: KmbCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        route, direction, service = (key.split("|") + ["", "", ""])[:3]
        self._route = route
        self._direction = direction
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_has_entity_name = True
        direction_label = "去程" if direction == "O" else "回程" if direction == "I" else direction
        service_label = "" if service in ("1", "") else f" 特別{service}"
        self._attr_name = f"{route} {direction_label}{service_label}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"九巴 {coordinator.stop_name}",
            manufacturer="Kowloon Motor Bus",
            model="ETA",
            configuration_url=f"https://data.etabus.gov.hk/v1/transport/kmb/stop-eta/{coordinator.stop_id}",
        )

    @property
    def _rows(self) -> list[dict]:
        return list(self.coordinator.data.get(self._key) or [])

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> int | None:
        if not self._rows:
            return None
        return _minutes(_parse(self._rows[0].get("eta")))

    @property
    def extra_state_attributes(self) -> dict:
        rows = self._rows
        times = [_parse(r.get("eta")) for r in rows[:3]]
        labels = [t.strftime("%H:%M") if t else None for t in times]
        first = rows[0] if rows else {}
        return {
            ATTR_DEST: first.get("dest_tc") or first.get("dest_en"),
            ATTR_REMARK: first.get("rmk_tc") or first.get("rmk_en"),
            ATTR_DIR: self._direction,
            ATTR_ETA_1: labels[0] if len(labels) > 0 else None,
            ATTR_ETA_2: labels[1] if len(labels) > 1 else None,
            ATTR_ETA_3: labels[2] if len(labels) > 2 else None,
            ATTR_MINS_2: _minutes(times[1]) if len(times) > 1 else None,
            ATTR_MINS_3: _minutes(times[2]) if len(times) > 2 else None,
            "route": self._route,
            "stop_id": self.coordinator.stop_id,
            "stop_name": self.coordinator.stop_name,
            "route_key": route_key(first) if first else self._key,
        }
