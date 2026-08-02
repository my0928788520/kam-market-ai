"""Local debug artifacts for offline parser verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import MatchedPositionReport, NormalizedFuturesPosition, RawPositionCapture, json_value


class PositionDebugWriter:
    def __init__(self, directory: str | Path = "debug/position") -> None:
        self.directory = Path(directory)

    def write(
        self,
        capture: RawPositionCapture,
        normalized: tuple[NormalizedFuturesPosition, ...],
        matched: MatchedPositionReport,
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._json("raw_position.json", {"capture": json_value(capture)})
        self._json("normalized_position.json", {"positions": json_value(normalized)})
        self._json("matched_position.json", {"matched": json_value(matched)})
        lines: list[str] = []
        for row in normalized:
            for warning in row.warnings:
                lines.append(f"row={row.source_index} warning={warning}")
        for warning in matched.warnings:
            lines.append(f"match warning={warning}")
        (self.directory / "parser.log").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _json(self, filename: str, payload: dict[str, Any]) -> None:
        (self.directory / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_value) + "\n",
            encoding="utf-8",
        )
