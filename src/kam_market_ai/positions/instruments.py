"""Explicit, conservative futures product and month canonicalization."""

from __future__ import annotations

import re


MTX_ALIASES = frozenset({"MTX", "TMF", "FITM"})
NON_MTX_PRODUCTS = frozenset({"TX", "TXF", "TE", "TEF"})
_MONTH = re.compile(r"(?<!\d)(20\d{2})[-/]?(0[1-9]|1[0-2])(?!\d)")


def canonical_product(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper().replace(" ", "")
    if not normalized:
        return None
    if normalized in MTX_ALIASES:
        return "MTX"
    if normalized in NON_MTX_PRODUCTS:
        return normalized
    prefix = re.match(r"[A-Z]+", normalized)
    if prefix and prefix.group(0) in MTX_ALIASES:
        return "MTX"
    if prefix and prefix.group(0) in NON_MTX_PRODUCTS:
        return prefix.group(0)
    return None


def canonical_month(value: str | None) -> str | None:
    if value is None:
        return None
    match = _MONTH.search(value.strip())
    if match is None:
        return None
    return f"{match.group(1)}{match.group(2)}"
