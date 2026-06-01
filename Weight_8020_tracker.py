#!/usr/bin/env python3
"""
AMM Position Tracker — Weighted AMM (Balancer-style)

Tracks impermanent loss and current value for weighted AMM positions.
Supports any weight ratio (e.g. 80/20, 50/50, 60/40).

IL formula for weighted pool:
    pool_value  = V_entry × (p_current / p_entry) ^ w_risky
    hold_value  = stable_amount + risky_amount × p_current
    IL          = pool_value / hold_value − 1
"""

import requests
from dataclasses import dataclass
from datetime import datetime


# ── Config ────────────────────────────────────────────────────────────────────
# Set to your actual SUI price when you entered the position.
# Leave as None to use current price as entry (IL will show 0 until you set this).
ENTRY_SUI_PRICE: float | None = None


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
class WeightedAMMPosition:
    name:            str
    protocol:        str
    stable_symbol:   str    # "USDC"
    risky_symbol:    str    # "SUI"
    weight_stable:   float  # 0.80
    weight_risky:    float  # 0.20
    entry_total_usd: float  # total USD value at entry
    entry_price:     float  # risky token price (USD) at entry

    @property
    def stable_amount(self) -> float:
        """Stablecoin amount at entry (1:1 with USD)."""
        return self.entry_total_usd * self.weight_stable

    @property
    def risky_amount(self) -> float:
        """Risky token amount at entry."""
        return self.entry_total_usd * self.weight_risky / self.entry_price

    @property
    def _invariant(self) -> float:
        return (self.stable_amount ** self.weight_stable) * (self.risky_amount ** self.weight_risky)


# ── AMM Math ──────────────────────────────────────────────────────────────────

def pool_value(pos: WeightedAMMPosition, price: float) -> float:
    """Closed-form pool value: V_entry × (price/entry_price) ^ w_risky."""
    ratio = price / pos.entry_price
    return pos.entry_total_usd * (ratio ** pos.weight_risky)


def hold_value(pos: WeightedAMMPosition, price: float) -> float:
    """Value of holding the initial token amounts outside the pool."""
    return pos.stable_amount + pos.risky_amount * price


def current_amounts(pos: WeightedAMMPosition, price: float) -> tuple[float, float]:
    """Actual token amounts inside the pool at current price."""
    w1, w2 = pos.weight_stable, pos.weight_risky
    wr = w1 / w2  # weight ratio, e.g. 4.0 for 80/20
    K = pos._invariant
    # Derived from: invariant + weight condition (value ratio = w1/w2)
    risky_now  = K / ((wr * price) ** w1)
    stable_now = wr * price * risky_now
    return stable_now, risky_now


def il_pct(pos: WeightedAMMPosition, price: float) -> float:
    """Impermanent loss as a percentage (negative = loss vs hold)."""
    pv = pool_value(pos, price)
    hv = hold_value(pos, price)
    return (pv / hv - 1) * 100


# ── Display ───────────────────────────────────────────────────────────────────

def display(pos: WeightedAMMPosition, price: float) -> None:
    pv           = pool_value(pos, price)
    s_now, r_now = current_amounts(pos, price)
    w_label      = f"{int(pos.weight_stable * 100)}/{int(pos.weight_risky * 100)}"
    sep          = "─" * 46

    print(f"\n{sep}")
    print(f"  {pos.name}  [{w_label} — {pos.protocol}]")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(sep)
    print(f"  {pos.stable_symbol:<6}  {s_now:>14,.2f}   ${s_now:>12,.2f}")
    print(f"  {pos.risky_symbol:<6}  {r_now:>14,.4f}   ${r_now * price:>12,.2f}")
    print(f"  {'─'*42}")
    print(f"  {'Total':<6}  {'':>14}   ${pv:>12,.2f}")
    print(f"{sep}\n")


# ── Positions ─────────────────────────────────────────────────────────────────

def main() -> None:
    sui_price = get_price_usd("sui")
    if sui_price is None:
        print("[error] Could not fetch SUI price from CoinGecko.")
        return

    entry = ENTRY_SUI_PRICE if ENTRY_SUI_PRICE else sui_price

    positions = [
        WeightedAMMPosition(
            name           = "USDC/SUI 80/20",
            protocol       = "Aftermath",
            stable_symbol  = "USDC",
            risky_symbol   = "SUI",
            weight_stable  = 0.80,
            weight_risky   = 0.20,
            entry_total_usd= 16_412.83,
            entry_price    = entry,
        ),
    ]

    for pos in positions:
        display(pos, price=sui_price)


if __name__ == "__main__":
    main()
