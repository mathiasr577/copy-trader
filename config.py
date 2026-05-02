import json
import os

HELIUS_API_KEY = "4695b324-4dd5-420c-890e-1d7cf26762c1"
BIRDEYE_API_KEY = "dc241f71cc354cfbb47394323eb9a08b"

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

BLACKLIST = {
    "HkFGQsW8mr8DTC2AE2WcC7MzwSnynfEryGMQSht271nf",  # bot confirmado
}

def load_watchlist():
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json") as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)
                addresses = data.get("addresses", [])
                return [a for a in addresses if a not in BLACKLIST]
        except Exception:
            return []
    return [
        "GFHMc9BegxJXLdHJrABxNVoPRdnmVxXiNeoUCEpgXVHw",
        "2ZmG87ddU7rcusmzgqRMu91FSrCb5jTnpGrD9yUevbr6",
    ]

def load_wallet_details():
    if os.path.exists("watchlist.json"):
        try:
            with open("watchlist.json") as f:
                content = f.read().strip()
                if not content:
                    return {}
                data = json.loads(content)
                wallets = data.get("wallets", [])
                return {w["address"]: w for w in wallets if "address" in w}
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
    existing_details = load_wallet_details()
    wallets = [existing_details.get(a, {"address": a}) for a in WATCHLIST]
    with open("watchlist.json", "w") as f:
        json.dump({"wallets": wallets, "addresses": WATCHLIST}, f, indent=2)

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