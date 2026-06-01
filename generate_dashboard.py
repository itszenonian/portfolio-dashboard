
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
import requests
from datetime import datetime
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
CETUS_POS_TYPE = "0x1eabed72c53feb3805120a081dc15963c204dc8d091542592abaf7a35689b2fb::position::Position"

COIN_DEC = {"USDC": 6, "USDT": 6, "DEEP": 6, "ETH": 8, "WBTC": 8, "LBTC": 8}

# NAVI protocol — global storage + per-reserve user_state tables
NAVI_RESERVES_TABLE    = "0xe6d4c6610b86ce7735ea754596d71d72d10c7980b5052fc3c8cdf8d09fea9b4b"
NAVI_VSUI_SUPPLY_TABLE = "0xe6457d247b6661b1cac123351998f88f3e724ff6e9ea542127b5dcb3176b3841"
NAVI_USDSUI_BORROW_TABLE = "0xdc9b3a385ea7c6dc443235db7ff9d82188a3e6f5b9af6e765ad9577d39c0af67"
NAVI_VSUI_IDX   = 5
NAVI_USDSUI_IDX = 34

# Aftermath SUI/USDC 80/20 (wallet 0x954c — staked LP)
AFTER_SUIUSDC_STAKE_ID = "0x391643800554dcf6d2747e47ea4f9e2473e813d97ab1b60175d48e3c731cbd6f"
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
            return {
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
                "BTC":   btc, "WBTC": btc, "LBTC": btc,
                "AFSUI": d.get("aftermath-staked-sui", {}).get("usd", 0),
            }
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
    ids = [sym_id[s] for s, _ in sc_tokens if s in sym_id]
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
        rate  = rates.get(underlying)
        if rate is None: continue
        dec   = COIN_DEC.get(underlying, 9)
        amt   = raw_sc * rate / (10 ** dec)
        price = prices.get(underlying)
        usd   = amt * price if price else None
        if usd and usd >= 0.01:
            rows.append({"sym": underlying, "amount": amt, "usd": usd})
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

def fetch_cetus_clmm(wallet, sui_price):
    found   = find_objects(wallet, CETUS_POS_TYPE.split("::")[-1])

    # also scan for the exact type
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
        tick_lower = decode_i32(int(pf["tick_lower_index"]["fields"]["bits"]))
        tick_upper = decode_i32(int(pf["tick_upper_index"]["fields"]["bits"]))
        sym_a = pf["coin_type_a"]["fields"]["name"].split("::")[-1]
        sym_b = pf["coin_type_b"]["fields"]["name"].split("::")[-1]

        pool   = rpc("sui_getObject", [pool_id, {"showContent": True}])
        pool_f = pool["data"]["content"]["fields"]
        sqrt_q64     = int(pool_f["current_sqrt_price"])
        current_tick = decode_i32(int(pool_f["current_tick_index"]["fields"]["bits"]))

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

        dec_adj       = 10**dec_a / 10**dec_b
        price_sui_per_a = (sqrt_P ** 2) * dec_adj
        price_now     = 1 / price_sui_per_a
        p_lower       = 1 / ((1.0001 ** tick_upper) * dec_adj)
        p_upper       = 1 / ((1.0001 ** tick_lower) * dec_adj)

        price_a_usd = 1.0        # USDSUI stablecoin
        price_b_usd = sui_price
        total_usd   = amt_a * price_a_usd + amt_b * price_b_usd
        in_range    = tick_lower <= current_tick <= tick_upper

        results.append({
            "name":      pf.get("name", f"{sym_b}/{sym_a}"),
            "pool_id":   pool_id,
            "sym_a":     sym_a, "sym_b": sym_b,
            "amt_a":     amt_a, "amt_b": amt_b,
            "usd_a":     amt_a * price_a_usd,
            "usd_b":     amt_b * price_b_usd,
            "total_usd": total_usd,
            "price_now": price_now,
            "p_lower":   p_lower,
            "p_upper":   p_upper,
            "in_range":  in_range,
        })
    return results


# ── Aftermath Finance: SUI/USDC 80/20 staked LP ──────────────────────────────

