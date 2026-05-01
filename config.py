import json
import os

HELIUS_API_KEY = "4695b324-4dd5-420c-890e-1d7cf26762c1"
BIRDEYE_API_KEY = "c07460fca95843f1a83edb16a1835abc"

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

BLACKLIST = {
    "HkFGQsW8mr8DTC2AE2WcC7MzwSnynfEryGMQSht271nf",  # bot confirmado
}

def load_watchlist():
    if os.path.exists("watchlist.json"):
        with open("watchlist.json") as f:
            data = json.load(f)
            # Soporta ambos formatos: {addresses:[]} y {wallets:[], addresses:[]}
            addresses = data.get("addresses", [])
            return [a for a in addresses if a not in BLACKLIST]
    return [
        "GFHMc9BegxJXLdHJrABxNVoPRdnmVxXiNeoUCEpgXVHw",
        "2ZmG87ddU7rcusmzgqRMu91FSrCb5jTnpGrD9yUevbr6",
    ]

def load_wallet_details():
    """Carga los datos completos que guardó el finder (sol_balance, tx_count, etc)."""
    if os.path.exists("watchlist.json"):
        with open("watchlist.json") as f:
            data = json.load(f)
            wallets = data.get("wallets", [])
            return {w["address"]: w for w in wallets if "address" in w}
    return {}

WATCHLIST = load_watchlist()
POLL_INTERVAL = 20

# ── Cola de wallets encontradas por Honest Mercy ──────────────────────────────
# Wallets aprobadas por el finder pero aún no copiadas — aparecen en el dashboard
PENDING_WALLETS = []

STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
}

# ── Persistencia ──────────────────────────────────────────────────────────────

def save_watchlist():
    """Persiste WATCHLIST al JSON preservando datos completos del finder."""
    existing_details = load_wallet_details()
    wallets = [existing_details.get(a, {"address": a}) for a in WATCHLIST]
    with open("watchlist.json", "w") as f:
        json.dump({"wallets": wallets, "addresses": WATCHLIST}, f, indent=2)

# ── Watchlist operations ──────────────────────────────────────────────────────

def add_to_watchlist(address):
    """Agrega wallet al tracker en memoria + JSON sin reiniciar."""
    if address in BLACKLIST:
        return False, "blacklisted"
    if address in WATCHLIST:
        return False, "already exists"
    WATCHLIST.append(address)
    save_watchlist()
    # Sacar de pending si estaba ahí
    dismiss_pending(address)
    return True, "added"

def remove_from_watchlist(address):
    """Remueve wallet del tracker en memoria + JSON sin reiniciar."""
    if address not in WATCHLIST:
        return False, "not found"
    WATCHLIST.remove(address)
    save_watchlist()
    return True, "removed"

# ── Pending queue (wallets encontradas por Honest Mercy) ─────────────────────

def add_pending_wallet(wallet_data):
    """Honest Mercy llama esto cuando encuentra una wallet nueva."""
    address = wallet_data.get("address")
    if not address:
        return False, "no address"
    if address in BLACKLIST:
        return False, "blacklisted"
    if address in WATCHLIST:
        return False, "already in watchlist"
    for p in PENDING_WALLETS:
        if p.get("address") == address:
            return False, "already pending"
    PENDING_WALLETS.append(wallet_data)
    return True, "added to pending"

def dismiss_pending(address):
    """Descarta una wallet de la cola de pending (rechazada o ya copiada)."""
    global PENDING_WALLETS
    before = len(PENDING_WALLETS)
    PENDING_WALLETS = [p for p in PENDING_WALLETS if p.get("address") != address]
    return len(PENDING_WALLETS) < before