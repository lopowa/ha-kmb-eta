"""Thin client for the public KMB / LWB ETA API (data.etabus.gov.hk)."""

from __future__ import annotations

import re

import aiohttp

from .const import API_STOP_ETA, API_STOPS

_TIMEOUT = aiohttp.ClientTimeout(total=30)
# KMB appends the pole code, e.g. "穗禾苑巴士總站 (FT920)".
_POLE = re.compile(r"\s*\(([A-Z]{1,4}\d{2,4})\)\s*$")


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


def pole_code(name: str) -> str:
    match = _POLE.search(name or "")
    return match.group(1) if match else ""


def base_name(name: str) -> str:
    """Stop name without the pole code in parentheses."""
    return _POLE.sub("", name or "").strip()


def stop_display_name(stop: dict) -> str:
    return stop.get("name_tc") or stop.get("name_en") or stop.get("stop") or ""


def group_same_name(stops: list[dict]) -> list[dict]:
    """Merge poles that share a name aside from the (FT920)-style code.

    Returns dicts: name, stops, poles.
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for stop in stops:
        raw = stop_display_name(stop)
        key = base_name(raw) or raw or stop.get("stop")
        if key not in groups:
            groups[key] = {"name": key, "stops": [], "poles": []}
            order.append(key)
        groups[key]["stops"].append(stop)
        code = pole_code(raw)
        if code:
            groups[key]["poles"].append(code)
    return [groups[key] for key in order]


def group_label(group: dict) -> str:
    poles = group.get("poles") or []
    if len(poles) > 1:
        return f"{group['name']}（{len(poles)}個站柱：{'、'.join(poles)}）"
    if len(poles) == 1:
        return f"{group['name']}（{poles[0]}）"
    return group["name"]


def route_key(item: dict) -> str:
    """Route identity. Includes the pole when several stops were merged."""
    base = f"{item.get('route')}|{item.get('dir')}|{item.get('service_type')}"
    pole = item.get("_pole")
    if pole:
        return f"{pole}|{base}"
    return base


def route_label(item: dict) -> str:
    direction = "去程" if item.get("dir") == "O" else "回程" if item.get("dir") == "I" else item.get("dir")
    dest = item.get("dest_tc") or item.get("dest_en") or ""
    service = item.get("service_type")
    extra = f" 特別班{service}" if service not in (1, "1", None) else ""
    pole = item.get("_pole")
    pole_bit = f" [{pole}]" if pole else ""
    return f"{item.get('route')} → {dest}（{direction}）{extra}{pole_bit}"


def unique_routes(rows: list[dict]) -> list[dict]:
    """One row per route key, preferring a row that has a destination name."""
    found: dict[str, dict] = {}
    for row in rows:
        key = route_key(row)
        current = found.get(key)
        if current is None or (not current.get("dest_tc") and row.get("dest_tc")):
            found[key] = row
    return list(found.values())
