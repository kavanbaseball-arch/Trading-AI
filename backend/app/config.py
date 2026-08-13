from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    account_name: str = "Pair Trading Tester"
    starting_cash: float = 100_000.0
    broker: str = "sim"

    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    z_entry: float = 2.0
    z_stop: float = 3.5
    z_lookback: int = 60
    coint_pvalue: float = 0.05
    coint_lookback_days: int = 252
    coint_retest_days: int = 21
    max_hold_days: int = 20
    max_notional_per_pair: float = 10_000.0
    max_open_pairs: int = 8
    max_gross_exposure_pct: float = 1.60
    pair_spread_corr_limit: float = 0.70
    engine_interval_seconds: int = 30
    slippage_bps: float = 1.0
    data_dir: Path = BACKEND_DIR / "data"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
