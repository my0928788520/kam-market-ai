"""SDK-agnostic raw adapter. It accepts JSON-like dictionaries only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .models import RawPositionCapture, RawPositionRow


class PositionRawAdapter:
    """Extract raw position rows without interpreting any SDK field value.

    Known response wrappers are unwrapped only when their value is a list. A
    mapping that is itself a row remains a row, which avoids silently guessing
    a proprietary SDK schema.
    """

    _WRAPPER_KEYS = ("data", "positions", "inventories", "items", "result")

    def capture(self, payload: Mapping[str, Any] | Sequence[Mapping[str, Any]], *, source: str = "offline-fixture") -> RawPositionCapture:
        rows = self._rows(payload)
        return RawPositionCapture.from_rows(
            tuple(RawPositionRow(source_index=index, payload=dict(row)) for index, row in enumerate(rows)),
            source=source,
        )

    def _rows(self, payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        if isinstance(payload, Mapping):
            for key in self._WRAPPER_KEYS:
                candidate = payload.get(key)
                if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
                    return [row for row in candidate if isinstance(row, Mapping)]
            return [payload]
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            return [row for row in payload if isinstance(row, Mapping)]
        raise TypeError("position payload must be a mapping or a sequence of mappings")
