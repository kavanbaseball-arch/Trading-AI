from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PairSpec:
    id: str
    sector: str
    symbol_a: str
    symbol_b: str
    name_a: str
    name_b: str
    active: bool = True
    notes: str = ""


# Universe requested for Pair Trading Tester.
# Inactive names are kept so the operator can explain why they are not traded.
PAIRS: list[PairSpec] = [
    # Technology
    PairSpec("AAPL-MSFT", "Technology", "AAPL", "MSFT", "Apple", "Microsoft"),
    PairSpec("GOOGL-META", "Technology", "GOOGL", "META", "Google", "Meta"),
    PairSpec(
        "CSCO-JNPR",
        "Technology",
        "CSCO",
        "JNPR",
        "Cisco",
        "Juniper Networks",
        active=False,
        notes="JNPR acquired by HPE; pair is no longer independently tradeable.",
    ),
    PairSpec("INTC-AMD", "Technology", "INTC", "AMD", "Intel", "AMD"),
    PairSpec("NVDA-AMD", "Technology", "NVDA", "AMD", "NVIDIA", "AMD"),
    # Consumer Goods
    PairSpec("KO-PEP", "Consumer Goods", "KO", "PEP", "Coca-Cola", "PepsiCo"),
    PairSpec("PG-CL", "Consumer Goods", "PG", "CL", "Procter & Gamble", "Colgate-Palmolive"),
    PairSpec("F-GM", "Consumer Goods", "F", "GM", "Ford", "General Motors"),
    PairSpec("NKE-ADDYY", "Consumer Goods", "NKE", "ADDYY", "Nike", "Adidas"),
    PairSpec("PM-MO", "Consumer Goods", "PM", "MO", "Philip Morris", "Altria Group"),
    # Energy
    PairSpec("XOM-CVX", "Energy", "XOM", "CVX", "ExxonMobil", "Chevron"),
    PairSpec("SLB-HAL", "Energy", "SLB", "HAL", "Schlumberger", "Halliburton"),
    PairSpec("COP-OXY", "Energy", "COP", "OXY", "ConocoPhillips", "Occidental Petroleum"),
    PairSpec("BP-SHEL", "Energy", "BP", "SHEL", "BP", "Shell"),
    PairSpec(
        "MRO-DVN",
        "Energy",
        "MRO",
        "DVN",
        "Marathon Oil",
        "Devon Energy",
        active=False,
        notes="MRO acquired by ConocoPhillips; pair retired.",
    ),
    # Financials
    PairSpec("JPM-BAC", "Financials", "JPM", "BAC", "JPMorgan Chase", "Bank of America"),
    PairSpec("GS-MS", "Financials", "GS", "MS", "Goldman Sachs", "Morgan Stanley"),
    PairSpec("C-WFC", "Financials", "C", "WFC", "Citigroup", "Wells Fargo"),
    PairSpec(
        "SCHW-AMTD",
        "Financials",
        "SCHW",
        "AMTD",
        "Charles Schwab",
        "TD Ameritrade",
        active=False,
        notes="AMTD acquired by Charles Schwab in 2020; pair retired.",
    ),
    PairSpec("BLK-STT", "Financials", "BLK", "STT", "BlackRock", "State Street"),
    # Healthcare
    PairSpec("PFE-MRK", "Healthcare", "PFE", "MRK", "Pfizer", "Merck"),
    PairSpec("JNJ-PG", "Healthcare", "JNJ", "PG", "Johnson & Johnson", "Procter & Gamble"),
    PairSpec("ABBV-LLY", "Healthcare", "ABBV", "LLY", "AbbVie", "Eli Lilly"),
    PairSpec("UNH-ELV", "Healthcare", "UNH", "ELV", "UnitedHealth", "Elevance Health"),
    PairSpec("AMGN-GILD", "Healthcare", "AMGN", "GILD", "Amgen", "Gilead Sciences"),
    # Retail
    PairSpec("WMT-TGT", "Retail", "WMT", "TGT", "Walmart", "Target"),
    PairSpec("HD-LOW", "Retail", "HD", "LOW", "Home Depot", "Lowe's"),
    PairSpec("M-JWN", "Retail", "M", "JWN", "Macy's", "Nordstrom"),
    PairSpec("COST-BJ", "Retail", "COST", "BJ", "Costco", "BJ's Wholesale Club"),
    PairSpec("BBY-GME", "Retail", "BBY", "GME", "Best Buy", "GameStop"),
    # Telecom
    PairSpec("T-VZ", "Telecom", "T", "VZ", "AT&T", "Verizon"),
    PairSpec(
        "TMUS-S",
        "Telecom",
        "TMUS",
        "S",
        "T-Mobile",
        "Sprint",
        active=False,
        notes="Sprint merged into T-Mobile; pair retired.",
    ),
    PairSpec("CMCSA-CHTR", "Telecom", "CMCSA", "CHTR", "Comcast", "Charter Communications"),
    PairSpec("LUMN-FYBR", "Telecom", "LUMN", "FYBR", "Lumen", "Frontier Communications"),
    PairSpec(
        "DISH-T",
        "Telecom",
        "DISH",
        "T",
        "Dish Network",
        "DirecTV / AT&T",
        active=False,
        notes="DirecTV is not an independent listed pair vs DISH as specified.",
    ),
    # Industrials
    PairSpec("BA-LMT", "Industrials", "BA", "LMT", "Boeing", "Lockheed Martin"),
    PairSpec("CAT-DE", "Industrials", "CAT", "DE", "Caterpillar", "Deere & Co."),
    PairSpec("HON-GE", "Industrials", "HON", "GE", "Honeywell", "GE"),
    PairSpec("RTX-NOC", "Industrials", "RTX", "NOC", "RTX", "Northrop Grumman"),
    PairSpec("UNP-NSC", "Industrials", "UNP", "NSC", "Union Pacific", "Norfolk Southern"),
    # Utilities
    PairSpec("DUK-SO", "Utilities", "DUK", "SO", "Duke Energy", "Southern Co."),
    PairSpec("EXC-D", "Utilities", "EXC", "D", "Exelon", "Dominion Energy"),
    PairSpec("NEE-AEP", "Utilities", "NEE", "AEP", "NextEra Energy", "American Electric Power"),
    PairSpec("PCG-ED", "Utilities", "PCG", "ED", "PG&E", "Consolidated Edison"),
    PairSpec("XEL-FE", "Utilities", "XEL", "FE", "Xcel Energy", "FirstEnergy"),
    # Consumer Discretionary
    PairSpec("MCD-SBUX", "Consumer Discretionary", "MCD", "SBUX", "McDonald's", "Starbucks"),
    PairSpec("YUM-DPZ", "Consumer Discretionary", "YUM", "DPZ", "Yum! Brands", "Domino's Pizza"),
    PairSpec("TSLA-NIO", "Consumer Discretionary", "TSLA", "NIO", "Tesla", "Nio"),
    PairSpec("BKNG-EXPE", "Consumer Discretionary", "BKNG", "EXPE", "Booking Holdings", "Expedia"),
]


def active_pairs() -> list[PairSpec]:
    return [p for p in PAIRS if p.active]


def all_symbols() -> list[str]:
    symbols: set[str] = set()
    for pair in active_pairs():
        symbols.add(pair.symbol_a)
        symbols.add(pair.symbol_b)
    return sorted(symbols)


def get_pair(pair_id: str) -> PairSpec | None:
    for pair in PAIRS:
        if pair.id == pair_id:
            return pair
    return None
