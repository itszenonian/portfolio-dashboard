#!/usr/bin/env python3
"""
On-chain position tracker — Sui RPC only
Queries: Walrus Staking, Cetus xCETUS, Scallop Lending
"""

import sys
import time
import requests
from datetime import datetime

sys.path.insert(0, "/Users/zenonian/Desktop/Claude/Projects/Portfolio tracker project")
from Dexscreener_API import price_in_sui, PAIRS

WALLET  = "0x954c6cd5de1dd1048cb8d158969d33b860e0486f9c7bf7ca71c44fbb57ac80c8"
RPC     = "https://fullnode.mainnet.sui.io"

SCALLOP_BS_TABLE = "0x8708eb23153bdc4b345c9f536fe05b62206f3f55629b26389d4fe5f129bd8368"

COIN_DECIMALS = {"USDC": 6, "USDT": 6, "ETH": 8, "WBTC": 8}

COINGECKO_IDS = {
    "WAL":   "walrus-2",
    "CETUS": "cetus-protocol",
    "SUI":   "sui",
    "USDC":  "usd-coin",
    "USDT":  "tether",
    "SCA":   "scallop-2",
    "WWAL":  "walrus-2",
    "HAWAL": "walrus-2",
    "HASUI": "haedal-staked-sui",
    "USDY":  "ondo-us-dollar-yield",
    "AFSUI": "aftermath-staked-sui",
}


# ── RPC helpers ───────────────────────────────────────────────────────────────

def rpc(method, params):
    r = requests.post(RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20)
    r.raise_for_status()
    return r.json().get("result")


def multi_get(ids):
    return rpc("sui_multiGetObjects", [ids, {"showContent": True, "showType": True}])


def find_objects(address, *patterns):
    found  = {p: [] for p in patterns}
    cursor = None
    while True:
        result = rpc("suix_getOwnedObjects", [
            address, {"options": {"showType": True}}, cursor, 50])
        for obj in result.get("data", []):
            t   = obj.get("data", {}).get("type", "")
            oid = obj.get("data", {}).get("objectId", "")
            for p in patterns:
                if p in t:
                    found[p].append(oid)
                    break
        if not result.get("hasNextPage"):
            break
        cursor = result.get("nextCursor")
    return found


# ── Prices ────────────────────────────────────────────────────────────────────

def get_prices() -> dict[str, float]:
    ids = ",".join(set(COINGECKO_IDS.values()))
    for attempt in range(3):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "usd"},
                timeout=15,
            )
            if r.status_code == 429:
                time.sleep(12)
                continue
            r.raise_for_status()
            raw = r.json()
            # map back to symbol → price
            result = {}
            for sym, cg_id in COINGECKO_IDS.items():
                if cg_id in raw and "usd" in raw[cg_id]:
                    result[sym] = raw[cg_id]["usd"]
            return result
        except Exception:
            time.sleep(5)
    return {}


# ── Walrus Staking ────────────────────────────────────────────────────────────

def fetch_walrus(ids: list[str], wal_price: float | None) -> tuple[float, float]:
    if not ids:
        return 0.0, 0.0
    objs      = multi_get(ids)
    total_wal = sum(
        int(o["data"]["content"]["fields"]["principal"])
        for o in objs if o.get("data")
    ) / 1e9
    return total_wal, total_wal * wal_price if wal_price else 0.0


# ── Cetus xCETUS ─────────────────────────────────────────────────────────────

def fetch_xcetus(ids: list[str], cetus_price: float | None) -> tuple[float, float]:
    if not ids:
        return 0.0, 0.0
    objs  = multi_get(ids)
    total = sum(
        int(o["data"]["content"]["fields"]["xcetus_balance"])
        for o in objs if o.get("data")
    ) / 1e9
    return total, total * cetus_price if cetus_price else 0.0


# ── Scallop — receipt tokens (supply) ────────────────────────────────────────