def fetch_aftermath_sui_usdc(sui_price: float, afsui_price: float) -> dict:
    sp = rpc("sui_getObject", [AFTER_SUIUSDC_STAKE_ID, {"showContent": True}])
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
    a  = data["amm_8020"]
    b  = data["amm_5050"]
    n  = data["navi"]
    sl = data["suilend"]
    oc = data["onchain_954c"]
    positions = []

    # 1. Aftermath 80/20
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

    # 2. SteammFi 50/50 (live data from fetch_suilend)
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
        "stats": [],
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
        "stats": [],
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
        for d in oc["sc_deps"]:
            sc_modal.append({"sym": d["sym"], "amount": d["amount"], "usd": d["usd"]})
    if oc["sc_borrs"]:
        sc_modal.append({"section": "Borrows"})
        for bv in oc["sc_borrs"]:
            sc_modal.append({"sym": bv["sym"], "amount": bv["amount"], "usd": bv["usd"], "is_debt": True})
    sc_card_rows = (
        [(r["sym"], f"{r['amount']:,.4f}", False) for r in oc["sc_supply"][:1]] +
        [(d["sym"], f"{d['amount']:,.4f}", False) for d in oc["sc_deps"][:2]] +
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
        "stats": [], "range_info": None, "status": None, "status_color": None,
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
            ],
            "stats": [],
            "range_info": f"Range  {pos['p_lower']:.4f} — {pos['p_upper']:.4f}  |  Now {pos['price_now']:.4f}",
            "status": "IN RANGE" if pos["in_range"] else "OUT OF RANGE",
            "status_color": sc2,
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
    elif pos.get("stats"):
        items = "".join(
            f'<div class="ls-item"><span>{s["label"]}</span>'
            f'<span style="color:{s["color"]}">{s["value"]}</span></div>'
            for s in pos["stats"]
        )
        stats_html = f'<div class="md-stats">{items}</div>'
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

    _NORM = {"WBTC": "BTC", "LBTC": "BTC", "HAWAL": "WAL", "WWAL": "WAL",
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
        f'<div class="pos-card" style="border-top:3px solid {color};cursor:pointer" onclick="{onclick}">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
        f'<div>'
        f'<div style="font-weight:700;font-size:.95rem;color:#f1f5f9">{s["ticker"]}</div>'
        f'<div style="font-size:.68rem;color:#64748b">{exch} &middot; {stype}</div>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<div style="font-size:.82rem;font-weight:600;color:#f1f5f9">${s.get("market_value",0):,.0f}</div>'
        f'<div style="font-size:.64rem;color:{gc}">{gsign}{gain:.1f}%</div>'
        f'</div></div>'
        f'<div style="font-size:.72rem;color:#94a3b8;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
        f'{s.get("name", s["ticker"])}</div>'
        f'<div style="display:flex;justify-content:space-between;font-size:.72rem">'
        f'<span style="color:#64748b">{s["shares"]:,.2f} sh @ {csym}{s["avg_cost"]:,.2f}</span>'
        f'<span style="color:{dc}">{dsign}{daily:.1f}%<span style="color:#475569"> 1d</span></span>'
        f'</div>'
        f'<div style="font-size:.68rem;color:#6366f1;font-weight:600;margin-top:4px">&#9998; Edit</div>'
        f'</div>'
    )


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(data):
    p      = data["prices"]
    ts     = data["timestamp"]
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
        for s in stocks:
            is_us  = s.get("currency", "USD") == "USD"
            csym   = "$" if is_us else "฿"
            gain   = s.get("pct_chg", 0)
            gc     = "#10b981" if gain >= 0 else "#f87171"
            gsign  = "+" if gain >= 0 else ""
            rows += (
                f'<tr>'
                f'<td class="ts-sym">{s["ticker"]}</td>'
                f'<td class="ts-price">{csym}{s.get("price",0):,.2f}</td>'
                f'<td class="ts-num">{s.get("shares",0):,.2f} sh</td>'
                f'<td class="ts-usd">{fmt(s.get("market_value",0))}'
                f'<span style="font-size:.6rem;color:{gc};margin-left:4px">{gsign}{gain:.1f}%</span>'
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

    proto_labels = ["Aftermath 80/20", "Aftermath LBTC/WBTC", "SteammFi 50/50",
                    "NAVI", "Suilend", "Walrus", "xCETUS", "Scallop"]
    proto_values = [
        round(data["amm_8020"]["total"], 2), round(af["total"], 2),
        round(data["amm_5050"]["total"], 2),
        round(n["net"], 2), round(sl["net"], 2),
        round(oc["wal_usd"], 2), round(oc["xcetus_usd"], 2), round(oc["sc_net"], 2),
    ]
    for pos in data["clmm_e64c"]:
        proto_labels.insert(3, f"Cetus CLMM ({pos['sym_b']}/{pos['sym_a']})")
        proto_values.insert(3, round(pos["total_usd"], 2))
    ember_usd = data.get("ember", {}).get("blue_usd", 0)
    if ember_usd > 0:
        proto_labels.append("Ember eBLUE")
        proto_values.append(round(ember_usd, 2))
    stzent_usd = data.get("stzent", {}).get("zent_usd", 0)
    if stzent_usd > 0:
        proto_labels.append("stZENT")
        proto_values.append(round(stzent_usd, 2))
    if cex_total > 0:
        proto_labels.append("Binance Futures")
        proto_values.append(round(cex_total, 2))
    if lending_bn != 0:
        proto_labels.append("Binance Loan")
        proto_values.append(round(lending_bn, 2))
    if stocks_total > 0:
        proto_labels.append("Stocks")
        proto_values.append(round(stocks_total, 2))

    proto_colors = ["#f97316","#fb923c","#06b6d4","#8b5cf6","#3b82f6","#f59e0b",
                    "#14b8a6","#a78bfa","#ec4899","#6366f1","#10b981","#eab308",
                    "#a855f7","#22d3ee","#84cc16"]
    proto_sorted   = sorted(zip(proto_values, proto_labels, proto_colors[:len(proto_values)]), reverse=True)
    proto_values   = [x[0] for x in proto_sorted]
    proto_labels   = [x[1] for x in proto_sorted]
    proto_colors   = [x[2] for x in proto_sorted]

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
            f'<td style="text-align:right;font-family:monospace;color:#e2e8f0">${main:,.2f}</td>'
            f'<td style="text-align:right;font-family:monospace;color:#60a5fa">${mm:,.2f}</td>'
            f'<td style="text-align:right;font-family:monospace;font-weight:600;color:#f1f5f9">${wk:,.2f}</td>'
            f'<td style="text-align:right;font-family:monospace;color:#64748b">${running:,.2f}</td>'
            f'<td style="text-align:right;font-family:monospace;color:{"#10b981" if yld and yld>=15 else "#f59e0b" if yld else "#475569"}">{yld_str}</td>'
            f'<td style="text-align:right;color:#64748b">{port_str}</td>'
            f'</tr>'
        )

    page3 = (
        f'<div class="stats-grid">'
        f'<div class="stat-card"><div class="sc-lbl">Cumulative Earned</div><div class="sc-val">${cumulative:,.2f}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Avg / Week</div><div class="sc-val">${avg_weekly:,.2f}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Avg Annual Yield</div><div class="sc-val">{avg_yield:.1f}%</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Best Week</div><div class="sc-val">${best_week_earn:,.2f}<div class="sc-lbl" style="margin-top:2px">{best_week[0]}</div></div></div>'
        f'</div>'
        f'<div class="charts-row">'
        f'<div class="chart-card"><h3>Weekly Earnings — Main vs MM</h3><canvas id="earn-bar"></canvas></div>'
        f'<div class="chart-card"><h3>Annualized Yield %</h3><canvas id="yield-line"></canvas></div>'
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
        f"      x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#475569', font: {{ size: 9 }}, maxRotation: 45 }} }},\n"
        f"      y: {{ stacked: true, grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#64748b', callback: v => '$' + v }} }}\n"
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
        f"      x: {{ grid: {{ display: false }}, ticks: {{ color: '#475569', font: {{ size: 9 }}, maxRotation: 45 }} }},\n"
        f"      y: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#64748b', callback: v => v + '%' }} }}\n"
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
        for s in stocks:
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
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0f18;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}

