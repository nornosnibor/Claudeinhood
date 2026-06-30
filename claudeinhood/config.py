"""Configuration loading from environment + optional YAML override."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .risk.manager import RiskConfig
from .strategy.vwap_reversion import VwapReversionParams


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AppConfig:
    # Broker / data
    alpaca_api_key: str = field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    alpaca_secret_key: str = field(default_factory=lambda: os.getenv("ALPACA_SECRET_KEY", ""))
    alpaca_paper: bool = field(default_factory=lambda: _env_bool("ALPACA_PAPER", True))
    alpaca_data_feed: str = field(default_factory=lambda: os.getenv("ALPACA_DATA_FEED", "iex"))

    # Trading universe
    primary_symbol: str = field(default_factory=lambda: os.getenv("PRIMARY_SYMBOL", "SPY"))
    trade_options: bool = field(default_factory=lambda: _env_bool("TRADE_OPTIONS", True))
    max_dte: int = field(default_factory=lambda: int(os.getenv("MAX_DTE", "1")))

    # Loop cadence
    poll_seconds: int = field(default_factory=lambda: int(os.getenv("POLL_SECONDS", "30")))

    # Flow confirmation (ProBors REST). Empty -> NullFlowFilter (never vetoes).
    probors_api_key: str = field(default_factory=lambda: os.getenv("PROBORS_API_KEY", ""))
    probors_base_url: str = field(default_factory=lambda: os.getenv("PROBORS_BASE_URL", "https://probors-service.bc-smart.com"))
    probors_flow_endpoint: str = field(default_factory=lambda: os.getenv("PROBORS_FLOW_ENDPOINT", ""))

    # Shadow mode: run the full loop and log signals/vetoes but place NO orders.
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", False))

    # ORB paper engine
    bar_minutes: int = field(default_factory=lambda: int(os.getenv("BAR_MINUTES", "5")))
    orb_minutes: int = field(default_factory=lambda: int(os.getenv("ORB_MINUTES", "15")))
    orb_volume_mult: float = field(default_factory=lambda: float(os.getenv("ORB_VOLUME_MULT", "1.2")))
    # Premium-based exits (Ronny's rules): take +target, stop at -stop, never expiry.
    target_premium_pct: float = field(default_factory=lambda: float(os.getenv("TARGET_PREMIUM_PCT", "0.20")))
    stop_premium_pct: float = field(default_factory=lambda: float(os.getenv("STOP_PREMIUM_PCT", "0.22")))
    max_trades_per_session: int = field(default_factory=lambda: int(os.getenv("MAX_TRADES_PER_SESSION", "1")))

    # Strategy + risk
    strategy: VwapReversionParams = field(default_factory=VwapReversionParams)
    risk: RiskConfig = field(default_factory=lambda: RiskConfig(
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.25")),
        max_risk_per_trade_pct=float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.10")),
        max_position_pct=float(os.getenv("MAX_POSITION_PCT", "0.50")),
        max_trades_per_day=int(os.getenv("MAX_TRADES_PER_DAY", "0")),
    ))

    def validate_for_live(self) -> list[str]:
        problems = []
        if not self.alpaca_api_key or not self.alpaca_secret_key:
            problems.append("ALPACA_API_KEY / ALPACA_SECRET_KEY are not set")
        return problems


def load_config() -> AppConfig:
    return AppConfig()


def build_flow_filter(cfg: AppConfig):
    """Return a configured ProBors filter if credentials+endpoint are present,
    else a NullFlowFilter (never vetoes)."""
    from .flow.base import NullFlowFilter
    from .flow.probors import ProBorsFlowFilter

    if cfg.probors_api_key and cfg.probors_flow_endpoint:
        return ProBorsFlowFilter(
            api_key=cfg.probors_api_key,
            base_url=cfg.probors_base_url,
            flow_endpoint=cfg.probors_flow_endpoint,
        )
    return NullFlowFilter()