def _scallop_rates(syms: set[str]) -> dict[str, float]:
    dfs    = rpc("suix_getDynamicFields", [SCALLOP_BS_TABLE, None, 50]) or {}
    sym_id = {
        d["name"]["value"]["name"].split("::")[-1].upper(): d["objectId"]
        for d in dfs.get("data", [])
    }
    ids = [sym_id[s] for s in syms if s in sym_id]
    if not ids:
        return {}
    rates = {}
    for o in multi_get(ids):
        if not o.get("data"):
            continue
        oid = o["data"]["objectId"]
        sym = next((s for s, i in sym_id.items() if i == oid), None)
        if not sym:
            continue
        bs     = o["data"]["content"]["fields"].get("value", {}).get("fields", {})
        cash   = int(bs.get("cash", 0))
        debt   = int(bs.get("debt", 0))
        rev    = int(bs.get("revenue", 0))
        supply = int(bs.get("market_coin_supply", 1))
        if supply > 0:
            rates[sym] = (cash + debt - rev) / supply
    return rates


def fetch_scallop_supply(balances: list[dict], prices: dict[str, float]):
    sc_tokens = []
    for b in balances:
        ct  = b["coinType"]
        raw = int(b["totalBalance"])
        if raw == 0:
            continue
        sym = ct.split("::")[-1].upper()
        if sym.startswith("SCALLOP_") and "REWARD" not in sym:
            sc_tokens.append((sym[len("SCALLOP_"):], raw))

    if not sc_tokens:
        return [], 0.0

    rates = _scallop_rates({u for u, _ in sc_tokens})
    rows, total = [], 0.0
    for underlying, raw_sc in sc_tokens:
        rate = rates.get(underlying)
        if rate is None:
            continue
        dec    = COIN_DECIMALS.get(underlying, 9)
        amount = raw_sc * rate / (10 ** dec)
        price  = prices.get(underlying)
        usd    = amount * price if price else None
        if usd and usd >= 0.01:
            rows.append((underlying, amount, price, usd))
            total += usd
    return rows, total


# ── Scallop — lending obligation ──────────────────────────────────────────────

def fetch_scallop_obligation(key_ids: list[str], prices: dict[str, float]):
    if not key_ids:
        return [], [], 0.0

    keys = multi_get(key_ids)
    obligation_ids = [
        k["data"]["content"]["fields"]["ownership"]["fields"]["of"]
        for k in keys if k.get("data")
    ]
    if not obligation_ids:
        return [], [], 0.0

    obligations = multi_get(obligation_ids)
    deposits, borrows = [], []

    for obj in obligations:
        if not obj.get("data"):
            continue
        f = obj["data"]["content"]["fields"]

        # Collateral (BalanceBag)
        bag_id  = f["balances"]["fields"]["bag"]["fields"]["id"]["id"]
        bag_dfs = rpc("suix_getDynamicFields", [bag_id, None, 50]) or {}
        bal_ids = [d["objectId"] for d in bag_dfs.get("data", [])]
        if bal_ids:
            for bo in multi_get(bal_ids):
                if not bo.get("data"):
                    continue
                bf  = bo["data"]["content"]["fields"]
                sym = bf["name"]["fields"]["name"].split("::")[-1].upper()
                raw = int(bf["value"])
                if raw == 0:
                    continue
                dec = COIN_DECIMALS.get(sym, 9)
                amt = raw / (10 ** dec)
                usd = amt * prices[sym] if sym in prices else None
                if usd and usd >= 0.01:
                    deposits.append((sym, amt, prices.get(sym), usd))

        # Borrows (WitTable)
        debts_id  = f["debts"]["fields"]["table"]["fields"]["id"]["id"]
        debt_dfs  = rpc("suix_getDynamicFields", [debts_id, None, 50]) or {}
        debt_ids  = [d["objectId"] for d in debt_dfs.get("data", [])]
        if debt_ids:
            for do in multi_get(debt_ids):
                if not do.get("data"):
                    continue
                df  = do["data"]["content"]["fields"]
                sym = df["name"]["fields"]["name"].split("::")[-1].upper()
                raw = int(df["value"]["fields"]["amount"])
                if raw == 0:
                    continue
                dec = COIN_DECIMALS.get(sym, 9)
                amt = raw / (10 ** dec)
                usd = amt * prices[sym] if sym in prices else None
                if usd and usd >= 0.01:
                    borrows.append((sym, amt, prices.get(sym), usd))

    net = sum(u for _, _, _, u in deposits) - sum(u for _, _, _, u in borrows)
    return deposits, borrows, net


# ── Display ───────────────────────────────────────────────────────────────────

sep = "─" * 58

def print_header(title: str):
    print(f"\n  {title}")
    print("  " + "─" * 54)

def print_row(sym, amount, price, usd, label=""):
    p_str = f"${price:,.4f}" if price else "N/A"
    tag   = f"  [{label}]" if label else ""
    print(f"  {sym:<10} {amount:>14,.4f}  {p_str:>10}  ${usd:>10,.2f}{tag}")

def print_total(label, usd):
    print("  " + "─" * 54)
    print(f"  {label:<36}  ${usd:>10,.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*58}")
    print(f"  On-chain Positions — Sui RPC")
    print(f"  Wallet: {WALLET[:16]}...{WALLET[-6:]}")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"{'═'*58}")

    print("\n  Fetching prices ...")
    prices = get_prices()
    hasui_ratio = price_in_sui(PAIRS["haSUI/SUI"])

    print("  Scanning on-chain objects ...")
    defi = find_objects(WALLET,
        "::staked_wal::StakedWal",
        "::xcetus::VeNFT",
        "::obligation::ObligationKey",
    )

    balances = rpc("suix_getAllBalances", [WALLET]) or []

    grand_total = 0.0

    # ── Walrus Staking ────────────────────────────────────────────────────
    wal_ids = defi["::staked_wal::StakedWal"]
    wal_amt, wal_usd = fetch_walrus(wal_ids, prices.get("WAL"))
    print_header(f"WALRUS STAKING  ({len(wal_ids)} position{'s' if len(wal_ids)!=1 else ''})")
    if wal_ids:
        print_row("WAL", wal_amt, prices.get("WAL"), wal_usd)
        print_total("Walrus Total", wal_usd)
        grand_total += wal_usd
    else:
        print("  No staked WAL found.")

    # ── Cetus xCETUS ──────────────────────────────────────────────────────
    venft_ids = defi["::xcetus::VeNFT"]
    xcetus_amt, xcetus_usd = fetch_xcetus(venft_ids, prices.get("CETUS"))
    print_header(f"CETUS — xCETUS  ({len(venft_ids)} position{'s' if len(venft_ids)!=1 else ''})")
    if venft_ids:
        print_row("xCETUS", xcetus_amt, prices.get("CETUS"), xcetus_usd)
        print_total("Cetus Total", xcetus_usd)
        grand_total += xcetus_usd
    else:
        print("  No xCETUS positions found.")

    # ── Scallop Supply ────────────────────────────────────────────────────
    sc_supply_rows, sc_supply_total = fetch_scallop_supply(balances, prices)
    print_header("SCALLOP — Supply (receipt tokens)")
    if sc_supply_rows:
        print(f"  {'Token':<10} {'Amount':>14}  {'Price':>10}  {'USD Value':>11}")
        print("  " + "─" * 54)
        for sym, amt, price, usd in sc_supply_rows:
            print_row(sym, amt, price, usd)
        print_total("Scallop Supply Total", sc_supply_total)
        grand_total += sc_supply_total
    else:
        print("  No Scallop supply positions found.")

    # ── Scallop Lending Obligation ────────────────────────────────────────
    key_ids = defi["::obligation::ObligationKey"]
    sc_deps, sc_borrs, sc_net = fetch_scallop_obligation(key_ids, prices)
    print_header(f"SCALLOP — Lending Obligation  ({len(key_ids)} key{'s' if len(key_ids)!=1 else ''})")
    if sc_deps or sc_borrs:
        if sc_deps:
            print("  Collateral:")
            for sym, amt, price, usd in sc_deps:
                print_row(sym, amt, price, usd, "collateral")
                if sym == "HASUI" and hasui_ratio:
                    sui_eq = amt * hasui_ratio
                    print(f"  {'SUI':<10} {sui_eq:>14,.4f}  {'':>10}  {'':>11}  (haSUI/SUI {hasui_ratio:.4f})")
        if sc_borrs:
            print("  Borrows (debt):")
            for sym, amt, price, usd in sc_borrs:
                print_row(sym, amt, price, usd, "debt")
        print_total("Scallop Net", sc_net)
        grand_total += sc_net
    else:
        print("  No Scallop obligation found.")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'═'*58}")
    print(f"  {'TOTAL (3 protocols)':<36}  ${grand_total:>10,.2f}")
    print(f"{'═'*58}\n")


if __name__ == "__main__":
    main()
