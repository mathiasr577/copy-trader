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
            addresses = data.get("addresses", [])
            return [a for a in addresses if a not in BLACKLIST]
    return [
        "GFHMc9BegxJXLdHJrABxNVoPRdnmVxXiNeoUCEpgXVHw",
        "2ZmG87ddU7rcusmzgqRMu91FSrCb5jTnpGrD9yUevbr6",
    ]

WATCHLIST = load_watchlist()

POLL_INTERVAL = 20

STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
}

def add_to_watchlist(address):
    """Agrega una wallet en memoria Y persiste al JSON sin reiniciar nada."""
    if address in BLACKLIST:
        return False, "blacklisted"
    if address in WATCHLIST:
        return False, "already exists"

    WATCHLIST.append(address)

    with open("watchlist.json", "w") as f:
        json.dump({"addresses": WATCHLIST}, f, indent=2)

    return True, "added"

def remove_from_watchlist(address):
    """Remueve una wallet en memoria Y persiste al JSON sin reiniciar nada."""
    if address not in WATCHLIST:
        return False, "not found"

    WATCHLIST.remove(address)

    with open("watchlist.json", "w") as f:
        json.dump({"addresses": WATCHLIST}, f, indent=2)

    return True, "removed"
