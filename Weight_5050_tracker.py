#!/usr/bin/env python3
"""
AMM Position Tracker — 50/50 Weighted AMM (Uniswap / CPMM style)

IL formula for 50/50 pool:
    pool_value  = V_entry × sqrt(price / entry_price)
    hold_value  = usdc_amount + wal_amount × price
    IL          = pool_value / hold_value − 1
                = 2√k / (1 + k) − 1     where k = price / entry_price
"""

import requests
from dataclasses import dataclass
from datetime import datetime


# ── Config ────────────────────────────────────────────────────────────────────
# Set to WAL price (USD) when you entered the position.
# Leave as None to use current price as entry (IL will show 0 until you set this).
ENTRY_WAL_PRICE: float | None = None


# ── Price Feed ────────────────────────────────────────────────────────────────

def get_price_usd(coingecko_id: str) -> float | None:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coingecko_id, "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()[coingecko_id]["usd"]
    except Exception:
        return None


# ── Position Model ────────────────────────────────────────────────────────────

@dataclass
class CPMM50Position:
    name:            str
    protocol:        str
    stable_symbol:   str    # "USDC"
    risky_symbol:    str    # "WAL"
    entry_total_usd: float  # total USD value at entry
    entry_price:     float  # risky token price (USD) at entry

    @property
    def stable_amount(self) -> float:
        return self.entry_total_usd * 0.50

    @property
    def risky_amount(self) -> float:
        return self.entry_total_usd * 0.50 / self.entry_price


# ── AMM Math ──────────────────────────────────────────────────────────────────

def pool_value(pos: CPMM50Position, price: float) -> float:
    """V_entry × sqrt(price / entry_price)"""
    k = price / pos.entry_price
    return pos.entry_total_usd * (k ** 0.5)


def hold_value(pos: CPMM50Position, price: float) -> float:
    """Value of holding initial tokens outside the pool."""
    return pos.stable_amount + pos.risky_amount * price


def current_amounts(pos: CPMM50Position, price: float) -> tuple[float, float]:
    """Actual token amounts inside the pool at current price."""
    # From CPMM invariant x*y=K and equal-value condition:
    # stable_now = sqrt(K) × sqrt(price)   [value side]
    # risky_now  = sqrt(K) / sqrt(price)
    K_xy = pos.stable_amount * pos.risky_amount  # constant product invariant
    import math
    stable_now = math.sqrt(K_xy * price)
    risky_now  = math.sqrt(K_xy / price)
    return stable_now, risky_now


def il_pct(pos: CPMM50Position, price: float) -> float:
    """Impermanent loss as a percentage."""
    pv = pool_value(pos, price)
    hv = hold_value(pos, price)
    return (pv / hv - 1) * 100


# ── Display ───────────────────────────────────────────────────────────────────

def display(pos: CPMM50Position, price: float) -> None:
    pv           = pool_value(pos, price)
    s_now, r_now = current_amounts(pos, price)
    sep          = "─" * 46

    print(f"\n{sep}")
    print(f"  {pos.name}  [50/50 — {pos.protocol}]")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(sep)
    print(f"  {pos.stable_symbol:<6}  {s_now:>14,.2f}   ${s_now:>12,.2f}")
    print(f"  {pos.risky_symbol:<6}  {r_now:>14,.2f}   ${r_now * price:>12,.2f}")
    print(f"  {'─'*42}")
    print(f"  {'Total':<6}  {'':>14}   ${pv:>12,.2f}")
    print(f"{sep}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    wal_price = get_price_usd("walrus-2")
    if wal_price is None:
        print("[error] Could not fetch WAL price from CoinGecko.")
        return

    entry = ENTRY_WAL_PRICE if ENTRY_WAL_PRICE else wal_price

    pos = CPMM50Position(
        name           = "WAL/USDC 50/50",
        protocol       = "SteammFi",
        stable_symbol  = "USDC",
        risky_symbol   = "WAL",
        entry_total_usd= 5_444.24,
        entry_price    = entry,
    )

    display(pos, price=wal_price)


if __name__ == "__main__":
    main()
