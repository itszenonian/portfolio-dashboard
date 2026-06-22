#!/usr/bin/env python3
"""
Ember eBLUE Position Tracker

Reads eBLUE vault share holdings from Sui RPC, converts to underlying BLUE
using the on-chain vault exchange rate, and fetches USD price.
"""

import os
import requests
import json
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
WALLET = os.getenv("WALLET_954C", "")

RPCS = {
    "Sui Fullnode": "https://fullnode.mainnet.sui.io",
    "Triton One":   "https://mainnet.sui.rpcpool.com",
}

EBLUE_TYPE = (
    "0xd84b887935d73110c8cb4b981f4925f83b7a20c41ac572840513422c5da283d6"
    "::eblue::EBLUE"
)

# Ember BLUE vault (Vault<BLUE, EBLUE>) — holds the exchange rate
EMBER_VAULT_ID = "0xf8d500875677345b6c0110ee8a48abc7c4974ca697df71eefd229827565168d0"

EBLUE_DECIMALS = 9
BLUE_DECIMALS  = 9


# ── RPC helpers ───────────────────────────────────────────────────────────────

def rpc(endpoint, method, params):
    """Make a JSON-RPC call to a Sui node."""
    r = requests.post(
        endpoint,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result")


def pick_rpc():
    """Try each RPC and return the first one that responds."""
    for name, url in RPCS.items():
        try:
            rpc(url, "sui_getLatestCheckpointSequenceNumber", [])
            return name, url
        except Exception:
            continue
    raise RuntimeError("All RPCs failed")


# ── On-chain data ─────────────────────────────────────────────────────────────

def get_eblue_coins(endpoint):
    """Fetch all eBLUE coin objects for the wallet."""
    coins = []
    cursor = None
    while True:
        result = rpc(endpoint, "suix_getCoins", [WALLET, EBLUE_TYPE, cursor, 50])
        for c in result.get("data", []):
            coins.append({
                "id":      c["coinObjectId"],
                "balance": int(c.get("balance", "0")),
            })
        if not result.get("hasNextPage"):
            break
        cursor = result.get("nextCursor")
    return coins


def get_vault_rate(endpoint):
    """Read the eBLUE vault's exchange rate from on-chain state.

    The vault stores a `rate.value` field (u64).
    Conversion: 1 eBLUE = 1e9 / rate  BLUE
    """
    obj = rpc(endpoint, "sui_getObject", [
        EMBER_VAULT_ID,
        {"showContent": True, "showType": True},
    ])
    fields = obj["data"]["content"]["fields"]
    rate_value = int(fields["rate"]["fields"]["value"])
    vault_name = fields.get("name", "Ember Vault")
    vault_balance = int(fields.get("balance", 0))
    pending_burn = int(fields.get("pending_shares_to_burn", 0))
    return {
        "rate_raw":       rate_value,
        "blue_per_eblue": 1e9 / rate_value,
        "name":           vault_name,
        "vault_balance":  vault_balance,
        "pending_burn":   pending_burn,
    }


# ── Price feed ────────────────────────────────────────────────────────────────

def get_blue_price():
    """Get BLUE (Bluefin) price from CoinGecko, fallback to DexScreener."""
    # CoinGecko
    for attempt in range(2):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bluefin", "vs_currencies": "usd"},
                timeout=15,
            )
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            price = r.json().get("bluefin", {}).get("usd")
            if price:
                return price, "CoinGecko"
        except Exception:
            pass

    # DexScreener fallback
    try:
        r = requests.get(
            "https://api.dexscreener.com/latest/dex/search?q=BLUE%20SUI",
            timeout=15,
        )
        pairs = r.json().get("pairs", [])
        for p in pairs:
            if (p.get("chainId") == "sui"
                    and p.get("baseToken", {}).get("symbol") == "BLUE"
                    and p.get("baseToken", {}).get("address", "").startswith("0xe1b45a0e")):
                price = float(p["priceUsd"])
                if price > 0:
                    return price, "DexScreener"
    except Exception:
        pass

    return 0.0, "unavailable"


# ── Display ───────────────────────────────────────────────────────────────────

def display(coins, vault, blue_price, price_source, rpc_name):
    total_eblue_raw = sum(c["balance"] for c in coins)
    total_eblue     = total_eblue_raw / 10**EBLUE_DECIMALS
    blue_per_eblue  = vault["blue_per_eblue"]
    total_blue      = total_eblue * blue_per_eblue
    total_usd       = total_blue * blue_price
    eblue_price     = blue_per_eblue * blue_price
    sep             = "─" * 66

    print(f"\n{'═'*66}")
    print(f"  Ember eBLUE Position Tracker")
    print(f"  Wallet: {WALLET[:16]}...{WALLET[-6:]}")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}   (via {rpc_name})")
    print(f"{'═'*66}")

    # ── Vault info ────────────────────────────────────────────────────────
    print(f"\n  VAULT: {vault['name']}")
    print(f"  {sep}")
    rate_pct = ((blue_per_eblue - 1.0) * 100)
    print(f"  Rate (on-chain):  {vault['rate_raw']}")
    print(f"  1 eBLUE         = {blue_per_eblue:.10f} BLUE  (+{rate_pct:.2f}% from inception)")
    vault_bal = vault["vault_balance"] / 10**BLUE_DECIMALS
    print(f"  Vault BLUE bal:   {vault_bal:>16,.4f} BLUE")

    # ── eBLUE holdings ────────────────────────────────────────────────────
    print(f"\n  eBLUE HOLDINGS ({len(coins)} object{'s' if len(coins) != 1 else ''})")
    print(f"  {sep}")
    print(f"  {'Object ID':<18}  {'eBLUE':>14}  {'→ BLUE':>14}  {'USD Value':>12}")
    print(f"  {'─'*18}  {'─'*14}  {'─'*14}  {'─'*12}")

    for c in sorted(coins, key=lambda x: x["balance"], reverse=True):
        eblue = c["balance"] / 10**EBLUE_DECIMALS
        blue  = eblue * blue_per_eblue
        usd   = blue * blue_price
        short = c["id"][:14] + "..."
        print(f"  {short:<18}  {eblue:>14,.2f}  {blue:>14,.2f}  ${usd:>11,.2f}")

    print(f"  {'─'*62}")
    print(f"  {'TOTAL':<18}  {total_eblue:>14,.2f}  {total_blue:>14,.2f}  ${total_usd:>11,.2f}")

    # ── Price info ────────────────────────────────────────────────────────
    print(f"\n  {sep}")
    print(f"  BLUE price:    ${blue_price:>12.6f}   ({price_source})")
    print(f"  eBLUE price:   ${eblue_price:>12.6f}   (BLUE × rate)")
    print(f"  Total value:   ${total_usd:>12,.2f}")
    print(f"{'═'*66}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("  Connecting to RPC ...")
    rpc_name, rpc_url = pick_rpc()
    print(f"  Using {rpc_name}")

    print("  Fetching eBLUE holdings ...")
    coins = get_eblue_coins(rpc_url)
    if not coins:
        print("  No eBLUE found for this wallet.")
        return

    print("  Reading vault exchange rate ...")
    vault = get_vault_rate(rpc_url)

    print("  Fetching BLUE price ...")
    blue_price, price_source = get_blue_price()
    if blue_price == 0:
        print("  [warn] Could not fetch BLUE price, showing 0.")

    display(coins, vault, blue_price, price_source, rpc_name)


if __name__ == "__main__":
    main()
