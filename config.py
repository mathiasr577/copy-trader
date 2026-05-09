import json
import os

HELIUS_API_KEY = "4695b324-4dd5-420c-890e-1d7cf26762c1"
BIRDEYE_API_KEY = "8f4c580eed1e490caeba742904617a07"

# Helius Developer plan con Enhanced WebSockets
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

BLACKLIST = {
    "HkFGQsW8mr8DTC2AE2WcC7MzwSnynfEryGMQSht271nf",
}

def load_watchlist():
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json") as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)

                # Soporta ambos formatos:
                # {"addresses": [...]}  ← formato viejo
                # {"wallets": [...]}    ← formato nuevo (lista de strings o dicts)
                addresses = data.get("addresses", [])

                if not addresses:
                    wallets = data.get("wallets", [])
                    for w in wallets:
                        if isinstance(w, str):
                            addresses.append(w)
                        elif isinstance(w, dict) and "address" in w:
                            addresses.append(w["address"])

                return [a for a in addresses if a not in BLACKLIST]
        except Exception as e:
            print(f"[config] Error cargando watchlist: {e}")
            return []
    return []

def load_wallet_details():
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json") as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = json.loads(content)
                wallets = data.get("wallets", [])
                result = {}
                for w in wallets:
                    if isinstance(w, dict) and "address" in w:
                        result[w["address"]] = w
                return result
        except Exception:
            return {}
    return {}

WATCHLIST = load_watchlist()
POLL_INTERVAL = 20

PENDING_WALLETS = []

STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
}

def save_watchlist():
    """Siempre guarda con ambas keys para compatibilidad."""
    existing_details = load_wallet_details()
    wallets_list = []
    for a in WATCHLIST:
        if a in existing_details:
            wallets_list.append(existing_details[a])
        else:
            wallets_list.append({"address": a})
    with open("watchlist.json", "w") as f:
        json.dump({
            "addresses": WATCHLIST,       # ← lo que load_watchlist() lee
            "wallets": wallets_list        # ← detalles extras
        }, f, indent=2)

def add_to_watchlist(address):
    if address in BLACKLIST:
        return False, "blacklisted"
    if address in WATCHLIST:
        return False, "already exists"
    WATCHLIST.append(address)
    save_watchlist()
    dismiss_pending(address)
    return True, "added"

def remove_from_watchlist(address):
    if address not in WATCHLIST:
        return False, "not found"
    WATCHLIST.remove(address)
    save_watchlist()
    return True, "removed"

def add_pending_wallet(wallet_data):
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
    global PENDING_WALLETS
    before = len(PENDING_WALLETS)
    PENDING_WALLETS = [p for p in PENDING_WALLETS if p.get("address") != address]
    return len(PENDING_WALLETS) < before