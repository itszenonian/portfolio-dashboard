
#!/usr/bin/env python3
"""
Portfolio Dashboard Generator
Fetches all position data and generates portfolio_dashboard.html
"""

import sys
import math
import hmac
import hashlib
import time
import json
import os
import base64
import requests
from datetime import datetime, timezone, timedelta

BANGKOK_TZ = timezone(timedelta(hours=7))
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from Dexscreener_API import price_in_sui, PAIRS

_BV_KEY  = os.getenv("BLOCKVISION_API_KEY", "")
_BN_KEY  = os.getenv("BINANCE_API_KEY", "")
_BN_SEC  = os.getenv("BINANCE_SECRET_KEY", "")
RPC      = "https://mainnet.sui.rpcpool.com"
_BV_RPC  = "https://sui-mainnet-endpoint.blockvision.org"
WALLET_954C    = os.getenv("WALLET_954C", "")
WALLET_E64C    = os.getenv("WALLET_E64C", "")
SCALLOP_BS_TBL = "0x8708eb23153bdc4b345c9f536fe05b62206f3f55629b26389d4fe5f129bd8368"
OBLIGATION_CAP = "::lending_market::ObligationOwnerCap"
CETUS_POS_TYPE   = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb::position::Position"
BLUEFIN_POS_TYPE = "0x3492c874c1e3b3e2984e8c41b589e642d4d0a5d6459e5a9cfc2d52fd7c89c267::position::Position"

COIN_DEC = {"USDC": 6, "USDT": 6, "DEEP": 6, "ETH": 8, "WBTC": 8, "LBTC": 8, "XBTC": 8}

# Scallop sCoin names (scallop_zwbtc, scallop_ha_sui, ...) don't match the rate-table /
# price keys. Map the stripped sCoin name -> the underlying market symbol used for the
# exchange rate, price and decimals. (zWBTC is valued via the WBTC market.)
SCOIN_ALIAS = {
    "HA_SUI": "HASUI", "AF_SUI": "AFSUI",
    "WORMHOLE_ETH": "ETH", "WORMHOLE_USDT": "USDT",
    "ZWBTC": "WBTC",
}
# Pretty display labels for those sCoins in the Scallop supply rows.
SCOIN_DISPLAY = {
    "ZWBTC": "BTC", "HA_SUI": "haSUI", "AF_SUI": "afSUI",
    "WORMHOLE_ETH": "ETH", "WORMHOLE_USDT": "USDT",
}

# NAVI protocol — global storage + per-reserve user_state tables
NAVI_RESERVES_TABLE    = "0xe6d4c6610b86ce7735ea754596d71d72d10c7980b5052fc3c8cdf8d09fea9b4b"
NAVI_VSUI_SUPPLY_TABLE = "0xe6457d247b6661b1cac123351998f88f3e724ff6e9ea542127b5dcb3176b3841"
NAVI_USDSUI_BORROW_TABLE = "0xdc9b3a385ea7c6dc443235db7ff9d82188a3e6f5b9af6e765ad9577d39c0af67"
NAVI_VSUI_IDX   = 5
NAVI_USDSUI_IDX = 34

# Aftermath SUI/USDC 80/20 (moved to wallet 0xe64c — staked LP; restaked 2026-06-17)
AFTER_SUIUSDC_STAKE_ID = "0xba9477bb10b80b72833b639495677b8ed90b499a4a5da25a1e7932c011e6ef8b"
AFTER_SUIUSDC_VAULT_ID = "0x0819f52c064eef993370aea4658affd3d73d5bad03b6a44c7bf8ab47eb537d06"
AFTER_SUIUSDC_POOL_ID  = "0xb0cc4ce941a6c6ac0ca6d8e6875ae5d86edbec392c3333d008ca88f377e5e181"

# Aftermath LBTC/lzWBTC 60/40 (wallet 0xe64c — staked LP)
AFTER_STAKE_ID = "0x1e5cf2b65900f491e614c092dfb56ef1ba94553911f06bec562dbaf5876d4a07"
AFTER_POOL_ID  = "0x0d79a676e6f98e14cf02dfe54e8ec5484debda6b31cb804b57be6d634e43bde8"
AFTER_VAULT_ID = "0x7fe07beeb86fec9fc0d80b02ad3fed24e9429612592bec51cb3781ff9578acb4"

# Ember BLUE vault (eBLUE → BLUE conversion)
EBLUE_TYPE     = "0xd84b887935d73110c8cb4b981f4925f83b7a20c41ac572840513422c5da283d6::eblue::EBLUE"
EMBER_VAULT_ID = "0xf8d500875677345b6c0110ee8a48abc7c4974ca697df71eefd229827565168d0"


# ── Static stock holdings (manual — update when portfolio changes) ─────────────
STOCKS_FILE       = Path(__file__).parent / "stocks.json"
HISTORY_FILE      = Path(__file__).parent / "history.json"
INTEREST_FILE     = Path(__file__).parent / "interest_data.json"

STOCKS = [
    {"ticker": "SCHD", "name": "Schwab U.S. Dividend Equity ETF",  "exchange": "ARCA",     "shares": 455.79, "avg_cost":  27.67, "price":  32.63, "market_value": 14872.43, "pct_chg":  17.9, "daily_chg":  0.2, "currency": "USD"},
    {"ticker": "SCHG", "name": "Schwab U.S. Large-Cap Growth ETF", "exchange": "ARCA",     "shares":   5.19, "avg_cost":  29.76, "price":  34.99, "market_value":   181.60, "pct_chg":  17.6, "daily_chg":  1.2, "currency": "USD"},
    {"ticker": "ZETA", "name": "Zeta Global Holdings Corp.",        "exchange": "NYSE",     "shares":  64.96, "avg_cost":  18.91, "price":  20.31, "market_value":  1319.34, "pct_chg":   7.4, "daily_chg":  4.4, "currency": "USD"},
    {"ticker": "ADBE", "name": "Adobe Inc.",                        "exchange": "NasdaqGS", "shares":   1.90, "avg_cost": 309.00, "price": 242.80, "market_value":   461.32, "pct_chg": -21.4, "daily_chg":  1.9, "currency": "USD"},
    {"ticker": "THSI", "name": "iShares SET High Dividend ETF",     "exchange": "SET",      "shares": 3000,   "avg_cost":  10.26, "price":  12.72, "market_value":  1167.69, "pct_chg":  24.0, "daily_chg": -0.5, "currency": "THB"},
    {"ticker": "TDEX", "name": "ThaiDex SET50 Exchange Traded Fund","exchange": "SET",      "shares":  800,   "avg_cost":   7.45, "price":   9.95, "market_value":   243.57, "pct_chg":  33.6, "daily_chg": -0.1, "currency": "THB"},
]


# ── RPC ───────────────────────────────────────────────────────────────────────

_USE_BV_ONLY = False  # flipped to True if rpcpool returns 403

def rpc(method, params):
    global _USE_BV_ONLY
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    if not _USE_BV_ONLY:
        for attempt in range(3):
            r = requests.post(RPC,
                headers={"Content-Type": "application/json"},
                json=payload, timeout=20)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 403:
                _USE_BV_ONLY = True  # IP blocked — use BlockVision for all future calls
                break
            r.raise_for_status()
            return r.json().get("result")

    # BlockVision with retry on rate limit
    if _BV_KEY:
        for attempt in range(5):
            r = requests.post(_BV_RPC,
                headers={"Content-Type": "application/json", "x-api-key": _BV_KEY},
                json=payload, timeout=20)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json().get("result")

def multi_get(ids):
    return rpc("sui_multiGetObjects", [ids, {"showContent": True, "showType": True}])

def find_objects(address, *patterns):
    found, cursor = {p: [] for p in patterns}, None
    while True:
        result = rpc("suix_getOwnedObjects",
            [address, {"options": {"showType": True}}, cursor, 50])
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

def fetch_all_prices() -> dict[str, float]:
    IDS = "sui,walrus-2,cetus-protocol,deep,haedal-staked-sui,bitcoin,aftermath-staked-sui,bluefin,zentry"
    for _ in range(3):
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                params={"ids": IDS, "vs_currencies": "usd"}, timeout=15)
            if r.status_code == 429:
                time.sleep(15); continue
            r.raise_for_status()
            d = r.json()
            btc = d.get("bitcoin", {}).get("usd", 0)
            p = {
                "SUI":   d.get("sui",                {}).get("usd", 0),
                "WAL":   d.get("walrus-2",           {}).get("usd", 0),
                "CETUS": d.get("cetus-protocol",     {}).get("usd", 0),
                "DEEP":  d.get("deep",               {}).get("usd", 0),
                "HASUI": d.get("haedal-staked-sui",  {}).get("usd", 0),
                "BLUE":  d.get("bluefin",            {}).get("usd", 0),
                "ZENT":  d.get("zentry",             {}).get("usd", 0),
                "USDC":  1.0, "USDT": 1.0,
                "WWAL":  d.get("walrus-2",           {}).get("usd", 0),
                "HAWAL": d.get("walrus-2",           {}).get("usd", 0),
                "BTC":   btc, "WBTC": btc, "LBTC": btc, "XBTC": btc,
                "STSUI": d.get("sui", {}).get("usd", 0),
                "AFSUI": d.get("aftermath-staked-sui", {}).get("usd", 0),
            }
            return p
        except Exception:
            time.sleep(5)
    return {}


# ── AMM math ──────────────────────────────────────────────────────────────────

def weighted_amm_amounts(entry_total, w_stable, w_risky, entry_price, current_price):
    K = (entry_total * w_stable) ** w_stable * (entry_total * w_risky / entry_price) ** w_risky
    wr = w_stable / w_risky
    risky_now  = K / ((wr * current_price) ** w_stable)
    stable_now = wr * current_price * risky_now
    pv = entry_total * ((current_price / entry_price) ** w_risky)
    return stable_now, risky_now, pv

def clmm_amounts(entry_total, price_lower, price_upper, current_price):
    sa, sb, s = math.sqrt(price_lower), math.sqrt(price_upper), math.sqrt(current_price)
    if current_price < price_lower:
        L = entry_total / (current_price * (1/sa - 1/sb))
    elif current_price > price_upper:
        L = entry_total / (sb - sa)
    else:
        L = entry_total / (2*s - current_price/sb - sa)
    if price_lower <= current_price <= price_upper:
        base  = L * (1/s - 1/sb)
        quote = L * (s - sa)
    elif current_price <= price_lower:
        base, quote = L * (1/sa - 1/sb), 0.0
    else:
        base, quote = 0.0, L * (sb - sa)
    return base, quote, base * current_price + quote


# ── On-chain: Walrus staking ──────────────────────────────────────────────────

def fetch_walrus(wallet):
    found = find_objects(wallet, "::staked_wal::StakedWal")
    ids   = found["::staked_wal::StakedWal"]
    if not ids: return 0.0, len(ids)
    objs  = multi_get(ids)
    total = sum(int(o["data"]["content"]["fields"]["principal"])
                for o in objs if o.get("data")) / 1e9
    return total, len(ids)


# ── On-chain: xCETUS ─────────────────────────────────────────────────────────

def fetch_xcetus(wallet):
    found = find_objects(wallet, "::xcetus::VeNFT")
    ids   = found["::xcetus::VeNFT"]
    if not ids: return 0.0
    objs  = multi_get(ids)
    return sum(int(o["data"]["content"]["fields"]["xcetus_balance"])
               for o in objs if o.get("data")) / 1e9


# ── On-chain: Scallop supply (receipt tokens) ─────────────────────────────────

def fetch_scallop_supply(wallet, prices):
    balances  = rpc("suix_getAllBalances", [wallet]) or []
    sc_tokens = []
    for b in balances:
        raw = int(b["totalBalance"])
        if raw == 0: continue
        sym = b["coinType"].split("::")[-1].upper()
        if sym.startswith("SCALLOP_") and "REWARD" not in sym:
            sc_tokens.append((sym[len("SCALLOP_"):], raw))
    if not sc_tokens: return []

    dfs    = rpc("suix_getDynamicFields", [SCALLOP_BS_TBL, None, 50]) or {}
    sym_id = {d["name"]["value"]["name"].split("::")[-1].upper(): d["objectId"]
              for d in dfs.get("data", [])}
    ids = [sym_id[SCOIN_ALIAS.get(s, s)] for s, _ in sc_tokens if SCOIN_ALIAS.get(s, s) in sym_id]
    rates = {}
    if ids:
        for o in multi_get(ids):
            if not o.get("data"): continue
            oid = o["data"]["objectId"]
            sym = next((s for s, i in sym_id.items() if i == oid), None)
            if not sym: continue
            bs = o["data"]["content"]["fields"].get("value", {}).get("fields", {})
            supply = int(bs.get("market_coin_supply", 1))
            if supply > 0:
                rates[sym] = (int(bs.get("cash",0)) + int(bs.get("debt",0)) - int(bs.get("revenue",0))) / supply

    rows = []
    for underlying, raw_sc in sc_tokens:
        key   = SCOIN_ALIAS.get(underlying, underlying)   # rate / price / decimals key
        rate  = rates.get(key)
        if rate is None: continue
        dec   = COIN_DEC.get(key, 9)
        amt   = raw_sc * rate / (10 ** dec)
        price = prices.get(key)
        usd   = amt * price if price else None
        if usd and usd >= 0.01:
            rows.append({"sym": SCOIN_DISPLAY.get(underlying, underlying), "amount": amt, "usd": usd})
    return rows


# ── On-chain: Scallop obligation ──────────────────────────────────────────────

def fetch_scallop_obligation(wallet, prices):
    found   = find_objects(wallet, "::obligation::ObligationKey")
    key_ids = found["::obligation::ObligationKey"]
    if not key_ids: return [], []

    keys = multi_get(key_ids)
    ob_ids = [k["data"]["content"]["fields"]["ownership"]["fields"]["of"]
              for k in keys if k.get("data")]
    if not ob_ids: return [], []

    deposits, borrows = [], []
    for obj in multi_get(ob_ids):
        if not obj.get("data"): continue
        f = obj["data"]["content"]["fields"]

        bag_id  = f["balances"]["fields"]["bag"]["fields"]["id"]["id"]
        bag_dfs = rpc("suix_getDynamicFields", [bag_id, None, 50]) or {}
        bal_ids = [d["objectId"] for d in bag_dfs.get("data", [])]
        if bal_ids:
            for bo in multi_get(bal_ids):
                if not bo.get("data"): continue
                bf  = bo["data"]["content"]["fields"]
                sym = bf["name"]["fields"]["name"].split("::")[-1].upper()
                raw = int(bf["value"])
                if raw == 0: continue
                dec = COIN_DEC.get(sym, 9)
                amt = raw / (10 ** dec)
                usd = amt * prices[sym] if sym in prices else None
                if usd and usd >= 0.01:
                    deposits.append({"sym": sym, "amount": amt, "usd": usd})

        debts_id = f["debts"]["fields"]["table"]["fields"]["id"]["id"]
        debt_dfs = rpc("suix_getDynamicFields", [debts_id, None, 50]) or {}
        debt_ids = [d["objectId"] for d in debt_dfs.get("data", [])]
        if debt_ids:
            for do in multi_get(debt_ids):
                if not do.get("data"): continue
                df  = do["data"]["content"]["fields"]
                sym = df["name"]["fields"]["name"].split("::")[-1].upper()
                raw = int(df["value"]["fields"]["amount"])
                if raw == 0: continue
                dec = COIN_DEC.get(sym, 9)
                amt = raw / (10 ** dec)
                usd = amt * prices[sym] if sym in prices else None
                if usd and usd >= 0.01:
                    borrows.append({"sym": sym, "amount": amt, "usd": usd})
    return deposits, borrows


# ── On-chain: Cetus CLMM (wallet_e64c) ───────────────────────────────────────

def decode_i32(bits):
    return bits if bits < 2**31 else bits - 2**32

def _cetus_find_tick(ticks_table_id, target_bits, head_ptrs):
    """Traverse Cetus skip list (O(log n) RPC calls) to find a tick by index bits."""
    def get_node(node_id):
        r = rpc("suix_getDynamicFieldObject",
                [ticks_table_id, {"type": "u64", "value": str(node_id)}])
        node_f = r["data"]["content"]["fields"]["value"]["fields"]
        tick_f = node_f["value"]["fields"]
        return {
            "bits": int(tick_f["index"]["fields"]["bits"]),
            "fgo_a": int(tick_f["fee_growth_outside_a"]),
            "fgo_b": int(tick_f["fee_growth_outside_b"]),
            "rgo":   [int(x) for x in tick_f.get("rewards_growth_outside", [])],
            "nexts": [n["fields"] for n in node_f["nexts"]],
        }

    n_levels    = len(head_ptrs)
    head_nexts  = [h["fields"] for h in head_ptrs]
    current     = {"nexts": head_nexts}

    def fwd(node, level):
        nexts = node["nexts"]
        if level >= len(nexts): return None
        opt = nexts[level]
        return None if opt.get("is_none", True) else int(opt["v"])

    target_signed = decode_i32(target_bits)

    for level in range(n_levels - 1, -1, -1):
        while True:
            nid = fwd(current, level)
            if nid is None: break
            node = get_node(nid)
            if decode_i32(node["bits"]) < target_signed:
                current = node
            else:
                break

    nid = fwd(current, 0)
    if nid is None: return None
    node = get_node(nid)
    return node if node["bits"] == target_bits else None


