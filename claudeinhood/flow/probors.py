"""ProBors flow adapter (REST).

NOTE: the live engine needs ProBors' REST API + an API key — it cannot use the
ProBors MCP server (MCP tools are called interactively by Claude, not by the
standalone engine process).

The HTTP plumbing is here and works; only `_map_response` needs the real
endpoint/field names from your ProBors plan's docs. Until those are filled in,
`read()` returns None (fail-open) so it never blocks or feeds bad data.

`requests` is imported lazily so the package works without it installed.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from .base import FlowReading

log = logging.getLogger("claudeinhood.flow.probors")


class ProBorsFlowFilter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.probors.com",
        *,
        # The endpoint that returns net options/whale flow for a ticker.
        # Set once confirmed from ProBors docs.
        flow_endpoint: Optional[str] = None,
        timeout: float = 3.0,
    ):
        self.api_key = api_key or os.getenv("PROBORS_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.flow_endpoint = flow_endpoint or os.getenv("PROBORS_FLOW_ENDPOINT", "")
        self.timeout = timeout

    def read(self, symbol: str) -> Optional[FlowReading]:
        if not self.api_key or not self.flow_endpoint:
            log.debug("ProBors not configured (api_key/flow_endpoint); skipping")
            return None
        try:
            import requests

            url = f"{self.base_url}/{self.flow_endpoint.lstrip('/')}"
            resp = requests.get(
                url,
                params={"ticker": symbol},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return self._map_response(resp.json(), symbol)
        except Exception:
            log.exception("ProBors flow fetch failed for %s", symbol)
            return None  # fail-open: never block trading on a data error

    def _map_response(self, payload: dict, symbol: str) -> Optional[FlowReading]:
        """Translate ProBors' JSON into a FlowReading.

        TODO: replace the field names below with the real ones from your plan's
        API docs. Aim to produce:
          net_sentiment in [-1, 1]  (e.g. (call_premium - put_premium)/total)
          strength      in [0, 1]   (e.g. normalized notional vs a daily baseline)
        Example skeleton (adjust keys):

            call = float(payload.get("call_premium", 0))
            put = float(payload.get("put_premium", 0))
            total = call + put
            if total <= 0:
                return None
            net = (call - put) / total
            notional = total
            strength = min(1.0, notional / FLOW_BASELINE_NOTIONAL)
            ts = datetime.fromtimestamp(payload["ts"], tz=timezone.utc)
            return FlowReading(net, strength, as_of=ts, source="probors",
                               notional=notional)
        """
        return None
