"""Config flow: search a stop, merge same-name poles, then multi-select routes."""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback as ha_callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import (
    async_get_stop_eta,
    async_get_stops,
    base_name,
    group_label,
    group_same_name,
    pole_code,
    route_key,
    route_label,
    stop_display_name,
    unique_routes,
)
from .const import (
    CONF_POLES,
    CONF_ROUTES,
    CONF_STOP_ID,
    CONF_STOP_IDS,
    CONF_STOP_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_MAX_MATCHES = 40


def _match_stops(stops: list[dict], query: str) -> list[dict]:
    needle = query.strip().lower()
    if not needle:
        return []
    hits = []
    for stop in stops:
        names = " ".join(
            [
                str(stop.get("name_tc") or ""),
                str(stop.get("name_en") or ""),
                str(stop.get("name_sc") or ""),
                base_name(str(stop.get("name_tc") or "")),
            ]
        ).lower()
        if needle in names:
            hits.append(stop)
            if len(hits) >= 200:
                break
    return hits


class KmbConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._groups: list[dict] = []
        self._group: dict | None = None
        self._route_rows: list[dict] = []

    @staticmethod
    @ha_callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KmbOptionsFlow:
        return KmbOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            query = user_input["query"].strip()
            direct_id = user_input.get("stop_id", "").strip()
            try:
                if direct_id:
                    self._group = {
                        "name": direct_id,
                        "stops": [{"stop": direct_id, "name_tc": direct_id}],
                        "poles": [],
                    }
                    return await self.async_step_routes()
                session = async_get_clientsession(self.hass)
                stops = await async_get_stops(session)
                self._groups = group_same_name(_match_stops(stops, query))[:_MAX_MATCHES]
            except Exception:
                _LOGGER.exception("Failed to load KMB stops")
                errors["base"] = "cannot_connect"
            else:
                if not self._groups:
                    errors["base"] = "no_stops"
                elif len(self._groups) == 1:
                    self._group = self._groups[0]
                    return await self.async_step_routes()
                else:
                    return await self.async_step_pick()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("query", default=""): TextSelector(),
                    vol.Optional("stop_id", default=""): TextSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_pick(self, user_input: dict | None = None):
        options = [
            {"value": group["name"], "label": group_label(group)} for group in self._groups
        ]
        if user_input is not None:
            chosen = user_input[CONF_STOP_NAME]
            self._group = next(g for g in self._groups if g["name"] == chosen)
            return await self.async_step_routes()

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_NAME): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def _load_routes(self) -> None:
        assert self._group is not None
        session = async_get_clientsession(self.hass)
        stops = self._group["stops"]
        poles = self._group.get("poles") or []
        multi = len(stops) > 1

        async def _one(stop: dict, index: int) -> list[dict]:
            rows = await async_get_stop_eta(session, stop["stop"])
            pole = poles[index] if index < len(poles) else pole_code(stop_display_name(stop))
            tagged = []
            for row in rows:
                item = dict(row)
                if multi and pole:
                    item["_pole"] = pole
                tagged.append(item)
            return tagged

        batches = await asyncio.gather(
            *(_one(stop, index) for index, stop in enumerate(stops)),
            return_exceptions=True,
        )
        rows: list[dict] = []
        errors = 0
        for batch in batches:
            if isinstance(batch, Exception):
                errors += 1
                _LOGGER.warning("KMB route list failed: %s", batch)
                continue
            rows.extend(batch)
        if errors and not rows:
            raise RuntimeError("all poles failed")
        self._route_rows = unique_routes(rows)

    async def async_step_routes(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        assert self._group is not None

        if not self._route_rows:
            try:
                await self._load_routes()
            except Exception:
                _LOGGER.exception("Failed to load ETAs")
                errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            selected = user_input[CONF_ROUTES]
            if not selected:
                errors["base"] = "no_routes_selected"
            else:
                stops = self._group["stops"]
                ids = [stop["stop"] for stop in stops]
                name = self._group["name"]
                await self.async_set_unique_id("kmb_" + "_".join(sorted(ids)))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"九巴 {name}",
                    data={
                        CONF_STOP_ID: ids[0],
                        CONF_STOP_IDS: ids,
                        CONF_STOP_NAME: name,
                        CONF_POLES: list(self._group.get("poles") or []),
                        CONF_ROUTES: selected,
                    },
                )

        if errors.get("base") == "cannot_connect" and not self._route_rows:
            return self.async_show_form(step_id="routes", data_schema=vol.Schema({}), errors=errors)

        if not self._route_rows and not errors:
            errors["base"] = "no_routes"

        schema = vol.Schema(
            {
                vol.Required(CONF_ROUTES): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": route_key(row), "label": route_label(row)}
                            for row in sorted(
                                self._route_rows,
                                key=lambda r: (str(r.get("route")), str(r.get("_pole") or "")),
                            )
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="routes",
            data_schema=schema,
            errors=errors,
            description_placeholders={"stop": group_label(self._group)},
        )


class KmbOptionsFlow(OptionsFlow):
    """Change which routes are tracked across every pole of this stop."""

    async def async_step_init(self, user_input: dict | None = None):
        entry = self.config_entry
        errors: dict[str, str] = {}
        current = list(entry.options.get(CONF_ROUTES) or entry.data.get(CONF_ROUTES) or [])
        ids = list(entry.data.get(CONF_STOP_IDS) or [entry.data[CONF_STOP_ID]])
        poles = list(entry.data.get(CONF_POLES) or [])
        multi = len(ids) > 1

        try:
            session = async_get_clientsession(self.hass)

            async def _one(index: int, stop_id: str) -> list[dict]:
                rows = await async_get_stop_eta(session, stop_id)
                pole = poles[index] if index < len(poles) else ""
                tagged = []
                for row in rows:
                    item = dict(row)
                    if multi and pole:
                        item["_pole"] = pole
                    tagged.append(item)
                return tagged

            batches = await asyncio.gather(
                *(_one(index, stop_id) for index, stop_id in enumerate(ids)),
                return_exceptions=True,
            )
            rows: list[dict] = []
            for batch in batches:
                if isinstance(batch, Exception):
                    continue
                rows.extend(batch)
            if not rows and ids:
                return self.async_abort(reason="cannot_connect")
            rows = unique_routes(rows)
        except Exception:
            _LOGGER.exception("Failed to refresh route list")
            return self.async_abort(reason="cannot_connect")

        known = {route_key(row) for row in rows}
        options = [
            {"value": route_key(row), "label": route_label(row)}
            for row in sorted(rows, key=lambda r: (str(r.get("route")), str(r.get("_pole") or "")))
        ]
        for key in current:
            if key not in known:
                options.append({"value": key, "label": f"{key}（暫時冇班次資料）"})

        if user_input is not None:
            selected = user_input[CONF_ROUTES]
            if not selected:
                errors["base"] = "no_routes_selected"
            else:
                return self.async_create_entry(title="", data={CONF_ROUTES: selected})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ROUTES, default=current): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )
