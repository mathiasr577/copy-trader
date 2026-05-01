import requests
import json
import time
import datetime
from config import BIRDEYE_API_KEY, HELIUS_API_KEY

BIRDEYE_HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": "solana"
}

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# URL del server en Railway — el finder le notifica las wallets aprobadas
SERVER_URL = "https://copy-trader-production-3ae0.up.railway.app"

# FILTROS
MIN_PNL           = 10000
MIN_TRADES        = 10
MIN_SOL           = 0.5
MIN_RECENT_DAYS   = 7
MIN_AGE_DAYS      = 14
MAX_BOT_GAP       = 3
MIN_UNIQUE_TOKENS = 3
MAX_WALLETS       = 50

STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
}

def rpc(method, params):
    try:
        r = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": method, "params": params
        }, timeout=20)
        return r.json().get("result")
    except Exception:
        return None

# ─── NOTIFICAR AL SERVER ──────────────────────────────────────────────────────

def notify_server(wallet_data):
    """
    Cuando el finder aprueba una wallet, la manda al server
    para que aparezca en el dashboard en tiempo real.
    """
    try:
        r = requests.post(
            f"{SERVER_URL}/api/pending/add",
            json=wallet_data,
            timeout=10
        )
        result = r.json()
        if result.get("ok"):
            print(f"  📡 Notificada al dashboard ({result.get('pending_total')} en queue)")
        else:
            print(f"  📡 Ya en queue: {result.get('message')}")
    except Exception as e:
        print(f"  📡 No se pudo notificar al server: {e}")

# ─── FUENTE 1: Birdeye top traders ───────────────────────────────────────────

def get_birdeye_traders():
    print("\n[fuente 1] Birdeye top traders...")
    try:
        r = requests.get(
            "https://public-api.birdeye.so/trader/gainers-losers",
            headers=BIRDEYE_HEADERS,
            timeout=20
        )
        items = r.json().get("data", {}).get("items", [])
        addresses = [t.get("address") for t in items if t.get("address")]
        print(f"  → {len(addresses)} wallets de Birdeye")
        return addresses
    except Exception as e:
        print(f"  → error: {e}")
        return []

# ─── FUENTE 2: Tokens trending + early buyers ─────────────────────────────────

def get_trending_tokens():
    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/tokenlist",
            headers=BIRDEYE_HEADERS,
            params={"sort_by": "v24hUSD", "sort_type": "desc", "limit": 20, "min_liquidity": 100000},
            timeout=20
        )
        tokens = r.json().get("data", {}).get("tokens", [])
        return [t["address"] for t in tokens if t.get("address")]
    except Exception:
        return []

def get_buyers_from_token(token_address):
    buyers = set()
    try:
        sigs = rpc("getSignaturesForAddress", [token_address, {"limit": 30}])
        if not sigs:
            return buyers
        for sig_data in sigs[:15]:
            sig = sig_data.get("signature", "")
            if not sig:
                continue
            tx = rpc("getTransaction", [sig, {
                "encoding": "json",
                "maxSupportedTransactionVersion": 0
            }])
            if not tx:
                continue
            keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
            if keys:
                buyers.add(keys[0])
            time.sleep(0.1)
    except Exception:
        pass
    return buyers

def get_trending_buyers():
    print("\n[fuente 2] Tokens trending + early buyers...")
    tokens = get_trending_tokens()
    if not tokens:
        print("  → sin tokens")
        return set()

    all_buyers = set()
    for i, token in enumerate(tokens[:6]):
        print(f"  → token {i+1}/6: {token[:8]}...")
        buyers = get_buyers_from_token(token)
        all_buyers.update(buyers)
        time.sleep(0.4)

    print(f"  → {len(all_buyers)} wallets encontradas")
    return all_buyers

# ─── ANÁLISIS DE WALLET ───────────────────────────────────────────────────────

