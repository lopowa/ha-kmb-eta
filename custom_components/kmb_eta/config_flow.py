"""Config flow: search a stop, then multi-select routes."""

from __future__ import annotations

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

from .api import async_get_stop_eta, async_get_stops, route_key, route_label, unique_routes
from .const import CONF_ROUTES, CONF_STOP_ID, CONF_STOP_NAME, DOMAIN

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
            ]
        ).lower()
        if needle in names:
            hits.append(stop)
            if len(hits) >= _MAX_MATCHES:
                break
    return hits


def _stop_option_label(stop: dict) -> str:
    return f"{stop.get('name_tc') or stop.get('name_en')} ({stop.get('stop')})"


class KmbConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._matches: list[dict] = []
        self._stop: dict | None = None
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
                    self._stop = {"stop": direct_id, "name_tc": direct_id}
                    return await self.async_step_routes()
                session = async_get_clientsession(self.hass)
                stops = await async_get_stops(session)
                self._matches = _match_stops(stops, query)
            except Exception:
                _LOGGER.exception("Failed to load KMB stops")
                errors["base"] = "cannot_connect"
            else:
                if not self._matches:
                    errors["base"] = "no_stops"
                elif len(self._matches) == 1:
                    self._stop = self._matches[0]
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
            description_placeholders={
                "hint": "輸入站名一部分，例如「美孚」或「長宏」。如果搜尋結果太多，可以加多幾個字。已知站 ID 可以直接填下面。"
            },
        )

    async def async_step_pick(self, user_input: dict | None = None):
        options = {stop["stop"]: _stop_option_label(stop) for stop in self._matches}
        if user_input is not None:
            chosen = user_input[CONF_STOP_ID]
            self._stop = next(s for s in self._matches if s["stop"] == chosen)
            return await self.async_step_routes()

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[{"value": k, "label": v} for k, v in options.items()],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_routes(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        assert self._stop is not None
        stop_id = self._stop["stop"]

        if not self._route_rows:
            try:
                session = async_get_clientsession(self.hass)
                rows = await async_get_stop_eta(session, stop_id)
                self._route_rows = unique_routes(rows)
            except Exception:
                _LOGGER.exception("Failed to load ETAs for %s", stop_id)
                errors["base"] = "cannot_connect"

        if user_input is not None and not errors:
            selected = user_input[CONF_ROUTES]
            if not selected:
                errors["base"] = "no_routes_selected"
            else:
                name = self._stop.get("name_tc") or self._stop.get("name_en") or stop_id
                await self.async_set_unique_id(f"kmb_{stop_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"九巴 {name}",
                    data={
                        CONF_STOP_ID: stop_id,
                        CONF_STOP_NAME: name,
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
                            for row in sorted(self._route_rows, key=lambda r: str(r.get("route")))
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
            description_placeholders={"stop": _stop_option_label(self._stop)},
        )


class KmbOptionsFlow(OptionsFlow):
    """Change which routes are tracked. Adding or removing reloads the entry."""

    async def async_step_init(self, user_input: dict | None = None):
        entry = self.config_entry
        errors: dict[str, str] = {}
        current = list(entry.options.get(CONF_ROUTES) or entry.data.get(CONF_ROUTES) or [])

        try:
            session = async_get_clientsession(self.hass)
            rows = unique_routes(await async_get_stop_eta(session, entry.data[CONF_STOP_ID]))
        except Exception:
            _LOGGER.exception("Failed to refresh route list")
            return self.async_abort(reason="cannot_connect")

        known = {route_key(row) for row in rows}
        options = [
            {"value": route_key(row), "label": route_label(row)}
            for row in sorted(rows, key=lambda r: str(r.get("route")))
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
