"""Stable, neutral contracts shared by the descriptive Evidence layer."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from ..analysis.observation import ObservationDirection
from ..models import Instrument
from ..storage.observation_query import ObservationQuery

EVIDENCE_TYPE = "DESCRIPTIVE_OBSERVATION_SUMMARY_V0_1"
EVIDENCE_SCHEMA_VERSION = "DESCRIPTIVE_EVIDENCE_SCHEMA_V0_1"
EVIDENCE_AGGREGATION_METHOD = "QUERY_AGGREGATION"


class CriteriaCanonicalCodec:
    """The one semantic representation of an Observation query criterion."""

    FIELDS = ("market", "instrument", "symbol", "session", "direction", "observation_type", "exchange_event_at_from", "exchange_event_at_to")

    @classmethod
    def canonical_payload(cls, criteria: Any) -> dict[str, object]:
        source: Mapping[str, Any] = criteria if isinstance(criteria, Mapping) else {name: getattr(criteria, name, None) for name in cls.FIELDS}
        payload: dict[str, object] = {}
        for name in cls.FIELDS:
            value = source.get(name)
            if isinstance(value, (Instrument, ObservationDirection)):
                value = value.value
            elif isinstance(value, datetime):
                value = value.isoformat()
            payload[name] = value
        return payload

    @classmethod
    def canonical_json(cls, criteria: Any) -> str:
        return json.dumps(cls.canonical_payload(criteria), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def to_query(cls, criteria: Mapping[str, object]) -> ObservationQuery:
        payload = cls.canonical_payload(criteria)
        try:
            return ObservationQuery(market=payload["market"], instrument=Instrument(payload["instrument"]) if payload["instrument"] else None, symbol=payload["symbol"], session=payload["session"], direction=ObservationDirection(payload["direction"]) if payload["direction"] else None, observation_type=payload["observation_type"], exchange_event_at_from=datetime.fromisoformat(payload["exchange_event_at_from"]) if payload["exchange_event_at_from"] else None, exchange_event_at_to=datetime.fromisoformat(payload["exchange_event_at_to"]) if payload["exchange_event_at_to"] else None, order="ASC")
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid evidence source criteria.") from error