def analyze_wallet(address):
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()

    # 1. Balance SOL
    result = rpc("getBalance", [address])
    if not result:
        return None, "sin respuesta RPC"
    sol = result.get("value", 0) / 1e9
    if sol < MIN_SOL:
        return None, f"balance bajo ({sol:.2f} SOL)"

    # 2. Historial
    sigs = rpc("getSignaturesForAddress", [address, {"limit": 100}])
    if not sigs or len(sigs) < MIN_TRADES:
        return None, f"pocas txs ({len(sigs) if sigs else 0})"

    # 3. Antigüedad
    oldest = sigs[-1].get("blockTime", 0)
    newest = sigs[0].get("blockTime", 0)
    if not oldest or not newest:
        return None, "sin timestamps"

    age_days = (now - oldest) / 86400
    if age_days < MIN_AGE_DAYS:
        return None, f"wallet nueva ({age_days:.0f} días)"

    # 4. Actividad reciente
    last_active = (now - newest) / 86400
    if last_active > MIN_RECENT_DAYS:
        return None, f"inactiva hace {last_active:.0f} días"

    # 5. Anti-bot por velocidad
    times = [s.get("blockTime", 0) for s in sigs[:20] if s.get("blockTime")]
    if len(times) >= 2:
        gaps = [abs(times[i] - times[i+1]) for i in range(len(times)-1)]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap < MAX_BOT_GAP:
            return None, f"bot por velocidad ({avg_gap:.1f}s)"

    # 6. Diversidad de tokens + PnL estimado
    token_mints = set()
    buys = 0
    sells = 0
    estimated_pnl = 0

    for sig_data in sigs[:40]:
        sig = sig_data.get("signature", "")
        if not sig:
            continue
        tx = rpc("getTransaction", [sig, {
            "encoding": "json",
            "maxSupportedTransactionVersion": 0
        }])
        if not tx:
            continue
        meta = tx.get("meta", {})
        if meta.get("err"):
            continue

        pre_balances  = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])

        pre_map = {}
        for b in pre_balances:
            if b.get("owner") == address:
                pre_map[b["mint"]] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

        post_map = {}
        for b in post_balances:
            if b.get("owner") == address:
                post_map[b["mint"]] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

        for mint in set(list(pre_map.keys()) + list(post_map.keys())):
            if mint in STABLECOINS:
                continue
            token_mints.add(mint)
            delta = post_map.get(mint, 0) - pre_map.get(mint, 0)
            if delta > 0.001:
                buys += 1
            elif delta < -0.001:
                sells += 1

        pre_sol  = meta.get("preBalances", [0])[0] / 1e9
        post_sol = meta.get("postBalances", [0])[0] / 1e9
        estimated_pnl += (post_sol - pre_sol)

        time.sleep(0.08)

    if len(token_mints) < MIN_UNIQUE_TOKENS:
        return None, f"poca diversidad ({len(token_mints)} tokens)"

    total_ops = buys + sells
    if total_ops > 0 and min(buys, sells) / max(buys, sells) < 0.15:
        return None, f"ratio desequilibrado ({buys}B/{sells}S)"

    return {
        "address": address,
        "sol_balance": round(sol, 3),
        "tx_count": len(sigs),
        "age_days": round(age_days, 0),
        "last_active_days": round(last_active, 1),
        "unique_tokens": len(token_mints),
        "buys": buys,
        "sells": sells,
        "estimated_pnl_sol": round(estimated_pnl, 3),
        "found_at": datetime.datetime.utcnow().isoformat(),
        "source": "honest_mercy"
    }, None

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_finder():
    print("=" * 60)
    print("[finder] Honest Mercy — Wallet Finder")
    print(f"  SOL mínimo:     {MIN_SOL}")
    print(f"  Trades mínimos: {MIN_TRADES}")
    print(f"  Activa últimos: {MIN_RECENT_DAYS} días")
    print(f"  Antigüedad mín: {MIN_AGE_DAYS} días")
    print(f"  Tokens únicos:  {MIN_UNIQUE_TOKENS}+")
    print(f"  Server:         {SERVER_URL}")
    print("=" * 60)

    # Cargar existentes
    existing = {}
    try:
        with open("watchlist.json") as f:
            data = json.load(f)
            for w in data.get("wallets", []):
                existing[w["address"]] = w
        print(f"[finder] {len(existing)} wallets existentes")
    except Exception:
        print("[finder] Empezando desde cero")

    # Juntar candidatas
    candidates = set()
    candidates.update(get_birdeye_traders())
    candidates.update(get_trending_buyers())
    candidates -= set(existing.keys())

    print(f"\n[finder] {len(candidates)} candidatas nuevas para analizar")
    print("-" * 60)

    new_count = 0
    for address in list(candidates)[:60]:
        if len(existing) >= MAX_WALLETS:
            print(f"[finder] Límite de {MAX_WALLETS} wallets alcanzado")
            break

        print(f"\n→ {address[:8]}...")
        result, reason = analyze_wallet(address)
        if result:
            existing[address] = result
            new_count += 1
            print(f"  ✅ APROBADA | SOL: {result['sol_balance']} | TXs: {result['tx_count']} | Edad: {result['age_days']}d | Tokens: {result['unique_tokens']}")
            # ← NUEVO: notificar al dashboard en tiempo real
            notify_server(result)
        else:
            print(f"  ❌ {reason}")

        time.sleep(0.2)

    # Guardar al JSON también (backup)
    all_wallets = list(existing.values())
    addresses = [w["address"] for w in all_wallets]
    with open("watchlist.json", "w") as f:
        json.dump({"wallets": all_wallets, "addresses": addresses}, f, indent=2)

    print(f"\n{'='*60}")
    print(f"[finder] +{new_count} nuevas | Total: {len(all_wallets)} wallets")

    return addresses

if __name__ == "__main__":
    run_finder()