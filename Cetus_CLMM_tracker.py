#!/usr/bin/env python3
"""
Cetus CLMM Position Tracker — Sui RPC
Fetches position data on-chain and computes token amounts from liquidity math.
"""

import math
import time
import requests
from datetime import datetime

WALLET = "0xe64cb49a4b073c88908e6d29db34b599f926281c94be60276e290fde5c6f03c9"
RPC    = "https://fullnode.mainnet.sui.io"

CETUS_POSITION_TYPE = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb::position::Position"


# ── RPC helpers ───────────────────────────────────────────────────────────────

def rpc(method, params):
    r = requests.post(RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20)
    r.raise_for_status()
    return r.json().get("result")


def multi_get(ids: list[str]) -> list[dict]:
    return rpc("sui_multiGetObjects", [ids, {"showContent": True, "showType": True}])


def find_cetus_positions(address: str) -> list[str]:
    """Scan owned objects for Cetus Position NFTs."""
    found, cursor = [], None
    while True:
        result = rpc("suix_getOwnedObjects",
            [address, {"options": {"showType": True}}, cursor, 50])
        for obj in result.get("data", []):
            if obj.get("data", {}).get("type", "") == CETUS_POSITION_TYPE:
                found.append(obj["data"]["objectId"])
        if not result.get("hasNextPage"):
            break
        cursor = result.get("nextCursor")
    return found


# ── Price feed ────────────────────────────────────────────────────────────────

def get_sui_price() -> float:
    for attempt in range(3):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "sui", "vs_currencies": "usd"},
                timeout=10,
            )
            if r.status_code == 429:
                time.sleep(12)
                continue
            r.raise_for_status()
            return r.json()["sui"]["usd"]
        except Exception:
            time.sleep(5)
    return 0.0


# ── CLMM math ─────────────────────────────────────────────────────────────────

def decode_i32(bits: int) -> int:
    """Convert Cetus I32 bits field to signed Python int."""
    return bits if bits < 2**31 else bits - 2**32


def token_amounts(
    liquidity: int,
    sqrt_price_q64: int,
    tick_lower: int,
    tick_upper: int,
    current_tick: int,
) -> tuple[float, float]:
    """
    Compute raw token amounts for a CLMM position.
    Returns (raw_A, raw_B) in smallest denomination.
    """
    sqrt_P       = sqrt_price_q64 / 2**64
    sqrt_P_lower = math.sqrt(1.0001 ** tick_lower)
    sqrt_P_upper = math.sqrt(1.0001 ** tick_upper)

    if tick_lower <= current_tick <= tick_upper:
        raw_A = liquidity * (sqrt_P_upper - sqrt_P) / (sqrt_P * sqrt_P_upper)
        raw_B = liquidity * (sqrt_P - sqrt_P_lower)
    elif current_tick < tick_lower:
        raw_A = liquidity * (sqrt_P_upper - sqrt_P_lower) / (sqrt_P_lower * sqrt_P_upper)
        raw_B = 0.0
    else:
        raw_A = 0.0
        raw_B = liquidity * (sqrt_P_upper - sqrt_P_lower)

    return raw_A, raw_B


# ── Display ───────────────────────────────────────────────────────────────────