def fetch_cetus_clmm(wallet, sui_price):
    pos_ids, cursor = [], None
    while True:
        result = rpc("suix_getOwnedObjects",
            [wallet, {"options": {"showType": True}}, cursor, 50])
        for obj in result.get("data", []):
            if obj.get("data", {}).get("type", "") == CETUS_POS_TYPE:
                pos_ids.append(obj["data"]["objectId"])
        if not result.get("hasNextPage"): break
        cursor = result.get("nextCursor")
    if not pos_ids: return []

    positions = multi_get(pos_ids)
    results   = []
    for pos_obj in positions:
        if not pos_obj.get("data"): continue
        pf         = pos_obj["data"]["content"]["fields"]
        pool_id    = pf["pool"]
        liquidity  = int(pf["liquidity"])
        tl_bits    = int(pf["tick_lower_index"]["fields"]["bits"])
        tu_bits    = int(pf["tick_upper_index"]["fields"]["bits"])
        tick_lower = decode_i32(tl_bits)
        tick_upper = decode_i32(tu_bits)
        sym_a = pf["coin_type_a"]["fields"]["name"].split("::")[-1]
        sym_b = pf["coin_type_b"]["fields"]["name"].split("::")[-1]
        pos_id = pf["id"]["id"]

        pool   = rpc("sui_getObject", [pool_id, {"showContent": True}])
        pool_f = pool["data"]["content"]["fields"]
        sqrt_q64     = int(pool_f["current_sqrt_price"])
        current_tick = decode_i32(int(pool_f["current_tick_index"]["fields"]["bits"]))
        fg_a         = int(pool_f["fee_growth_global_a"])
        fg_b         = int(pool_f["fee_growth_global_b"])

        def meta_dec(coin_name):
            ct   = coin_name if coin_name.startswith("0x") else "0x" + coin_name
            meta = rpc("suix_getCoinMetadata", [ct])
            return int(meta["decimals"]) if meta else 9

        dec_a = meta_dec(pf["coin_type_a"]["fields"]["name"])
        dec_b = meta_dec(pf["coin_type_b"]["fields"]["name"])

        sqrt_P       = sqrt_q64 / 2**64
        sqrt_P_lower = math.sqrt(1.0001 ** tick_lower)
        sqrt_P_upper = math.sqrt(1.0001 ** tick_upper)

        if tick_lower <= current_tick <= tick_upper:
            raw_a = liquidity * (sqrt_P_upper - sqrt_P) / (sqrt_P * sqrt_P_upper)
            raw_b = liquidity * (sqrt_P - sqrt_P_lower)
        elif current_tick < tick_lower:
            raw_a = liquidity * (sqrt_P_upper - sqrt_P_lower) / (sqrt_P_lower * sqrt_P_upper)
            raw_b = 0.0
        else:
            raw_a, raw_b = 0.0, liquidity * (sqrt_P_upper - sqrt_P_lower)

        amt_a = raw_a / 10**dec_a
        amt_b = raw_b / 10**dec_b

        dec_adj         = 10**dec_a / 10**dec_b
        price_sui_per_a = (sqrt_P ** 2) * dec_adj
        price_now       = 1 / price_sui_per_a
        p_lower         = 1 / ((1.0001 ** tick_upper) * dec_adj)
        p_upper         = 1 / ((1.0001 ** tick_lower) * dec_adj)

        price_a_usd = 1.0
        price_b_usd = sui_price
        total_usd   = amt_a * price_a_usd + amt_b * price_b_usd
        in_range    = tick_lower <= current_tick <= tick_upper

        # ── Fees (Q64) via PositionInfo + tick traversal ──────────────
        fee_a = fee_b = 0.0
        rewards = []
        try:
            Q64 = 2**64; Q128 = 2**128

            # PositionInfo from pool's position_manager
            pm_table = pool_f["position_manager"]["fields"]["positions"]["fields"]["id"]["id"]
            pi = rpc("suix_getDynamicFieldObject",
                     [pm_table, {"type": "0x2::object::ID", "value": pos_id}])
            pi_f = pi["data"]["content"]["fields"]["value"]["fields"]["value"]["fields"]

            pos_fga   = int(pi_f["fee_growth_inside_a"])
            pos_fgb   = int(pi_f["fee_growth_inside_b"])
            fee_owned_a = int(pi_f["fee_owned_a"])
            fee_owned_b = int(pi_f["fee_owned_b"])

            # Tick data via skip list traversal
            ticks_table = pool_f["tick_manager"]["fields"]["ticks"]["fields"]["id"]["id"]
            head_ptrs   = pool_f["tick_manager"]["fields"]["ticks"]["fields"]["head"]
            lower_tick  = _cetus_find_tick(ticks_table, tl_bits, head_ptrs)
            upper_tick  = _cetus_find_tick(ticks_table, tu_bits, head_ptrs)

            fgo_la = lower_tick["fgo_a"] if lower_tick else 0
            fgo_lb = lower_tick["fgo_b"] if lower_tick else 0
            fgo_ua = upper_tick["fgo_a"] if upper_tick else 0
            fgo_ub = upper_tick["fgo_b"] if upper_tick else 0
            rgo_l  = lower_tick["rgo"]   if lower_tick else []
            rgo_u  = upper_tick["rgo"]   if upper_tick else []

            fb_a = fgo_la if current_tick >= tick_lower else (fg_a - fgo_la) % Q128
            fb_b = fgo_lb if current_tick >= tick_lower else (fg_b - fgo_lb) % Q128
            fa_a = fgo_ua if current_tick <  tick_upper else (fg_a - fgo_ua) % Q128
            fa_b = fgo_ub if current_tick <  tick_upper else (fg_b - fgo_ub) % Q128
            fgi_a = (fg_a - fb_a - fa_a) % Q128
            fgi_b = (fg_b - fb_b - fa_b) % Q128

            fee_a = (((fgi_a - pos_fga) % Q128) * liquidity // Q64 + fee_owned_a) / 10**dec_a
            fee_b = (((fgi_b - pos_fgb) % Q128) * liquidity // Q64 + fee_owned_b) / 10**dec_b

            # Rewards (SUI rewarder)
            rm     = pool_f["rewarder_manager"]["fields"]
            for i, rewarder in enumerate(rm.get("rewarders", [])):
                rf       = rewarder["fields"]
                rgg      = int(rf["growth_global"])
                rsym     = rf["reward_coin"]["fields"]["name"].split("::")[-1]
                pos_ri   = pi_f["rewards"][i]["fields"] if i < len(pi_f.get("rewards", [])) else {}
                amt_owned = int(pos_ri.get("amount_owned", 0))
                last_g    = int(pos_ri.get("growth_inside", 0))
                r_below   = rgo_l[i] if current_tick >= tick_lower and i < len(rgo_l) else (rgg - rgo_l[i]) % Q128 if i < len(rgo_l) else 0
                r_above   = rgo_u[i] if current_tick <  tick_upper and i < len(rgo_u) else (rgg - rgo_u[i]) % Q128 if i < len(rgo_u) else 0
                rgi       = (rgg - r_below - r_above) % Q128
                pending   = ((rgi - last_g) % Q128) * liquidity // Q64 + amt_owned
                if pending > 0:
                    rewards.append({"sym": rsym, "amount": pending / 10**9, "usd": pending / 10**9 * sui_price})
        except Exception:
            pass

        results.append({
            "name":      pf.get("name", f"{sym_b}/{sym_a}"),
            "pool_id":   pool_id,
            "sym_a":     sym_a, "sym_b": sym_b,
            "amt_a":     amt_a, "amt_b": amt_b,
            "usd_a":     amt_a * price_a_usd,
            "usd_b":     amt_b * price_b_usd,
            "total_usd": total_usd,
            "fee_a":     fee_a,  "fee_a_usd": fee_a * price_a_usd,
            "fee_b":     fee_b,  "fee_b_usd": fee_b * price_b_usd,
            "fee_usd":   fee_a * price_a_usd + fee_b * price_b_usd,
            "rewards":   rewards,
            "rewards_usd": sum(r["usd"] for r in rewards),
            "price_now": price_now,
            "p_lower":   p_lower,
            "p_upper":   p_upper,
            "in_range":  in_range,
        })
    return results


# ── Bluefin CLMM (wallet_e64c) ────────────────────────────────────────────────

def fetch_bluefin_clmm(wallet, prices):
    pos_ids, cursor = [], None
    while True:
        result = rpc("suix_getOwnedObjects",
            [wallet, {"options": {"showType": True}}, cursor, 50])
        for obj in result.get("data", []):
            if obj.get("data", {}).get("type", "") == BLUEFIN_POS_TYPE:
                pos_ids.append(obj["data"]["objectId"])
        if not result.get("hasNextPage"): break
        cursor = result.get("nextCursor")
    if not pos_ids: return []

    positions = multi_get(pos_ids)
    results   = []
    for pos_obj in positions:
        if not pos_obj.get("data"): continue
        pf         = pos_obj["data"]["content"]["fields"]
        pool_id    = pf["pool_id"]
        liquidity  = int(pf["liquidity"])
        tick_lower = decode_i32(int(pf["lower_tick"]["fields"]["bits"]))
        tick_upper = decode_i32(int(pf["upper_tick"]["fields"]["bits"]))

        # coin types are plain strings (not nested objects like Cetus)
        ct_a   = pf["coin_type_a"]
        ct_b   = pf["coin_type_b"]
        sym_a  = ct_a.split("::")[-1]
        sym_b  = ct_b.split("::")[-1]

        pool     = rpc("sui_getObject", [pool_id, {"showContent": True}])
        pool_f   = pool["data"]["content"]["fields"]
        sqrt_q64     = int(pool_f["current_sqrt_price"])
        current_tick = decode_i32(int(pool_f["current_tick_index"]["fields"]["bits"]))
        fg_a         = int(pool_f["fee_growth_global_coin_a"])
        fg_b         = int(pool_f["fee_growth_global_coin_b"])
        pool_rwds    = pool_f.get("reward_infos", [])
        tick_table   = pool_f["ticks_manager"]["fields"]["ticks"]["fields"]["id"]["id"]

        def meta_dec(ct):
            full = ct if ct.startswith("0x") else "0x" + ct
            meta = rpc("suix_getCoinMetadata", [full])
            return int(meta["decimals"]) if meta else COIN_DEC.get(ct.split("::")[-1].upper(), 9)

        dec_a = meta_dec(ct_a)
        dec_b = meta_dec(ct_b)

        sqrt_P       = sqrt_q64 / 2**64
        sqrt_P_lower = math.sqrt(1.0001 ** tick_lower)
        sqrt_P_upper = math.sqrt(1.0001 ** tick_upper)

        if tick_lower <= current_tick <= tick_upper:
            raw_a = liquidity * (sqrt_P_upper - sqrt_P) / (sqrt_P * sqrt_P_upper)
            raw_b = liquidity * (sqrt_P - sqrt_P_lower)
        elif current_tick < tick_lower:
            raw_a = liquidity * (sqrt_P_upper - sqrt_P_lower) / (sqrt_P_lower * sqrt_P_upper)
            raw_b = 0.0
        else:
            raw_a, raw_b = 0.0, liquidity * (sqrt_P_upper - sqrt_P_lower)

        amt_a = raw_a / 10**dec_a
        amt_b = raw_b / 10**dec_b

        price_a_usd = prices.get(sym_a, 0)
        price_b_usd = prices.get(sym_b, 0)
        total_usd   = amt_a * price_a_usd + amt_b * price_b_usd

        dec_adj   = 10**dec_a / 10**dec_b
        price_now = (sqrt_P ** 2) * dec_adj
        p_lower   = (1.0001 ** tick_lower) * dec_adj
        p_upper   = (1.0001 ** tick_upper) * dec_adj
        in_range  = tick_lower <= current_tick <= tick_upper

        # Fetch tick data for fee_growth_inside and reward_growths_inside
        i32_type = "0x714a63a0dba6da4f017b42d5d0fb78867f18bcde904868e51d951a5a6f5b7f57::i32::I32"
        tl_bits  = int(pf["lower_tick"]["fields"]["bits"])
        tu_bits  = int(pf["upper_tick"]["fields"]["bits"])
        def get_tick(bits):
            r = rpc("suix_getDynamicFieldObject", [tick_table, {"type": i32_type, "value": {"bits": bits}}])
            f = r["data"]["content"]["fields"]["value"]["fields"]
            return (int(f["fee_growth_outside_a"]), int(f["fee_growth_outside_b"]),
                    [int(x) for x in f.get("reward_growths_outside", [])])
        fgo_la, fgo_lb, rgo_l = get_tick(tl_bits)
        fgo_ua, fgo_ub, rgo_u = get_tick(tu_bits)

        Q128 = 2**128
        fb_a = fgo_la if current_tick >= tick_lower else (fg_a - fgo_la) % Q128
        fb_b = fgo_lb if current_tick >= tick_lower else (fg_b - fgo_lb) % Q128
        fa_a = fgo_ua if current_tick <  tick_upper else (fg_a - fgo_ua) % Q128
        fa_b = fgo_ub if current_tick <  tick_upper else (fg_b - fgo_ub) % Q128
        fgi_a = (fg_a - fb_a - fa_a) % Q128
        fgi_b = (fg_b - fb_b - fa_b) % Q128

        Q64       = 2**64
        fee_a_raw = ((fgi_a - int(pf["fee_growth_coin_a"])) % Q128) * liquidity // Q64 + int(pf.get("token_a_fee", 0))
        fee_b_raw = ((fgi_b - int(pf["fee_growth_coin_b"])) % Q128) * liquidity // Q64 + int(pf.get("token_b_fee", 0))
        fee_a     = fee_a_raw / 10**dec_a
        fee_b     = fee_b_raw / 10**dec_b
        fee_a_usd = fee_a * price_a_usd
        fee_b_usd = fee_b * price_b_usd

        # Protocol rewards (Q64 scaling)
        rewards = []
        for i, ri in enumerate(pf.get("reward_infos", [])):
            if i >= len(pool_rwds): break
            prf         = pool_rwds[i]["fields"]
            rgg         = int(prf["reward_growth_global"])
            rdec        = int(prf["reward_coin_decimals"])
            rsym        = prf["reward_coin_symbol"]
            rprice      = prices.get(rsym.upper(), 0)
            coins_owed  = int(ri["fields"]["coins_owed_reward"])
            last_growth = int(ri["fields"]["reward_growth_inside_last"])
            r_below = rgo_l[i] if current_tick >= tick_lower else (rgg - rgo_l[i]) % Q128
            r_above = rgo_u[i] if current_tick <  tick_upper else (rgg - rgo_u[i]) % Q128
            rgi     = (rgg - r_below - r_above) % Q128
            pending = ((rgi - last_growth) % Q128) * liquidity // Q64 + coins_owed
            amt     = pending / 10**rdec
            if amt > 0:
                rewards.append({"sym": rsym, "amount": amt, "usd": amt * rprice})

        results.append({
            "name":      pf.get("name", f"{sym_a}/{sym_b}"),
            "pool_id":   pool_id,
            "sym_a":     sym_a, "sym_b": sym_b,
            "amt_a":     amt_a, "amt_b": amt_b,
            "usd_a":     amt_a * price_a_usd,
            "usd_b":     amt_b * price_b_usd,
            "total_usd": total_usd,
            "fee_a":     fee_a,     "fee_a_usd": fee_a_usd,
            "fee_b":     fee_b,     "fee_b_usd": fee_b_usd,
            "fee_usd":   fee_a_usd + fee_b_usd,
            "rewards":   rewards,
            "rewards_usd": sum(r["usd"] for r in rewards),
            "price_now": price_now,
            "p_lower":   p_lower,
            "p_upper":   p_upper,
            "in_range":  in_range,
        })
    return results


# ── Aftermath Finance: SUI/USDC 80/20 staked LP ──────────────────────────────

_AFTERMATH_8020_ZERO = {
    "total": 0.0, "usdc_amt": 0.0, "usdc_usd": 0.0,
    "sui_amt": 0.0, "sui_usd": 0.0, "afsui_amt": 0.0, "afsui_usd": 0.0, "lp_frac": 0.0,
}

def fetch_aftermath_sui_usdc(sui_price: float, afsui_price: float) -> dict:
    sp = rpc("sui_getObject", [AFTER_SUIUSDC_STAKE_ID, {"showContent": True}])
    if not sp.get("data"):
        return _AFTERMATH_8020_ZERO
    sf = sp["data"]["content"]["fields"]
    user_lp     = int(sf["balance"])
    base_acc    = int(sf["base_rewards_accumulated"][0])
    base_debt   = int(sf["base_rewards_debt"][0])
    mult_acc    = int(sf["multiplier_rewards_accumulated"][0])
    mult_debt   = int(sf["multiplier_rewards_debt"][0])
    mult_staked = int(sf["multiplier_staked_amount"])

    vt = rpc("sui_getObject", [AFTER_SUIUSDC_VAULT_ID, {"showContent": True}])
    vf = vt["data"]["content"]["fields"]
    acc_per_share = int(vf["total_rewards_accumulated_per_share"][0])

    po = rpc("sui_getObject", [AFTER_SUIUSDC_POOL_ID, {"showContent": True}])
    pf = po["data"]["content"]["fields"]
    lp_supply   = int(pf["lp_supply"]["fields"]["value"])
    norm_bals   = [int(x) for x in pf["normalized_balances"]]
    dec_scalars = [int(x) for x in pf["decimal_scalars"]]
    coin_decs   = pf["coin_decimals"]   # [9, 6] — SUI, USDC

    lp_frac  = user_lp / lp_supply
    sui_raw  = norm_bals[0] / dec_scalars[0]
    usdc_raw = norm_bals[1] / dec_scalars[1]
    sui_amt  = sui_raw  * lp_frac / 10 ** coin_decs[0]
    usdc_amt = usdc_raw * lp_frac / 10 ** coin_decs[1]
    sui_usd  = sui_amt  * sui_price
    usdc_usd = usdc_amt   # USDC = $1

    # Pending afSUI rewards (base + multiplier streams)
    PREC       = 10 ** 18
    base_pend  = max(0, (user_lp     * acc_per_share // PREC) - base_debt) + base_acc
    mult_pend  = max(0, (mult_staked * acc_per_share // PREC) - mult_debt) + mult_acc
    afsui_raw  = base_pend + mult_pend
    afsui_amt  = afsui_raw / 1e9    # afSUI has 9 decimals
    afsui_usd  = afsui_amt * (afsui_price or sui_price)

    return {
        "sui_amt":   sui_amt,   "sui_usd":   sui_usd,
        "usdc_amt":  usdc_amt,  "usdc_usd":  usdc_usd,
        "afsui_amt": afsui_amt, "afsui_usd": afsui_usd,
        "lp_frac":   lp_frac,
        "total":     sui_usd + usdc_usd + afsui_usd,
    }


# ── Aftermath Finance: LBTC/lzWBTC 60/40 staked LP ──────────────────────────

def fetch_aftermath_lbtcwbtc(btc_price: float, deep_price: float) -> dict:
    # Staked position
    sp = rpc("sui_getObject", [AFTER_STAKE_ID, {"showContent": True}])
    sf = sp["data"]["content"]["fields"]
    user_lp     = int(sf["balance"])
    base_debt   = int(sf["base_rewards_debt"][0])
    mult_debt   = int(sf["multiplier_rewards_debt"][0])
    mult_staked = int(sf["multiplier_staked_amount"])

    # Vault — read current accumulator
    vt = rpc("sui_getObject", [AFTER_VAULT_ID, {"showContent": True}])
    vf = vt["data"]["content"]["fields"]
    acc_per_share = int(vf["total_rewards_accumulated_per_share"][0])

    # Pool — read LP supply and coin balances
    po = rpc("sui_getObject", [AFTER_POOL_ID, {"showContent": True}])
    pf = po["data"]["content"]["fields"]
    lp_supply   = int(pf["lp_supply"]["fields"]["value"])
    norm_bals   = [int(x) for x in pf["normalized_balances"]]
    dec_scalars = [int(x) for x in pf["decimal_scalars"]]
    coin_decs   = pf["coin_decimals"]   # [8, 8]

    lp_frac  = user_lp / lp_supply
    wbtc_raw = norm_bals[0] / dec_scalars[0]
    lbtc_raw = norm_bals[1] / dec_scalars[1]
    wbtc_amt = wbtc_raw * lp_frac / 10 ** coin_decs[0]
    lbtc_amt = lbtc_raw * lp_frac / 10 ** coin_decs[1]
    wbtc_usd = wbtc_amt * btc_price
    lbtc_usd = lbtc_amt * btc_price

    # Pending DEEP (base + multiplier streams)
    PREC      = 10 ** 18
    base_pend = (mult_staked * acc_per_share // PREC) - base_debt
    mult_pend = (mult_staked * acc_per_share // PREC) - mult_debt
    deep_raw  = max(0, base_pend + mult_pend)
    deep_amt  = deep_raw / 1e6    # DEEP has 6 decimals
    deep_usd  = deep_amt * deep_price

    return {
        "wbtc_amt": wbtc_amt, "wbtc_usd": wbtc_usd,
        "lbtc_amt": lbtc_amt, "lbtc_usd": lbtc_usd,
        "deep_amt": deep_amt, "deep_usd": deep_usd,
        "lp_frac":  lp_frac,
        "total":    wbtc_usd + lbtc_usd + deep_usd,
    }


# ── Lending rewards (wallet reward coins) ────────────────────────────────────

def fetch_lending_rewards(wallet, prices):
    """Placeholder — lending protocol rewards (NAVX/SEND/SCA) require complex
    protocol-specific incentive math that isn't implemented yet."""
    return {"navi": {"amount": 0, "usd": 0, "sym": "NAVX"},
            "send": {"amount": 0, "usd": 0, "sym": "SEND"},
            "sca":  {"amount": 0, "usd": 0, "sym": "SCA"}}


# ── NAVI (RPC) ───────────────────────────────────────────────────────────────

def fetch_navi(prices) -> dict:
    """Fetch live NAVI vSUI/USDSUI position for wallet 0x954c."""
    def reserve_indices(idx):
        ro = rpc("suix_getDynamicFieldObject", [
            NAVI_RESERVES_TABLE, {"type": "u8", "value": idx}
        ])
        rf = ro["data"]["content"]["fields"]["value"]["fields"]
        return int(rf["current_supply_index"]), int(rf["current_borrow_index"])

    sup_idx, _ = reserve_indices(NAVI_VSUI_IDX)
    _, bor_idx = reserve_indices(NAVI_USDSUI_IDX)

    # vSUI supply balance
    vsui_obj = rpc("suix_getDynamicFieldObject", [
        NAVI_VSUI_SUPPLY_TABLE, {"type": "address", "value": WALLET_954C}
    ])
    vsui_scaled = int(vsui_obj["data"]["content"]["fields"]["value"]) if vsui_obj and vsui_obj.get("data") else 0
    vsui_amt = vsui_scaled * sup_idx / 1e27 / 1e9   # 9 decimals

    # USDSUI borrow balance
    usdsui_obj = rpc("suix_getDynamicFieldObject", [
        NAVI_USDSUI_BORROW_TABLE, {"type": "address", "value": WALLET_954C}
    ])
    usdsui_scaled = int(usdsui_obj["data"]["content"]["fields"]["value"]) if usdsui_obj and usdsui_obj.get("data") else 0
    usdsui_amt = usdsui_scaled * bor_idx / 1e27 / 1e9  # 9 decimals

    vsui_price  = prices.get("vSUI", prices.get("SUI", 1))
    usdsui_price = prices.get("USDSUI", 1.0)
    col_usd     = vsui_amt * vsui_price
    debt_usd    = usdsui_amt * usdsui_price
    vsui_ratio  = prices.get("vSUI", prices.get("SUI", 1)) / max(prices.get("SUI", 1), 1e-9)
    ltv         = debt_usd / col_usd if col_usd > 0 else 0
    # HF = (collateral × liq_threshold) / debt  →  1.0 = liquidation point
    hf          = (col_usd * 0.80) / debt_usd if debt_usd > 0 else 99.0

    return {
        "vsui_amt":  vsui_amt,
        "col_usd":   col_usd,
        "debt":      usdsui_amt,
        "debt_usd":  debt_usd,
        "net":       col_usd - debt_usd,
        "ltv":       ltv,
        "hf":        hf,
        "sui_equiv": vsui_amt * vsui_ratio,
    }


# ── Ember eBLUE (RPC) ─────────────────────────────────────────────────────────

def fetch_ember_eblue(blue_price: float) -> dict:
    """Fetch eBLUE vault position: coins + on-chain exchange rate → BLUE value."""
    # 1. Get all eBLUE coins for wallet
    coins, cursor = [], None
    while True:
        result = rpc("suix_getCoins", [WALLET_954C, EBLUE_TYPE, cursor, 50])
        for c in result.get("data", []):
            coins.append(int(c.get("balance", "0")))
        if not result.get("hasNextPage"):
            break
        cursor = result.get("nextCursor")

    total_eblue_raw = sum(coins)
    if total_eblue_raw == 0:
        return {"eblue_amt": 0, "blue_amt": 0, "blue_usd": 0,
                "rate": 1.0, "yield_pct": 0, "n_objects": 0}

    # 2. Read vault exchange rate
    vault = rpc("sui_getObject", [EMBER_VAULT_ID, {"showContent": True}])
    rate_value = int(vault["data"]["content"]["fields"]["rate"]["fields"]["value"])
    blue_per_eblue = 1e9 / rate_value   # 1 eBLUE = this many BLUE

    eblue_amt = total_eblue_raw / 1e9   # 9 decimals
    blue_amt  = eblue_amt * blue_per_eblue
    blue_usd  = blue_amt * blue_price
    yield_pct = (blue_per_eblue - 1.0) * 100

    return {
        "eblue_amt": eblue_amt,
        "blue_amt":  blue_amt,
        "blue_usd":  blue_usd,
        "rate":      blue_per_eblue,
        "yield_pct": yield_pct,
        "n_objects": len(coins),
    }


# ── Binance (REST API) ────────────────────────────────────────────────────────

def _bn_sign(params: dict) -> str:
    from urllib.parse import urlencode
    return hmac.new(_BN_SEC.encode(), urlencode(params).encode(), hashlib.sha256).hexdigest()

def _bn_ts() -> int:
    return requests.get("https://api.binance.com/api/v3/time", timeout=10).json()["serverTime"]

def fetch_binance(prices: dict) -> dict:
    """Fetch Binance Futures positions + Crypto Loan in one call."""
    if not _BN_KEY or not _BN_SEC:
        return {"futures": [], "loan": None, "futures_margin": 0,
                "futures_pnl": 0, "loan_net": 0, "total": 0}

    hdrs = {"Accept": "application/json", "X-MBX-APIKEY": _BN_KEY}
    ts = _bn_ts()

    # ── Futures account ──────────────────────────────────────────────────
    fp = {"timestamp": ts}
    fp["signature"] = _bn_sign(fp)
    fa = requests.get("https://fapi.binance.com/fapi/v2/account",
                      params=fp, headers=hdrs, timeout=15).json()
    margin_bal = float(fa.get("totalMarginBalance", 0))
    wallet_bal = float(fa.get("totalWalletBalance", 0))
    total_pnl  = float(fa.get("totalUnrealizedProfit", 0))

    # Active positions
    pp = {"timestamp": _bn_ts()}
    pp["signature"] = _bn_sign(pp)
    pr = requests.get("https://fapi.binance.com/fapi/v2/positionRisk",
                      params=pp, headers=hdrs, timeout=15).json()
    futures = []
    if isinstance(pr, list):
        for p in pr:
            amt = float(p.get("positionAmt", 0))
            if amt == 0:
                continue
            sym   = p["symbol"]
            entry = float(p["entryPrice"])
            mark  = float(p["markPrice"])
            pnl   = float(p["unRealizedProfit"])
            lev   = int(p["leverage"])
            side  = "Long" if amt > 0 else "Short"
            notional = abs(amt) * mark
            futures.append({
                "symbol": sym, "side": side, "size": abs(amt),
                "entry": entry, "mark": mark, "pnl": pnl,
                "leverage": lev, "notional": notional,
            })

    # ── Crypto Loan ──────────────────────────────────────────────────────
    lp = {"timestamp": _bn_ts()}
    lp["signature"] = _bn_sign(lp)
    lr = requests.get("https://api.binance.com/sapi/v2/loan/flexible/ongoing/orders",
                      params=lp, headers=hdrs, timeout=15).json()
    loan = None
    loan_net = 0.0
    if lr.get("rows"):
        row = lr["rows"][0]  # primary loan
        col_coin  = row["collateralCoin"]
        col_amt   = float(row["collateralAmount"])
        debt_amt  = float(row["totalDebt"])
        ltv       = float(row["currentLTV"])
        col_price = prices.get(col_coin, 0)
        col_usd   = col_amt * col_price
        loan_net  = col_usd - debt_amt
        loan = {
            "col_coin": col_coin, "col_amt": col_amt,
            "col_usd": col_usd, "col_price": col_price,
            "debt_coin": row["loanCoin"], "debt_amt": debt_amt,
            "ltv": ltv, "net": loan_net,
        }

    total_bn = margin_bal + loan_net

    return {
        "futures": futures, "loan": loan,
        "futures_margin": margin_bal, "futures_wallet": wallet_bal,
        "futures_pnl": total_pnl, "loan_net": loan_net,
        "total": total_bn,
    }


# ── Ethereum (RPC) ────────────────────────────────────────────────────────────

def fetch_eth_stzent(zent_price: float) -> dict:
    """Fetch stZENT ERC20 balance on Ethereum for the given wallet."""
    rpc_url = "https://ethereum-rpc.publicnode.com"
    wallet_eth = os.getenv("WALLET_ETH", "")
    stZENT_contract = "0x996d67AA9b37df96428ad3608cb21352BF1FDB90"
    
    # balanceOf(address)
    data = "0x70a08231" + wallet_eth[2:].zfill(64)
    try:
        res = requests.post(rpc_url, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "eth_call",
            "params": [{"to": stZENT_contract, "data": data}, "latest"]
        }, timeout=10).json()
        
        res_hex = res.get("result", "0x0")
        if res_hex != "0x" and res_hex is not None:
            amt = int(res_hex, 16) / 1e18
        else:
            amt = 0.0
    except Exception:
        amt = 0.0

    return {
        "stzent_amt": amt,
        "zent_usd": amt * zent_price
    }


# ── Suilend (RPC) ─────────────────────────────────────────────────────────────

def fetch_suilend(prices):
    SUILEND_OBL_CAP = "::lending_market::ObligationOwnerCap"
    found   = find_objects(WALLET_954C, SUILEND_OBL_CAP)
    cap_ids = found[SUILEND_OBL_CAP]
    if not cap_ids: return [], [], {}

    caps = multi_get(cap_ids)
    ob_ids = [c["data"]["content"]["fields"]["obligation_id"]
              for c in caps if c.get("data")]
    if not ob_ids: return [], [], {}

    obligations = multi_get(ob_ids)
    deposits, borrows = [], []
    proto = {
        "deposited_usd": 0.0,
        "allowed_borrow_usd": 0.0,
        "unhealthy_borrow_usd": 0.0,
        "borrowed_usd": 0.0,
        "wal_usd": 0.0,
        "steamm_lp": {"usd": 0.0, "wal_amt": 0.0, "usdc_amt": 0.0}
    }
    
    ALIAS = {"SPRING_SUI": "sSUI"}
    
    # Cache for reserves to avoid redundant RPC calls
    lending_markets = {}

    for obj in obligations:
        if not obj.get("data"): continue
        obl = obj["data"]["content"]["fields"]
        lm_id = obl["lending_market_id"]
        
        if lm_id not in lending_markets:
            lm = rpc("sui_getObject", [lm_id, {"showContent": True}])
            if lm and lm.get("data"):
                lending_markets[lm_id] = lm["data"]["content"]["fields"]["reserves"]
            else:
                # Isolated market object not directly fetchable — scan for SteammFi LP only.
                for dep in obl.get("deposits", []):
                    df = dep["fields"]
                    raw_sym = df["coin_type"]["fields"]["name"].split("::")[-1]
                    if "STEAMM_LP_BWAL_BUSDC" not in raw_sym:
                        continue
                    lp_amt = int(df["deposited_ctoken_amount"])
                    pool = rpc("sui_getObject", ["0xe4455aac45acee48f8b69c671c245363faa7380b3dcbe3af0fbe00cc4b68e9eb", {"showContent": True}])
                    if pool and pool.get("data"):
                        pf = pool["data"]["content"]["fields"]
                        total_lp = int(pf["lp_supply"]["fields"]["value"])
                        b_wal  = int(pf["balance_a"]) / 1e9
                        b_usdc = int(pf["balance_b"]) / 1e6
                        if total_lp > 0:
                            share  = lp_amt / total_lp
                            my_wal  = share * b_wal
                            my_usdc = share * b_usdc
                            usd = (my_wal * prices.get("WAL", 0)) + my_usdc
                            proto["steamm_lp"] = {"usd": usd, "wal_amt": my_wal, "usdc_amt": my_usdc}
                            deposits.append({"sym": "[SteammFi LP] WAL/USDC", "amount": lp_amt / 1e9,
                                             "usd": usd, "open_ltv": 0.0, "close_ltv": 0.0})
                continue

        reserves = lending_markets[lm_id]

        def reserve_info(idx):
            res    = reserves[int(idx)]["fields"]
            config = res["config"]["fields"]["element"]["fields"]
            avail  = int(res["available_amount"])
            supply = int(res["ctoken_supply"])
            brw    = res.get("borrowed_amount")
            borrowed = int(brw["fields"]["value"]) if isinstance(brw, dict) else int(brw)
            total_under = avail + borrowed / 1e18
            cbr    = int(res["cumulative_borrow_rate"]["fields"]["value"])
            return {
                "open_ltv":  int(config["open_ltv_pct"]) / 100,
                "close_ltv": int(config["close_ltv_pct"]) / 100,
                "ctoken_rate": total_under / supply if supply > 0 else 1.0,
                "cbr": cbr,
            }

        for dep in obl.get("deposits", []):
            df   = dep["fields"]
            raw_sym = df["coin_type"]["fields"]["name"].split("::")[-1]
            sym  = ALIAS.get(raw_sym, raw_sym)
            if sym.startswith("STEAMM_LP"):
                sym = f"[SteammFi LP] {sym}"

            ri   = reserve_info(df["reserve_array_index"])
            dec  = COIN_DEC.get(raw_sym, 9)
            amt  = int(df["deposited_ctoken_amount"]) * ri["ctoken_rate"] / (10 ** dec)
            price = prices.get(sym, prices.get(raw_sym))
            usd   = amt * price if price else (int(df["market_value"]["fields"]["value"]) / 1e18)

            # Override SteammFi LP with live pool valuation (oracle price is wrong)
            if "STEAMM_LP_BWAL_BUSDC" in raw_sym:
                lp_amt = int(df["deposited_ctoken_amount"])
                pool = rpc("sui_getObject", ["0xe4455aac45acee48f8b69c671c245363faa7380b3dcbe3af0fbe00cc4b68e9eb", {"showContent": True}])
                if pool and pool.get("data"):
                    pf = pool["data"]["content"]["fields"]
                    total_lp = int(pf["lp_supply"]["fields"]["value"])
                    b_wal  = int(pf["balance_a"]) / 1e9
                    b_usdc = int(pf["balance_b"]) / 1e6
                    if total_lp > 0:
                        share   = lp_amt / total_lp
                        my_wal  = share * b_wal
                        my_usdc = share * b_usdc
                        usd = (my_wal * prices.get("WAL", 0)) + my_usdc
                        amt = lp_amt / 1e9
                        proto["steamm_lp"] = {"usd": usd, "wal_amt": my_wal, "usdc_amt": my_usdc}

            if amt > 0 and usd:
                deposits.append({"sym": sym, "amount": amt, "usd": usd,
                                 "open_ltv": ri["open_ltv"], "close_ltv": ri["close_ltv"]})

        for bor in obl.get("borrows", []):
            bf   = bor["fields"]
            raw_sym = bf["coin_type"]["fields"]["name"].split("::")[-1]
            sym  = ALIAS.get(raw_sym, raw_sym)
            ri   = reserve_info(bf["reserve_array_index"])
            user_raw = int(bf["borrowed_amount"]["fields"]["value"])
            user_cbr = int(bf["cumulative_borrow_rate"]["fields"]["value"])
            real     = user_raw / user_cbr * ri["cbr"]
            dec  = COIN_DEC.get(raw_sym, 9)
            amt  = real / 1e18 / (10 ** dec)
            price = prices.get(sym, prices.get(raw_sym))
            usd   = amt * price if price else (int(bf["market_value"]["fields"]["value"]) / 1e18)
            
            if amt > 0.001 and usd:
                borrows.append({"sym": sym, "amount": amt, "usd": usd})

        def dec18(k):
            return int(obl[k]["fields"]["value"]) / 1e18

        proto["deposited_usd"]        += dec18("deposited_value_usd")
        proto["allowed_borrow_usd"]   += dec18("allowed_borrow_value_usd")
        proto["unhealthy_borrow_usd"] += dec18("unhealthy_borrow_value_usd")
        proto["borrowed_usd"]         += dec18("weighted_borrowed_value_usd")

    return deposits, borrows, proto



# ── Stock helpers ─────────────────────────────────────────────────────────────

def load_stocks() -> list:
    """Load stocks from JSON file; return empty list if missing."""
    if not STOCKS_FILE.exists():
        return []
    try:
        return json.loads(STOCKS_FILE.read_text())
    except Exception:
        return []


def save_stocks(stocks: list) -> None:
    """Persist stocks list to JSON file."""
    STOCKS_FILE.write_text(json.dumps(stocks, indent=2))


def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text())

def save_history(history: list) -> None:
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def fetch_stock_prices(stocks: list) -> None:
    """Fetch current prices for all stocks via Yahoo Finance and update in-place."""
    if not stocks:
        return
    # Fetch THB/USD rate once
    thb_usd = 1 / 33.0
    try:
        r = requests.get("https://query2.finance.yahoo.com/v8/finance/chart/THBUSD=X",
            params={"range": "1d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}, timeout=10)
        if r.status_code == 200:
            m = r.json()["chart"]["result"][0]["meta"]
            thb_usd = m.get("regularMarketPrice", thb_usd)
    except Exception:
        pass
    for s in stocks:
        ticker = s["ticker"]
        # Build Yahoo Finance symbol: append .BK for SET stocks
        if "." in ticker:
            sym = ticker
        elif s.get("exchange", "").upper() in ("SET", "THAILAND", "BKK"):
            sym = ticker + ".BK"
        else:
            sym = ticker
        if ticker.upper() == "CASH":
            s["current_price"] = 1.0
            s["price"]         = 1.0
            s["currency"]      = "THB"
            s["market_value"]  = s["shares"] * thb_usd
            s["pct_chg"]       = 0.0
            s["daily_chg"]     = 0.0
            s.setdefault("name", "Cash (THB)")
            s.setdefault("exchange", "THB")
            continue
        try:
            r = requests.get(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval": "1d", "range": "2d"},
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=10,
            )
            data = r.json()
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev  = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            currency = meta.get("currency", "USD")
            s["current_price"] = price
            s["currency"]      = currency
            s["pct_chg"]       = (price - s["avg_cost"]) / s["avg_cost"] * 100 if s["avg_cost"] else 0
            fx = thb_usd if currency == "THB" else 1.0
            s["market_value"]  = s["shares"] * price * fx
            s["daily_chg"]     = (price - prev) / prev * 100 if prev else 0
            # Try to get exchange info from meta
            exch_map = {
                "SET":  "SET",
                "NYQ":  "NYSE",
                "NGM":  "NASDAQ",
                "NMS":  "NASDAQ",
                "PCX":  "NYSE ARCA",
                "ASE":  "AMEX",
                "BTS":  "BATS",
            }
            exch_code = meta.get("exchangeName", "")
            s["exchange"] = exch_map.get(exch_code, exch_code)
            # name from longName or shortName
            s.setdefault("name", meta.get("longName") or meta.get("shortName") or ticker)
        except Exception as e:
            s.setdefault("current_price", 0)
            fallback_fx = thb_usd if s.get("currency", "USD") == "THB" else 1.0
            s.setdefault("market_value", s["shares"] * s.get("avg_cost", 0) * fallback_fx)
            s.setdefault("pct_chg", 0)
            s.setdefault("daily_chg", 0)
            s.setdefault("exchange", "")
            s.setdefault("currency", "USD")


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt(v):
    return f"${v:,.2f}"


# ── LTV / Health Factor bars ──────────────────────────────────────────────────

def _health_bar_html(ltv_bar, hf=None):
    """Combined health bar: HF + LTV in one row, segmented zone bar."""
    cur  = ltv_bar["current"]
    mltv = ltv_bar["max_ltv"]
    liq  = ltv_bar["liq_threshold"]

    if cur >= liq:           ltv_color = "#ef4444"
    elif cur >= mltv:        ltv_color = "#f97316"
    elif cur >= mltv * 0.85: ltv_color = "#f59e0b"
    else:                    ltv_color = "#10b981"

    cur_pct  = min(cur  * 100, 100)
    mltv_pct = min(mltv * 100, 100)
    liq_pct  = min(liq  * 100, 100)
    warn_w   = max(liq_pct - mltv_pct, 0)
    danger_w = max(100 - liq_pct, 0)

    # HF section
    hf_html = ""
    if hf is not None:
        if hf < 1.1:      hf_color = "#ef4444"
        elif hf < 1.3:    hf_color = "#f97316"
        elif hf < 1.5:    hf_color = "#f59e0b"
        else:             hf_color = "#10b981"
        hf_str = f"{hf:.2f}" if hf < 99 else "∞"
        hf_html = (
            f'<div style="display:flex;align-items:baseline;gap:3px">'
            f'<span style="font-size:.96rem;font-weight:800;font-family:monospace;color:{hf_color}">{hf_str}</span>'
            f'<span style="font-size:.62rem;color:#475569">HF</span>'
            f'</div>'
        )

    zones = (
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{mltv_pct:.1f}%;background:#10b98118;border-radius:4px 0 0 4px"></div>'
        f'<div style="position:absolute;left:{mltv_pct:.1f}%;top:0;height:100%;width:{warn_w:.1f}%;background:#f9731618"></div>'
        f'<div style="position:absolute;left:{liq_pct:.1f}%;top:0;height:100%;width:{danger_w:.1f}%;background:#ef444418;border-radius:0 4px 4px 0"></div>'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{cur_pct:.1f}%;background:{ltv_color};opacity:.5;border-radius:4px;transition:width .3s"></div>'
        f'<div style="position:absolute;left:{cur_pct:.1f}%;top:-4px;height:14px;width:2px;background:{ltv_color};border-radius:1px;transform:translateX(-50%)"></div>'
        f'<div style="position:absolute;left:{cur_pct:.1f}%;top:13px;transform:translateX(-50%);font-size:.62rem;font-weight:700;font-family:monospace;color:{ltv_color};white-space:nowrap">{cur:.0%}</div>'
        f'<div class="ltv-tick" data-lbl="{mltv:.0%}" style="left:{mltv_pct:.1f}%"></div>'
        f'<div class="ltv-tick ltv-tick-liq" data-lbl="{liq:.0%}" style="left:{liq_pct:.1f}%"></div>'
    )

    return (
        f'<div class="ltv-wrap">'
        f'<div style="display:flex;align-items:center;margin-bottom:9px">'
        f'{hf_html}'
        f'</div>'
        f'<div class="ltv-track" style="height:7px">{zones}</div>'
        f'</div>'
    )


# ── Position card / modal helpers ─────────────────────────────────────────────

def _build_positions(data, p):
    """Build normalized position list used for cards + modals."""
    a   = data["amm_8020"]
    b   = data["amm_5050"]
    n   = data["navi"]
    sl  = data["suilend"]
    oc  = data["onchain_954c"]
    lrw = data.get("lending_rewards", {})
    positions = []

    # 1. Aftermath 80/20 (only show if position still open)
    if a["total"] > 0:
        positions.append({
            "id": "aftermath", "title": "USDC / SUI  80/20",
            "protocol": "Aftermath", "color": "#f97316",
            "category": "AMM", "badge": "Weighted AMM", "total": a["total"],
            "auto": True,
            "card_rows": [
                ("USDC", f"{a['usdc_amt']:,.2f}", False),
                ("SUI",  f"{a['sui_amt']:,.4f}",  False),
            ],
            "modal_tokens": [
                {"sym": "USDC",  "amount": a["usdc_amt"],  "usd": a["usdc_usd"]},
                {"sym": "SUI",   "amount": a["sui_amt"],   "usd": a["sui_usd"]},
                {"sym": "afSUI", "amount": a["afsui_amt"], "usd": a["afsui_usd"], "note": "pending reward"},
            ],
            "stats": [
                {"label": "LP Share", "value": f"{a['lp_frac']:.2%}",       "color": "#94a3b8"},
                {"label": "Weights",  "value": "80% USDC / 20% SUI",         "color": "#94a3b8"},
                {"label": "Reward",   "value": f"{a['afsui_amt']:.4f} afSUI","color": "#60a5fa"},
            ],
            "range_info": None, "status": None, "status_color": None,
        })

    # 2. SteammFi 50/50 (only show if position still open)
    if b["total"] > 0:
        positions.append({
            "id": "steammfi", "title": "WAL / USDC  50/50",
            "protocol": "SteammFi", "color": "#06b6d4",
            "category": "AMM", "badge": "Constant Product", "total": b["total"],
            "auto": True,
            "card_rows": [
                ("USDC", f"{b['stable']:,.2f}", False),
                ("WAL",  f"{b['risky']:,.4f}",  False),
            ],
            "modal_tokens": [
                {"sym": "USDC", "amount": b["stable"], "usd": b["stable"]},
                {"sym": "WAL",  "amount": b["risky"],  "usd": b["risky"] * p.get("WAL", 0)},
            ],
            "stats": [], "range_info": None, "status": None, "status_color": None,
        })

    # 3. NAVI
    positions.append({
        "id": "navi", "title": "vSUI / USDsui",
        "protocol": "NAVI", "color": "#3b82f6",
        "category": "Lending", "badge": "Lending", "total": n["net"],
        "auto": True,
        "card_rows": [
            ("vSUI",   f"{n['vsui_amt']:,.2f}", False),
            ("USDsui", f"{n['debt']:,.2f}",     True),
        ],
        "modal_tokens": [
            {"sym": "vSUI",   "amount": n["vsui_amt"],  "usd": n["col_usd"]},
            {"sym": "SUI",    "amount": n["sui_equiv"],  "usd": n["sui_equiv"] * p.get("SUI", 1), "dim": True, "note": "equiv"},
            {"sym": "USDsui", "amount": n["debt"],       "usd": n["debt_usd"], "is_debt": True},
        ],
        "stats": (
            [{"label": "NAVX Reward", "value": f"{lrw['navi']['amount']:.2f} (${lrw['navi']['usd']:.2f})", "color": "#60a5fa"}]
            if lrw.get("navi", {}).get("amount", 0) > 0 else []
        ),
        "ltv_bar": {"current": n["ltv"], "max_ltv": 0.75, "liq_threshold": 0.80},
        "hf_bar":  n["hf"],
        "range_info": None, "status": None, "status_color": None,
    })

    # 4. Suilend — exclude SteammFi LP (isolated market, separate position)
    sl_deps_main = [d for d in sl["deposits"] if "SteammFi LP" not in d.get("sym", "")]
    sl_card_rows = [(d["sym"], f"{d['amount']:,.4f}", False) for d in sl_deps_main[:2]]
    sl_card_rows += [(b["sym"], f"{b['amount']:,.2f}", True) for b in sl["borrows"][:1]]
    sl_modal_tokens = []
    _ssui_ratio = p.get("sSUI", p.get("SUI", 1)) / p.get("SUI", 1) if p.get("SUI") else 1.0
    for d in sl_deps_main:
        sl_modal_tokens.append({"sym": d["sym"], "amount": d["amount"], "usd": d["usd"], "note": "supply"})
        if d["sym"] == "sSUI":
            sui_equiv = d["amount"] * _ssui_ratio
            sl_modal_tokens.append({"sym": "SUI", "amount": sui_equiv, "usd": sui_equiv * p.get("SUI", 0), "dim": True, "note": "equiv"})
    for bv in sl["borrows"]:
        sl_modal_tokens.append({"sym": bv["sym"], "amount": bv["amount"], "usd": bv["usd"], "is_debt": True})
    positions.append({
        "id": "suilend", "title": "Multi-collateral",
        "protocol": "Suilend", "color": "#f59e0b",
        "category": "Lending", "badge": "Lending", "total": sl["net"],
        "auto": True,
        "card_rows": sl_card_rows,
        "modal_tokens": sl_modal_tokens,
        "stats": (
            [{"label": "SEND Reward", "value": f"{lrw['send']['amount']:.2f} (${lrw['send']['usd']:.2f})", "color": "#60a5fa"}]
            if lrw.get("send", {}).get("amount", 0) > 0 else []
        ),
        "ltv_bar": {"current": sl["ltv"], "max_ltv": sl["max_ltv"], "liq_threshold": sl["liq_threshold"]},
        "hf_bar":  sl["health_factor"],
        "range_info": None, "status": None, "status_color": None,
    })

    # 5. Walrus staking
    positions.append({
        "id": "walrus", "title": "WAL Staking",
        "protocol": "Walrus", "color": "#14b8a6",
        "category": "Staking", "badge": f"{oc['wal_positions']} positions",
        "auto": True,
        "total": oc["wal_usd"],
        "card_rows": [("WAL", f"{oc['wal_amt']:,.4f}", False)],
        "modal_tokens": [{"sym": "WAL", "amount": oc["wal_amt"], "usd": oc["wal_usd"]}],
        "stats": [], "range_info": None, "status": None, "status_color": None,
    })

    # 6. xCETUS
    positions.append({
        "id": "xcetus", "title": "xCETUS Lock",
        "protocol": "CETUS", "color": "#8b5cf6",
        "category": "Staking", "badge": "Ve-lock",
        "auto": True,
        "total": oc["xcetus_usd"],
        "card_rows": [("xCETUS", f"{oc['xcetus_amt']:,.4f}", False)],
        "modal_tokens": [{"sym": "xCETUS", "amount": oc["xcetus_amt"], "usd": oc["xcetus_usd"]}],
        "stats": [], "range_info": None, "status": None, "status_color": None,
    })

    # 7. Scallop
    sc_modal = []
    if oc["sc_supply"]:
        sc_modal.append({"section": "Supply"})
        for r in oc["sc_supply"]:
            sc_modal.append({"sym": r["sym"], "amount": r["amount"], "usd": r["usd"]})
    if oc["sc_deps"]:
        sc_modal.append({"section": "Collateral"})
        _sui_p = p.get("SUI") or 1.0
        _hasui_ratio = (p.get("HASUI", _sui_p) / _sui_p) if _sui_p else 1.0
        for d in oc["sc_deps"]:
            disp = "haSUI" if d["sym"] == "HASUI" else d["sym"]
            sc_modal.append({"sym": disp, "amount": d["amount"], "usd": d["usd"]})
            if d["sym"] == "HASUI":
                _eq = d["amount"] * _hasui_ratio
                sc_modal.append({"sym": "SUI", "amount": _eq, "usd": _eq * _sui_p, "dim": True, "note": "equiv"})
    if oc["sc_borrs"]:
        sc_modal.append({"section": "Borrows"})
        for bv in oc["sc_borrs"]:
            sc_modal.append({"sym": bv["sym"], "amount": bv["amount"], "usd": bv["usd"], "is_debt": True})
    sc_card_rows = (
        [(r["sym"], f"{r['amount']:,.4f}", False) for r in oc["sc_supply"][:1]] +
        [(("haSUI" if d["sym"]=="HASUI" else d["sym"]), f"{d['amount']:,.4f}", False) for d in oc["sc_deps"][:2]] +
        [(bv["sym"], f"{bv['amount']:,.2f}", True) for bv in oc["sc_borrs"][:1]]
    )
    positions.append({
        "id": "scallop", "title": "Lending",
        "protocol": "Scallop", "color": "#ec4899",
        "category": "Lending", "badge": "Supply + Obligation",
        "auto": True,
        "total": oc["sc_net"],
        "card_rows": sc_card_rows[:4],
        "modal_tokens": sc_modal,
        "stats": (
            [{"label": "SCA Reward", "value": f"{lrw['sca']['amount']:.2f} (${lrw['sca']['usd']:.2f})", "color": "#60a5fa"}]
            if lrw.get("sca", {}).get("amount", 0) > 0 else []
        ),
        "range_info": None, "status": None, "status_color": None,
    })

    # 8. Aftermath LBTC/lzWBTC
    af = data["aftermath"]
    positions.append({
        "id": "aftermath_lbtc", "title": "LBTC / lzWBTC  60/40",
        "protocol": "Aftermath", "color": "#f97316",
        "category": "AMM", "badge": "Weighted AMM", "total": af["total"],
        "auto": True,
        "card_rows": [
            ("lzWBTC", f"{af['wbtc_amt']:.6f}", False),
            ("LBTC",   f"{af['lbtc_amt']:.6f}", False),
        ],
        "modal_tokens": [
            {"sym": "lzWBTC", "amount": af["wbtc_amt"], "usd": af["wbtc_usd"]},
            {"sym": "LBTC",   "amount": af["lbtc_amt"], "usd": af["lbtc_usd"]},
            {"sym": "DEEP",   "amount": af["deep_amt"], "usd": af["deep_usd"], "note": "pending reward"},
        ],
        "stats": [
            {"label": "LP Share",  "value": f"{af['lp_frac']:.2%}",      "color": "#94a3b8"},
            {"label": "Weights",   "value": "60% WBTC / 40% LBTC",       "color": "#94a3b8"},
            {"label": "Reward",    "value": f"{af['deep_amt']:.4f} DEEP", "color": "#60a5fa"},
            {"label": "Lock",      "value": "14d  2× multiplier",         "color": "#94a3b8"},
        ],
        "range_info": None, "status": None, "status_color": None,
    })

    # 9. Cetus CLMM e64c
    for i, pos in enumerate(data["clmm_e64c"]):
        sc2 = "#10b981" if pos["in_range"] else "#ef4444"
        positions.append({
            "id": f"cetus_e64c_{i}",
            "title": f"{pos['sym_b']}/{pos['sym_a']}  CLMM",
            "protocol": "CETUS", "color": "#8b5cf6",
            "category": "AMM", "badge": "Concentrated",
            "auto": True,
            "total": pos["total_usd"],
            "card_rows": [
                (pos["sym_a"], f"{pos['amt_a']:,.4f}", False),
                (pos["sym_b"], f"{pos['amt_b']:,.4f}", False),
            ],
            "modal_tokens": [
                {"sym": pos["sym_a"], "amount": pos["amt_a"], "usd": pos["usd_a"]},
                {"sym": pos["sym_b"], "amount": pos["amt_b"], "usd": pos["usd_b"]},
                *([{"sym": pos["sym_a"], "amount": pos["fee_a"], "usd": pos["fee_a_usd"], "note": "fees earned"}] if pos.get("fee_a", 0) > 0 else []),
                *([{"sym": pos["sym_b"], "amount": pos["fee_b"], "usd": pos["fee_b_usd"], "note": "fees earned"}] if pos.get("fee_b", 0) > 0 else []),
                *([{"sym": r["sym"], "amount": r["amount"], "usd": r["usd"], "note": "rewards"} for r in pos.get("rewards", [])]),
            ],
            "stats": [
                *([ {"label": f"{pos['sym_a']} Fee", "value": f"{pos['fee_a']:.4f}", "color": "#10b981"} ] if pos.get("fee_a", 0) > 0 else []),
                *([ {"label": f"{pos['sym_b']} Fee", "value": f"{pos['fee_b']:.4f}", "color": "#10b981"} ] if pos.get("fee_b", 0) > 0 else []),
                *([ {"label": f"{r['sym']} Reward", "value": f"{r['amount']:.4f}", "color": "#60a5fa"} for r in pos.get("rewards", []) ]),
            ],
            "range_info": f"Range  {pos['p_lower']:.4f} — {pos['p_upper']:.4f}  |  Now {pos['price_now']:.4f}",
            "status": "IN RANGE" if pos["in_range"] else "OUT OF RANGE",
            "status_color": sc2,
        })

    # 9b. Bluefin CLMM e64c
    def _fmt_price(v):
        if v >= 1000: return f"{v:,.2f}"
        if v >= 1:    return f"{v:.4f}"
        return f"{v:.6f}"

    _SYM_DISPLAY = {"XBTC": "BTC"}
    for i, pos in enumerate(data["bluefin_clmm"]):
        sc = "#10b981" if pos["in_range"] else "#ef4444"
        disp_a = _SYM_DISPLAY.get(pos["sym_a"], pos["sym_a"])
        disp_b = _SYM_DISPLAY.get(pos["sym_b"], pos["sym_b"])
        positions.append({
            "id": f"bluefin_e64c_{i}",
            "title": f"{disp_a}/{disp_b}  CLMM",
            "protocol": "Bluefin", "color": "#3b82f6",
            "category": "AMM", "badge": "Concentrated",
            "auto": True,
            "total": pos["total_usd"],
            "card_rows": [
                (disp_a, f"{pos['amt_a']:,.6f}", False),
                (disp_b, f"{pos['amt_b']:,.2f}", False),
            ],
            "modal_tokens": [
                {"sym": disp_a, "amount": pos["amt_a"], "usd": pos["usd_a"]},
                {"sym": disp_b, "amount": pos["amt_b"], "usd": pos["usd_b"]},
                *([{"sym": disp_a, "amount": pos["fee_a"], "usd": pos["fee_a_usd"], "note": "fees earned"}] if pos["fee_a"] > 0 else []),
                *([{"sym": disp_b, "amount": pos["fee_b"], "usd": pos["fee_b_usd"], "note": "fees earned"}] if pos["fee_b"] > 0 else []),
                *([{"sym": r["sym"], "amount": r["amount"], "usd": r["usd"], "note": "rewards"} for r in pos["rewards"]]),
            ],
            "stats": [
                *([ {"label": f"{disp_a} Fee", "value": f"{pos['fee_a']:.6f}", "color": "#10b981"} ] if pos["fee_a"] > 0 else []),
                *([ {"label": f"{disp_b} Fee", "value": f"{pos['fee_b']:.4f}", "color": "#10b981"} ] if pos["fee_b"] > 0 else []),
                *([ {"label": f"{r['sym']} Reward", "value": f"{r['amount']:.4f}", "color": "#60a5fa"} for r in pos["rewards"] ]),
            ],
            "range_info": (
                f"Range  {_fmt_price(pos['p_lower'])} — {_fmt_price(pos['p_upper'])}"
                f"  |  Now {_fmt_price(pos['price_now'])}"
                f"  {disp_b}/{disp_a}"
            ),
            "status": "IN RANGE" if pos["in_range"] else "OUT OF RANGE",
            "status_color": sc,
        })

    # 10. Ember eBLUE (Staking)
    ember = data.get("ember", {})
    if ember.get("blue_usd", 0) > 0:
        positions.append({
            "id": "ember_eblue", "title": "eBLUE Vault",
            "protocol": "Ember", "color": "#6366f1",
            "category": "Staking", "badge": "Yield Vault",
            "auto": True,
            "total": ember["blue_usd"],
            "card_rows": [
                ("eBLUE", f"{ember['eblue_amt']:,.4f}", False),
                ("BLUE",  f"{ember['blue_amt']:,.4f}",  False),
            ],
            "modal_tokens": [
                {"sym": "eBLUE", "amount": ember["eblue_amt"], "usd": ember["blue_usd"]},
                {"sym": "BLUE",  "amount": ember["blue_amt"],  "usd": ember["blue_usd"]},
            ],
            "stats": [
                {"label": "Exchange Rate", "value": f"{ember.get('rate', 1):.6f} BLUE/eBLUE", "color": "#94a3b8"},
                {"label": "Yield",         "value": f"{ember.get('yield_pct', 0):.3f}%",       "color": "#10b981"},
                {"label": "Objects",       "value": str(ember.get("n_objects", 0)),             "color": "#94a3b8"},
            ],
            "range_info": None, "status": None, "status_color": None,
        })

    # 11. stZENT (Staking)
    stzent = data.get("stzent", {})
    if stzent.get("zent_usd", 0) > 0:
        positions.append({
            "id": "stzent", "title": "stZENT Staking",
            "protocol": "Zentry", "color": "#a855f7",
            "category": "Staking", "badge": "ERC-20 Stake",
            "auto": True,
            "total": stzent["zent_usd"],
            "card_rows": [
                ("stZENT", f"{stzent['stzent_amt']:,.4f}", False),
            ],
            "modal_tokens": [
                {"sym": "stZENT", "amount": stzent["stzent_amt"], "usd": stzent["zent_usd"]},
            ],
            "stats": [], "range_info": None, "status": None, "status_color": None,
        })

    # 12. Binance Futures (CEX → Futures)
    bn = data.get("binance", {})
    futures_margin = bn.get("futures_margin", 0)
    if futures_margin > 0:
        future_rows = []
        for f in bn.get("futures", [])[:3]:
            pnl_sign = "+" if f["pnl"] >= 0 else ""
            future_rows.append((f["symbol"], f"{f['side']} {f['size']:,.4f}", False))
        if not future_rows:
            future_rows = [("Margin Balance", f"{futures_margin:,.2f}", False)]
        futures_modal = []
        for f in bn.get("futures", []):
            futures_modal.append({"sym": f["symbol"], "amount": f["size"], "usd": f["notional"], "note": f"{f['side']} {f['leverage']}x"})
        if not futures_modal:
            futures_modal = [{"sym": "USDT", "amount": futures_margin, "usd": futures_margin}]
        positions.append({
            "id": "binance_futures", "title": "Futures Account",
            "protocol": "Binance", "color": "#eab308",
            "category": "Futures", "badge": "Futures",
            "auto": True,
            "total": futures_margin,
            "card_rows": future_rows[:3],
            "modal_tokens": futures_modal,
            "stats": [
                {"label": "Wallet Balance", "value": fmt(bn.get("futures_wallet", 0)), "color": "#94a3b8"},
                {"label": "Unrealized PnL", "value": fmt(bn.get("futures_pnl", 0)),    "color": "#10b981" if bn.get("futures_pnl", 0) >= 0 else "#f87171"},
            ],
            "range_info": None, "status": None, "status_color": None,
        })

    # 13. Binance Loan (Lending)
    loan = bn.get("loan")
    if loan and loan.get("net", 0) != 0:
        positions.append({
            "id": "binance_loan", "title": "Crypto Loan",
            "protocol": "Binance", "color": "#3b82f6",
            "category": "Lending", "badge": "Flex Loan",
            "auto": True,
            "total": loan["net"],
            "card_rows": [
                (loan["col_coin"], f"{loan['col_amt']:,.4f}", False),
                (loan["debt_coin"], f"{loan['debt_amt']:,.2f}", True),
            ],
            "modal_tokens": [
                {"sym": loan["col_coin"],  "amount": loan["col_amt"],  "usd": loan["col_usd"]},
                {"sym": loan["debt_coin"], "amount": loan["debt_amt"], "usd": loan["debt_amt"], "is_debt": True},
            ],
            "stats": [
                {"label": "LTV", "value": f"{loan['ltv']:.2%}", "color": "#f59e0b"},
                {"label": "Net", "value": fmt(loan["net"]),     "color": "#f1f5f9"},
            ],
            "range_info": None, "status": None, "status_color": None,
        })

    return positions


def _pos_card(pos):
    color  = pos["color"]
    status = ""
    if pos.get("status"):
        sc = pos["status_color"]
        status = f'<div class="pc-status" style="color:{sc}">&#9679; {pos["status"]}</div>'
    rows = ""
    for sym, val, is_debt in pos["card_rows"][:3]:
        tc = "#f87171" if is_debt else "#94a3b8"
        sign = "−" if is_debt else ""
        rows += (f'<div class="pc-row">'
                 f'<span class="pc-sym" style="color:{tc}">{sym}</span>'
                 f'<span class="pc-val">{sign}{val}</span></div>')
    ltv_html = _health_bar_html(pos["ltv_bar"], pos.get("hf_bar")) if pos.get("ltv_bar") else ""
    if pos.get("auto"):
        auto_html = '<div class="pc-live">&#9679; LIVE</div>'
    else:
        auto_html = '<div class="pc-live" style="color:#f8717188">&#9679; MANUAL</div>'
    return (
        f'<div class="pos-card" style="border-top:3px solid {color}" onclick="openModal(\'{pos["id"]}\')">'
        f'<div class="pc-header">'
        f'<div class="pc-badges">'
        f'<span class="badge" style="background:{color}22;color:{color}">{pos["protocol"]}</span>'
        f'<span class="badge" style="background:#ffffff11;color:#94a3b8">{pos["badge"]}</span>'
        f'</div><div class="pc-arrow">&#8250;</div></div>'
        f'<div class="pc-title">{pos["title"]}</div>'
        f'{status}'
        f'<div class="pc-tokens">{rows}</div>'
        f'{ltv_html}'
        f'<div class="pc-card-footer">'
        f'<div class="pc-total">{fmt(pos["total"])}</div>'
        f'{auto_html}'
        f'</div>'
        f'</div>'
    )


def _modal_content(pos):
    color = pos["color"]
    range_html = ""
    if pos.get("range_info"):
        sc = pos["status_color"]
        range_html = (
            f'<div class="md-range">'
            f'<div class="md-status" style="color:{sc}">&#9679; {pos["status"]}</div>'
            f'<div class="md-range-info">{pos["range_info"]}</div>'
            f'</div>'
        )
    token_rows = ""
    for t in pos["modal_tokens"]:
        if "section" in t:
            token_rows += f'<tr><td colspan="3" class="mt-section">{t["section"]}</td></tr>'
            continue
        is_debt = t.get("is_debt", False)
        is_dim  = t.get("dim", False)
        sym_col = "#475569" if is_dim else ("#f87171" if is_debt else "#94a3b8")
        num_col = "#475569" if is_dim else ("#f87171" if is_debt else "#e2e8f0")
        sign = "−" if is_debt else ""
        note = f' <span class="mt-note">{t["note"]}</span>' if t.get("note") else ""
        token_rows += (
            f'<tr>'
            f'<td class="mt-sym" style="color:{sym_col}">{t["sym"]}{note}</td>'
            f'<td class="mt-num" style="color:{num_col}">{sign}{t["amount"]:,.4f}</td>'
            f'<td class="mt-usd">{sign}{fmt(t["usd"])}</td>'
            f'</tr>'
        )
    stats_html = ""
    if pos.get("ltv_bar"):
        inner = _health_bar_html(pos["ltv_bar"], pos.get("hf_bar"))
        stats_html = f'<div class="md-ltv">{inner}</div>'
    if pos.get("stats"):
        items = "".join(
            f'<div class="ls-item"><span>{s["label"]}</span>'
            f'<span class="priv" style="color:{s["color"]}">{s["value"]}</span></div>'
            for s in pos["stats"]
        )
        stats_html += f'<div class="md-stats">{items}</div>'
    return (
        f'<div class="md-header">'
        f'<div>'
        f'<div class="md-title">{pos["title"]}</div>'
        f'<div class="md-badges">'
        f'<span class="badge" style="background:{color}22;color:{color}">{pos["protocol"]}</span>'
        f'<span class="badge" style="background:#ffffff11;color:#94a3b8">{pos["badge"]}</span>'
        f'</div></div>'
        f'<button class="md-close" onclick="closeModal()">&#10005;</button>'
        f'</div>'
        f'{range_html}'
        f'<table class="mt-table">'
        f'<thead><tr><th>Token</th><th>Amount</th><th>USD Value</th></tr></thead>'
        f'<tbody>{token_rows}</tbody>'
        f'</table>'
        f'{stats_html}'
        f'<div class="md-footer">{fmt(pos["total"])}</div>'
    )


def _build_token_totals(data, p):
    """Aggregate token amounts across all positions."""
    assets, debts = {}, {}

    sui_p       = p.get("SUI", 1)
    afsui_ratio = p.get("AFSUI", sui_p) / sui_p

    _NORM = {"WBTC": "BTC", "LBTC": "BTC", "XBTC": "BTC", "HAWAL": "WAL", "WWAL": "WAL",
             "USDSUI": "USDC", "USDT": "USDC", "AFSUI": "SUI"}
    _RATIO = {
        "USDSUI": p.get("USDSUI", 1.0),
        "USDT":   p.get("USDT",   1.0),
        "AFSUI":  afsui_ratio,
    }

    def add(d, sym, amount, usd):
        ratio = _RATIO.get(sym, 1.0)
        sym   = _NORM.get(sym, sym)
        if sym not in d:
            d[sym] = {"amount": 0.0, "usd": 0.0}
        d[sym]["amount"] += amount * ratio
        d[sym]["usd"]    += usd

    a8 = data["amm_8020"]
    a5 = data["amm_5050"]
    n  = data["navi"]
    sl = data["suilend"]
    oc = data["onchain_954c"]

    vsui_ratio  = p.get("vSUI",  sui_p) / sui_p
    ssui_ratio  = p.get("sSUI",  sui_p) / sui_p
    hasui_ratio = p.get("HASUI", sui_p) / sui_p

    add(assets, "USDC",  a8["usdc_amt"],  a8["usdc_usd"])
    add(assets, "SUI",   a8["sui_amt"],   a8["sui_usd"])
    add(assets, "AFSUI", a8["afsui_amt"], a8["afsui_usd"])
    add(assets, "USDC", a5["stable"],                    a5["stable"])
    add(assets, "WAL",  a5["risky"],                     a5["risky"] * p.get("WAL", 0))
    add(assets, "SUI",    n["vsui_amt"] * vsui_ratio,   n["col_usd"])
    add(debts,  "USDSUI", n["debt"],                    n["debt_usd"])
    for d in sl["deposits"]:
        if "SteammFi LP" in d["sym"]:
            continue  # underlying WAL/USDC already counted via amm_5050
        if d["sym"] == "sSUI":
            add(assets, "SUI", d["amount"] * ssui_ratio, d["usd"])
        else:
            add(assets, d["sym"], d["amount"], d["usd"])
    for b in sl["borrows"]:
        add(debts, b["sym"], b["amount"], b["usd"])
    add(assets, "WAL",    oc["wal_amt"],    oc["wal_usd"])
    add(assets, "xCETUS", oc["xcetus_amt"], oc["xcetus_usd"])
    for r in oc["sc_supply"]:
        add(assets, r["sym"], r["amount"], r["usd"])
    for d in oc["sc_deps"]:
        if d["sym"] == "HASUI":
            add(assets, "SUI", d["amount"] * hasui_ratio, d["usd"])
        else:
            add(assets, d["sym"], d["amount"], d["usd"])
    for b in oc["sc_borrs"]:
        add(debts, b["sym"], b["amount"], b["usd"])
    af = data["aftermath"]
    add(assets, "BTC",  af["wbtc_amt"] + af["lbtc_amt"], af["wbtc_usd"] + af["lbtc_usd"])
    add(assets, "DEEP", af["deep_amt"], af["deep_usd"])
    for pos in data["clmm_e64c"]:
        add(assets, pos["sym_a"], pos["amt_a"], pos["usd_a"])
        add(assets, pos["sym_b"], pos["amt_b"], pos["usd_b"])
    for pos in data["bluefin_clmm"]:
        add(assets, pos["sym_a"], pos["amt_a"], pos["usd_a"])
        add(assets, pos["sym_b"], pos["amt_b"], pos["usd_b"])

    # Ember eBLUE
    ember = data.get("ember", {})
    if ember.get("blue_amt", 0) > 0:
        add(assets, "BLUE", ember["blue_amt"], ember.get("blue_usd", 0))

    # stZENT
    stzent = data.get("stzent", {})
    if stzent.get("stzent_amt", 0) > 0:
        add(assets, "ZENT", stzent["stzent_amt"], stzent.get("zent_usd", 0))

    # Binance loan collateral / debt
    bn   = data.get("binance", {})
    loan = bn.get("loan")
    if loan:
        add(assets, loan["col_coin"],  loan["col_amt"],  loan["col_usd"])
        add(debts,  loan["debt_coin"], loan["debt_amt"], loan["debt_amt"])

    assets = dict(sorted(assets.items(), key=lambda x: -x[1]["usd"]))
    debts  = dict(sorted(debts.items(),  key=lambda x: -x[1]["usd"]))
    return assets, debts


# ── Stock card builder ────────────────────────────────────────────────────────

def _stock_card(s):
    is_us  = s.get("currency", "USD") == "USD"
    color  = "#6366f1" if is_us else "#f59e0b"
    gain   = s.get("pct_chg", 0)
    gc     = "#10b981" if gain >= 0 else "#f87171"
    gsign  = "+" if gain >= 0 else ""
    daily  = s.get("daily_chg", 0)
    dc     = "#10b981" if daily >= 0 else "#f87171"
    dsign  = "+" if daily >= 0 else ""
    stype  = "Cash" if s["ticker"].upper() == "CASH" else ("ETF" if "ETF" in s.get("name", "") else "Stock")
    csym   = "&#3647;" if not is_us else "$"
    exch   = s.get("exchange") or "—"
    name_esc = s.get("name", s["ticker"]).replace("'", "\\'")
    onclick  = f"openStockEdit('{s['ticker']}',{s['shares']},{s['avg_cost']},'{s.get('currency','USD')}','{name_esc}')"
    return (
        f'<div class="pos-card stock-card" style="border-top:3px solid {color};cursor:pointer" onclick="{onclick}">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
        f'<div>'
        f'<div class="priv" style="font-weight:700;font-size:.95rem;color:#f1f5f9">{s["ticker"]}</div>'
        f'<div style="font-size:.68rem;color:#64748b">{exch} &middot; {stype}</div>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<div class="priv" style="font-size:.82rem;font-weight:600;color:#f1f5f9">${s.get("market_value",0):,.0f}</div>'
        f'<div class="priv" style="font-size:.64rem;color:{gc}">{gsign}{gain:.1f}%</div>'
        f'</div></div>'
        f'<div class="priv" style="font-size:.72rem;color:#94a3b8;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
        f'{s.get("name", s["ticker"])}</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:.72rem">'
        f'<span class="priv" style="color:#64748b">{s["shares"]:,.2f} sh @ {csym}{s["avg_cost"]:,.2f}</span>'
        f'<span class="priv" style="color:{dc}">{dsign}{daily:.1f}%<span style="color:#475569"> 1d</span></span>'
        f'</div>'
        f'<div class="pc-edit-hint" style="font-size:.68rem;color:#4da2ff;font-weight:600;margin-top:4px">&#9998; Edit</div>'
        f'</div>'
    )


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(data):
    p      = data["prices"]
    ts     = data["timestamp"]
    updated_epoch = int(datetime.now().timestamp())
    grand  = data["grand_total"]
    n      = data["navi"]
    sl     = data["suilend"]
    oc     = data["onchain_954c"]
    bn     = data.get("binance", {})
    stocks  = data.get("stocks", [])
    history = data.get("history", [])
    stocks_total = data.get("stocks_total", 0)

    amm_total     = data["amm_total"]
    lending_total = data["lending_total"]
    onchain_total = data["onchain_total"]
    cex_total     = bn.get("futures_margin", 0)
    lending_bn    = bn.get("loan_net", 0)
    crypto_total  = amm_total + lending_total + onchain_total + cex_total

    af = data["aftermath"]

    # Gross / debt totals
    # SteammFi LP is already in amm_5050 — exclude it from Suilend deposits to avoid double-count
    sl_deposits_no_lp = [d for d in sl["deposits"] if "SteammFi LP" not in d.get("sym", "")]
    gross = (
        data["amm_8020"]["total"] + data["amm_5050"]["total"] + data["clmm_e64c_total"] +
        data["bluefin_clmm_total"] +
        af["total"] +
        n["col_usd"] +
        sum(d["usd"] for d in sl_deposits_no_lp) +
        oc["wal_usd"] + oc["xcetus_usd"] +
        sum(r["usd"] for r in oc["sc_supply"]) +
        sum(d["usd"] for d in oc["sc_deps"]) +
        data.get("ember", {}).get("blue_usd", 0) +
        data.get("stzent", {}).get("zent_usd", 0) +
        (bn.get("loan", {}) or {}).get("col_usd", 0) +
        cex_total + stocks_total
    )
    total_debt = (
        n["debt_usd"] +
        sum(b["usd"] for b in sl["borrows"]) +
        sum(b["usd"] for b in oc["sc_borrs"]) +
        ((bn.get("loan", {}) or {}).get("debt_amt", 0))
    )
    net_value = gross - total_debt

    # Build positions + token totals
    positions = _build_positions(data, p)
    tok_assets, tok_debts = _build_token_totals(data, p)

    # Token summary HTML
    def _ts_rows(d):
        rows = ""
        for sym, v in d.items():
            price = v["usd"] / v["amount"] if v["amount"] > 0 else 0
            price_str = f'${price:,.4f}' if price < 100 else f'${price:,.2f}'
            rows += (
                f'<tr><td class="ts-sym">{sym}</td>'
                f'<td class="ts-price">{price_str}</td>'
                f'<td class="ts-num">{v["amount"]:,.4f}</td>'
                f'<td class="ts-usd">{fmt(v["usd"])}</td></tr>'
            )
        return rows

    asset_total_usd = sum(v["usd"] for v in tok_assets.values())
    debt_total_usd  = sum(v["usd"] for v in tok_debts.values())
    net_crypto_usd  = asset_total_usd - debt_total_usd

    # Stock holdings rows
    def _stock_rows():
        rows = ""
        # Cash always sorts to the bottom; other stocks keep their order (stable sort)
        for s in sorted(stocks, key=lambda x: x.get("ticker", "").upper() == "CASH"):
            is_us  = s.get("currency", "USD") == "USD"
            csym   = "$" if is_us else "฿"
            gain   = s.get("pct_chg", 0)
            gc     = "#10b981" if gain >= 0 else "#f87171"
            gsign  = "+" if gain >= 0 else ""
            rows += (
                f'<tr>'
                f'<td class="ts-sym">{s["ticker"]}</td>'
                f'<td class="ts-price">{csym}{s.get("price",0):,.2f}</td>'
                f'<td class="ts-num">{s.get("shares",0):,.2f}<span class="stock-sh"> sh</span></td>'
                f'<td class="ts-usd">{fmt(s.get("market_value",0))}'
                f'<span class="stock-gain" style="color:{gc}">{gsign}{gain:.1f}%</span>'
                f'</td></tr>'
            )
        return rows

    token_summary_html = (
        '<div class="ts-card">'
        '<div class="ts-sections">'

        # ── Crypto assets
        '<div class="ts-section">'
        '<div class="ts-head">Token Holdings</div>'
        '<table class="ts-table">'
        '<thead><tr><th>Token</th><th>Price</th><th>Amount</th><th>USD Value</th></tr></thead>'
        f'<tbody>{_ts_rows(tok_assets)}</tbody>'
        '<tfoot><tr>'
        '<td class="ts-total-lbl" colspan="3">Total Assets</td>'
        f'<td class="ts-total-val">{fmt(asset_total_usd)}</td>'
        '</tr></tfoot>'
        '</table>'
        '</div>'

        # ── Crypto debt
        '<div class="ts-section">'
        '<div class="ts-head debt">Total Debt</div>'
        '<table class="ts-table">'
        '<thead><tr><th>Token</th><th>Price</th><th>Amount</th><th>USD Value</th></tr></thead>'
        f'<tbody>{_ts_rows(tok_debts)}</tbody>'
        '<tfoot><tr>'
        '<td class="ts-total-lbl" colspan="3">Total Debt</td>'
        f'<td class="ts-total-val debt">{fmt(debt_total_usd)}</td>'
        '</tr></tfoot>'
        '</table>'
        '</div>'

        # ── Stock holdings
        + (
        '<div class="ts-section">'
        '<div class="ts-head">Stock Holdings</div>'
        '<table class="ts-table">'
        '<thead><tr><th>Ticker</th><th>Price</th><th>Position</th><th>USD Value</th></tr></thead>'
        f'<tbody>{_stock_rows()}</tbody>'
        '<tfoot><tr>'
        '<td class="ts-total-lbl" colspan="3">Total Stocks</td>'
        f'<td class="ts-total-val">{fmt(stocks_total)}</td>'
        '</tr></tfoot>'
        '</table>'
        '</div>'
        if stocks else ''
        ) +

        # ── Category summary
        '<div class="ts-section">'
        '<div class="ts-head">By Category</div>'
        '<table class="ts-table">'
        '<thead><tr><th>Category</th><th colspan="2"></th><th>Value</th></tr></thead>'
        '<tbody>'
        f'<tr><td class="ts-sym">Crypto (net)</td><td colspan="2"></td><td class="ts-usd">{fmt(net_crypto_usd)}</td></tr>'
        f'<tr><td class="ts-sym">Stocks</td><td colspan="2"></td><td class="ts-usd">{fmt(stocks_total)}</td></tr>'
        '</tbody>'
        '<tfoot><tr>'
        '<td class="ts-total-lbl" colspan="3">Total Portfolio</td>'
        f'<td class="ts-total-val">{fmt(net_crypto_usd + stocks_total)}</td>'
        '</tr></tfoot>'
        '</table>'
        '</div>'

        '</div>'
        '</div>'
    )

    # Chart data
    chart_labels = ["AMM Positions", "Lending", "Staking", "Futures", "Stocks"]
    chart_values = [
        round(amm_total, 2),
        round(lending_total + lending_bn, 2),
        round(onchain_total, 2),
        round(cex_total, 2),
        round(stocks_total, 2),
    ]
    chart_colors = ["#f97316", "#3b82f6", "#10b981", "#eab308", "#6366f1"]

    # Protocol color map — each protocol's own brand color
    _PROTO_COLOR = {
        "Aftermath":  "#62FFD0",
        "SteammFi":   "#1DF2C9",
        "Cetus":      "#1DF2C9",
        "Bluefin":    "#2A5ADA",
        "NAVI":       "#0DC3A4",
        "Suilend":    "#EA4630",
        "Walrus":     "#6800FF",
        "Scallop":    "#2563EB",
        "Ember":      "#60CA9C",
        "Zentry":     "#a855f7",
        "Binance":    "#F0B90B",
        "Stocks":     "#6366f1",
    }
    _proto_agg = {}  # label → (value, color)

    def _padd(label, value, proto_key=None):
        color = _PROTO_COLOR.get(proto_key or label, "#94a3b8")
        _proto_agg[label] = (_proto_agg.get(label, (0, color))[0] + value, color)

    _padd("Aftermath", round(af["total"] + data["amm_8020"]["total"], 2), "Aftermath")
    if data["amm_5050"]["total"] > 0:
        _padd("SteammFi", round(data["amm_5050"]["total"], 2), "SteammFi")
    cetus_total = sum(pos["total_usd"] for pos in data["clmm_e64c"])
    if cetus_total > 0:
        _padd("Cetus", round(cetus_total, 2), "Cetus")
    bluefin_total = sum(pos["total_usd"] for pos in data["bluefin_clmm"])
    if bluefin_total > 0:
        _padd("Bluefin", round(bluefin_total, 2), "Bluefin")
    _padd("NAVI",    round(n["net"], 2),        "NAVI")
    _padd("Suilend", round(sl["net"], 2),       "Suilend")
    _padd("Walrus",  round(oc["wal_usd"], 2),   "Walrus")
    _padd("Cetus",   round(oc["xcetus_usd"], 2),"Cetus")
    _padd("Scallop", round(oc["sc_net"], 2),    "Scallop")
    ember_usd = data.get("ember", {}).get("blue_usd", 0)
    if ember_usd > 0:
        _padd("Ember", round(ember_usd, 2), "Ember")
    stzent_usd = data.get("stzent", {}).get("zent_usd", 0)
    if stzent_usd > 0:
        _padd("Zentry", round(stzent_usd, 2), "Zentry")
    if cex_total > 0:
        _padd("Binance", round(cex_total + (lending_bn or 0), 2), "Binance")
    elif lending_bn != 0:
        _padd("Binance", round(lending_bn, 2), "Binance")
    if stocks_total > 0:
        _padd("Stocks", round(stocks_total, 2), "Stocks")

    proto_sorted = sorted(_proto_agg.items(), key=lambda x: x[1][0], reverse=True)
    proto_labels = [x[0]    for x in proto_sorted]
    proto_values = [x[1][0] for x in proto_sorted]
    proto_colors = [x[1][1] for x in proto_sorted]

    # ── Page 1: allocation bars
    categories = sorted([
        ("AMM Positions", amm_total,                    "#f97316"),
        ("Lending",       lending_total + lending_bn,   "#3b82f6"),
        ("Staking",       onchain_total,                "#10b981"),
        ("Futures",       cex_total,                    "#eab308"),
        ("Stocks",        stocks_total,                 "#6366f1"),
    ], key=lambda x: x[1], reverse=True)
    cat_rows = ""
    for lbl, val, col in categories:
        if val <= 0:
            continue
        w = val / grand * 100 if grand > 0 else 0
        cat_rows += (
            f'<div class="cat-row">'
            f'<div class="cat-info"><span class="cat-lbl">{lbl}</span>'
            f'<span class="cat-val">{fmt(val)}</span></div>'
            f'<div class="cat-bar"><div class="cat-fill" style="width:{w:.1f}%;background:{col}"></div></div>'
            f'</div>'
        )

    # ── Page 1: lending risk cards
    sl_debt_usd  = sum(b["usd"] for b in sl["borrows"])
    sl_col_usd   = sum(d["usd"] for d in sl["deposits"])
    hf           = sl["health_factor"]
    navi_health  = _health_bar_html({"current": n["ltv"],  "max_ltv": 0.75,          "liq_threshold": 0.80}, n["hf"])
    sl_health    = _health_bar_html({"current": sl["ltv"], "max_ltv": sl["max_ltv"], "liq_threshold": sl["liq_threshold"]}, hf)

    risk_cards = (
        f'<div class="risk-card">'
        f'<div class="rh"><span class="badge" style="background:#3b82f622;color:#3b82f6">NAVI</span> Lending Risk</div>'
        f'<div class="ra-row">'
        f'<div class="ra-item"><span class="ra-lbl">Collateral</span><span class="ra-val">{fmt(n["col_usd"])}</span></div>'
        f'<div class="ra-item"><span class="ra-lbl">Debt</span><span class="ra-val" style="color:#f87171">{fmt(n["debt_usd"])}</span></div>'
        f'<div class="ra-item"><span class="ra-lbl">Net</span><span class="ra-val">{fmt(n["net"])}</span></div>'
        f'</div>'
        f'{navi_health}'
        f'</div>'
        f'<div class="risk-card">'
        f'<div class="rh"><span class="badge" style="background:#f59e0b22;color:#f59e0b">Suilend</span> Lending Risk</div>'
        f'<div class="ra-row">'
        f'<div class="ra-item"><span class="ra-lbl">Collateral</span><span class="ra-val">{fmt(sl_col_usd)}</span></div>'
        f'<div class="ra-item"><span class="ra-lbl">Debt</span><span class="ra-val" style="color:#f87171">{fmt(sl_debt_usd)}</span></div>'
        f'<div class="ra-item"><span class="ra-lbl">Net</span><span class="ra-val">{fmt(sl["net"])}</span></div>'
        f'</div>'
        f'{sl_health}'
        f'</div>'
    )

    # ── Page 3: Interest sheet ────────────────────────────────────────────────
    # Load interest data from interest_data.json
    _iraw     = json.loads(INTEREST_FILE.read_text())
    _combined = [(r["label"], r["sort"], r["main"], r["mm"],
                  r.get("yield"), r.get("crypto")) for r in _iraw]

    int_labels   = [d[1] for d in _combined]  # use YYYY-MM-DD sort key, matches page 1 chart
    int_main     = [round(d[2], 2) for d in _combined]
    int_mm       = [round(d[3], 2) for d in _combined]
    int_total    = [round(d[2]+d[3], 2) for d in _combined]
    int_yield    = [d[4] for d in _combined]
    int_port     = [d[5] for d in _combined]

    # Stats
    total_earned   = sum(d[2]+d[3] for d in _combined)
    avg_weekly     = total_earned / len(_combined)
    yield_weeks    = [d for d in _combined if d[4] is not None]
    avg_yield      = sum(d[4] for d in yield_weeks) / len(yield_weeks) if yield_weeks else 0
    best_week      = max(_combined, key=lambda x: x[2]+x[3])
    best_week_earn = best_week[2] + best_week[3]
    cumulative     = total_earned

    # Table rows
    running = 0.0
    int_rows = ""
    for d in _combined:
        lbl, _, main, mm, yld, port = d
        wk = main + mm
        running += wk
        yr = "'25" if "'25" in lbl else "'26"
        yr_col = "#6366f1" if "'25" in lbl else "#f97316"
        yld_str  = f"{yld:.2f}%" if yld is not None else "—"
        port_str = f"${port:,.0f}" if port is not None else "—"
        int_rows += (
            f'<tr>'
            f'<td style="color:#94a3b8;font-size:.78rem">{lbl}</td>'
            f'<td class="priv" style="text-align:right;font-family:monospace;color:#e2e8f0">${main:,.2f}</td>'
            f'<td class="priv" style="text-align:right;font-family:monospace;color:#60a5fa">${mm:,.2f}</td>'
            f'<td class="priv" style="text-align:right;font-family:monospace;font-weight:600;color:#f1f5f9">${wk:,.2f}</td>'
            f'<td class="priv" style="text-align:right;font-family:monospace;color:#64748b">${running:,.2f}</td>'
            f'<td style="text-align:right;font-family:monospace;color:{"#10b981" if yld and yld>=15 else "#f59e0b" if yld else "#475569"}">{yld_str}</td>'
            f'<td class="priv" style="text-align:right;color:#64748b">{port_str}</td>'
            f'</tr>'
        )

    page3 = (
        f'<div class="stats-grid">'
        f'<div class="stat-card"><div class="sc-lbl">Cumulative Earned</div><div class="sc-val">${cumulative:,.2f}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Avg / Week</div><div class="sc-val">${avg_weekly:,.2f}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Avg Annual Yield</div><div class="sc-val no-priv">{avg_yield:.1f}%</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Best Week</div><div class="sc-val">${best_week_earn:,.2f}<div class="sc-lbl" style="margin-top:2px">{best_week[0]}</div></div></div>'
        f'</div>'
        f'<div class="charts-row">'
        f'<div class="chart-card priv-chart"><h3>Weekly Earnings — Main vs MM</h3><canvas id="earn-bar" role="img" aria-label="Bar chart of weekly earnings, main account versus money market"></canvas></div>'
        f'<div class="chart-card"><h3>Annualized Yield %</h3><canvas id="yield-line" role="img" aria-label="Line chart of annualized yield percent over time"></canvas></div>'
        f'</div>'
        f'<div class="ts-card">'
        f'<div class="ts-head" style="margin-bottom:14px">Cashflow — Combined 2025 &amp; 2026 Weekly Breakdown</div>'
        f'<table class="ts-table">'
        f'<thead><tr>'
        f'<th>Week</th><th style="text-align:right">Main</th><th style="text-align:right">MM</th>'
        f'<th style="text-align:right">Total</th><th style="text-align:right">Cumulative</th>'
        f'<th style="text-align:right">Ann. Yield'
        f'<span class="tip-wrap"><span class="tip-icon">i</span>'
        f'<div class="tip-box"><strong>How Ann. Yield is calculated</strong>'
        f'<code>(Weekly ÷ Crypto Portfolio) × 52</code><br><br>'
        f'Weekly = Main + MM cashflow earned that week from DeFi positions.<br><br>'
        f'Divided by the crypto portfolio value, then multiplied by 52 to annualize the rate.'
        f'</div></span>'
        f'</th><th style="text-align:right">Crypto Portfolio</th>'
        f'</tr></thead>'
        f'<tbody>{int_rows}</tbody>'
        f'</table>'
        f'</div>'
    )

    # Interest chart JS
    interest_js = (
        f"const earnCtx = document.getElementById('earn-bar').getContext('2d');\n"
        f"new Chart(earnCtx, {{\n"
        f"  type: 'bar',\n"
        f"  data: {{\n"
        f"    labels: {json.dumps(int_labels)},\n"
        f"    datasets: [\n"
        f"      {{ label: 'Main', data: {json.dumps(int_main)}, backgroundColor: '#f97316', borderRadius: 3, borderWidth: 0 }},\n"
        f"      {{ label: 'MM',   data: {json.dumps(int_mm)},   backgroundColor: '#6366f1', borderRadius: 3, borderWidth: 0 }}\n"
        f"    ]\n"
        f"  }},\n"
        f"  options: {{\n"
        f"    plugins: {{ legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }} }},\n"
        f"    scales: {{\n"
        f"      x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 9 }}, maxRotation: 45 }} }},\n"
        f"      y: {{ stacked: true, grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#94a3b8', callback: v => '$' + v }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n\n"
        f"const yieldCtx = document.getElementById('yield-line').getContext('2d');\n"
        f"new Chart(yieldCtx, {{\n"
        f"  type: 'line',\n"
        f"  data: {{\n"
        f"    labels: {json.dumps([d[0] for d in yield_weeks])},\n"
        f"    datasets: [{{ label: 'Ann. Yield %', data: {json.dumps([d[4] for d in yield_weeks])},\n"
        f"      borderColor: '#10b981', backgroundColor: '#10b98112', borderWidth: 2,\n"
        f"      pointRadius: 3, tension: 0.3, fill: true }}]\n"
        f"  }},\n"
        f"  options: {{\n"
        f"    plugins: {{ legend: {{ display: false }} }},\n"
        f"    scales: {{\n"
        f"      x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 9 }}, maxRotation: 45 }} }},\n"
        f"      y: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#94a3b8', callback: v => v + '%' }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n\n"
    )

    # ── Page 2: card grid grouped by category
    order = [
        ("AMM",     "AMM Positions"),
        ("Lending", "Lending"),
        ("Staking", "Staking"),
        ("Futures", "Futures"),
    ]
    page2_html = ""
    for cat_key, cat_name in order:
        cat_pos = [pos for pos in positions if pos["category"] == cat_key]
        if not cat_pos:
            continue
        page2_html += f'<div class="section-label">{cat_name}</div><div class="card-grid">'
        for pos in cat_pos:
            page2_html += _pos_card(pos)
        page2_html += '</div>'

    # Stocks section
    if stocks:
        page2_html += (
            '<div style="display:flex;align-items:center;justify-content:space-between;margin:28px 0 10px">'
            '<div class="section-label" style="margin:0">Stocks</div>'
            '<button class="add-stock-btn" onclick="openAddStock()">+ Add Stock</button>'
            '</div><div class="card-grid">'
        )
        for s in sorted(stocks, key=lambda x: x.get("ticker", "").upper() == "CASH"):
            page2_html += _stock_card(s)
        page2_html += '</div>'
    else:
        page2_html += (
            '<div style="display:flex;align-items:center;justify-content:space-between;margin:28px 0 10px">'
            '<div class="section-label" style="margin:0">Stocks</div>'
            '<button class="add-stock-btn" onclick="openAddStock()">+ Add Stock</button>'
            '</div>'
            '<div style="color:#475569;font-size:.8rem;padding:12px 0">No stocks tracked yet. Click + Add Stock to get started.</div>'
        )

    # ── Hidden modal content divs
    modals_html = '<div style="display:none">'
    for pos in positions:
        modals_html += f'<div id="modal-{pos["id"]}">{_modal_content(pos)}</div>'
    modals_html += '</div>'

    # ── Static CSS
    CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700;800&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d111b;--surface:#18222b;--surface2:#1e2933;--surface3:#24303e;
  --border:#ffffff0d;--border2:#ffffff18;
  --text:#e8eaf0;--text2:#8892a4;--text3:#6b778c;
  --accent:#4da2ff;--accent2:#6fbcf0;--accent-glow:#4da2ff33;
  --green:#10b981;--red:#f87171;--orange:#f97316;--yellow:#f59e0b;
  --blue:#3b82f6;--purple:#8b5cf6;
  --font-display:'Space Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
body{background:radial-gradient(ellipse 1000px 700px at 50% -10%,#9945ff33,transparent 70%),radial-gradient(ellipse 1000px 900px at 0% 100%,#5eead466,transparent 75%),radial-gradient(ellipse 1000px 900px at 100% 100%,#5eead466,transparent 75%),var(--bg);background-attachment:fixed;color:var(--text);font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;line-height:1.5;-webkit-font-smoothing:antialiased}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#ffffff14;border-radius:99px}

/* ── Nav ── */
.top-nav{display:flex;align-items:flex-start;justify-content:space-between;padding:24px 28px 8px;gap:16px;flex-wrap:wrap;max-width:1440px;margin:0 auto}
.nav-left{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.nav-brand{font-size:1.8rem;font-weight:800;color:var(--text);white-space:nowrap;letter-spacing:.04em;text-transform:uppercase;display:flex;align-items:center;gap:8px;font-family:var(--font-display);cursor:pointer;transition:opacity .15s}
.nav-brand:hover{opacity:.82}
.page-menu{display:flex;gap:4px;flex-wrap:wrap}
.page-menu-item{appearance:none;-webkit-appearance:none;background:none;border:none;font-family:inherit;padding:5px 12px;border-radius:8px;font-size:.8rem;font-weight:500;color:var(--text2);cursor:pointer;transition:background .12s,color .12s;white-space:nowrap}
.page-menu-item:hover{background:var(--surface2);color:var(--text)}
.page-menu-item.active{background:var(--surface2);color:var(--accent);font-weight:600}
.page-menu-item:focus-visible,.nav-refresh-btn:focus-visible,.nav-brand:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nav-right{display:flex;align-items:center;gap:16px}
.nav-ts{font-size:.72rem;color:var(--text2)}
.nav-ts.ts-aging{color:#f59e0b}
.nav-ts.ts-stale{color:#f87171;font-weight:600}
.nav-ts .ts-rel{opacity:.85}
.nav-refresh-btn{padding:7px 12px;border-radius:8px;border:1px solid var(--border2);background:transparent;color:var(--text2);font-size:1rem;line-height:1;cursor:pointer;transition:all .18s;font-family:inherit;display:inline-flex}
.nav-refresh-btn:hover:not(:disabled){background:var(--surface3);color:var(--text);border-color:var(--border2)}
.nav-refresh-btn:disabled{opacity:.7;cursor:not-allowed}
.nav-refresh-btn.spinning{color:var(--accent)}
.nav-refresh-btn.spinning span{display:inline-block;animation:nav-spin 0.9s linear infinite}
.nav-refresh-btn.refresh-error{color:var(--red);border-color:var(--red)}
.nav-refresh-btn#privacy-btn.active{color:var(--accent);border-color:var(--accent)}
@keyframes nav-spin{to{transform:rotate(360deg)}}

/* ── Privacy mode ── */
body.priv-on .sc-val,
body.priv-on .pc-val,
body.priv-on .pc-total,
body.priv-on .cat-val,
body.priv-on .ra-val,
body.priv-on .mt-num,
body.priv-on .mt-usd,
body.priv-on .ts-num,
body.priv-on .ts-price,
body.priv-on .ts-usd,
body.priv-on .ts-total-val,
body.priv-on .pc-sym,
body.priv-on .pc-title,
body.priv-on .ts-sym,
body.priv-on .mt-sym,
body.priv-on .md-title,
body.priv-on .md-footer,
body.priv-on .md-range-info,
body.priv-on .badge,
body.priv-on .priv{filter:blur(6px);user-select:none;transition:filter .2s}
body.priv-on .sc-val.no-priv{filter:none;user-select:auto}
body.priv-on .priv-chart{filter:blur(8px);transition:filter .2s}
body.priv-on .stock-card{pointer-events:none;cursor:default!important}
body.priv-on .stock-card .pc-edit-hint{opacity:.2}
body.priv-on .add-stock-btn{pointer-events:none;opacity:.35;cursor:not-allowed}

/* ── Pages ── */
.page{display:none;padding:28px 28px 48px;max-width:1440px;margin:0 auto}
.page.active{display:block}

/* ── Stats ── */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px}
.stat-card{background:var(--surface);border-radius:14px;padding:20px 22px;border:1px solid var(--border);position:relative;overflow:hidden;transition:border-color .18s}
.stat-card::after{content:'';position:absolute;inset:0;border-radius:14px;background:linear-gradient(135deg,#ffffff04 0%,transparent 60%);pointer-events:none}
.stat-card:hover{border-color:var(--border2)}
.sc-lbl{font-size:.66rem;color:var(--text2);text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.sc-val{font-size:1.3rem;font-weight:800;color:var(--text);margin-top:7px;letter-spacing:-.02em;font-variant-numeric:tabular-nums;font-family:var(--font-display)}
.sc-val.debt{color:var(--red)}

/* ── Chart card ── */
.chart-card{background:var(--surface);border-radius:16px;padding:22px 24px;margin-bottom:24px;border:1px solid var(--border)}
.chart-tabs{display:flex;gap:6px;margin-bottom:20px}
.chart-tab{padding:6px 14px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text3);font-size:.73rem;font-weight:600;cursor:pointer;transition:all .18s;font-family:inherit;letter-spacing:.01em}
.chart-tab:hover:not(.active){border-color:var(--border2);color:var(--text2)}
.chart-tab.active{background:var(--accent-glow);border-color:var(--accent);color:var(--accent2)}
.chart-pane{display:none}.chart-pane.active{display:block}
.hist-legend{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap}
.hl-item{display:inline-flex;align-items:center;gap:8px;font-size:.76rem;font-weight:600;letter-spacing:.01em;color:var(--text2);cursor:pointer;user-select:none;padding:6px 13px;border-radius:999px;border:1px solid var(--border2);background:var(--surface2);transition:background .16s,border-color .16s,color .16s,opacity .16s}
.hl-item:hover{border-color:var(--c)}
.hl-item input{position:absolute;opacity:0;pointer-events:none;width:0;height:0}
.hl-dot{width:11px;height:11px;border-radius:50%;border:2px solid var(--c);background:var(--c);box-shadow:0 0 7px -1px var(--c);transition:all .16s;flex:none}
.hl-item:has(input:checked){color:var(--text);border-color:color-mix(in srgb,var(--c) 50%,transparent);background:color-mix(in srgb,var(--c) 14%,var(--surface2))}
.hl-item:has(input:not(:checked)){opacity:.5}
.hl-item:has(input:not(:checked)) .hl-dot{background:transparent;box-shadow:none}
.hl-item:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:2px}

/* ── Token summary ── */
.ts-card{background:var(--surface);border-radius:16px;padding:22px 24px;margin-bottom:24px;border:1px solid var(--border)}
.ts-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:32px}
@media(max-width:700px){.ts-sections{grid-template-columns:1fr}}
.ts-head{font-size:.65rem;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--border);font-weight:600}
.ts-head.debt{color:var(--red);border-bottom-color:#f8717120}
.ts-table{width:100%;border-collapse:collapse;font-size:.8rem}
.ts-table th{font-size:.6rem;color:var(--text3);text-transform:uppercase;padding-bottom:7px;border-bottom:1px solid var(--border);text-align:left;font-weight:500;letter-spacing:.05em}
.ts-table th:not(:first-child){text-align:right}
.ts-table td{padding:6px 0;border-bottom:1px solid var(--border)}
.ts-table tr:last-of-type td{border-bottom:none}
.ts-sym{color:var(--text2);width:22%;font-weight:500}
.ts-price{text-align:right;font-family:'SF Mono',ui-monospace,monospace;color:var(--text3);width:22%;font-size:.77rem}
.ts-num{text-align:right;font-family:'SF Mono',ui-monospace,monospace;color:var(--text);width:30%;font-size:.77rem}
.ts-usd{text-align:right;color:var(--text3);width:26%;font-size:.77rem}
.ts-total-lbl{color:var(--text3);font-size:.65rem;text-transform:uppercase;letter-spacing:.05em;padding-top:10px;border-top:1px solid var(--border2);font-weight:500}
.ts-total-val{text-align:right;font-weight:700;color:var(--text);font-family:'SF Mono',ui-monospace,monospace;font-size:.9rem;padding-top:10px;border-top:1px solid var(--border2)}
.ts-total-val.debt{color:var(--red)}

/* ── Risk cards ── */
.risk-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}
@media(max-width:640px){.risk-row{grid-template-columns:1fr}}
.risk-card{background:var(--surface);border-radius:16px;padding:22px 24px;border:1px solid var(--border)}
.rh{font-size:.8rem;font-weight:700;color:var(--text);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.risk-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.rs-lbl{font-size:.62rem;color:var(--text3);text-transform:uppercase;margin-bottom:3px;font-weight:500;letter-spacing:.05em}
.rs-val{font-size:.83rem;font-weight:600;color:var(--text2);font-family:'SF Mono',ui-monospace,monospace}

/* ── Section label ── */
.section-label{font-size:.65rem;color:var(--text3);text-transform:uppercase;letter-spacing:.1em;margin:32px 0 14px;font-weight:600;display:flex;align-items:center;gap:10px}
.section-label::after{content:'';flex:1;height:1px;background:var(--border)}

/* ── Position cards ── */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-bottom:8px}
.pos-card{background:var(--surface);border-radius:14px;padding:18px 20px;cursor:pointer;transition:transform .18s,box-shadow .18s,border-color .18s,background .18s;user-select:none;display:flex;flex-direction:column;border:1px solid var(--border);position:relative;overflow:hidden}
.pos-card::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,#ffffff03 0%,transparent 50%);pointer-events:none;border-radius:14px}
.pos-card:hover{transform:translateY(-3px);box-shadow:0 12px 40px #00000060,0 0 0 1px var(--border2);background:var(--surface2);border-color:var(--border2)}
.pc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.pc-badges{display:flex;gap:5px;flex-wrap:wrap}
.pc-arrow{color:var(--border2);font-size:1.1rem;font-weight:700;transition:all .18s;opacity:.6}
.pos-card:hover .pc-arrow{color:var(--text2);opacity:1;transform:translateX(2px)}
.badge{font-size:.64rem;padding:3px 9px;border-radius:999px;font-weight:600;letter-spacing:.02em}
.pc-title{font-size:.9rem;font-weight:700;color:var(--text);margin-bottom:6px;letter-spacing:-.01em}
.pc-status{font-size:.67rem;font-weight:700;margin-bottom:7px;letter-spacing:.02em}
.pc-tokens{margin-bottom:12px}
.pc-row{display:flex;justify-content:space-between;padding:3px 0;font-size:.77rem}
.pc-sym{color:var(--text2)}
.pc-val{font-family:'SF Mono',ui-monospace,monospace;color:var(--text);font-size:.77rem}
.pc-card-footer{display:flex;align-items:center;justify-content:space-between;padding-top:12px;border-top:1px solid var(--border);margin-top:auto}
.pc-total{font-size:1rem;font-weight:800;color:var(--text);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.pc-live{font-size:.6rem;font-weight:700;letter-spacing:.06em;color:#10b98160;text-transform:uppercase}
.ltv-wrap{padding:10px 0 28px}
.ltv-cur-row{display:flex;align-items:baseline;gap:2px;margin-bottom:8px}
.ltv-cur-val{font-size:.82rem;font-weight:700;font-family:'SF Mono',ui-monospace,monospace}
.ltv-cur-lbl{font-size:.65rem;color:var(--text3)}
.ltv-track{position:relative;height:6px;background:#ffffff0e;border-radius:3px}
.ltv-fill{position:absolute;left:0;top:0;height:100%;border-radius:3px;transition:width .3s}
.ltv-tick{position:absolute;top:-4px;width:2px;height:14px;background:var(--text3);border-radius:1px}
.ltv-tick::after{content:attr(data-lbl);position:absolute;top:17px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:.6rem;color:var(--text3);letter-spacing:.02em}
.ltv-tick-liq{background:var(--red)}
.ltv-tick-liq::after{color:var(--red)}
.md-ltv{padding:4px 22px 8px}
.ra-row{display:flex;gap:16px;margin:8px 0 2px;flex-wrap:wrap}
.ra-item{display:flex;flex-direction:column;gap:2px}
.ra-lbl{font-size:.6rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:500}
.ra-val{font-size:.82rem;font-weight:600;color:var(--text);font-family:'SF Mono',ui-monospace,monospace}

/* ── Modal ── */
.modal-ov{position:fixed;inset:0;background:rgba(2,4,12,.82);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .22s;z-index:999;padding:16px;backdrop-filter:blur(8px)}
.modal-ov.open{opacity:1;pointer-events:all}
.modal-box{background:var(--surface);border-radius:18px;width:100%;max-width:560px;max-height:92vh;overflow-y:auto;transform:translateY(10px) scale(.98);transition:transform .22s;border:1px solid var(--border2);box-shadow:0 24px 80px #00000099}
.modal-ov.open .modal-box{transform:translateY(0) scale(1)}
.md-header{display:flex;align-items:flex-start;justify-content:space-between;padding:22px 22px 14px}
.md-title{font-size:1rem;font-weight:700;color:var(--text);margin-bottom:7px;letter-spacing:-.01em}
.md-badges{display:flex;gap:6px}
.md-close,.modal-close{background:none;border:none;color:var(--text3);font-size:1rem;cursor:pointer;padding:4px;line-height:1;transition:color .15s;flex-shrink:0;border-radius:6px}
.md-close:hover,.modal-close:hover{color:var(--text);background:var(--border)}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:22px 22px 14px;border-bottom:1px solid var(--border)}
.md-range{padding:0 22px 14px;border-bottom:1px solid var(--border);margin-bottom:4px}
.md-status{font-size:.7rem;font-weight:700;margin-bottom:4px;letter-spacing:.03em}
.md-range-info{font-size:.69rem;color:var(--text3);font-family:'SF Mono',ui-monospace,monospace}
.mt-table{width:calc(100% - 44px);margin:10px 22px 0;border-collapse:collapse;font-size:.81rem}
.mt-table th{text-align:left;font-size:.6rem;color:var(--text3);text-transform:uppercase;padding-bottom:7px;border-bottom:1px solid var(--border);font-weight:500;letter-spacing:.05em}
.mt-table th:not(:first-child){text-align:right}
.mt-table td{padding:7px 0;border-bottom:1px solid var(--border)}
.mt-table tr:last-of-type td{border-bottom:none}
.mt-sym{color:var(--text2);width:42%;font-weight:500}
.mt-num{text-align:right;font-family:'SF Mono',ui-monospace,monospace;width:30%}
.mt-usd{text-align:right;color:var(--text3);width:28%;font-family:'SF Mono',ui-monospace,monospace;font-size:.76rem}
.mt-note{font-size:.6rem;color:var(--text3);font-style:italic;margin-left:4px}
.mt-section{font-size:.6rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;padding:12px 0 3px;font-weight:600}
.md-stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 22px 0;padding:14px;background:var(--surface3);border-radius:12px;border:1px solid var(--border)}
.ls-item{display:flex;flex-direction:column;gap:4px}
.ls-item span:first-child{font-size:.6rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:500}
.ls-item span:last-child{font-size:.82rem;font-weight:600;font-family:'SF Mono',ui-monospace,monospace}
.md-footer{text-align:right;font-size:1.1rem;font-weight:800;color:var(--text);font-family:var(--font-display);padding:16px 22px 22px;border-top:1px solid var(--border);margin-top:14px;letter-spacing:-.02em}

/* ── Tooltip ── */
.tip-wrap{position:relative;display:inline-block;cursor:help}
.tip-icon{font-size:.65rem;color:var(--text3);margin-left:3px;vertical-align:middle;border:1px solid var(--text3);border-radius:50%;padding:0 3px;line-height:1.3;opacity:.7}
.tip-box{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:var(--surface3);border:1px solid var(--border2);border-radius:10px;padding:11px 14px;width:240px;font-size:.71rem;color:var(--text2);line-height:1.6;z-index:99;white-space:normal;text-align:left;box-shadow:0 10px 30px #00000066}
.tip-box strong{color:var(--text);display:block;margin-bottom:5px;font-size:.74rem}
.tip-box code{color:#60a5fa;font-family:'SF Mono',ui-monospace,monospace;font-size:.71rem}
.tip-wrap:hover .tip-box{display:block}

/* ── Stock modals ── */
.add-stock-btn{padding:6px 14px;border-radius:8px;border:1px solid var(--accent);background:var(--accent-glow);color:var(--accent2);font-size:.71rem;font-weight:600;cursor:pointer;transition:all .18s;font-family:inherit}
.add-stock-btn:hover{background:#6366f133;box-shadow:0 0 16px var(--accent-glow)}
.se-field{display:flex;flex-direction:column;gap:5px;margin-bottom:14px;padding:0 22px}
.se-lbl{font-size:.65rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;font-weight:500}
.se-input{background:var(--bg);border:1px solid var(--border2);border-radius:10px;color:var(--text);font-size:.93rem;padding:10px 13px;width:100%;outline:none;font-family:'SF Mono',ui-monospace,monospace;appearance:none;transition:border-color .18s,box-shadow .18s}
.se-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.se-hint{font-size:.62rem;color:var(--text3);margin-top:4px}
.se-save{margin:6px 22px 22px;width:calc(100% - 44px);padding:11px;border-radius:10px;border:none;background:linear-gradient(135deg,#4da2ff,#6fbcf0);color:#fff;font-size:.85rem;font-weight:700;cursor:pointer;transition:all .18s;display:block;letter-spacing:.01em;font-family:inherit;box-shadow:0 4px 16px #4da2ff40}
.se-save:hover:not(:disabled){opacity:.9;box-shadow:0 6px 24px #4da2ff55;transform:translateY(-1px)}
.se-save:disabled{opacity:.4;cursor:not-allowed;box-shadow:none;transform:none}

/* ── Allocation bars (unused but keep for compat) ── */
.alloc-card{background:var(--surface);border-radius:16px;padding:22px 24px;margin-bottom:24px;border:1px solid var(--border)}
.alloc-card h3{font-size:.65rem;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin-bottom:16px;font-weight:600}
.cat-row{margin-bottom:14px}.cat-info{display:flex;justify-content:space-between;margin-bottom:5px}
.cat-lbl{font-size:.82rem;color:var(--text2)}.cat-val{font-size:.82rem;font-weight:600;color:var(--text);font-family:monospace}
.cat-bar{height:5px;border-radius:3px;background:#ffffff0a;overflow:hidden}.cat-fill{height:100%;border-radius:3px;transition:width .4s}

/* ── Overview / Agents nested sections ── */
.overview-subnav,.agent-subnav{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 22px;padding:7px;background:var(--surface);border:1px solid var(--border);border-radius:16px;width:max-content;max-width:100%}
.overview-subtab,.agent-subtab{appearance:none;-webkit-appearance:none;border:none;background:transparent;color:var(--text2);font-family:inherit;font-size:.82rem;font-weight:650;padding:8px 14px;border-radius:11px;cursor:pointer;transition:background .15s,color .15s,box-shadow .15s;white-space:nowrap}
.overview-subtab:hover,.agent-subtab:hover{background:var(--surface2);color:var(--text)}
.overview-subtab.active,.agent-subtab.active{background:linear-gradient(135deg,#4da2ff22,#bc7def22);color:var(--accent);box-shadow:inset 0 0 0 1px var(--border2)}
.overview-panel,.agent-panel{display:none}
.overview-panel.active,.agent-panel.active{display:block}
.agent-graph-img{display:block;width:100%;height:auto;border-radius:16px;border:1px solid var(--border);background:var(--surface2);margin-top:14px}
.bt-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:14px 0 14px}
.bt-field{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:11px 12px}
.bt-field label{display:block;font-size:.62rem;text-transform:uppercase;letter-spacing:.055em;color:var(--text3);margin-bottom:7px;font-weight:700}
.bt-field input,.bt-field select{width:100%;background:var(--bg);border:1px solid var(--border2);border-radius:9px;color:var(--text);padding:8px 9px;font-family:'SF Mono',ui-monospace,monospace;font-size:.82rem;outline:none}
.bt-field input:focus,.bt-field select:focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-glow)}
.bt-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:10px 0 14px}
.bt-metric{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:11px 12px}
.bt-metric span:first-child{display:block;font-size:.6rem;text-transform:uppercase;letter-spacing:.055em;color:var(--text3);margin-bottom:5px}
.bt-metric span:last-child{font-size:.9rem;color:var(--text);font-weight:750;font-family:'SF Mono',ui-monospace,monospace}
.bt-chart-wrap{height:420px;background:var(--surface2);border:1px solid var(--border);border-radius:16px;padding:14px;margin-top:12px}
.bt-toggles{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.bt-toggle{display:inline-flex;align-items:center;gap:7px;background:var(--surface2);border:1px solid var(--border);border-radius:999px;color:var(--text2);font-size:.72rem;padding:7px 10px;cursor:pointer;user-select:none}
.bt-toggle input{accent-color:#4da2ff}

/* ── Phone fit / safe-area polish ── */
html{width:100%;max-width:100%;overflow-x:hidden}
body{width:100%;max-width:100%;overflow-x:hidden}
.charts-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px;margin-bottom:24px}
.chart-card h3,.ts-card h3{font-size:1.05rem;line-height:1.25;margin-bottom:12px;color:var(--text);letter-spacing:-.02em}
.chart-card canvas{display:block;max-width:100%}
@media(max-width:700px){
  body{background-size:auto;background-position:center top,0 100%,100% 100%}
  .top-nav{width:100%;max-width:100%;padding:calc(18px + env(safe-area-inset-top,0px)) max(16px,env(safe-area-inset-right,0px)) 10px max(16px,env(safe-area-inset-left,0px));gap:14px;display:block}
  .nav-left{display:block;width:100%}
  .nav-brand{font-size:clamp(1.72rem,7.2vw,2.05rem);line-height:1.05;margin-bottom:18px;white-space:normal;letter-spacing:.035em}
  .page-menu{display:grid;grid-template-columns:repeat(3,max-content);justify-content:start;column-gap:7px;row-gap:10px;width:100%}
  .page-menu-item{font-size:.86rem;padding:6px 12px;border-radius:9px}
  .nav-right{width:100%;justify-content:flex-start;gap:16px;margin-top:22px}
  .nav-ts{font-size:.76rem;min-width:112px}
  .nav-refresh-btn{width:44px;height:40px;align-items:center;justify-content:center;border-radius:11px;padding:0}
  .page{width:100%;max-width:100%;padding:28px max(16px,env(safe-area-inset-right,0px)) 44px max(16px,env(safe-area-inset-left,0px));margin:0}
  .stats-grid{grid-template-columns:1fr;gap:16px;margin-bottom:34px}
  .stat-card{width:100%;min-height:118px;border-radius:16px;padding:24px 28px;display:flex;flex-direction:column;justify-content:center}
  .sc-lbl{font-size:.73rem;letter-spacing:.1em}
  .sc-val{font-size:1.52rem;margin-top:9px}
  .charts-row{grid-template-columns:1fr;gap:24px;margin-bottom:28px;width:100%}
  .chart-card,.ts-card,.risk-card,.alloc-card{width:100%;border-radius:16px;padding:22px 24px;margin-bottom:24px}
  .chart-card h3{font-size:1.38rem;line-height:1.18;margin-bottom:14px;letter-spacing:-.04em}
  .chart-card>canvas{width:100%!important;height:250px!important}
  #earn-bar{height:260px!important}
  .chart-tabs{overflow-x:auto;padding-bottom:4px;scrollbar-width:none}
  .chart-tabs::-webkit-scrollbar{display:none}
  .ts-card{overflow-x:hidden}
  .ts-sections{gap:30px}
  .ts-table{width:100%;min-width:0;table-layout:fixed;font-size:clamp(.62rem,2.25vw,.72rem)}
  .ts-table th{font-size:clamp(.48rem,1.8vw,.56rem);letter-spacing:.035em;padding-bottom:6px}
  .ts-table td{padding:6px 0;vertical-align:middle}
  .ts-sym{width:18%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ts-price{width:25%;font-size:clamp(.58rem,2.15vw,.68rem)}
  .ts-num{width:28%;font-size:clamp(.58rem,2.15vw,.68rem)}
  .ts-usd{width:29%;font-size:clamp(.58rem,2.15vw,.68rem)}
  .ts-total-lbl{font-size:.58rem}
  .ts-total-val{font-size:.78rem}
  .cashflow-panel .ts-table th:nth-child(2),
  .cashflow-panel .ts-table td:nth-child(2),
  .cashflow-panel .ts-table th:nth-child(3),
  .cashflow-panel .ts-table td:nth-child(3){display:none}
  .cashflow-panel .ts-table{font-size:clamp(.58rem,2.05vw,.68rem)}
  .cashflow-panel .ts-table th{font-size:clamp(.44rem,1.62vw,.52rem);line-height:1.15}
  .overview-subnav,.agent-subnav{width:100%;display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:18px}
  .overview-subtab,.agent-subtab{font-size:.78rem;padding:8px 6px}
  .bt-controls{grid-template-columns:repeat(2,1fr)}
  .bt-chart-wrap{height:360px;padding:10px}
  .card-grid{grid-template-columns:1fr;gap:14px}
  .pos-card{width:100%;border-radius:16px;padding:20px 22px}
  .modal-ov{padding:max(12px,env(safe-area-inset-top,0px)) max(12px,env(safe-area-inset-right,0px)) max(12px,env(safe-area-inset-bottom,0px)) max(12px,env(safe-area-inset-left,0px))}
}
@media(max-width:380px){
  .top-nav{padding-left:12px;padding-right:12px}
  .page{padding-left:12px;padding-right:12px}
  .page-menu{grid-template-columns:repeat(3,max-content)}
  .stat-card,.chart-card,.ts-card,.risk-card,.alloc-card{padding-left:18px;padding-right:18px}
  .chart-card h3{font-size:1.18rem}
}
"""

    # ── Static JS
    JS = """
const PAGES = ['market', 'overview', 'agents'];
const OVERVIEW_TABS = ['summary', 'cashflow', 'positions'];
const AGENT_TABS = ['overview', 'lp', 'usdc'];
function selectAgentTab(tab, pushHash = true) {
  if (!AGENT_TABS.includes(tab)) tab = 'overview';
  document.querySelectorAll('.agent-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('agents-' + tab);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('.agent-subtab').forEach(b => {
    const on = b.dataset.agentTab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (pushHash) {
    const next = tab === 'overview' ? 'agents' : 'agents-' + tab;
    if (location.hash.replace(/^#/, '') !== next) location.hash = next;
  }
  if (tab === 'lp') setTimeout(renderLpBacktest, 60);
}
function selectOverviewTab(tab, pushHash = true) {
  if (!OVERVIEW_TABS.includes(tab)) tab = 'summary';
  document.querySelectorAll('.overview-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('overview-' + tab);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('.overview-subtab').forEach(b => {
    const on = b.dataset.overviewTab === tab;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (pushHash) {
    const next = tab === 'summary' ? 'overview' : 'overview-' + tab;
    if (location.hash.replace(/^#/, '') !== next) location.hash = next;
  }
  setTimeout(() => window.dispatchEvent(new Event('resize')), 80);
}
function showPage(name, overviewTab, agentTab) {
  if (name === 'interest') { name = 'overview'; overviewTab = 'cashflow'; }
  if (name === 'positions') { name = 'overview'; overviewTab = 'positions'; }
  if (name === 'agents-backtest') { name = 'agents'; agentTab = 'lp'; }
  if (name === 'agents-lp') { name = 'agents'; agentTab = 'lp'; }
  if (name === 'agents-usdc') { name = 'agents'; agentTab = 'usdc'; }
  if (!PAGES.includes(name)) name = 'market';
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const pg = document.getElementById('page-' + name);
  if (pg) pg.classList.add('active');
  document.querySelectorAll('.page-menu-item').forEach(i => {
    const on = i.dataset.page === name;
    i.classList.toggle('active', on);
    i.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  if (name === 'overview') selectOverviewTab(overviewTab || 'summary', false);
  if (name === 'agents') selectAgentTab(agentTab || 'overview', false);
}
// Tabs drive the URL hash so views are bookmarkable/shareable; hashchange does the work.
function selectPage(name) {
  if (location.hash.replace(/^#/, '') === name) showPage(name);
  else location.hash = name;
}
function goToMarket() { selectPage('market'); }
function _routeFromHash() {
  let name = (location.hash || '').replace(/^#/, '') || 'market';
  let overviewTab = 'summary';
  let agentTab = 'overview';
  if (name === 'overview-cashflow') { name = 'overview'; overviewTab = 'cashflow'; }
  if (name === 'overview-positions') { name = 'overview'; overviewTab = 'positions'; }
  if (name === 'agents-backtest') { name = 'agents'; agentTab = 'lp'; }
  if (name === 'agents-lp') { name = 'agents'; agentTab = 'lp'; }
  if (name === 'agents-usdc') { name = 'agents'; agentTab = 'usdc'; }
  if (name === 'interest') { name = 'overview'; overviewTab = 'cashflow'; }
  if (name === 'positions') { name = 'overview'; overviewTab = 'positions'; }
  showPage(name, overviewTab, agentTab);
}
window.addEventListener('hashchange', _routeFromHash);
window.addEventListener('DOMContentLoaded', _routeFromHash);

// Show/hide a line on the history chart via the checkboxes above it.
function toggleHistLine(idx, on) {
  if (!window.histChart) return;
  histChart.setDatasetVisibility(idx, on);
  histChart.update();
}

// Sanitize all rendered markdown (briefs are auto-synced from an external source).
function mdSafe(s) {
  const html = marked.parse(s || '');
  return (window.DOMPurify ? DOMPurify.sanitize(html) : html);
}

// Color the "Updated" stamp by age and show a relative "x ago" hint.
(function staleCheck() {
  const el = document.getElementById('nav-ts');
  if (!el) return;
  const upd = parseInt(el.dataset.updated || '0', 10) * 1000;
  if (!upd) return;
  const ageH = (Date.now() - upd) / 3600000;
  el.classList.add(ageH >= 24 ? 'ts-stale' : ageH >= 6 ? 'ts-aging' : 'ts-fresh');
  const rel = ageH < 1 ? Math.max(1, Math.round(ageH * 60)) + 'm ago'
            : ageH < 24 ? Math.round(ageH) + 'h ago'
            : Math.round(ageH / 24) + 'd ago';
  el.title = 'Last refreshed ' + rel;
  const badge = document.createElement('span');
  badge.className = 'ts-rel';
  badge.textContent = ' ' + rel;
  el.appendChild(badge);
})();

const EYE_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 19c-7 0-11-7-11-7a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 7 11 7a18.5 18.5 0 01-2.16 3.19"/><path d="M14.12 14.12a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
function updatePrivacyBtn(on) {
  const btn = document.getElementById('privacy-btn');
  if (!btn) return;
  btn.classList.toggle('active', on);
  btn.querySelector('span').innerHTML = on ? EYE_OFF_ICON : EYE_ICON;
  btn.title = on ? 'Show numbers' : 'Hide numbers';
}
function togglePrivacy() {
  if (document.body.classList.contains('priv-on')) {
    openLoginModal();
  } else {
    document.body.classList.add('priv-on');
    updatePrivacyBtn(true);
  }
}
function openLoginModal() {
  document.getElementById('login-error').style.display = 'none';
  document.getElementById('login-user').value = '';
  document.getElementById('login-pass').value = '';
  document.getElementById('login-ov').classList.add('open');
  setTimeout(() => document.getElementById('login-user').focus(), 50);
}
function closeLoginModal() {
  document.getElementById('login-ov').classList.remove('open');
}
function submitLogin() {
  const u = document.getElementById('login-user').value.trim();
  const p = document.getElementById('login-pass').value;
  if (u === 'admin' && p === '__DASH_PASS__') {
    document.body.classList.remove('priv-on');
    updatePrivacyBtn(false);
    closeLoginModal();
  } else {
    document.getElementById('login-error').style.display = 'block';
  }
}
(function initPrivacy() {
  document.body.classList.add('priv-on');
  updatePrivacyBtn(true);
})();
function openModal(id) {
  const src = document.getElementById('modal-' + id);
  if (!src) return;
  document.getElementById('modal-inner').innerHTML = src.innerHTML;
  document.getElementById('modal-ov').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeModal() {
  document.getElementById('modal-ov').classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeModal(); closeStockEdit(); closeAddStock(); }
});

function openStockEdit(ticker, shares, avgCost, currency, name) {
  if (document.body.classList.contains('priv-on')) return;
  document.getElementById('se-title').textContent = ticker + ' · ' + name;
  document.getElementById('se-ticker').value  = ticker;
  document.getElementById('se-shares').value  = shares;
  document.getElementById('se-avgcost').value = avgCost;
  document.getElementById('se-sym').textContent = currency === 'THB' ? '฿' : '$';
  const btn = document.getElementById('se-save-btn');
  btn.disabled = false; btn.textContent = 'Save & Refresh';
  document.getElementById('stock-edit-ov').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeStockEdit() {
  document.getElementById('stock-edit-ov').classList.remove('open');
  document.body.style.overflow = '';
}
async function saveStock() {
  const btn = document.getElementById('se-save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  const payload = {
    ticker:   document.getElementById('se-ticker').value,
    shares:   parseFloat(document.getElementById('se-shares').value),
    avg_cost: parseFloat(document.getElementById('se-avgcost').value),
  };
  try {
    const r = await fetch('/stocks/update', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const j = await r.json();
    if (j.ok) { closeStockEdit(); btn.textContent = 'Refreshing…'; await doRefresh(); }
    else { btn.textContent = j.error || 'Error'; btn.disabled = false; }
  } catch(e) { btn.textContent = 'No server'; btn.disabled = false; }
}

function openAddStock() {
  if (document.body.classList.contains('priv-on')) return;
  document.getElementById('as-ticker').value  = '';
  document.getElementById('as-shares').value  = '';
  document.getElementById('as-avgcost').value = '';
  const btn = document.getElementById('as-save-btn');
  btn.disabled = false; btn.textContent = 'Add & Refresh';
  document.getElementById('add-stock-ov').classList.add('open');
  document.body.style.overflow = 'hidden';
  setTimeout(() => document.getElementById('as-ticker').focus(), 50);
}
function closeAddStock() {
  document.getElementById('add-stock-ov').classList.remove('open');
  document.body.style.overflow = '';
}
async function addStock() {
  const btn = document.getElementById('as-save-btn');
  btn.disabled = true; btn.textContent = 'Adding…';
  const ticker   = document.getElementById('as-ticker').value.trim().toUpperCase();
  const shares   = parseFloat(document.getElementById('as-shares').value);
  const avg_cost = parseFloat(document.getElementById('as-avgcost').value);
  if (!ticker || isNaN(shares) || isNaN(avg_cost)) {
    btn.textContent = 'Fill all fields'; btn.disabled = false; return;
  }
  try {
    const r = await fetch('/stocks/add', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticker,shares,avg_cost})});
    const j = await r.json();
    if (j.ok) { closeAddStock(); await doRefresh(); }
    else { btn.textContent = j.error || 'Error'; btn.disabled = false; }
  } catch(e) { btn.textContent = 'No server'; btn.disabled = false; }
}

async function doRefresh() {
  try {
    const r = await fetch('/refresh', {method:'POST'});
    const j = await r.json();
    if (j.ok) { window.location.reload(); }
  } catch(e) { window.location.reload(); }
}
async function triggerRefresh() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true; btn.classList.add('spinning');
  try {
    await fetch('/refresh', {method:'POST'});
    pollRefreshStatus(btn);
  } catch(e) {
    refreshFailed(btn);
  }
}
async function pollRefreshStatus(btn) {
  for (let i = 0; i < 60; i++) {
    await new Promise(res => setTimeout(res, 3000));
    try {
      const r = await fetch('/refresh-status');
      const j = await r.json();
      if (j.done) {
        if (j.ok) { window.location.reload(); } else { refreshFailed(btn); }
        return;
      }
    } catch(e) { /* transient — keep polling */ }
  }
  refreshFailed(btn);
}
function refreshFailed(btn) {
  btn.classList.remove('spinning');
  btn.classList.add('refresh-error');
  setTimeout(() => { btn.classList.remove('refresh-error'); btn.disabled = false; }, 4000);
}

// ── Market Brief ──────────────────────────────────────────────────────────────
let _mbNotes = [];
const _mbGridCache = {};

(function mbInit() {
  if (document.getElementById('mb-history-list')) mbLoad();
})();

function mbTodayStr() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

async function mbLoad() {
  try {
    const r = await fetch('/market/notes');
    _mbNotes = await r.json();
    const picker = document.getElementById('mb-date-picker');
    let date = mbTodayStr();
    if (picker) {
      if (_mbNotes.length) {
        const dates = _mbNotes.map(n => n.date).sort();
        picker.min = dates[0];
        picker.max = dates[dates.length - 1];
      }
      if (!picker.value) picker.value = date;
      date = picker.value;
    }
    mbRenderDate(date);
  } catch(e) { console.warn('Market notes load failed', e); }
}

function mbSelectDate(date) {
  mbRenderDate(date);
}

function mbRenderDate(date) {
  const list = document.getElementById('mb-history-list');
  if (!list) return;
  const n = _mbNotes.find(x => x.date === date);
  if (!n) {
    list.innerHTML = `<div class="mb-empty">No brief for ${date}.</div>`;
    return;
  }
  list.innerHTML = `
    <div class="mb-note">
      <div class="mb-note-header">
        <div>
          <div class="mb-note-date">${n.date}</div>
          ${n.title ? `<div class="mb-note-title">${n.title}</div>` : ''}
        </div>
        <button class="mb-note-del" onclick="mbDelete('${n.date}')" title="Delete">✕</button>
      </div>
      ${n.content ? mbFormatBody(n.content, n.date) : ''}
    </div>
  `;
}

// Splits a brief into intro / categorized items ([Macro], [Crypto], ...) / summary.
function mbParse(content) {
  const lines = (content || '').split('\\n');
  const items = [];
  const summary = [];
  let mode = 'intro';
  let buffer = [];
  let currentCategory = null;

  function flushItem() {
    if (currentCategory && buffer.length) items.push({category: currentCategory, text: buffer.join('\\n').trim()});
    buffer = [];
  }

  for (const line of lines) {
    if (line.trim() === '---') { flushItem(); mode = 'summary'; continue; }
    if (mode === 'intro') {
      if (line.startsWith('>')) continue;
      if (line.trim() === '') continue;
      mode = 'items';
    }
    if (mode === 'items') {
      const m = line.match(/^📰\s*\*\*\[([^\]]+)\]\s*(.*)$/);
      if (m) { flushItem(); currentCategory = m[1].trim(); buffer.push('📰 **' + m[2]); }
      else { buffer.push(line); }
      continue;
    }
    summary.push(line);
  }
  flushItem();

  return { items, summaryText: summary.join('\\n').trim() };
}

// Renders each category as its own card. Falls back to one block if no [Category] tags found.
function mbFormatBody(content, noteId) {
  const { items, summaryText } = mbParse(content);

  if (!items.length) return `<div class="mb-note-body">${mdSafe(content)}</div>`;

  const order = [];
  const groups = {};
  items.forEach(it => {
    if (!groups[it.category]) { groups[it.category] = []; order.push(it.category); }
    groups[it.category].push(it.text);
  });

  const summaryHtml = summaryText ? `<div class="mb-note-body mb-note-summary">${mdSafe(summaryText)}</div>` : '';

  const gridId = 'mb-grid-' + noteId;
  const filterHtml = order.length > 1 ? `<div class="mb-category-filter">
    <button class="mb-filter-btn active" onclick="mbFilterCategory(this,'${gridId}','all')">All</button>
    ${order.map(cat => `<button class="mb-filter-btn" onclick="mbFilterCategory(this,'${gridId}','${cat}')">${cat}</button>`).join('')}
  </div>` : '';

  const categoriesHtml = `<div class="mb-category-grid" id="${gridId}">${order.map(cat => `
    <div class="mb-category-card" data-category="${cat}">
      <div class="mb-category-head">${cat}</div>
      ${groups[cat].map(t => `<div class="mb-note-body mb-cat-item">${mdSafe(t)}</div>`).join('')}
    </div>
  `).join('')}</div>`;

  _mbGridCache[gridId] = categoriesHtml;
  return summaryHtml + filterHtml + categoriesHtml;
}

// "All" restores the current day's category grid. Picking a specific category instead
// shows that category's news across every loaded day, most recent first, each item
// tagged with its date.
function mbFilterCategory(btn, gridId, cat) {
  btn.parentElement.querySelectorAll('.mb-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const grid = document.getElementById(gridId);
  if (!grid) return;
  if (cat === 'all') {
    grid.innerHTML = _mbGridCache[gridId] || '';
    return;
  }
  const dated = [];
  _mbNotes.slice().sort((a, b) => b.date.localeCompare(a.date)).forEach(n => {
    mbParse(n.content).items
      .filter(it => it.category === cat)
      .forEach(it => dated.push({date: n.date, text: it.text}));
  });
  grid.innerHTML = `<div class="mb-category-card" data-category="${cat}">
    <div class="mb-category-head">${cat}</div>
    ${dated.map(d => `<div class="mb-note-body mb-cat-item">${mdSafe(d.text)}<div class="mb-cat-date">${d.date}</div></div>`).join('')}
  </div>`;
}

async function mbDelete(date) {
  if (!confirm('Delete brief for ' + date + '?')) return;
  try {
    await fetch('/market/note/delete', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date})});
    await mbLoad();
  } catch(e) {}
}
"""

    # ── Chart JS
    chart_js = (
        f"const barCtx = document.getElementById('bar').getContext('2d');\n"
        f"new Chart(barCtx, {{\n"
        f"  type: 'bar',\n"
        f"  data: {{ labels: {json.dumps(proto_labels)}, datasets: [{{ data: {json.dumps(proto_values)}, backgroundColor: {json.dumps(proto_colors)}, borderRadius: 6, borderWidth: 0 }}] }},\n"
        f"  options: {{\n"
        f"    indexAxis: 'y',\n"
        f"    maintainAspectRatio: false,\n"
        f"    layout: {{ padding: {{ right: 80 }} }},\n"
        f"    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.x.toLocaleString(undefined, {{minimumFractionDigits:0,maximumFractionDigits:0}}) }} }} }},\n"
        f"    scales: {{\n"
        f"      x: {{ display: false }},\n"
        f"      y: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }} }}\n"
        f"    }}\n"
        f"  }},\n"
        f"  plugins: [{{ id:'barLabels', afterDatasetsDraw(chart) {{\n"
        f"    const {{ctx, scales: {{x, y}}}} = chart;\n"
        f"    chart.data.datasets[0].data.forEach((v, i) => {{\n"
        f"      const bar = chart.getDatasetMeta(0).data[i];\n"
        f"      ctx.save(); ctx.fillStyle='#94a3b8'; ctx.font='11px monospace';\n"
        f"      ctx.textAlign='left'; ctx.textBaseline='middle';\n"
        f"      ctx.fillText('$'+v.toLocaleString(undefined,{{maximumFractionDigits:0}}), bar.x+8, bar.y);\n"
        f"      ctx.restore();\n"
        f"    }});\n"
        f"  }}}}]\n"
        f"}});\n"
    )

    # ── History line chart
    hist_dates  = [h["date"] for h in history]
    hist_crypto = [h["crypto"] for h in history]
    hist_stock  = [h["stock"]  for h in history]
    hist_total  = [h["total"]  for h in history]
    history_js = (
        f"const histCtx = document.getElementById('history-chart').getContext('2d');\n"
        f"const histChart = new Chart(histCtx, {{\n"
        f"  type: 'line',\n"
        f"  data: {{\n"
        f"    labels: {json.dumps(hist_dates)},\n"
        f"    datasets: [\n"
        f"      {{ label: 'Total', data: {json.dumps(hist_total)}, borderColor: '#f1f5f9', backgroundColor: '#f1f5f908', borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.3, fill: false }},\n"
        f"      {{ label: 'Crypto', data: {json.dumps(hist_crypto)}, borderColor: '#4da2ff', backgroundColor: '#4da2ff08', borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 4, tension: 0.3, fill: false }},\n"
        f"      {{ label: 'Stocks', data: {json.dumps(hist_stock)}, borderColor: '#6366f1', backgroundColor: '#6366f108', borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 4, tension: 0.3, fill: false }}\n"
        f"    ]\n"
        f"  }},\n"
        f"  options: {{\n"
        f"    responsive: true,\n"
        f"    interaction: {{ mode: 'index', intersect: false }},\n"
        f"    plugins: {{\n"
        f"      legend: {{ display: false }},\n"
        f"      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString(undefined, {{minimumFractionDigits:0,maximumFractionDigits:0}}) }} }}\n"
        f"    }},\n"
        f"    scales: {{\n"
        f"      x: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }}, maxTicksLimit: 10 }} }},\n"
        f"      y: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#94a3b8', callback: v => '$' + (v/1000).toFixed(0) + 'k' }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n"
        f"window.histChart = histChart;\n"
    )
    # Category chart data
    cat_labels = []
    cat_values = []
    cat_colors_chart = []
    _cat_data = [
        ("AMM",     amm_total,                    "#f97316"),
        ("Lending", lending_total + lending_bn,   "#3b82f6"),
        ("Staking", onchain_total,                "#10b981"),
        ("Futures", cex_total,                    "#f59e0b"),
        ("Stocks",  stocks_total,                 "#8b5cf6"),
    ]
    for lbl, val, col in sorted(_cat_data, key=lambda x: -x[1]):
        if val > 0:
            cat_labels.append(lbl)
            cat_values.append(round(val, 2))
            cat_colors_chart.append(col)

    cat_js = (
        f"const catCtx = document.getElementById('cat-chart').getContext('2d');\n"
        f"new Chart(catCtx, {{\n"
        f"  type: 'bar',\n"
        f"  data: {{ labels: {json.dumps(cat_labels)}, datasets: [{{ data: {json.dumps(cat_values)}, backgroundColor: {json.dumps(cat_colors_chart)}, borderRadius: 6, borderWidth: 0 }}] }},\n"
        f"  options: {{\n"
        f"    indexAxis: 'y', maintainAspectRatio: false,\n"
        f"    layout: {{ padding: {{ right: 90 }} }},\n"
        f"    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ' $' + ctx.parsed.x.toLocaleString(undefined,{{maximumFractionDigits:0}}) }} }} }},\n"
        f"    scales: {{ x: {{ display: false }}, y: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 12 }} }} }} }}\n"
        f"  }},\n"
        f"  plugins: [{{ id:'catLabels', afterDatasetsDraw(chart) {{\n"
        f"    const {{ctx, scales: {{x, y}}}} = chart;\n"
        f"    chart.data.datasets[0].data.forEach((v, i) => {{\n"
        f"      const bar = chart.getDatasetMeta(0).data[i];\n"
        f"      ctx.save(); ctx.fillStyle='#94a3b8'; ctx.font='11px monospace';\n"
        f"      ctx.textAlign='left'; ctx.textBaseline='middle';\n"
        f"      ctx.fillText('$'+v.toLocaleString(undefined,{{maximumFractionDigits:0}}), bar.x+8, bar.y);\n"
        f"      ctx.restore();\n"
        f"    }});\n"
        f"  }}}}]\n"
        f"}});\n"
    )

    # ── By-asset chart data: Crypto / Stock / Stable (cash + stablecoins)
    _STABLE_SYMS = {"USDC", "USDT", "USDSUI", "FDUSD", "BUCK", "AUSD", "MUSD",
                    "USDE", "SUI_USDE", "USDY", "DAI", "WUSDC", "USDC.E"}
    crypto_usd = sum(v["usd"] for s, v in tok_assets.items() if s.upper() not in _STABLE_SYMS)
    stable_cr  = sum(v["usd"] for s, v in tok_assets.items() if s.upper() in _STABLE_SYMS)
    cash_usd   = sum(s.get("market_value", 0) for s in stocks if s["ticker"].upper() == "CASH")
    stock_usd  = sum(s.get("market_value", 0) for s in stocks if s["ticker"].upper() != "CASH")
    _asset_data = [
        ("Crypto",       crypto_usd,             "#34d399"),
        ("Stock",        stock_usd,              "#8b5cf6"),
        ("Stable asset", stable_cr + cash_usd,   "#38bdf8"),
    ]
    _ad = [(l, round(v, 2), c) for l, v, c in _asset_data if v > 0]
    asset_labels  = [x[0] for x in _ad]
    asset_values  = [x[1] for x in _ad]
    asset_colors  = [x[2] for x in _ad]
    asset_js = (
        f"const assetCtx = document.getElementById('asset-chart').getContext('2d');\n"
        f"const _assetData = {json.dumps(asset_values)};\n"
        f"const _assetTotal = _assetData.reduce((a,b)=>a+b,0) || 1;\n"
        f"new Chart(assetCtx, {{\n"
        f"  type: 'doughnut',\n"
        f"  data: {{ labels: {json.dumps(asset_labels)}, datasets: [{{ data: _assetData, backgroundColor: {json.dumps(asset_colors)}, borderColor: '#0f172a', borderWidth: 2 }}] }},\n"
        f"  options: {{\n"
        f"    maintainAspectRatio: false, cutout: '62%',\n"
        f"    plugins: {{\n"
        f"      legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 12 }}, padding: 16, usePointStyle: true }} }},\n"
        f"      tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.label + ': $' + ctx.parsed.toLocaleString(undefined,{{maximumFractionDigits:0}}) + '  (' + (ctx.parsed/_assetTotal*100).toFixed(1) + '%)' }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n"
    )

    # ── Second By-asset donut: Crypto vs Stock (uses the Portfolio History totals)
    _cs_data = [("Crypto", crypto_total, "#34d399"), ("Stock", stocks_total, "#8b5cf6")]
    _cs = [(l, round(v, 2), c) for l, v, c in _cs_data if v > 0]
    cs_labels = [x[0] for x in _cs]
    cs_values = [x[1] for x in _cs]
    cs_colors = [x[2] for x in _cs]
    assetcs_js = (
        f"const assetCsCtx = document.getElementById('asset-cs-chart').getContext('2d');\n"
        f"const _csData = {json.dumps(cs_values)};\n"
        f"const _csTotal = _csData.reduce((a,b)=>a+b,0) || 1;\n"
        f"new Chart(assetCsCtx, {{\n"
        f"  type: 'doughnut',\n"
        f"  data: {{ labels: {json.dumps(cs_labels)}, datasets: [{{ data: _csData, backgroundColor: {json.dumps(cs_colors)}, borderColor: '#0f172a', borderWidth: 2 }}] }},\n"
        f"  options: {{\n"
        f"    maintainAspectRatio: false, cutout: '62%',\n"
        f"    plugins: {{\n"
        f"      legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 12 }}, padding: 16, usePointStyle: true }} }},\n"
        f"      tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.label + ': $' + ctx.parsed.toLocaleString(undefined,{{maximumFractionDigits:0}}) + '  (' + (ctx.parsed/_csTotal*100).toFixed(1) + '%)' }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n"
    )

    chart_switch_js = """
function switchChart(tab) {
  document.querySelectorAll('.chart-tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.chart-pane').forEach(p => p.classList.remove('active'));
  document.querySelector('.chart-tab[data-tab="'+tab+'"]').classList.add('active');
  document.getElementById('pane-'+tab).classList.add('active');
}
"""

    chart_js += history_js + cat_js + asset_js + assetcs_js + interest_js + chart_switch_js

    bar_h = max(320, len(proto_labels) * 34)
    cat_h = max(160, len(cat_labels) * 52)

    tabbed_chart = (
        '<div class="chart-card priv-chart">'
        '<div class="chart-tabs">'
        '<button class="chart-tab active" data-tab="history" onclick="switchChart(\'history\')">Portfolio History</button>'
        '<button class="chart-tab" data-tab="protocol" onclick="switchChart(\'protocol\')">By Protocol</button>'
        '<button class="chart-tab" data-tab="category" onclick="switchChart(\'category\')">By Category</button>'
        '<button class="chart-tab" data-tab="asset" onclick="switchChart(\'asset\')">By Asset</button>'
        '</div>'
        '<div id="pane-history" class="chart-pane active">'
        '<div class="hist-legend">'
        '<label class="hl-item" style="--c:#f1f5f9"><input type="checkbox" checked onchange="toggleHistLine(0,this.checked)"><span class="hl-dot"></span>Total</label>'
        '<label class="hl-item" style="--c:#4da2ff"><input type="checkbox" checked onchange="toggleHistLine(1,this.checked)"><span class="hl-dot"></span>Crypto</label>'
        '<label class="hl-item" style="--c:#6366f1"><input type="checkbox" checked onchange="toggleHistLine(2,this.checked)"><span class="hl-dot"></span>Stocks</label>'
        '</div>'
        '<canvas id="history-chart" role="img" aria-label="Line chart of portfolio value over time: total, crypto and stocks"></canvas></div>'
        f'<div id="pane-protocol" class="chart-pane"><div style="height:{bar_h}px"><canvas id="bar" role="img" aria-label="Bar chart of value by protocol"></canvas></div></div>'
        f'<div id="pane-category" class="chart-pane"><div style="height:{cat_h}px"><canvas id="cat-chart" role="img" aria-label="Bar chart of value by category"></canvas></div></div>'
        '<div id="pane-asset" class="chart-pane">'
        '<div style="display:flex;flex-wrap:wrap;gap:24px;justify-content:center">'
        '<div style="flex:1;min-width:240px;max-width:430px">'
        '<div style="text-align:center;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:#94a3b8;margin-bottom:8px">Crypto / Stock / Stable</div>'
        '<div style="height:320px"><canvas id="asset-chart" role="img" aria-label="Doughnut chart of allocation by asset type: crypto, stock, stable asset"></canvas></div>'
        '</div>'
        '<div style="flex:1;min-width:240px;max-width:430px">'
        '<div style="text-align:center;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:#94a3b8;margin-bottom:8px">Crypto vs Stock</div>'
        '<div style="height:320px"><canvas id="asset-cs-chart" role="img" aria-label="Doughnut chart of crypto versus stock allocation"></canvas></div>'
        '</div>'
        '</div></div>'
        '</div>'
    )

    # ── Market Brief page (dynamic via JS fetch from /market/notes)
    market_page_html = f"""
<style>
.mb-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
@media(max-width:700px){{.mb-grid{{grid-template-columns:1fr}}}}
.mb-history-card{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:22px 24px}}
.mb-history-head-row{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid var(--border)}}
.mb-history-head{{font-size:.65rem;text-transform:uppercase;letter-spacing:.09em;font-weight:700;color:var(--text3)}}
.mb-date-picker{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:.82rem;font-weight:600;color:var(--text);font-family:inherit;cursor:pointer;color-scheme:dark}}
.mb-note{{padding:16px 0;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:6px}}
.mb-note:last-child{{border-bottom:none;padding-bottom:0}}
.mb-note-header{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}
.mb-note-date{{font-size:.74rem;font-weight:700;color:var(--accent2);font-family:'SF Mono',ui-monospace,monospace;flex-shrink:0;margin-top:2px}}
.mb-note-title{{font-size:1.05rem;font-weight:700;color:var(--text);line-height:1.4}}
.mb-note-body{{font-size:.98rem;color:var(--text2);line-height:1.85}}
.mb-note-body p{{margin:0 0 14px}}
.mb-note-body p:last-child{{margin-bottom:0}}
.mb-note-body h1,.mb-note-body h2,.mb-note-body h3{{color:var(--text);font-weight:700;line-height:1.4;margin:22px 0 10px}}
.mb-note-body h1:first-child,.mb-note-body h2:first-child,.mb-note-body h3:first-child{{margin-top:0}}
.mb-note-body h1{{font-size:1.2rem}}
.mb-note-body h2{{font-size:1.1rem}}
.mb-note-body h3{{font-size:1.02rem}}
.mb-note-body strong{{color:var(--text);font-weight:700}}
.mb-note-body a{{color:var(--accent);text-decoration:none;word-break:break-all}}
.mb-note-body a:hover{{text-decoration:underline}}
.mb-note-body ul,.mb-note-body ol{{margin:0 0 14px;padding-left:22px}}
.mb-note-body li{{margin-bottom:6px}}
.mb-note-body blockquote{{border-left:2px solid var(--border2);padding-left:14px;margin:0 0 14px;color:var(--text3);font-style:italic}}
.mb-note-body blockquote p{{margin-bottom:0}}
.mb-note-body hr{{border:none;border-top:1px solid var(--border);margin:20px 0}}
.mb-category-grid{{display:flex;flex-direction:column;gap:16px;margin-bottom:4px}}
.mb-category-card{{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:18px 20px}}
.mb-category-head{{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;font-weight:700;color:var(--accent);margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border)}}
.mb-cat-item{{padding-bottom:14px;margin-bottom:14px;border-bottom:1px solid var(--border)}}
.mb-cat-item:last-child{{padding-bottom:0;margin-bottom:0;border-bottom:none}}
.mb-cat-date{{text-align:right;font-size:.68rem;font-family:'SF Mono',ui-monospace,monospace;color:var(--text3);margin-top:6px}}
.mb-note-summary{{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-bottom:16px}}
.mb-note-summary p{{margin:0}}
.mb-category-filter{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
.mb-filter-btn{{background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:7px 16px;font-size:.78rem;font-weight:600;color:var(--text2);cursor:pointer;transition:all .15s;font-family:inherit}}
.mb-filter-btn:hover{{border-color:var(--accent);color:var(--text)}}
.mb-filter-btn.active{{background:linear-gradient(135deg,#4da2ff,#6fbcf0);border-color:transparent;color:#fff}}
.mb-note-del{{background:none;border:none;color:var(--text3);font-size:.75rem;cursor:pointer;padding:2px 6px;border-radius:5px;transition:all .15s;flex-shrink:0}}
.mb-note-del:hover{{color:var(--red);background:#f8717115}}
.mb-empty{{color:var(--text3);font-size:.82rem;text-align:center;padding:32px 0}}
</style>
<div class="mb-history-card">
  <div class="mb-history-head-row">
    <div class="mb-history-head">Daily Brief</div>
    <input type="date" id="mb-date-picker" class="mb-date-picker" onchange="mbSelectDate(this.value)">
  </div>
  <div id="mb-history-list"><div class="mb-empty">No briefs yet.</div></div>
</div>
"""

    # ── Agent Team page (static diagram of the Kive sub-agent team)
    agent_team_page_html = """
<style>
.at-intro{color:var(--text2);font-size:.95rem;line-height:1.75;margin-bottom:22px;max-width:780px}
.at-intro strong{color:var(--text)}
.at-card-lg{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:22px 24px;margin-bottom:24px}
.at-head{font-size:.65rem;text-transform:uppercase;letter-spacing:.09em;font-weight:700;color:var(--text3);margin-bottom:18px}
.at-svg-wrap{overflow-x:auto;padding-bottom:6px}
.at-svg{width:100%;min-width:780px;height:auto;display:block}
.at-node{cursor:default}
.at-box{transition:filter .15s}
.at-node:hover .at-box{filter:brightness(1.3)}
.at-name{font-size:15px;font-weight:700;fill:var(--text)}
.at-role{font-size:10.5px;fill:var(--text3)}
.at-kname{font-size:19px;font-weight:800;fill:#ecd9ff}
.at-krole{font-size:11px;fill:#caa9e6}
.at-yname{font-size:13px;font-weight:700;fill:#c9d2de}
.at-edge{stroke:#5b6472;stroke-width:2;fill:none}
.at-dash{stroke:#4b5563;stroke-width:1.5;stroke-dasharray:4 4;fill:none}
.at-elabel{font-size:11px;font-weight:700;fill:#9aa3b2;font-family:'SF Mono',ui-monospace,monospace}
.at-pill-box{fill:rgba(255,255,255,.03);stroke:#3a4250;stroke-width:1;stroke-dasharray:3 3}
.at-pill-text{font-size:10.5px;fill:var(--text3);font-weight:600}
.at-legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:18px;padding-top:16px;border-top:1px solid var(--border)}
.at-leg{display:flex;align-items:center;gap:7px;font-size:.78rem;color:var(--text2)}
.at-leg .dot{width:11px;height:11px;border-radius:3px}
.at-flows{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:14px}
.at-flows li{font-size:.88rem;color:var(--text2);line-height:1.6}
.at-flows .fl-name{font-weight:700;color:var(--text);font-family:'SF Mono',ui-monospace,monospace;font-size:.82rem}
.at-flows .fl-chain{color:var(--text3);font-family:'SF Mono',ui-monospace,monospace;font-size:.8rem}
.at-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:14px}
.at-card{background:var(--surface2);border:1px solid var(--border);border-left:3px solid var(--c);border-radius:12px;padding:16px 18px}
.at-card h4{margin:0;font-size:1.02rem;color:var(--text);display:flex;align-items:center;gap:8px}
.at-card .at-role-tag{display:block;font-size:.7rem;color:var(--c);font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin-top:3px}
.at-card p{margin:9px 0 0;font-size:.85rem;color:var(--text2);line-height:1.6}
.at-card .at-flow{font-size:.74rem;color:var(--text3);margin-top:10px;font-family:'SF Mono',ui-monospace,monospace}
</style>

<p class="at-intro"><strong>Kive</strong> is your main agent. You talk to Kive; Kive orchestrates a team of specialist sub-agents and routes each request to the right one. This page maps the team and how work flows between them.</p>

<div class="at-card-lg">
  <div class="at-head">Team Map</div>
  <div class="at-svg-wrap">
  <svg class="at-svg" viewBox="0 0 1090 540" role="img" aria-label="Horizontal diagram of the Kive agent team and how the agents connect">
    <defs>
      <marker id="at-arrow" markerWidth="9" markerHeight="9" refX="6.5" refY="3" orient="auto" markerUnits="strokeWidth">
        <path d="M0,0 L7,3 L0,6 Z" fill="#5b6472"/>
      </marker>
    </defs>

    <!-- Kive: one stem to a vertical trunk, then right-angle branches into each agent -->
    <line class="at-edge" x1="154" y1="280" x2="200" y2="280"/>
    <line class="at-edge" x1="200" y1="70" x2="200" y2="495"/>
    <line class="at-edge" x1="200" y1="70" x2="240" y2="70" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="200" y1="185" x2="240" y2="185" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="200" y1="295" x2="240" y2="295" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="200" y1="405" x2="240" y2="405" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="200" y1="495" x2="240" y2="495" marker-end="url(#at-arrow)"/>
    <!-- research chain (left to right) -->
    <line class="at-edge" x1="358" y1="70" x2="418" y2="70" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="536" y1="70" x2="588" y2="70" marker-end="url(#at-arrow)"/>
    <line class="at-edge" x1="706" y1="70" x2="758" y2="70" marker-end="url(#at-arrow)"/>
    <!-- outputs (dashed) -->
    <line class="at-dash" x1="876" y1="70" x2="903" y2="70" marker-end="url(#at-arrow)"/>
    <line class="at-dash" x1="358" y1="185" x2="418" y2="185" marker-end="url(#at-arrow)"/>
    <line class="at-dash" x1="358" y1="295" x2="418" y2="295" marker-end="url(#at-arrow)"/>
    <!-- diary store: Diry writes (elbow), Zammy reads (elbow) -->
    <polyline class="at-edge" points="358,405 506,405 506,426" fill="none" marker-end="url(#at-arrow)"/>
    <polyline class="at-edge" points="506,472 506,495 362,495" fill="none" marker-end="url(#at-arrow)"/>
    <text class="at-elabel" x="432" y="398" text-anchor="middle">writes</text>
    <text class="at-elabel" x="438" y="489" text-anchor="middle">reads</text>

    <!-- Kive -->
    <g class="at-node"><title>Kive — your main agent / orchestrator. Routes every request to the right specialist.</title>
      <rect class="at-box" x="26" y="252" width="128" height="56" rx="14" fill="#2a1840" stroke="#bc7def" stroke-width="2"/>
      <text class="at-kname" x="90" y="277" text-anchor="middle">Kive</text>
      <text class="at-krole" x="90" y="294" text-anchor="middle">Orchestrator</text></g>

    <!-- research chain -->
    <g class="at-node"><title>Ken — Research Planner. Turns a topic into a lightweight search plan (sections + keywords).</title>
      <rect class="at-box" x="242" y="45" width="116" height="50" rx="12" fill="#0e2238" stroke="#4da2ff"/>
      <text class="at-name" x="300" y="68" text-anchor="middle">Ken</text>
      <text class="at-role" x="300" y="84" text-anchor="middle">Research planner</text></g>
    <g class="at-node"><title>Glast — Web Researcher &amp; NotebookLM Curator. Researches each section of Ken's plan into a notebook.</title>
      <rect class="at-box" x="420" y="45" width="116" height="50" rx="12" fill="#0e2238" stroke="#4da2ff"/>
      <text class="at-name" x="478" y="68" text-anchor="middle">Glast</text>
      <text class="at-role" x="478" y="84" text-anchor="middle">Web researcher</text></g>
    <g class="at-node"><title>Nelly — Report Writer. Turns the notebook into a human-readable, easy report.</title>
      <rect class="at-box" x="590" y="45" width="116" height="50" rx="12" fill="#0e2238" stroke="#4da2ff"/>
      <text class="at-name" x="648" y="68" text-anchor="middle">Nelly</text>
      <text class="at-role" x="648" y="84" text-anchor="middle">Report writer</text></g>
    <g class="at-node"><title>Zeny — Report Generator &amp; Knowledge Curator. Saves the report as markdown to the Knowledge folder.</title>
      <rect class="at-box" x="760" y="45" width="116" height="50" rx="12" fill="#0e2238" stroke="#4da2ff"/>
      <text class="at-name" x="818" y="68" text-anchor="middle">Zeny</text>
      <text class="at-role" x="818" y="84" text-anchor="middle">Knowledge curator</text></g>

    <!-- Monday -->
    <g class="at-node"><title>Monday — Python Script Master Reviewer. Security, vulnerability and architecture review.</title>
      <rect class="at-box" x="242" y="160" width="116" height="50" rx="12" fill="#2e1b12" stroke="#f59e0b"/>
      <text class="at-name" x="300" y="183" text-anchor="middle">Monday</text>
      <text class="at-role" x="300" y="199" text-anchor="middle">Code reviewer</text></g>
    <!-- Finn -->
    <g class="at-node"><title>Finn — Financial News Curator. Daily Thai financial news brief, runs as a cloud routine at 9 AM.</title>
      <rect class="at-box" x="242" y="270" width="116" height="50" rx="12" fill="#0f2a1f" stroke="#34d399"/>
      <text class="at-name" x="300" y="293" text-anchor="middle">Finn</text>
      <text class="at-role" x="300" y="309" text-anchor="middle">News curator</text></g>
    <!-- Diry -->
    <g class="at-node"><title>Diry — Diary Keeper. Writes dated entries to diary.md whenever Kive does something on your behalf.</title>
      <rect class="at-box" x="242" y="380" width="116" height="50" rx="12" fill="#2b1320" stroke="#f472b6"/>
      <text class="at-name" x="300" y="403" text-anchor="middle">Diry</text>
      <text class="at-role" x="300" y="419" text-anchor="middle">Diary keeper</text></g>
    <!-- Zammy -->
    <g class="at-node"><title>Zammy — Diary Reflection Analyst. Reads diary.md and reflects on Problems / What I Have / Reflection.</title>
      <rect class="at-box" x="242" y="470" width="116" height="50" rx="12" fill="#261433" stroke="#c879ef"/>
      <text class="at-name" x="300" y="493" text-anchor="middle">Zammy</text>
      <text class="at-role" x="300" y="509" text-anchor="middle">Diary reflector</text></g>

    <!-- diary.md store (shared by Diry & Zammy) -->
    <g class="at-node"><title>diary.md — your running log. Diry writes to it; Zammy reads from it.</title>
      <rect class="at-box" x="441" y="428" width="130" height="44" rx="10" fill="#161b24" stroke="#7c889a" stroke-dasharray="5 4"/>
      <text class="at-pill-text" x="506" y="455" text-anchor="middle" style="font-size:13px;fill:var(--text2);font-weight:700">&#128214; diary.md</text></g>

    <!-- output pills -->
    <g><rect class="at-pill-box" x="905" y="56" width="150" height="28" rx="14"/>
      <text class="at-pill-text" x="980" y="74" text-anchor="middle">&#128193; Knowledge folder</text></g>
    <g><rect class="at-pill-box" x="420" y="171" width="160" height="28" rx="14"/>
      <text class="at-pill-text" x="500" y="189" text-anchor="middle">&#128274; Review report</text></g>
    <g><rect class="at-pill-box" x="420" y="281" width="160" height="28" rx="14"/>
      <text class="at-pill-text" x="500" y="299" text-anchor="middle">&#128202; Dashboard Brief</text></g>
  </svg>
  </div>
  <div class="at-legend">
    <span class="at-leg"><span class="dot" style="background:#bc7def"></span>Orchestrator</span>
    <span class="at-leg"><span class="dot" style="background:#4da2ff"></span>Research pipeline</span>
    <span class="at-leg"><span class="dot" style="background:#f59e0b"></span>Code review</span>
    <span class="at-leg"><span class="dot" style="background:#34d399"></span>News</span>
    <span class="at-leg"><span class="dot" style="background:#f472b6"></span>Diary keeper</span>
    <span class="at-leg"><span class="dot" style="background:#c879ef"></span>Reflection</span>
  </div>
</div>

<div class="at-card-lg">
  <div class="at-head">Workflows</div>
  <ul class="at-flows">
    <li><span class="fl-name">/research</span> &nbsp;<span class="fl-chain">Ken (plan) &rarr; Glast (research) &rarr; Nelly (write) &rarr; Zeny (save)</span><br>A topic becomes a search plan, deep research, a readable report, then a saved file in the Knowledge folder.</li>
    <li><span class="fl-name">/review-python</span> &nbsp;<span class="fl-chain">Monday &rarr; security report</span><br>A Python script gets a full security, vulnerability, and architecture review.</li>
    <li><span class="fl-name">daily brief</span> &nbsp;<span class="fl-chain">Finn &rarr; Dashboard Market Brief</span><br>Runs itself at 9 AM (cloud routine) and publishes the Thai finance brief to this dashboard.</li>
    <li><span class="fl-name">log</span> &nbsp;<span class="fl-chain">Diry &rarr; writes diary.md</span><br>After every action Kive does for you, Diry records a dated entry in the diary.</li>
    <li><span class="fl-name">reflect</span> &nbsp;<span class="fl-chain">Zammy &rarr; reads diary.md</span><br>Reflects your diary into Problems, What I Have, and Reflection About Me.</li>
  </ul>
</div>

<div class="at-card-lg">
  <div class="at-head">The Team</div>
  <div class="at-cards">
    <div class="at-card" style="--c:#bc7def"><h4>Kive<span class="at-role-tag">Main orchestrator</span></h4><p>Your main agent. Talks to you and routes every request to the right specialist sub-agent.</p></div>
    <div class="at-card" style="--c:#4da2ff"><h4>Ken<span class="at-role-tag">Research planner</span></h4><p>Turns a topic into a lightweight search plan &mdash; sections and keywords for Glast to research within.</p><div class="at-flow">/research &middot; step 1</div></div>
    <div class="at-card" style="--c:#4da2ff"><h4>Glast<span class="at-role-tag">Web researcher</span></h4><p>Takes Ken's plan, browses trustworthy sources, and curates findings into a NotebookLM notebook &mdash; framed around your interests.</p><div class="at-flow">/research &middot; step 2</div></div>
    <div class="at-card" style="--c:#4da2ff"><h4>Nelly<span class="at-role-tag">Report writer</span></h4><p>Reads the notebook and writes a human-readable, easy-to-understand report.</p><div class="at-flow">/research &middot; step 3</div></div>
    <div class="at-card" style="--c:#4da2ff"><h4>Zeny<span class="at-role-tag">Knowledge curator</span></h4><p>Generates the report from NotebookLM and saves it as markdown in your Knowledge folder.</p><div class="at-flow">/research &middot; step 4</div></div>
    <div class="at-card" style="--c:#f59e0b"><h4>Monday<span class="at-role-tag">Code reviewer</span></h4><p>Reviews a Python script for security, vulnerabilities, and architecture &mdash; returns a structured report.</p><div class="at-flow">/review-python</div></div>
    <div class="at-card" style="--c:#34d399"><h4>Finn<span class="at-role-tag">News curator</span></h4><p>Daily Thai financial news brief from Reuters, Investing.com &amp; Cointelegraph. Runs at 9 AM as a cloud routine.</p><div class="at-flow">daily brief &rarr; dashboard</div></div>
    <div class="at-card" style="--c:#f472b6"><h4>Diry<span class="at-role-tag">Diary keeper</span></h4><p>Writes the diary &mdash; logs a dated entry every time Kive does something on your behalf.</p><div class="at-flow">writes &rarr; diary.md</div></div>
    <div class="at-card" style="--c:#c879ef"><h4>Zammy<span class="at-role-tag">Diary reflector</span></h4><p>Reads your diary and reflects it into Problems, What I Have, and Reflection About Me.</p><div class="at-flow">reads &larr; diary.md</div></div>
  </div>
</div>
"""

    # ── Assemble HTML
    overview_summary_html = (
        '<div class="stats-grid">'
        f'<div class="stat-card"><div class="sc-lbl">Gross Assets</div><div class="sc-val">{fmt(gross)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Total Debt</div><div class="sc-val debt">{fmt(total_debt)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Net Value</div><div class="sc-val">{fmt(net_value)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Positions</div><div class="sc-val">{len(positions)}</div></div>'
        '</div>'
        + tabbed_chart +
        token_summary_html +
        '<div class="risk-row">' + risk_cards + '</div>'
    )

    page1 = (
        '<div class="overview-subnav" role="tablist" aria-label="Overview sections">'
        '<button type="button" class="overview-subtab active" data-overview-tab="summary" onclick="selectOverviewTab(\'summary\')">Summary</button>'
        '<button type="button" class="overview-subtab" data-overview-tab="cashflow" onclick="selectOverviewTab(\'cashflow\')">Cashflow</button>'
        '<button type="button" class="overview-subtab" data-overview-tab="positions" onclick="selectOverviewTab(\'positions\')">Positions</button>'
        '</div>'
        '<div id="overview-summary" class="overview-panel active">' + overview_summary_html + '</div>'
        '<div id="overview-cashflow" class="overview-panel cashflow-panel">' + page3 + '</div>'
        '<div id="overview-positions" class="overview-panel positions-panel">' + page2_html + '</div>'
    )

    stock_modals = (
        '<div id="stock-edit-ov" class="modal-ov">'
        '  <div class="modal-box" style="max-width:340px">'
        '    <div class="modal-header">'
        '      <span id="se-title" style="font-weight:700"></span>'
        '      <button class="modal-close" onclick="closeStockEdit()">&#10005;</button>'
        '    </div>'
        '    <div style="padding:16px 0 0">'
        '    <div class="se-field">'
        '      <span class="se-lbl">Shares</span>'
        '      <input id="se-shares" class="se-input" type="number" step="any">'
        '    </div>'
        '    <div class="se-field">'
        '      <span class="se-lbl">Avg Cost (<span id="se-sym">$</span>)</span>'
        '      <input id="se-avgcost" class="se-input" type="number" step="any">'
        '    </div>'
        '    <input id="se-ticker" type="hidden">'
        '    <button id="se-save-btn" class="se-save" onclick="saveStock()">Save &amp; Refresh</button>'
        '    </div>'
        '  </div>'
        '</div>'
        '<div id="add-stock-ov" class="modal-ov">'
        '  <div class="modal-box" style="max-width:340px">'
        '    <div class="modal-header">'
        '      <span style="font-weight:700">Add Stock</span>'
        '      <button class="modal-close" onclick="closeAddStock()">&#10005;</button>'
        '    </div>'
        '    <div style="padding:16px 0 0">'
        '    <div class="se-field">'
        '      <span class="se-lbl">Ticker</span>'
        '      <input id="as-ticker" class="se-input" type="text" placeholder="e.g. AAPL or THSI (auto-.BK for SET)">'
        '      <span class="se-hint">For SET stocks, just enter the ticker &#8212; .BK suffix added automatically.</span>'
        '    </div>'
        '    <div class="se-field">'
        '      <span class="se-lbl">Shares</span>'
        '      <input id="as-shares" class="se-input" type="number" step="any">'
        '    </div>'
        '    <div class="se-field">'
        '      <span class="se-lbl">Avg Cost</span>'
        '      <input id="as-avgcost" class="se-input" type="number" step="any">'
        '    </div>'
        '    <button id="as-save-btn" class="se-save" onclick="addStock()">Add &amp; Refresh</button>'
        '    </div>'
        '  </div>'
        '</div>'
        '<div id="login-ov" class="modal-ov">'
        '  <div class="modal-box" style="max-width:320px">'
        '    <div class="modal-header">'
        '      <span style="font-weight:700">Unlock View</span>'
        '      <button class="modal-close" onclick="closeLoginModal()">&#10005;</button>'
        '    </div>'
        '    <div style="padding:16px 0 0">'
        '    <div class="se-field">'
        '      <span class="se-lbl">Username</span>'
        '      <input id="login-user" class="se-input" type="text" autocomplete="off">'
        '    </div>'
        '    <div class="se-field">'
        '      <span class="se-lbl">Password</span>'
        '      <input id="login-pass" class="se-input" type="password" autocomplete="off" onkeydown="if(event.key===\'Enter\')submitLogin()">'
        '      <span id="login-error" class="se-hint" style="color:#f87171;display:none">Incorrect username or password.</span>'
        '    </div>'
        '    <button class="se-save" onclick="submitLogin()">Unlock</button>'
        '    </div>'
        '  </div>'
        '</div>'
    )

    LP_WALLET = "0xLP_WALLET_REDACTED"
    LP_POOL   = "0x440e5e3b13b8220c5c338bb5a4291cab5c58064eaf3654c77f3e9aed5147689c"
    graph_path = Path(__file__).parent / "assets" / "sui_vol_backtest_7d.png"
    if graph_path.exists():
        lp_graph_src = "data:image/png;base64," + base64.b64encode(graph_path.read_bytes()).decode("ascii")
    else:
        lp_graph_src = "/assets/sui_vol_backtest_7d.png"
    data_path = Path(__file__).parent / "assets" / "sui_vol_backtest_data.json"
    lp_backtest_data = data_path.read_text() if data_path.exists() else "[]"
    agents_page_html = (
        '<div style="margin-bottom:22px">'
        '<h2 style="font-family:var(--font-display);font-size:1.6rem;letter-spacing:.03em;'
        'text-transform:uppercase;color:var(--text);margin:0">Agentic Agents</h2>'
        '</div>'
        '<div class="agent-subnav" role="tablist" aria-label="Agent sections">'
        '<button type="button" class="agent-subtab active" data-agent-tab="overview" onclick="selectAgentTab(\'overview\')">Overview</button>'
        '<button type="button" class="agent-subtab" data-agent-tab="lp" onclick="selectAgentTab(\'lp\')">LP Agent</button>'
        '<button type="button" class="agent-subtab" data-agent-tab="usdc" onclick="selectAgentTab(\'usdc\')">USDC Agent</button>'
        '</div>'
        '<div id="agents-overview" class="agent-panel active">'
        '<div class="chart-card">'
        '<h3 style="font-size:1.18rem;margin:0 0 14px;color:var(--text)">Agents Overview</h3>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px">'
        '<button type="button" onclick="selectAgentTab(\'lp\')" style="text-align:left;background:var(--surface2);border:1px solid var(--border);border-radius:14px;padding:16px;cursor:pointer;color:inherit;font-family:inherit">'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);font-weight:800;margin-bottom:7px">LP Agent</div>'
        '<div style="font-size:1rem;font-weight:750;color:var(--text);margin-bottom:6px">Cetus CLMM liquidity manager</div>'
        '<div style="font-size:.78rem;color:var(--text2);line-height:1.55">Auto-swaps SUI/USDSUI, opens LP range, watches SUI volatility, and rebalances when volatility crosses 0.20% per poll.</div>'
        '</button>'
        '<button type="button" onclick="selectAgentTab(\'usdc\')" style="text-align:left;background:var(--surface2);border:1px solid var(--border);border-radius:14px;padding:16px;cursor:pointer;color:inherit;font-family:inherit">'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);font-weight:800;margin-bottom:7px">USDC Agent</div>'
        '<div style="font-size:1rem;font-weight:750;color:var(--text);margin-bottom:6px">Send &amp; receive USDC</div>'
        '<div style="font-size:.78rem;color:var(--text2);line-height:1.55">Dedicated SUI wallet for native USDC transfers with dry-run mode, send cap, daily cap, and allowlist safety.</div>'
        '</button>'
        '</div>'
        '</div>'
        '</div>'
        '<div id="agents-lp" class="agent-panel">'

        '<div class="chart-card">'
        '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
        '<h3 style="font-size:1.18rem;margin:0;color:var(--text)">LP Agent &mdash; Cetus CLMM (SUI)</h3>'
        '<span style="font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;'
        'padding:3px 9px;border-radius:999px;background:var(--surface3);color:var(--yellow);'
        'border:1px solid var(--border2)">Dry-run &middot; awaiting funding</span>'
        '</div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0 18px">'
        + ''.join(
            f'<div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:13px 15px">'
            f'<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:5px">{lbl}</div>'
            f'<div style="font-size:.95rem;font-weight:600;color:var(--text)">{val}</div></div>'
            for lbl, val in [
                ("Network", "SUI mainnet"),
                ("DEX", "Cetus CLMM"),
                ("Pair", "USDSUI / SUI"),
                ("Range", "&plusmn;10&ndash;25% (volatility-adaptive)"),
                ("Gas reserve", "3 SUI"),
                ("Mode", "DRY_RUN (safe)"),
                ("Rebalance trigger", "Vol &gt; 0.20% / poll"),
            ]
        )
        + '</div>'
        '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:14px">'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text3);margin-bottom:12px;font-weight:700">How it works</div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px">'
        + ''.join(
            f'<div style="background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:12px 13px">'
            f'<div style="font-size:.64rem;color:var(--accent);font-weight:800;letter-spacing:.05em;text-transform:uppercase;margin-bottom:5px">{step}</div>'
            f'<div style="font-size:.82rem;color:var(--text);font-weight:700;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:.72rem;color:var(--text2);line-height:1.5">{body}</div></div>'
            for step, title, body in [
                ("01", "Read pool price", "Checks the live USDSUI/SUI Cetus pool and current wallet balance."),
                ("02", "Keep gas safe", "Leaves 3 SUI untouched so the wallet can always pay transaction gas."),
                ("03", "Auto-swap", "Uses deployable SUI, swaps part into USDSUI, then prepares both sides."),
                ("04", "Open LP range", "Deposits into a concentrated liquidity band around current price."),
                ("05", "Watch + rebalance", "Calculates SUI realized volatility; if it is above 0.20% per poll, it closes and reopens."),
                ("06", "Risk gates", "Dry-run, capital cap, slippage cap, and daily rebalance limit protect it."),
            ]
        )
        + '</div></div>'
        '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px 16px">'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:6px">Agent wallet</div>'
        f'<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;color:var(--accent2);'
        f'word-break:break-all;line-height:1.5">{LP_WALLET}</div>'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin:12px 0 6px">Pool</div>'
        f'<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;color:var(--text2);'
        f'word-break:break-all;line-height:1.5">{LP_POOL}</div>'
        '</div>'
        '<div class="chart-card">'
        '<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:12px">'
        '<div><h3 style="font-size:1.18rem;margin:0 0 6px;color:var(--text)">LP Backtest &mdash; Adjustable SUI Volatility Trigger</h3>'
        '<p style="margin:0;color:var(--text2);font-size:.82rem;line-height:1.6">Change the settings by hand to see when the LP bot would rebalance. Data = recent SUI 1-minute candles.</p></div>'
        '<span style="font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:4px 10px;border-radius:999px;background:var(--surface3);color:var(--yellow);border:1px solid var(--border2)">Interactive</span>'
        '</div>'
        '<div class="bt-controls">'
        '<div class="bt-field"><label>Lookback</label><select id="bt-days" onchange="renderLpBacktest()"><option value="1">1 day</option><option value="3">3 days</option><option value="7" selected>7 days</option></select></div>'
        '<div class="bt-field"><label>Vol window / polls</label><input id="bt-window" type="number" min="5" max="240" step="1" value="30" oninput="renderLpBacktest()"></div>'
        '<div class="bt-field"><label>Threshold % / poll</label><input id="bt-threshold" type="number" min="0.01" max="2" step="0.01" value="0.20" oninput="renderLpBacktest()"></div>'
        '<div class="bt-field"><label>Daily cap</label><input id="bt-cap" type="number" min="1" max="50" step="1" value="6" oninput="renderLpBacktest()"></div>'
        '<div class="bt-field"><label>Min range %</label><select id="bt-min-range" onchange="renderLpBacktest()"><option value="0">0</option><option value="5">5</option><option value="10" selected>10</option><option value="15">15</option><option value="20">20</option><option value="25">25</option></select></div>'
        '<div class="bt-field"><label>Max range %</label><select id="bt-max-range" onchange="renderLpBacktest()"><option value="5">5</option><option value="10">10</option><option value="15">15</option><option value="20">20</option><option value="25" selected>25</option><option value="30">30</option><option value="35">35</option><option value="40">40</option><option value="45">45</option><option value="50">50</option></select></div>'
        '</div>'
        '<div class="bt-metrics">'
        '<div class="bt-metric"><span>Avg vol</span><span id="bt-avg">—</span></div>'
        '<div class="bt-metric"><span>Max vol</span><span id="bt-max">—</span></div>'
        '<div class="bt-metric"><span>Above threshold</span><span id="bt-spikes">—</span></div>'
        '<div class="bt-metric"><span>Rebalances</span><span id="bt-rebalances">—</span></div>'
        '<div class="bt-metric"><span>Avg range</span><span id="bt-avg-range">—</span></div>'
        '<div class="bt-metric"><span>Latest range</span><span id="bt-latest-range">—</span></div>'
        '<div class="bt-metric"><span>Widen / normal</span><span id="bt-actions">—</span></div>'
        '</div>'
        '<div class="bt-toggles">'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="0" checked onchange="applyLpBacktestVisibility()">Price</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="1" checked onchange="applyLpBacktestVisibility()">Range upper</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="2" checked onchange="applyLpBacktestVisibility()">Range lower</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="3" onchange="applyLpBacktestVisibility()">Volatility</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="4" checked onchange="applyLpBacktestVisibility()">Threshold</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="5" checked onchange="applyLpBacktestVisibility()">Widen</label>'
        '<label class="bt-toggle"><input type="checkbox" data-bt-ds="6" checked onchange="applyLpBacktestVisibility()">Normalize</label>'
        '<button type="button" class="bt-toggle" onclick="resetLpZoom()" style="cursor:pointer;border:none">&#8634; Reset zoom</button>'
        '</div>'
        '<div class="bt-chart-wrap"><canvas id="lp-backtest-chart"></canvas></div>'
        '<p style="margin:12px 0 0;color:var(--text3);font-size:.72rem;line-height:1.6">Note: this is a signal backtest, not P&amp;L. Purple band = the active LP position range. It stays fixed after deposit. Orange ▲ = volatility-triggered symmetric widen around the same center. Green ▼ = volatility-triggered symmetric normalize/shorten around the same center. If price leaves the band, it is allowed to stay out of range; no automatic recenter or price-following shift.</p>'
        '</div>'
        '</div>'
        '</div>'

        '<div id="agents-usdc" class="agent-panel">'
        '<div class="chart-card">'
        '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
        '<h3 style="font-size:1.18rem;margin:0;color:var(--text)">USDC Agent &mdash; Send &amp; Receive (SUI)</h3>'
        '<span style="font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;'
        'padding:3px 9px;border-radius:999px;background:var(--surface3);color:var(--yellow);'
        'border:1px solid var(--border2)">Dry-run &middot; awaiting funding</span>'
        '</div>'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0 18px">'
        + ''.join(
            f'<div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:13px 15px">'
            f'<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:5px">{lbl}</div>'
            f'<div style="font-size:.95rem;font-weight:600;color:var(--text)">{val}</div></div>'
            for lbl, val in [
                ("Network", "SUI mainnet"),
                ("Token", "USDC (native)"),
                ("Functions", "Send + Receive"),
                ("Per-send cap", "10 USDC"),
                ("Daily cap", "50 USDC"),
                ("Mode", "DRY_RUN (safe)"),
            ]
        )
        + '</div>'
        '<div style="background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px 16px">'
        '<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:6px">Receive address</div>'
        '<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;color:var(--accent2);'
        'word-break:break-all;line-height:1.5">0xUSDC_WALLET_REDACTED</div>'
        '</div>'
        '</div>'
        '</div>'
    )

    lp_backtest_js = """
const LP_BACKTEST_DATA = __LP_BACKTEST_DATA__;
let lpBacktestChart = null;
function _btMean(a){ return a.reduce((s,x)=>s+x,0)/(a.length||1); }
function _btStd(a){ if(a.length<2) return null; const m=_btMean(a); const v=a.reduce((s,x)=>s+(x-m)*(x-m),0)/(a.length-1); return Math.sqrt(v); }
function _btDayKey(ms){ return new Date(ms).toISOString().slice(0,10); }
function _btClamp(x, lo, hi){ return Math.max(lo, Math.min(hi, x)); }
function _btStep5(x){ return Math.round(x * 20) / 20; }
function resetLpZoom(){
  const canvas = document.getElementById('lp-backtest-chart');
  const chart = canvas && window.Chart ? Chart.getChart(canvas) : lpBacktestChart;
  if(chart && chart.resetZoom) chart.resetZoom();
}
function applyLpBacktestVisibility(){
  const canvas = document.getElementById('lp-backtest-chart');
  const chart = canvas && window.Chart ? Chart.getChart(canvas) : lpBacktestChart;
  if(!chart) return;
  document.querySelectorAll('[data-bt-ds]').forEach(cb => {
    const idx = Number(cb.dataset.btDs);
    chart.setDatasetVisibility(idx, cb.checked);
  });
  chart.update();
}
function renderLpBacktest(){
  const canvas = document.getElementById('lp-backtest-chart');
  if(!canvas || !window.Chart || !LP_BACKTEST_DATA.length) return;
  const days = Math.max(1, Number(document.getElementById('bt-days')?.value || 7));
  const win = Math.max(5, Math.min(240, Number(document.getElementById('bt-window')?.value || 30)));
  const threshold = Math.max(0.0001, Number(document.getElementById('bt-threshold')?.value || 0.20) / 100);
  const cap = Math.max(1, Number(document.getElementById('bt-cap')?.value || 6));
  const minRange = Math.max(0.001, Number(document.getElementById('bt-min-range')?.value || 10) / 100);
  const maxRange = Math.max(minRange + 0.001, Number(document.getElementById('bt-max-range')?.value || 25) / 100);
  const lastT = LP_BACKTEST_DATA[LP_BACKTEST_DATA.length-1].t;
  const cutoff = lastT - days*24*60*60*1000;
  const rows = LP_BACKTEST_DATA.filter(r => r.t >= cutoff);
  const vols = [];
  for(let i=0;i<rows.length;i++){
    const start = Math.max(0, i-win+1);
    const samp = rows.slice(start, i+1).map(r=>r.p);
    if(samp.length < Math.min(8, win)){ vols.push(null); continue; }
    const rets=[];
    for(let j=1;j<samp.length;j++) if(samp[j-1]>0 && samp[j]>0) rets.push(Math.log(samp[j]/samp[j-1]));
    vols.push(_btStd(rets));
  }
  const volTriggers = vols.map(v => v !== null && v > threshold);
  const desiredRangePct = vols.map(v => v === null ? minRange : _btStep5(_btClamp(minRange + Math.max(0, (v / threshold) - 1) * 0.10, minRange, maxRange)));
  const rangeUpper = [];
  const rangeLower = [];
  const activeRangePct = [];
  const rb = [];
  const rbKind = [];
  const dayCount = {};
  const rangeDrift = 0.35;
  let activeUpper = null;
  let activeLower = null;
  let activeCenter = null;
  let activePct = minRange;
  for(let i=0;i<rows.length;i++){
    const priceNow = rows[i].p;
    if(activeUpper === null || activeLower === null){
      activeCenter = priceNow;
      activePct = desiredRangePct[i];
      activeUpper = activeCenter * (1 + activePct);
      activeLower = activeCenter * (1 - activePct);
      rb.push(false);
      rbKind.push('open');
    }else{
      const prevPct = activePct;
      const volHigh = volTriggers[i];
      const widenNeeded = volHigh && desiredRangePct[i] > activePct * (1 + 0.01);
      const calmNormalize = vols[i] !== null && vols[i] <= threshold && desiredRangePct[i] < activePct / (1 + rangeDrift);
      const shouldRebalance = widenNeeded || calmNormalize;
      const k = _btDayKey(rows[i].t);
      dayCount[k] = dayCount[k] || 0;
      if(shouldRebalance && dayCount[k] < cap){
        dayCount[k]++;
        activePct = desiredRangePct[i];
        activeUpper = activeCenter * (1 + activePct);
        activeLower = activeCenter * (1 - activePct);
        rb.push(true);
        if(activePct > prevPct * (1 + 0.01)) rbKind.push('widen');
        else if(activePct < prevPct / (1 + rangeDrift)) rbKind.push('normalize');
        else rbKind.push('widen');
      }else{
        rb.push(false);
        rbKind.push('hold');
      }
    }
    rangeUpper.push(activeUpper);
    rangeLower.push(activeLower);
    activeRangePct.push(activePct);
  }
  const validRanges = activeRangePct.filter(v => Number.isFinite(v));
  const valid = vols.filter(v=>v!==null);
  const avg = valid.length ? _btMean(valid) : 0;
  const mx = valid.length ? Math.max(...valid) : 0;
  const spikeN = volTriggers.filter(Boolean).length;
  const rbN = rb.filter(Boolean).length;
  const widenN = rbKind.filter(k=>k==='widen').length;
  const normalizeN = rbKind.filter(k=>k==='normalize').length;
  const pct = valid.length ? spikeN/valid.length*100 : 0;
  const set = (id, txt) => { const el=document.getElementById(id); if(el) el.textContent=txt; };
  set('bt-avg', (avg*100).toFixed(3)+'%');
  set('bt-max', (mx*100).toFixed(3)+'%');
  set('bt-spikes', spikeN + ' (' + pct.toFixed(2) + '%)');
  set('bt-rebalances', String(rbN));
  set('bt-avg-range', '±' + (_btMean(validRanges)*100).toFixed(1) + '%');
  set('bt-latest-range', '±' + ((activeRangePct[activeRangePct.length-1] || minRange)*100).toFixed(1) + '%');
  set('bt-actions', widenN + ' / ' + normalizeN);
  const labels = rows.map(r => new Date(r.t).toLocaleString('en-US',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}));
  const price = rows.map(r=>r.p);
  const volPct = vols.map(v=>v===null?null:v*100);
  const thPct = rows.map(_=>threshold*100);
  const widenPts = rows.map((r,i)=> rbKind[i] === 'widen' ? {x:i, y:price[i]} : null).filter(Boolean);
  const normalizePts = rows.map((r,i)=> rbKind[i] === 'normalize' ? {x:i, y:price[i]} : null).filter(Boolean);
  const cfg = {
    type:'line',
    data:{labels,datasets:[
      {label:'SUI price', data:price, yAxisID:'y', borderColor:'#4da2ff', backgroundColor:'#4da2ff33', borderWidth:2, pointRadius:0, tension:.18},
      {label:'LP range upper', data:rangeUpper, yAxisID:'y', borderColor:'#bc7def', backgroundColor:'#bc7def12', borderWidth:1.5, pointRadius:0, tension:.18, borderDash:[4,4]},
      {label:'LP range lower', data:rangeLower, yAxisID:'y', borderColor:'#bc7def', backgroundColor:'#bc7def12', borderWidth:1.5, pointRadius:0, tension:.18, borderDash:[4,4], fill:'-1'},
      {label:'Calculated vol %', data:volPct, yAxisID:'y1', borderColor:'#34d399', backgroundColor:'#34d39933', borderWidth:2, pointRadius:0, tension:.18},
      {label:'Threshold %', data:thPct, yAxisID:'y1', borderColor:'#fbbf24', borderWidth:2, pointRadius:0, borderDash:[6,5]},
      {label:'Widen range ▲', data:widenPts, type:'scatter', yAxisID:'y', parsing:false, pointRadius:5, pointHoverRadius:7, pointStyle:'triangle', rotation:0, backgroundColor:'#fb923c', borderColor:'#fff', borderWidth:1},
      {label:'Normalize / shorten ▼', data:normalizePts, type:'scatter', yAxisID:'y', parsing:false, pointRadius:5, pointHoverRadius:7, pointStyle:'triangle', rotation:180, backgroundColor:'#22c55e', borderColor:'#fff', borderWidth:1}
    ]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},zoom:{limits:{x:{minRange:60*60*1000}},pan:{enabled:true,mode:'x',modifierKey:'ctrl'},zoom:{wheel:{enabled:true},pinch:{enabled:true},drag:{enabled:true,backgroundColor:'rgba(99,102,241,0.18)',borderColor:'rgba(99,102,241,0.6)',borderWidth:1},mode:'x'}},tooltip:{callbacks:{label:(ctx)=> ctx.dataset.label==='Calculated vol %'||ctx.dataset.label==='Threshold %' ? ctx.dataset.label+': '+Number(ctx.parsed.y).toFixed(3)+'%' : ctx.dataset.label+': '+Number(ctx.parsed.y).toFixed(4)}}},scales:{x:{ticks:{color:'#94a3b8',maxTicksLimit:7},grid:{color:'#1f2937'}},y:{position:'left',ticks:{color:'#94a3b8'},grid:{color:'#1f2937'}},y1:{position:'right',ticks:{color:'#94a3b8',callback:v=>v+'%'},grid:{drawOnChartArea:false}}}}
  };
  if(lpBacktestChart){ lpBacktestChart.destroy(); }
  lpBacktestChart = new Chart(canvas.getContext('2d'), cfg);
  applyLpBacktestVisibility();
}
""".replace('__LP_BACKTEST_DATA__', lp_backtest_data)

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">\n'
        '<title>Portfolio Dashboard</title>\n'
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js" integrity="sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
        '<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js" integrity="sha384-Cs3dgUx6+jDxxuqHvVH8Onpyj2LF1gKZurLDlhqzuJmUqVYMJ0THTWpxK5Z086Zm" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
        '<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js" integrity="sha384-zPzbVRXfR492Sd5D+HydTYCxxgHAfgVO8KERbLlpeH5unsmbAEXrscGUUqLZG9BM" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
        '<script src="https://cdn.jsdelivr.net/npm/marked@14.1.4/marked.min.js" integrity="sha384-lqPzN0kmFw9t2syAMwVPM4VbAyqsz/lPyYWbb2Xt6nSPM0WPNrpSWCUBgdcAdgnC" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
        '<script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.7/dist/purify.min.js" integrity="sha384-XQqX/4yiUGu+oyr87jvWzRuqBUK/adrY0DunhL+tID9m/9dwSpV8h9Fk/Sg6ifVQ" crossorigin="anonymous" referrerpolicy="no-referrer"></script>\n'
        '<style>' + CSS + '</style>\n'
        '</head>\n<body>\n\n'
        '<nav class="top-nav">\n'
        '  <div class="nav-left">\n'
        '  <div class="nav-brand" onclick="goToMarket()" role="button" tabindex="0" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();goToMarket()}">Kive <span style="color:#bc7def">Dashboard</span></div>\n'
        '  <div class="page-menu" id="page-menu" role="tablist" aria-label="Dashboard sections">\n'
        '    <button type="button" class="page-menu-item active" id="page-menu-market" role="tab" aria-selected="true" data-page="market" onclick="selectPage(\'market\')">Market</button>\n'
        '    <button type="button" class="page-menu-item" role="tab" aria-selected="false" data-page="overview" onclick="selectPage(\'overview\')">Overview</button>\n'
        '    <button type="button" class="page-menu-item" role="tab" aria-selected="false" data-page="agents" onclick="selectPage(\'agents\')">Agents</button>\n'
        '  </div></div>\n'
        f'  <div class="nav-right"><div class="nav-ts" id="nav-ts" data-updated="{updated_epoch}">Updated</div>\n'
        '  <button id="privacy-btn" class="nav-refresh-btn" onclick="togglePrivacy()" title="Hide numbers" aria-label="Toggle balance visibility"><span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg></span></button>\n'
        '  <button id="refresh-btn" class="nav-refresh-btn" onclick="triggerRefresh()" title="Refresh" aria-label="Refresh data"><span>&#8635;</span></button>\n'
        '  </div>\n'
        '</nav>\n\n'
        '<div id="page-market" class="page active">\n' + market_page_html + '\n</div>\n\n'
        '<div id="page-overview" class="page">\n' + page1 + '\n</div>\n\n'
        '<div id="page-agents" class="page">\n' + agents_page_html + '\n</div>\n\n'
        '<div id="modal-ov" class="modal-ov" onclick="closeModal()">\n'
        '  <div class="modal-box" onclick="event.stopPropagation()">\n'
        '    <div id="modal-inner"></div>\n'
        '  </div>\n'
        '</div>\n\n'
        + stock_modals + '\n\n'
        + modals_html + '\n\n'
        '<script>\n' + JS + '\n' + chart_js + '\n' + lp_backtest_js + '\n</script>\n'
        '</body>\n</html>'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main(write_history=False):
    print("=" * 54)
    print("  Portfolio Dashboard Generator")
    print("=" * 54)

    print("\n[1/7] Fetching prices ...")
    prices = fetch_all_prices()
    sui  = prices["SUI"]
    wal  = prices["WAL"]
    cetus = prices["CETUS"]

    print("[2/7] Fetching LST ratios from DexScreener ...")
    vsui_ratio    = price_in_sui(PAIRS["vSUI/SUI"])    or 1.0
    ssui_ratio    = price_in_sui(PAIRS["sSUI/SUI"])    or 1.0
    hasui_ratio   = price_in_sui(PAIRS["haSUI/SUI"])   or 1.0
    usdsui_ratio  = price_in_sui(PAIRS["USDSUI/USDC"]) or 1.0
    suiusdt_ratio = price_in_sui(PAIRS["suiUSDT/USDC"]) or 1.0
    prices["vSUI"]   = vsui_ratio * sui
    prices["sSUI"]   = ssui_ratio * sui
    prices["HASUI"]  = hasui_ratio * sui
    prices["USDSUI"] = usdsui_ratio
    prices["USDT"]   = suiusdt_ratio

    print("[3/7] Fetching Aftermath SUI/USDC 80/20 position (0x954c) ...")
    amm_8020 = fetch_aftermath_sui_usdc(sui, prices.get("AFSUI", sui))

    print("[3b/7] Fetching NAVI vSUI/USDSUI position (0x954c) ...")
    navi = fetch_navi(prices)

    print("[4/7] Fetching Suilend on-chain data ...")
    sl_deps, sl_borrs, sl_proto = fetch_suilend(prices)

    # Correct LTV params: DEEP and WAL are 30% open / 36% liq threshold
    _SUILEND_LTV = {"DEEP": (0.30, 0.36), "WAL": (0.30, 0.36)}

    def _sl_open_ltv(dep):
        return _SUILEND_LTV[dep["sym"]][0] if dep["sym"] in _SUILEND_LTV else dep.get("open_ltv", 0)

    def _sl_close_ltv(dep):
        return _SUILEND_LTV[dep["sym"]][1] if dep["sym"] in _SUILEND_LTV else dep.get("close_ltv", 0)

    def _sl_usd(dep):
        return dep["amount"] * sui if dep["sym"] == "sSUI" else dep["usd"]

    # SteammFi LP is in an isolated market — excluded from lending risk calcs
    sl_risk_deps   = [d for d in sl_deps if "SteammFi LP" not in d.get("sym", "")]

    sl_col  = sum(d["usd"] for d in sl_deps)   # display total (includes LP)
    sl_debt = sum(b["usd"] for b in sl_borrs)
    # SteammFi LP is already counted in amm_total — exclude from net to avoid double-count
    sl_col_for_net = sum(d["usd"] for d in sl_deps if "SteammFi LP" not in d.get("sym", ""))
    sl_net  = sl_col_for_net - sl_debt
    sl_col_calc    = sum(_sl_usd(d) for d in sl_risk_deps)
    allowed_borrow = sum(_sl_usd(d) * _sl_open_ltv(d)  for d in sl_risk_deps)
    liq_capacity   = sum(_sl_usd(d) * _sl_close_ltv(d) for d in sl_risk_deps)
    sl_hf         = liq_capacity   / sl_debt     if sl_debt     > 0 else 99.0
    sl_ltv        = sl_debt        / sl_col_calc if sl_col_calc > 0 else 0
    sl_max_ltv    = allowed_borrow / sl_col_calc if sl_col_calc > 0 else 0.75
    sl_liq_thresh = liq_capacity   / sl_col_calc if sl_col_calc > 0 else 0.825

    print("[5/7] Fetching on-chain positions (0x954c) ...")
    wal_amt, wal_n  = fetch_walrus(WALLET_954C)
    wal_usd         = wal_amt * wal
    xcetus_amt      = fetch_xcetus(WALLET_954C)
    xcetus_usd      = xcetus_amt * cetus
    sc_supply       = fetch_scallop_supply(WALLET_954C, prices)
    sc_supply_usd   = sum(r["usd"] for r in sc_supply)
    sc_deps, sc_borrs = fetch_scallop_obligation(WALLET_954C, prices)
    sc_dep_usd  = sum(d["usd"] for d in sc_deps)
    sc_borr_usd = sum(b["usd"] for b in sc_borrs)
    sc_net      = sc_supply_usd + sc_dep_usd - sc_borr_usd

    print("[5a/8] Fetching lending rewards (NAVX/SEND/SCA) ...")
    lending_rewards = fetch_lending_rewards(WALLET_954C, prices)

    print("[5b/8] Fetching Ember eBLUE vault position ...")
    ember = fetch_ember_eblue(prices.get("BLUE", 0))

    print("[5c/10] Fetching Zentry (stZENT) ...")
    stzent = fetch_eth_stzent(prices.get("ZENT", 0))

    onchain_total = wal_usd + xcetus_usd + ember["blue_usd"] + stzent["zent_usd"]

    print("[6/10] Fetching Binance Futures + Loan ...")
    try:
        qr = requests.get("https://api.coingecko.com/api/v3/simple/price",
                          params={"ids": "quant-network", "vs_currencies": "usd"}, timeout=15)
        prices["QNT"] = qr.json().get("quant-network", {}).get("usd", 0)
    except Exception:
        prices["QNT"] = 0
    binance = fetch_binance(prices)

    print("[7/10] Fetching Aftermath LBTC/lzWBTC position (0xe64c) ...")
    aftermath = fetch_aftermath_lbtcwbtc(prices.get("BTC", 0), prices.get("DEEP", 0))

    print("[8/10] Fetching Cetus CLMM positions (0xe64c) ...")
    clmm_e64c_list  = fetch_cetus_clmm(WALLET_E64C, sui)
    clmm_e64c_total = sum(p["total_usd"] for p in clmm_e64c_list)

    print("[8b/10] Fetching Bluefin CLMM positions (0xe64c) ...")
    bluefin_clmm_list  = fetch_bluefin_clmm(WALLET_E64C, prices)
    bluefin_clmm_total = sum(p["total_usd"] for p in bluefin_clmm_list)

    total_5050 = sl_proto.get("steamm_lp", {}).get("usd", 0.0)

    print("[9/10] Fetching stock prices ...")
    stocks = load_stocks()
    fetch_stock_prices(stocks)
    save_stocks(stocks)

    amm_total     = amm_8020["total"] + total_5050 + aftermath["total"] + clmm_e64c_total + bluefin_clmm_total
    lending_total = navi["net"] + sl_net + sc_net
    cex_total     = binance["futures_margin"]
    stocks_total  = sum(s.get("market_value", 0) for s in stocks)
    crypto_total  = amm_total + lending_total + onchain_total + cex_total
    grand_total   = crypto_total + stocks_total

    # Append to history only when explicitly requested (via update_weekly.py at 23:45)
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    if write_history:
        entry = {"date": today, "crypto": round(crypto_total, 2), "stock": round(stocks_total, 2), "total": round(grand_total, 2)}
        if history and history[-1]["date"] == today:
            history[-1] = entry
        else:
            history.append(entry)
        save_history(history)

    data = {
        "prices":    prices,
        "timestamp": datetime.now(BANGKOK_TZ).strftime("%H:%M  %d-%m-%y"),
        "grand_total":    grand_total,
        "amm_total":      amm_total,
        "lending_total":  lending_total,
        "onchain_total":  onchain_total,
        "clmm_e64c_total":    clmm_e64c_total,
        "bluefin_clmm_total": bluefin_clmm_total,
        "cex_total":      cex_total,
        "amm_8020": amm_8020,
        "amm_5050": {
            "total": total_5050,
            "stable": sl_proto.get("steamm_lp", {}).get("usdc_amt", 0.0),
            "risky":  sl_proto.get("steamm_lp", {}).get("wal_amt",  0.0),
        },
        "navi": navi,
        "suilend": {"deposits": sl_deps, "borrows": sl_borrs, "net": sl_net,
                    "health_factor": sl_hf, "ltv": sl_ltv, "borrow_cap": allowed_borrow,
                    "max_ltv": sl_max_ltv, "liq_threshold": sl_liq_thresh, "proto": sl_proto},
        "onchain_954c": {"wal_amt": wal_amt, "wal_usd": wal_usd, "wal_positions": wal_n,
                         "xcetus_amt": xcetus_amt, "xcetus_usd": xcetus_usd,
                         "sc_supply": sc_supply, "sc_deps": sc_deps, "sc_borrs": sc_borrs,
                         "sc_net": sc_net},
        "clmm_e64c":    clmm_e64c_list,
        "bluefin_clmm": bluefin_clmm_list,
        "aftermath": aftermath,
        "ember": ember,
        "stzent": stzent,
        "binance": binance,
        "lending_rewards": lending_rewards,
        "stocks":       stocks,
        "stocks_total": stocks_total,
        "history":      history,
        "lending_total_with_bn_loan": lending_total + binance.get("loan_net", 0),
    }

    print("[10/10] Generating HTML ...")
    html = build_html(data)
    out  = Path(__file__).parent / "portfolio_dashboard.html"
    out.write_text(html)

    print(f"\n{'='*54}")
    print(f"  Dashboard saved -> {out.name}")
    print(f"  Grand Total      {fmt(grand_total)}  (Stocks: {fmt(stocks_total)})")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-history", action="store_true",
                        help="Append today's totals to history.json (run by update_weekly.py only)")
    args = parser.parse_args()
    main(write_history=args.save_history)
