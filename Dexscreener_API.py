import requests

BASE_URL = "https://api.dexscreener.com/latest/dex"

# ── Known pair addresses (pinned for accuracy) ──────────────────────────────
PAIRS = {
    "sSUI/SUI":      "0x5c5e87f0adf458b77cc48e17a7b81a0e7bc2e9c6c609b67c0851ef059a866f3a",
    "vSUI/SUI":      "0x6c545e78638c8c1db7a48b282bb8ca79da107993fcb185f75cedc1f5adb2f535",
    "haSUI/SUI":     "0x871d8a227114f375170f149f7e9d45be822dd003eba225e83c05ac80828596bc",
    "USDSUI/USDC":   "0xa7417fb5f59e23b0a7826d78f025653823c49265be07bbf6dd9e553ba4249a56",
    "suiUSDT/USDC":  "0x737ec6a4d3ed0c7e6cc18d8ba04e7ffd4806b726c97efd89867597368c4d06a9",
}


def get_pairs(addresses: list[str]) -> list[dict]:
    """Fetch one or more pairs by address. Returns raw pair objects."""
    joined = ",".join(addresses)
    r = requests.get(f"{BASE_URL}/pairs/sui/{joined}", timeout=10)
    r.raise_for_status()
    return r.json().get("pairs", [])


def get_pair(address: str) -> dict | None:
    """Fetch a single pair by address. Returns the pair object or None."""
    results = get_pairs([address])
    return results[0] if results else None


def price_in_sui(pair_address: str) -> float | None:
    """Return the price of the base token in SUI (priceNative)."""
    pair = get_pair(pair_address)
    if not pair:
        return None
    return float(pair["priceNative"])


def price_in_usd(pair_address: str) -> float | None:
    """Return the price of the base token in USD (priceUsd)."""
    pair = get_pair(pair_address)
    if not pair:
        return None
    return float(pair.get("priceUsd", 0))


def search(query: str, chain: str = "sui") -> list[dict]:
    """Search pairs by token name or symbol. Filters by chain if provided."""
    r = requests.get(f"{BASE_URL}/search?q={query}", timeout=10)
    r.raise_for_status()
    pairs = r.json().get("pairs", [])
    if chain:
        pairs = [p for p in pairs if p.get("chainId", "").lower() == chain.lower()]
    return pairs


def pair_summary(address: str) -> dict | None:
    """Return a clean summary dict for a pair."""
    pair = get_pair(address)
    if not pair:
        return None
    return {
        "base":         pair["baseToken"]["symbol"],
        "quote":        pair["quoteToken"]["symbol"],
        "dex":          pair["dexId"],
        "price_native": float(pair["priceNative"]),
        "price_usd":    float(pair.get("priceUsd", 0)),
        "volume_24h":   pair.get("volume", {}).get("h24", 0),
        "liquidity_usd":pair.get("liquidity", {}).get("usd", 0),
        "change_24h":   pair.get("priceChange", {}).get("h24", 0),
        "pair_address": pair["pairAddress"],
    }


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("DexScreener API — Sui Pairs\n")
    for name, addr in PAIRS.items():
        s = pair_summary(addr)
        if s:
            print(f"{name}")
            print(f"  Price : {s['price_native']} SUI  (${s['price_usd']})")
            print(f"  DEX   : {s['dex']}")
            print(f"  Vol24h: ${s['volume_24h']:,.2f}")
            print(f"  Liq   : ${s['liquidity_usd']:,.2f}")
            print(f"  Chg24h: {s['change_24h']}%")
            print()