def display(
    pos_name:   str,
    sym_a:      str,
    sym_b:      str,
    dec_a:      int,
    dec_b:      int,
    amt_a:      float,
    amt_b:      float,
    price_a_usd: float,
    price_b_usd: float,
    price_now:  float,
    p_lower:    float,
    p_upper:    float,
    in_range:   bool,
    pool_id:    str,
) -> None:
    val_a   = amt_a * price_a_usd
    val_b   = amt_b * price_b_usd
    total   = val_a + val_b
    status  = "● IN RANGE" if in_range else "○ OUT OF RANGE"
    sep     = "─" * 60

    print(f"\n{sep}")
    print(f"  Cetus CLMM — {sym_b}/{sym_a}  [{status}]")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Pool  {pool_id[:20]}...{pool_id[-6:]}")
    print(f"  Range  {p_lower:.4f} — {p_upper:.4f} {sym_a}/{sym_b}  |  Now {price_now:.4f}")
    print(sep)
    print(f"  {sym_a:<10} {amt_a:>14,.4f}   ${val_a:>12,.2f}")
    print(f"  {sym_b:<10} {amt_b:>14,.4f}   ${val_b:>12,.2f}")
    print(f"  {'─'*56}")
    print(f"  {'Total':<10} {'':>14}   ${total:>12,.2f}")
    print(f"{sep}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'═'*60}")
    print(f"  Cetus CLMM Tracker")
    print(f"  Wallet: {WALLET[:16]}...{WALLET[-6:]}")
    print(f"{'═'*60}")

    print("\n  Fetching SUI price ...")
    sui_price = get_sui_price()

    print("  Scanning for Cetus positions ...")
    pos_ids = find_cetus_positions(WALLET)
    if not pos_ids:
        print("  No Cetus CLMM positions found.")
        return

    positions = multi_get(pos_ids)

    for pos_obj in positions:
        if not pos_obj.get("data"):
            continue

        pf       = pos_obj["data"]["content"]["fields"]
        pool_id  = pf["pool"]
        liquidity = int(pf["liquidity"])
        tick_lower = decode_i32(int(pf["tick_lower_index"]["fields"]["bits"]))
        tick_upper = decode_i32(int(pf["tick_upper_index"]["fields"]["bits"]))
        sym_a = pf["coin_type_a"]["fields"]["name"].split("::")[-1]
        sym_b = pf["coin_type_b"]["fields"]["name"].split("::")[-1]
        name  = pf.get("name", f"{sym_a}/{sym_b}")

        # Fetch pool for current tick + sqrt_price
        pool = rpc("sui_getObject", [pool_id, {"showContent": True}])
        pool_f = pool["data"]["content"]["fields"]
        sqrt_price_q64 = int(pool_f["current_sqrt_price"])
        current_tick   = decode_i32(int(pool_f["current_tick_index"]["fields"]["bits"]))

        # Fetch coin metadata for decimals (coin types need 0x prefix)
        def full_type(name: str) -> str:
            return name if name.startswith("0x") else "0x" + name

        coin_meta_a = rpc("suix_getCoinMetadata", [full_type(pf["coin_type_a"]["fields"]["name"])])
        coin_meta_b = rpc("suix_getCoinMetadata", [full_type(pf["coin_type_b"]["fields"]["name"])])
        dec_a = int(coin_meta_a["decimals"]) if coin_meta_a else 9
        dec_b = int(coin_meta_b["decimals"]) if coin_meta_b else 9

        # Compute amounts
        raw_a, raw_b = token_amounts(liquidity, sqrt_price_q64, tick_lower, tick_upper, current_tick)
        amt_a = raw_a / 10**dec_a
        amt_b = raw_b / 10**dec_b

        # Prices — coin_b here is SUI; coin_a is a stablecoin pegged to USD
        price_a_usd = 1.0      # USDSUI ≈ $1
        price_b_usd = sui_price

        # Decimal adjustment for human-readable price
        dec_adj = 10**dec_a / 10**dec_b
        price_sui_per_a = (( sqrt_price_q64 / 2**64) ** 2) * dec_adj
        price_now       = 1 / price_sui_per_a            # USDSUI per SUI
        p_lower_raw     = (1.0001 ** tick_lower) * dec_adj
        p_upper_raw     = (1.0001 ** tick_upper) * dec_adj
        p_lower         = 1 / p_upper_raw                # invert and swap
        p_upper         = 1 / p_lower_raw

        in_range = tick_lower <= current_tick <= tick_upper

        display(
            pos_name    = name,
            sym_a       = sym_a,
            sym_b       = sym_b,
            dec_a       = dec_a,
            dec_b       = dec_b,
            amt_a       = amt_a,
            amt_b       = amt_b,
            price_a_usd = price_a_usd,
            price_b_usd = price_b_usd,
            price_now   = price_now,
            p_lower     = p_lower,
            p_upper     = p_upper,
            in_range    = in_range,
            pool_id     = pool_id,
        )


if __name__ == "__main__":
    main()
