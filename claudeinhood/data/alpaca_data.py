"""Live/historical bar data from Alpaca.

`alpaca-py` is imported lazily so the pure modules don't depend on it.

Feed selection matters for VWAP accuracy:
  * "iex"  — free, partial volume coverage (VWAP slightly off).
  * "sip"  — full consolidated tape (paid Algo Trader Plus). Use this for live
             trading once subscribed.
Set via ALPACA_DATA_FEED.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd


class AlpacaData:
    def __init__(self, api_key: str, secret_key: str, feed: str = "iex"):
        from alpaca.data.historical import StockHistoricalDataClient

        self._client = StockHistoricalDataClient(api_key, secret_key)
        self.feed = feed

    def recent_bars(self, symbol: str, bar_minutes: int = 5, lookback_minutes: int = 420) -> pd.DataFrame:
        """Recent bars at an arbitrary minute timeframe (e.g. 5-min for ORB)."""
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(bar_minutes, TimeFrameUnit.Minute),
            start=start, end=end, feed=DataFeed(self.feed),
        )
        bars = self._client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            return df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        return df[["open", "high", "low", "close", "volume"]].copy()

    def recent_minute_bars(self, symbol: str, lookback_minutes: int = 240) -> pd.DataFrame:
        """Return recent 1-minute bars for the current session as a DataFrame
        indexed by timestamp with columns: open, high, low, close, volume.
        """
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=DataFeed(self.feed),
        )
        bars = self._client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            return df
        # Multi-index (symbol, timestamp) -> single symbol slice.
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        return df[["open", "high", "low", "close", "volume"]].copy()

    @staticmethod
    def current_session_only(df: pd.DataFrame, tz: str = "America/New_York") -> pd.DataFrame:
        """Filter to bars from the latest calendar trading day in ``df`` so VWAP
        is computed per-session (VWAP resets each day)."""
        if df.empty:
            return df
        local = df.tz_convert(tz) if df.index.tz else df.tz_localize("UTC").tz_convert(tz)
        last_day = local.index[-1].date()
        mask = [ts.date() == last_day for ts in local.index]
        return df[mask]
