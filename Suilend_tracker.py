#!/usr/bin/env python3
"""
Suilend Supply Position Tracker — On-chain via Sui RPC

Reads deposits, borrows, LTV, and health factor directly from the Suilend
lending market and obligation objects on-chain.
"""

import sys
import time
import requests
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, "/Users/zenonian/Desktop/Claude/Projects/Portfolio tracker project")
from Dexscreener_API import price_in_sui, PAIRS


# ── Config ────────────────────────────────────────────────────────────────────
WALLET  = "0x954c6cd5de1dd1048cb8d158969d33b860e0486f9c7bf7ca71c44fbb57ac80c8"
RPC     = "https://fullnode.mainnet.sui.io"

SUILEND_PKG     = "0xf95b06141ed4a174f239417323bde3f209b972f5930d8521ea38a52aff3a6ddf"
OBLIGATION_CAP  = "::lending_market::ObligationOwnerCap"

# Decimals by coin symbol (default 9 for Sui-native tokens)
COIN_DECIMALS = {"USDC": 6, "USDT": 6, "DEEP": 6, "ETH": 8, "WBTC": 8}

# CoinGecko mapping for price feeds
COINGECKO_IDS = {
    "SUI":        "sui",
    "SPRING_SUI": "sui",       # sSUI tracks SUI; we apply the sSUI/SUI ratio separately
    "DEEP":       "deep",
    "WAL":        "walrus-2",
    "USDC":       "usd-coin",
    "USDT":       "tether",
}

# Human-readable symbol aliases
SYMBOL_ALIAS = {
    "SPRING_SUI": "sSUI",
}


# ── RPC helpers ───────────────────────────────────────────────────────────────

def rpc(method, params):
    r = requests.post(RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=20)
    r.raise_for_status()
    return r.json().get("result")


def get_object(oid):
    return rpc("sui_getObject", [oid, {"showContent": True, "showType": True}])


def multi_get(ids):
    return rpc("sui_multiGetObjects", [ids, {"showContent": True, "showType": True}])


def find_objects(address, *patterns):
    """Scan all owned objects for type patterns."""
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


# ── Price Feed ────────────────────────────────────────────────────────────────

def get_prices() -> dict[str, float]:
    """Fetch prices from CoinGecko with retry."""
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
            result = {}
            for sym, cg_id in COINGECKO_IDS.items():
                if cg_id in raw and "usd" in raw[cg_id]:
                    result[sym] = raw[cg_id]["usd"]
            return result
        except Exception:
            time.sleep(5)
    return {}


# ── Position Model ────────────────────────────────────────────────────────────

@dataclass
class CollateralAsset:
    symbol:      str
    amount:      float
    price_usd:   float
    max_ltv:     float   # open_ltv_pct / 100
    liq_thresh:  float   # close_ltv_pct / 100

    @property
    def value_usd(self) -> float:
        return self.amount * self.price_usd

    @property
    def borrow_capacity(self) -> float:
        return self.value_usd * self.max_ltv

    @property
    def liq_buffer(self) -> float:
        return self.value_usd * self.liq_thresh


@dataclass
class BorrowAsset:
    symbol:     str
    amount:     float
    price_usd:  float

    @property
    def value_usd(self) -> float:
        return self.amount * self.price_usd


# ── On-chain Data Fetching ────────────────────────────────────────────────────

def fetch_suilend_positions() -> tuple[list[CollateralAsset], list[BorrowAsset], dict]:
    """
    Fetch deposits, borrows, and protocol parameters from the Suilend
    obligation object via Sui RPC.

    Returns: (deposits, borrows, protocol_values)
    """
    # 1. Find ObligationOwnerCap in wallet
    found = find_objects(WALLET, OBLIGATION_CAP)
    cap_ids = found[OBLIGATION_CAP]
    if not cap_ids:
        return [], [], {}

    # 2. Get obligation ID from cap
    caps = multi_get(cap_ids)
    obligation_ids = [
        c["data"]["content"]["fields"]["obligation_id"]
        for c in caps if c.get("data")
    ]
    if not obligation_ids:
        return [], [], {}

    # 3. Get obligation + lending market
    obligation = get_object(obligation_ids[0])
    obl_fields = obligation["data"]["content"]["fields"]
    lending_market_id = obl_fields["lending_market_id"]
    lending_market = get_object(lending_market_id)
    reserves = lending_market["data"]["content"]["fields"]["reserves"]

    # 4. Helper: get reserve config + exchange rate
    def reserve_info(reserve_idx):
        res = reserves[int(reserve_idx)]["fields"]
        config = res["config"]["fields"]["element"]["fields"]
        avail = int(res["available_amount"])
        ctoken_supply = int(res["ctoken_supply"])
        borrowed_raw = res.get("borrowed_amount")
        if isinstance(borrowed_raw, dict):
            borrowed = int(borrowed_raw["fields"]["value"])
        else:
            borrowed = int(borrowed_raw)
        total_underlying = avail + borrowed / 1e18
        ctoken_rate = total_underlying / ctoken_supply if ctoken_supply > 0 else 1.0
        reserve_cbr = int(res["cumulative_borrow_rate"]["fields"]["value"])
        return {
            "open_ltv":    int(config["open_ltv_pct"]) / 100,
            "close_ltv":   int(config["close_ltv_pct"]) / 100,
            "ctoken_rate":  ctoken_rate,
            "reserve_cbr":  reserve_cbr,
            "coin_type":   res["coin_type"]["fields"]["name"],
        }

    # 5. Parse deposits
    deposits_raw = obl_fields.get("deposits", [])
    deposit_infos = []
    for dep in deposits_raw:
        df = dep["fields"]
        coin_name = df["coin_type"]["fields"]["name"]
        sym = coin_name.split("::")[-1]
        ctoken_amount = int(df["deposited_ctoken_amount"])
        reserve_idx = df["reserve_array_index"]
        ri = reserve_info(reserve_idx)
        dec = COIN_DECIMALS.get(sym, 9)
        amount = ctoken_amount * ri["ctoken_rate"] / (10 ** dec)
        deposit_infos.append({
            "symbol": sym,
            "amount": amount,
            "open_ltv": ri["open_ltv"],
            "close_ltv": ri["close_ltv"],
        })

    # 6. Parse borrows
    borrows_raw = obl_fields.get("borrows", [])
    borrow_infos = []
    for bor in borrows_raw:
        bf = bor["fields"]
        coin_name = bf["coin_type"]["fields"]["name"]
        sym = coin_name.split("::")[-1]
        user_borrow_raw = int(bf["borrowed_amount"]["fields"]["value"])
        user_cbr = int(bf["cumulative_borrow_rate"]["fields"]["value"])
        reserve_idx = bf["reserve_array_index"]
        ri = reserve_info(reserve_idx)
        # Accrue interest: real_amount = user_borrow / user_cbr * reserve_cbr
        real_amount_raw = user_borrow_raw / user_cbr * ri["reserve_cbr"]
        dec = COIN_DECIMALS.get(sym, 9)
        amount = real_amount_raw / 1e18 / (10 ** dec)
        borrow_infos.append({
            "symbol": sym,
            "amount": amount,
        })

    # 7. Protocol-level values (Decimal with 18 precision)
    def dec18(field_name):
        return int(obl_fields[field_name]["fields"]["value"]) / 1e18

    protocol_values = {
        "deposited_value_usd":          dec18("deposited_value_usd"),
        "allowed_borrow_value_usd":     dec18("allowed_borrow_value_usd"),
        "unhealthy_borrow_value_usd":   dec18("unhealthy_borrow_value_usd"),
        "unweighted_borrowed_value_usd": dec18("unweighted_borrowed_value_usd"),
        "weighted_borrowed_value_usd":  dec18("weighted_borrowed_value_usd"),
    }

    return deposit_infos, borrow_infos, protocol_values


# ── Display ───────────────────────────────────────────────────────────────────

def display(assets: list[CollateralAsset], borrows: list[BorrowAsset],
            protocol: dict, ssui_ratio: float = 0.0) -> None:
    total_col   = sum(a.value_usd for a in assets)
    total_cap   = sum(a.borrow_capacity for a in assets)
    total_liq   = sum(a.liq_buffer for a in assets)
    total_debt  = sum(b.value_usd for b in borrows)
    net_val     = total_col - total_debt
    sep         = "─" * 66

    print(f"\n{'═'*66}")
    print(f"  Suilend — On-chain Position Tracker")
    print(f"  Wallet: {WALLET[:16]}...{WALLET[-6:]}")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"{'═'*66}")

    # ── Deposits ──────────────────────────────────────────────────────────
    print(f"\n  SUPPLY POSITIONS ({len(assets)} asset{'s' if len(assets)!=1 else ''})")
    print(f"  {sep}")
    print(f"  {'Asset':<6}  {'Amount':>14}  {'Price':>10}  {'USD Value':>12}  {'LTV':>5}  {'Liq':>5}")
    print(f"  {'─'*6}  {'─'*14}  {'─'*10}  {'─'*12}  {'─'*5}  {'─'*5}")

    for a in assets:
        disp = SYMBOL_ALIAS.get(a.symbol, a.symbol)
        print(f"  {disp:<6}  {a.amount:>14,.4f}  ${a.price_usd:>9,.4f}  ${a.value_usd:>11,.2f}  {a.max_ltv*100:>4.0f}%  {a.liq_thresh*100:>4.0f}%")
        if a.symbol == "SPRING_SUI" and ssui_ratio:
            sui_eq = a.amount * ssui_ratio
            print(f"  {'':>6}  {'':>14}  {'':>10}  {'':>12}  (sSUI/SUI {ssui_ratio:.4f}  ≈ {sui_eq:,.2f} SUI)")

    print(f"  {'─'*62}")
    print(f"  {'Collateral Total':<36}  ${total_col:>11,.2f}")

    # ── Borrows ───────────────────────────────────────────────────────────
    if borrows:
        print(f"\n  BORROW POSITIONS ({len(borrows)} asset{'s' if len(borrows)!=1 else ''})")
        print(f"  {sep}")
        print(f"  {'Asset':<6}  {'Amount':>14}  {'Price':>10}  {'USD Value':>12}")
        print(f"  {'─'*6}  {'─'*14}  {'─'*10}  {'─'*12}")
        for b in borrows:
            print(f"  {b.symbol:<6}  {b.amount:>14,.4f}  ${b.price_usd:>9,.4f}  ${b.value_usd:>11,.2f}  [debt]")
        print(f"  {'─'*62}")
        print(f"  {'Total Debt':<36}  ${total_debt:>11,.2f}")

    # ── Health & LTV ──────────────────────────────────────────────────────
    print(f"\n  {'─'*62}")
    print(f"  Net value           ${net_val:>11,.2f}")

    if total_debt > 0:
        ltv    = total_debt / total_col if total_col > 0 else 0
        health = total_liq / total_debt if total_debt > 0 else 999
        util   = total_debt / total_cap if total_cap > 0 else 0

        status = '✓ safe' if health > 1.5 else ('⚠ caution' if health > 1.1 else '✗ danger')
        print(f"  Health factor       {health:>10.4f}  {status}")
        print(f"  Current LTV         {ltv*100:>9.2f}%")
        print(f"  Borrow capacity     ${total_cap:>11,.2f}  ({util*100:.1f}% used)")
        print(f"  Liq threshold       ${total_liq:>11,.2f}")

        # On-chain values from obligation (for cross-check)
        if protocol:
            print(f"\n  On-chain (obligation object):")
            print(f"    Deposited value   ${protocol['deposited_value_usd']:>11,.2f}")
            print(f"    Allowed borrow    ${protocol['allowed_borrow_value_usd']:>11,.2f}")
            print(f"    Borrowed (unwtd)  ${protocol['unweighted_borrowed_value_usd']:>11,.2f}")
            print(f"    Liq threshold     ${protocol['unhealthy_borrow_value_usd']:>11,.2f}")
    else:
        print(f"  Max borrow          ${total_cap:>11,.2f}  available")
        print(f"  No active debt")

    print(f"{'═'*66}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("  Fetching prices ...")
    prices = get_prices()
    if not prices or "SUI" not in prices:
        print("[error] Could not fetch prices.")
        return

    # sSUI price via DexScreener ratio
    ssui_ratio = price_in_sui(PAIRS["sSUI/SUI"])
    ssui_price = ssui_ratio * prices["SUI"] if ssui_ratio else 0
    prices["SPRING_SUI"] = ssui_price

    print("  Fetching on-chain Suilend positions ...")
    deposit_infos, borrow_infos, protocol = fetch_suilend_positions()

    if not deposit_infos and not borrow_infos:
        print("  No Suilend positions found for this wallet.")
        return

    # Build CollateralAsset list
    assets = []
    for d in deposit_infos:
        sym = d["symbol"]
        price = prices.get(sym, 0)
        assets.append(CollateralAsset(
            symbol     = sym,
            amount     = d["amount"],
            price_usd  = price,
            max_ltv    = d["open_ltv"],
            liq_thresh = d["close_ltv"],
        ))

    # Build BorrowAsset list
    borrows = []
    for b in borrow_infos:
        sym = b["symbol"]
        price = prices.get(sym, 0)
        borrows.append(BorrowAsset(
            symbol    = sym,
            amount    = b["amount"],
            price_usd = price,
        ))

    display(assets, borrows, protocol, ssui_ratio=ssui_ratio or 0.0)


if __name__ == "__main__":
    main()