/* Nav */
.top-nav{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;background:#13162a;border-bottom:1px solid #ffffff0a;position:sticky;top:0;z-index:100;gap:16px;flex-wrap:wrap}
.nav-brand{font-size:.95rem;font-weight:700;color:#f1f5f9;white-space:nowrap;letter-spacing:.01em}
.tab-group{display:flex;gap:3px;background:#0d0f18;border-radius:8px;padding:3px}
.tab-btn{padding:7px 18px;border-radius:6px;border:none;background:transparent;color:#64748b;font-size:.82rem;font-weight:600;cursor:pointer;transition:all .15s;letter-spacing:.01em}
.tab-btn.active{background:#1e2235;color:#f1f5f9}
.tab-btn:hover:not(.active){color:#94a3b8}
.nav-right{display:flex;align-items:center;gap:14px}
.nav-total-wrap{display:flex;flex-direction:column;align-items:flex-end}
.nav-total-lbl{font-size:.6rem;color:#475569;text-transform:uppercase;letter-spacing:.08em;margin-bottom:1px}
.nav-total{font-size:1.2rem;font-weight:800;color:#f1f5f9;font-family:monospace}
.nav-ts{font-size:.65rem;color:#475569}
.nav-refresh-btn{padding:7px 14px;border-radius:7px;border:1px solid #ffffff14;background:transparent;color:#94a3b8;font-size:.78rem;font-weight:600;cursor:pointer;transition:all .15s;white-space:nowrap}
.nav-refresh-btn:hover:not(:disabled){background:#1e2235;color:#f1f5f9;border-color:#ffffff22}
.nav-refresh-btn:disabled{opacity:.45;cursor:not-allowed}

/* Pages */
.page{display:none;padding:24px;max-width:1200px;margin:0 auto}
.page.active{display:block}

/* Stats */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:#1a1d2e;border-radius:12px;padding:18px 20px;border-left:3px solid #ffffff08}
.sc-lbl{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em}
.sc-val{font-size:1.25rem;font-weight:700;color:#f1f5f9;margin-top:5px;font-family:monospace}
.sc-val.debt{color:#f87171}

/* Charts */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.chart-card{background:#1a1d2e;border-radius:12px;padding:20px}
.chart-card h3{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}
@media(max-width:640px){.charts-row{grid-template-columns:1fr}}

/* Allocation bars */
.alloc-card{background:#1a1d2e;border-radius:12px;padding:20px;margin-bottom:24px}
.alloc-card h3{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:16px}
.cat-row{margin-bottom:14px}
.cat-info{display:flex;justify-content:space-between;margin-bottom:5px}
.cat-lbl{font-size:.82rem;color:#94a3b8}
.cat-val{font-size:.82rem;font-weight:600;color:#f1f5f9;font-family:monospace}
.cat-bar{height:6px;border-radius:3px;background:#ffffff08;overflow:hidden}
.cat-fill{height:100%;border-radius:3px;transition:width .4s}

/* Token summary */
.ts-card{background:#1a1d2e;border-radius:12px;padding:20px;margin-bottom:24px}
.ts-sections{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}
@media(max-width:700px){.ts-sections{grid-template-columns:1fr}}
.ts-head{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #ffffff08}
.ts-head.debt{color:#f87171;border-bottom-color:#f8717118}
.ts-table{width:100%;border-collapse:collapse;font-size:.8rem}
.ts-table th{font-size:.62rem;color:#475569;text-transform:uppercase;padding-bottom:6px;border-bottom:1px solid #ffffff0a;text-align:left}
.ts-table th:not(:first-child){text-align:right}
.ts-table td{padding:5px 0;border-bottom:1px solid #ffffff04}
.ts-sym{color:#94a3b8;width:22%}
.ts-price{text-align:right;font-family:monospace;color:#64748b;width:22%}
.ts-num{text-align:right;font-family:monospace;color:#e2e8f0;width:30%}
.ts-usd{text-align:right;color:#64748b;width:26%}
.ts-total-lbl{color:#64748b;font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;padding-top:9px;border-top:1px solid #ffffff0f}
.ts-total-val{text-align:right;font-weight:700;color:#f1f5f9;font-family:monospace;font-size:.9rem;padding-top:9px;border-top:1px solid #ffffff0f}
.ts-total-val.debt{color:#f87171}

/* Risk cards */
.risk-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
@media(max-width:640px){.risk-row{grid-template-columns:1fr}}
.risk-card{background:#1a1d2e;border-radius:12px;padding:20px}
.rh{font-size:.82rem;font-weight:600;color:#f1f5f9;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.risk-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.rs-lbl{font-size:.65rem;color:#475569;text-transform:uppercase;margin-bottom:2px}
.rs-val{font-size:.82rem;font-weight:600;color:#cbd5e1;font-family:monospace}

/* Section label */
.section-label{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin:28px 0 12px;padding-left:10px;border-left:2px solid #ffffff18}

/* Position cards */
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;margin-bottom:8px}
.pos-card{background:#1a1d2e;border-radius:12px;padding:18px;cursor:pointer;transition:transform .15s,box-shadow .15s,background .15s;user-select:none;display:flex;flex-direction:column}
.pos-card:hover{transform:translateY(-2px);box-shadow:0 8px 28px #00000055;background:#1e2235}
.pc-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.pc-badges{display:flex;gap:6px;flex-wrap:wrap}
.pc-arrow{color:#334155;font-size:1rem;font-weight:700;transition:color .15s}
.pos-card:hover .pc-arrow{color:#64748b}
.badge{font-size:.67rem;padding:2px 8px;border-radius:999px;font-weight:600;letter-spacing:.01em}
.pc-title{font-size:.92rem;font-weight:700;color:#f1f5f9;margin-bottom:6px}
.pc-status{font-size:.68rem;font-weight:700;margin-bottom:6px}
.pc-tokens{margin-bottom:10px}
.pc-row{display:flex;justify-content:space-between;padding:3px 0;font-size:.78rem}
.pc-sym{color:#94a3b8}
.pc-val{font-family:monospace;color:#e2e8f0}
.pc-card-footer{display:flex;align-items:center;justify-content:space-between;padding-top:10px;border-top:1px solid #ffffff0f;margin-top:auto}
.pc-total{font-size:1.05rem;font-weight:700;color:#f1f5f9;font-family:monospace}
.pc-live{font-size:.62rem;font-weight:700;letter-spacing:.04em;color:#4ade8088}
.ltv-wrap{padding:10px 0 26px}
.ltv-cur-row{display:flex;align-items:baseline;gap:2px;margin-bottom:7px}
.ltv-cur-val{font-size:.82rem;font-weight:700;font-family:monospace}
.ltv-cur-lbl{font-size:.67rem;color:#64748b}
.ltv-track{position:relative;height:6px;background:#ffffff14;border-radius:3px}
.ltv-fill{position:absolute;left:0;top:0;height:100%;border-radius:3px;transition:width .3s}
.ltv-tick{position:absolute;top:-4px;width:2px;height:14px;background:#64748b;border-radius:1px}
.ltv-tick::after{content:attr(data-lbl);position:absolute;top:17px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:.62rem;color:#64748b;letter-spacing:.02em}
.ltv-tick-liq{background:#ef4444}
.ltv-tick-liq::after{color:#ef4444}
.md-ltv{padding:4px 20px 8px}
.ra-row{display:flex;gap:16px;margin:8px 0 2px;flex-wrap:wrap}
.ra-item{display:flex;flex-direction:column;gap:2px}
.ra-lbl{font-size:.62rem;color:#64748b;text-transform:uppercase;letter-spacing:.04em}
.ra-val{font-size:.82rem;font-weight:600;color:#f1f5f9;font-family:monospace}

/* Modal */
.modal-ov{position:fixed;inset:0;background:rgba(0,0,0,.78);display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;transition:opacity .2s;z-index:999;padding:16px;backdrop-filter:blur(4px)}
.modal-ov.open{opacity:1;pointer-events:all}
.modal-box{background:#1a1d2e;border-radius:14px;width:100%;max-width:560px;max-height:92vh;overflow-y:auto;transform:scale(.97);transition:transform .2s;border:1px solid #ffffff08}
.modal-ov.open .modal-box{transform:scale(1)}
.md-header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 20px 14px}
.md-title{font-size:1rem;font-weight:700;color:#f1f5f9;margin-bottom:6px}
.md-badges{display:flex;gap:6px}
.md-close,.modal-close{background:none;border:none;color:#475569;font-size:1rem;cursor:pointer;padding:4px;line-height:1;transition:color .15s;flex-shrink:0}
.md-close:hover,.modal-close:hover{color:#f1f5f9}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:20px 20px 14px;border-bottom:1px solid #ffffff0a}
.md-range{padding:0 20px 12px;border-bottom:1px solid #ffffff0a;margin-bottom:4px}
.md-status{font-size:.72rem;font-weight:700;margin-bottom:3px}
.md-range-info{font-size:.7rem;color:#64748b;font-family:monospace}
.mt-table{width:calc(100% - 40px);margin:8px 20px 0;border-collapse:collapse;font-size:.82rem}
.mt-table th{text-align:left;font-size:.63rem;color:#475569;text-transform:uppercase;padding-bottom:6px;border-bottom:1px solid #ffffff0a}
.mt-table th:not(:first-child){text-align:right}
.mt-table td{padding:6px 0;border-bottom:1px solid #ffffff04}
.mt-sym{color:#94a3b8;width:42%}
.mt-num{text-align:right;font-family:monospace;width:30%}
.mt-usd{text-align:right;color:#64748b;width:28%}
.mt-note{font-size:.62rem;color:#475569;font-style:italic;margin-left:4px}
.mt-section{font-size:.62rem;color:#475569;text-transform:uppercase;letter-spacing:.05em;padding:10px 0 2px}
.md-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 20px 0;padding:12px;background:#ffffff06;border-radius:10px}
.ls-item{display:flex;flex-direction:column;gap:3px}
.ls-item span:first-child{font-size:.63rem;color:#475569;text-transform:uppercase;letter-spacing:.04em}
.ls-item span:last-child{font-size:.82rem;font-weight:600;font-family:monospace}
.md-footer{text-align:right;font-size:1.1rem;font-weight:700;color:#f1f5f9;font-family:monospace;padding:14px 20px 20px;border-top:1px solid #ffffff0f;margin-top:12px}

/* Tooltip */
.tip-wrap{position:relative;display:inline-block;cursor:help}
.tip-icon{font-size:.68rem;color:#475569;margin-left:3px;vertical-align:middle;border:1px solid #475569;border-radius:50%;padding:0 3px;line-height:1.3}
.tip-box{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#1e2235;border:1px solid #ffffff1a;border-radius:8px;padding:10px 13px;width:230px;font-size:.72rem;color:#94a3b8;line-height:1.55;z-index:99;white-space:normal;text-align:left;box-shadow:0 8px 24px #00000055}
.tip-box strong{color:#f1f5f9;display:block;margin-bottom:5px;font-size:.75rem}
.tip-box code{color:#60a5fa;font-family:monospace;font-size:.72rem}
.tip-wrap:hover .tip-box{display:block}

/* Stock modals */
.add-stock-btn{padding:5px 13px;border-radius:6px;border:1px solid #6366f144;background:#6366f111;color:#818cf8;font-size:.72rem;font-weight:600;cursor:pointer;transition:all .15s}
.add-stock-btn:hover{background:#6366f122;border-color:#818cf8}
.se-field{display:flex;flex-direction:column;gap:5px;margin-bottom:14px;padding:0 20px}
.se-lbl{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.se-input{background:#0d0f18;border:1px solid #ffffff14;border-radius:8px;color:#f1f5f9;font-size:.95rem;padding:9px 12px;width:100%;outline:none;font-family:monospace;appearance:none;transition:border-color .15s}
.se-input:focus{border-color:#6366f166}
.se-hint{font-size:.63rem;color:#475569;margin-top:4px}
.se-save{margin:6px 20px 20px;width:calc(100% - 40px);padding:10px;border-radius:8px;border:none;background:#6366f1;color:#fff;font-size:.85rem;font-weight:700;cursor:pointer;transition:opacity .15s;display:block}
.se-save:hover:not(:disabled){opacity:.85}
.se-save:disabled{opacity:.45;cursor:not-allowed}
"""

    # ── Static JS
    JS = """
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelector('.tab-btn[data-page="' + name + '"]').classList.add('active');
}
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
    if (j.ok) { closeStockEdit(); doRefresh(); }
    else { btn.textContent = j.error || 'Error'; btn.disabled = false; }
  } catch(e) { btn.textContent = 'No server'; btn.disabled = false; }
}

function openAddStock() {
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
    if (j.ok) { closeAddStock(); doRefresh(); }
    else { btn.textContent = j.error || 'Error'; btn.disabled = false; }
  } catch(e) { btn.textContent = 'No server'; btn.disabled = false; }
}

function doRefresh() {
  window.location.reload();
}
async function triggerRefresh() {
  const btn = document.getElementById('refresh-btn');
  btn.disabled = true; btn.textContent = '⟳ Refreshing…';
  try {
    const r = await fetch('/refresh', {method:'POST'});
    const j = await r.json();
    if (j.ok) { window.location.reload(); }
    else {
      btn.textContent = '✕ ' + (j.error || 'Error').slice(0, 30);
      setTimeout(() => { btn.textContent = '⟳ Refresh'; btn.disabled = false; }, 4000);
    }
  } catch(e) {
    btn.textContent = '✕ No server';
    setTimeout(() => { btn.textContent = '⟳ Refresh'; btn.disabled = false; }, 4000);
  }
}
"""

    # ── Chart JS
    chart_js = (
        f"const donutCtx = document.getElementById('donut').getContext('2d');\n"
        f"new Chart(donutCtx, {{\n"
        f"  type: 'doughnut',\n"
        f"  data: {{ labels: {json.dumps(chart_labels)}, datasets: [{{ data: {json.dumps(chart_values)}, backgroundColor: {json.dumps(chart_colors)}, borderWidth: 0, hoverOffset: 6 }}] }},\n"
        f"  options: {{ plugins: {{ legend: {{ position: 'right', labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }} }}, cutout: '65%' }}\n"
        f"}});\n\n"
        f"const barCtx = document.getElementById('bar').getContext('2d');\n"
        f"new Chart(barCtx, {{\n"
        f"  type: 'bar',\n"
        f"  data: {{ labels: {json.dumps(proto_labels)}, datasets: [{{ data: {json.dumps(proto_values)}, backgroundColor: {json.dumps(proto_colors[:len(proto_values)])}, borderRadius: 6, borderWidth: 0 }}] }},\n"
        f"  options: {{\n"
        f"    indexAxis: 'y',\n"
        f"    plugins: {{ legend: {{ display: false }} }},\n"
        f"    scales: {{\n"
        f"      x: {{ grid: {{ color: '#ffffff0a' }}, ticks: {{ color: '#64748b', callback: v => '$' + v.toLocaleString() }} }},\n"
        f"      y: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n"
    )

    # ── History line chart
    hist_dates  = [h["date"] for h in history]
    hist_crypto = [h["crypto"] for h in history]
    hist_stock  = [h["stock"]  for h in history]
    hist_total  = [h["total"]  for h in history]
    history_js = (
        f"const histCtx = document.getElementById('history-chart').getContext('2d');\n"
        f"new Chart(histCtx, {{\n"
        f"  type: 'line',\n"
        f"  data: {{\n"
        f"    labels: {json.dumps(hist_dates)},\n"
        f"    datasets: [\n"
        f"      {{ label: 'Total', data: {json.dumps(hist_total)}, borderColor: '#f1f5f9', backgroundColor: '#f1f5f908', borderWidth: 2, pointRadius: 2, tension: 0.3, fill: false }},\n"
        f"      {{ label: 'Crypto', data: {json.dumps(hist_crypto)}, borderColor: '#f97316', backgroundColor: '#f9731608', borderWidth: 1.5, pointRadius: 2, tension: 0.3, fill: false }},\n"
        f"      {{ label: 'Stocks', data: {json.dumps(hist_stock)}, borderColor: '#6366f1', backgroundColor: '#6366f108', borderWidth: 1.5, pointRadius: 2, tension: 0.3, fill: false }}\n"
        f"    ]\n"
        f"  }},\n"
        f"  options: {{\n"
        f"    responsive: true,\n"
        f"    interaction: {{ mode: 'index', intersect: false }},\n"
        f"    plugins: {{\n"
        f"      legend: {{ labels: {{ color: '#94a3b8', font: {{ size: 11 }}, boxWidth: 12 }} }},\n"
        f"      tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString(undefined, {{minimumFractionDigits:0,maximumFractionDigits:0}}) }} }}\n"
        f"    }},\n"
        f"    scales: {{\n"
        f"      x: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#475569', font: {{ size: 10 }}, maxTicksLimit: 10 }} }},\n"
        f"      y: {{ grid: {{ color: '#ffffff08' }}, ticks: {{ color: '#64748b', callback: v => '$' + (v/1000).toFixed(0) + 'k' }} }}\n"
        f"    }}\n"
        f"  }}\n"
        f"}});\n"
    )
    chart_js += history_js + interest_js

    # ── Assemble HTML
    page1 = (
        '<div class="stats-grid">'
        f'<div class="stat-card"><div class="sc-lbl">Gross Assets</div><div class="sc-val">{fmt(gross)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Total Debt</div><div class="sc-val debt">{fmt(total_debt)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Net Value</div><div class="sc-val">{fmt(net_value)}</div></div>'
        f'<div class="stat-card"><div class="sc-lbl">Positions</div><div class="sc-val">{len(positions)}</div></div>'
        '</div>'
        '<div class="charts-row">'
        '<div class="chart-card"><h3>Category Allocation</h3><canvas id="donut"></canvas></div>'
        '<div class="chart-card"><h3>Value by Protocol</h3><canvas id="bar"></canvas></div>'
        '</div>'
        '<div class="chart-card" style="margin-bottom:24px"><h3>Portfolio History</h3><canvas id="history-chart"></canvas></div>'
        + token_summary_html +
        '<div class="alloc-card"><h3>Breakdown</h3>' + cat_rows + '</div>'
        '<div class="risk-row">' + risk_cards + '</div>'
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
    )

    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>Portfolio Dashboard</title>\n'
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n'
        '<style>' + CSS + '</style>\n'
        '</head>\n<body>\n\n'
        '<nav class="top-nav">\n'
        '  <div class="nav-brand">Portfolio Dashboard</div>\n'
        '  <div class="tab-group">\n'
        '    <button class="tab-btn active" data-page="overview" onclick="showPage(\'overview\')">Overview</button>\n'
        '    <button class="tab-btn" data-page="interest" onclick="showPage(\'interest\')">Cashflow</button>\n'
        '    <button class="tab-btn" data-page="positions" onclick="showPage(\'positions\')">Positions</button>\n'
        '  </div>\n'
        f'  <div class="nav-right"><div class="nav-total-wrap"><div class="nav-total-lbl">Portfolio</div><div class="nav-total">{fmt(grand)}</div></div><div class="nav-ts">Updated {ts}</div><button id="refresh-btn" class="nav-refresh-btn" onclick="triggerRefresh()">&#8635; Refresh</button></div>\n'
        '</nav>\n\n'
        '<div id="page-overview" class="page active">\n' + page1 + '\n</div>\n\n'
        '<div id="page-interest" class="page">\n' + page3 + '\n</div>\n\n'
        '<div id="page-positions" class="page">\n' + page2_html + '\n</div>\n\n'
        '<div id="modal-ov" class="modal-ov" onclick="closeModal()">\n'
        '  <div class="modal-box" onclick="event.stopPropagation()">\n'
        '    <div id="modal-inner"></div>\n'
        '  </div>\n'
        '</div>\n\n'
        + stock_modals + '\n\n'
        + modals_html + '\n\n'
        '<script>\n' + JS + '\n' + chart_js + '\n</script>\n'
        '</body>\n</html>'
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
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

    total_5050 = sl_proto.get("steamm_lp", {}).get("usd", 0.0)

    print("[9/10] Fetching stock prices ...")
    stocks = load_stocks()
    fetch_stock_prices(stocks)
    save_stocks(stocks)

    amm_total     = amm_8020["total"] + total_5050 + aftermath["total"] + clmm_e64c_total
    lending_total = navi["net"] + sl_net + sc_net
    cex_total     = binance["futures_margin"]
    stocks_total  = sum(s.get("market_value", 0) for s in stocks)
    crypto_total  = amm_total + lending_total + onchain_total + cex_total
    grand_total   = crypto_total + stocks_total

    # Append to history on Wednesdays only (keeps chart weekly)
    history = load_history()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if now.weekday() == 2:  # Wednesday
        entry = {"date": today, "crypto": round(crypto_total, 2), "stock": round(stocks_total, 2), "total": round(grand_total, 2)}
        if history and history[-1]["date"] == today:
            history[-1] = entry
        else:
            history.append(entry)
    save_history(history)

    data = {
        "prices":    prices,
        "timestamp": datetime.now().strftime("%Y-%m-%d  %H:%M:%S"),
        "grand_total":    grand_total,
        "amm_total":      amm_total,
        "lending_total":  lending_total,
        "onchain_total":  onchain_total,
        "clmm_e64c_total": clmm_e64c_total,
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
        "clmm_e64c": clmm_e64c_list,
        "aftermath": aftermath,
        "ember": ember,
        "stzent": stzent,
        "binance": binance,
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
    main()
