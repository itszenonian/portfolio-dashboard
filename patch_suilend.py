import re

with open("/Users/zenonian/Desktop/Claude/Projects/Portfolio tracker project/generate_dashboard.py", "r") as f:
    content = f.read()

# I will replace the current fetch_suilend function with the correct loop.
# The fetch_suilend function ends around "return deposits, borrows, proto"
# I'll just find the "def fetch_suilend" block and replace it.

start_idx = content.find("def fetch_suilend(prices):")
end_idx = content.find("def fetch_navi", start_idx)

new_func = """def fetch_suilend(prices):
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
            if lm.get("result"):
                lending_markets[lm_id] = lm["result"]["data"]["content"]["fields"]["reserves"]
            else:
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
            
            # Special Steamm Valuation
            if "STEAMM_LP_BWAL_BUSDC" in raw_sym:
                lp_amt = int(df["deposited_ctoken_amount"])
                pool = rpc("sui_getObject", ["0xe4455aac45acee48f8b69c671c245363faa7380b3dcbe3af0fbe00cc4b68e9eb", {"showContent": True}])
                if pool.get("result"):
                    pf = pool["result"]["data"]["content"]["fields"]
                    total_lp = int(pf["lp_supply"]["fields"]["value"])
                    b_wal = int(pf["balance_a"]) / 1e9
                    b_usdc = int(pf["balance_b"]) / 1e6
                    if total_lp > 0:
                        share = lp_amt / total_lp
                        my_wal = share * b_wal
                        my_usdc = share * b_usdc
                        usd = (my_wal * prices.get("WAL", 0)) + my_usdc
                        proto["steamm_lp"] = {"usd": usd, "wal_amt": my_wal, "usdc_amt": my_usdc}
                        amt = lp_amt / 1e9

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

# """

content = content[:start_idx] + new_func + content[end_idx:]

with open("/Users/zenonian/Desktop/Claude/Projects/Portfolio tracker project/generate_dashboard.py", "w") as f:
    f.write(content)

print("Patched fetch_suilend successfully.")
