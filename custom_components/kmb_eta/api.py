"""Thin client for the public KMB / LWB ETA API (data.etabus.gov.hk)."""

from __future__ import annotations

import aiohttp

from .const import API_STOP_ETA, API_STOPS

_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def async_fetch_json(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def async_get_stops(session: aiohttp.ClientSession) -> list[dict]:
    payload = await async_fetch_json(session, API_STOPS)
    return list(payload.get("data") or [])


async def async_get_stop_eta(session: aiohttp.ClientSession, stop_id: str) -> list[dict]:
    payload = await async_fetch_json(session, API_STOP_ETA.format(stop_id=stop_id))
    return list(payload.get("data") or [])


def route_key(item: dict) -> str:
    """Stable id for one route+direction+service type at a stop."""
    return f"{item.get('route')}|{item.get('dir')}|{item.get('service_type')}"


def route_label(item: dict) -> str:
    direction = "去程" if item.get("dir") == "O" else "回程" if item.get("dir") == "I" else item.get("dir")
    dest = item.get("dest_tc") or item.get("dest_en") or ""
    service = item.get("service_type")
    extra = f" 特別班{service}" if service not in (1, "1", None) else ""
    return f"{item.get('route')} → {dest}（{direction}）{extra}"


def unique_routes(rows: list[dict]) -> list[dict]:
    """One row per route key, preferring a row that has a destination name."""
    found: dict[str, dict] = {}
    for row in rows:
        key = route_key(row)
        current = found.get(key)
        if current is None or (not current.get("dest_tc") and row.get("dest_tc")):
            found[key] = row
    return list(found.values())
