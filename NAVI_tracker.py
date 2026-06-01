#!/usr/bin/env python3
"""
NAVI Lending Position Tracker

Tracks collateral value, debt, LTV, and liquidation price for a NAVI borrow position.
Uses DexScreener for live vSUI/SUI ratio and CoinGecko for SUI price.
"""

import sys
import requests
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, "/Users/zenonian/Desktop/Claude/Projects/Portfolio tracker project")
from Dexscreener_API import price_in_sui, PAIRS


# ── Price Feed ────────────────────────────────────────────────────────────────

def get_sui_price() -> float | None:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "sui", "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["sui"]["usd"]
    except Exception:
        return None


def get_vsui_usd(sui_price: float) -> float | None:
    ratio = price_in_sui(PAIRS["vSUI/SUI"])
    if ratio is None:
        return None
    return ratio * sui_price


# ── Position Model ────────────────────────────────────────────────────────────

@dataclass
class NAVIPosition:
    name:                  str
    collateral_symbol:     str    # "vSUI"
    collateral_amount:     float  # 4886.27
    debt_symbol:           str    # "USDC"
    debt_amount:           float  # 1500.0
    max_ltv:               float  # 0.75
    liquidation_threshold: float  # 0.80


# ── Metrics ───────────────────────────────────────────────────────────────────

def collateral_value(pos: NAVIPosition, vsui_usd: float) -> float:
    return pos.collateral_amount * vsui_usd


def current_ltv(pos: NAVIPosition, vsui_usd: float) -> float:
    return pos.debt_amount / collateral_value(pos, vsui_usd)


def liquidation_price_vsui(pos: NAVIPosition) -> float:
    """vSUI USD price at which LTV hits liquidation threshold."""
    return pos.debt_amount / (pos.collateral_amount * pos.liquidation_threshold)


def liquidation_price_sui(pos: NAVIPosition, vsui_ratio: float) -> float:
    """SUI USD price at which liquidation triggers."""
    return liquidation_price_vsui(pos) / vsui_ratio


def safe_borrow_remaining(pos: NAVIPosition, vsui_usd: float) -> float:
    """How much more USDC can be borrowed before hitting max LTV."""
    max_debt = collateral_value(pos, vsui_usd) * pos.max_ltv
    return max(0.0, max_debt - pos.debt_amount)


# ── Display ───────────────────────────────────────────────────────────────────

def display(pos: NAVIPosition, sui_price: float, vsui_usd: float, vsui_ratio: float) -> None:
    col_val   = collateral_value(pos, vsui_usd)
    debt_val  = pos.debt_amount
    net_val   = col_val - debt_val
    ltv       = current_ltv(pos, vsui_usd)
    liq_vsui  = liquidation_price_vsui(pos)
    liq_sui   = liquidation_price_sui(pos, vsui_ratio)
    room      = safe_borrow_remaining(pos, vsui_usd)
    drop_to_liq = (liq_sui / sui_price - 1) * 100
    sep       = "─" * 52

    ltv_status = (
        "✓ safe" if ltv < pos.max_ltv * 0.80
        else ("⚠ caution" if ltv < pos.max_ltv
        else "✗ over limit")
    )

    sui_equivalent = pos.collateral_amount * vsui_ratio

    print(f"\n{sep}")
    print(f"  {pos.name}  [Lending — NAVI]")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(sep)
    print(f"  {pos.collateral_symbol:<6}  {pos.collateral_amount:>14,.2f}   ${col_val:>12,.2f}  (collateral)")
    print(f"  {'SUI':<6}  {sui_equivalent:>14,.4f}   {'':>14}  (vSUI/SUI {vsui_ratio:.4f})")
    print(f"  {pos.debt_symbol:<6}  {pos.debt_amount:>14,.2f}   ${debt_val:>12,.2f}  (debt)")
    print(f"  {'─'*48}")
    print(f"  {'Net':<6}  {'':>14}   ${net_val:>12,.2f}")
    print()
    print(f"  LTV now        {ltv*100:>6.2f}%   {ltv_status}")
    print(f"  Max LTV        {pos.max_ltv*100:>6.2f}%")
    print(f"  Liq threshold  {pos.liquidation_threshold*100:>6.2f}%")
    print(f"  Borrow room    ${room:>11,.2f}  USDC remaining")
    print()
    print(f"  Liq price      ${liq_sui:.4f} SUI  ({drop_to_liq:+.1f}% from now)")
    print(f"                 ${liq_vsui:.4f} vSUI")
    print(f"{sep}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sui_price = get_sui_price()
    if sui_price is None:
        print("[error] Could not fetch SUI price.")
        return

    vsui_usd = get_vsui_usd(sui_price)
    if vsui_usd is None:
        print("[error] Could not fetch vSUI/SUI ratio from DexScreener.")
        return

    vsui_ratio = vsui_usd / sui_price

    pos = NAVIPosition(
        name                  = "vSUI / USDC Loan",
        collateral_symbol     = "vSUI",
        collateral_amount     = 4_886.27,
        debt_symbol           = "USDC",
        debt_amount           = 1_500.00,
        max_ltv               = 0.75,
        liquidation_threshold = 0.80,
    )

    display(pos, sui_price, vsui_usd, vsui_ratio)


if __name__ == "__main__":
    main()
