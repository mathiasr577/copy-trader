import time
import requests
from datetime import datetime
from config import RPC_URL, WATCHLIST, POLL_INTERVAL
from parser import parse_swap

detected_trades = []
last_seen = {}

def rpc(method, params):
    try:
        r = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": method, "params": params
        }, timeout=20)
        data = r.json()
        return data.get("result")
    except Exception as e:
        print(f"[rpc error] {method}: {e}")
        return None

def get_signatures(wallet):
    result = rpc("getSignaturesForAddress", [wallet, {"limit": 10}])
    return [x["signature"] for x in result] if result else []

def get_tx(sig):
    return rpc("getTransaction", [sig, {
        "encoding": "json",
        "maxSupportedTransactionVersion": 0
    }])

def process_wallet(wallet):
    global detected_trades, last_seen

    sigs = get_signatures(wallet)
    if not sigs:
        return

    if wallet not in last_seen:
        last_seen[wallet] = sigs[0]
        print(f"[init] {wallet[:8]}... listo")
        return

    if sigs[0] == last_seen[wallet]:
        return

    new_sigs = []
    for sig in sigs:
        if sig == last_seen[wallet]:
            break
        new_sigs.append(sig)

    last_seen[wallet] = sigs[0]

    for sig in reversed(new_sigs):
        tx = get_tx(sig)
        if not tx:
            continue
        swap = parse_swap(tx, wallet)
        if swap:
            ts = datetime.fromtimestamp(swap["block_time"]).strftime("%H:%M:%S")
            swap["time"] = ts
            detected_trades.insert(0, swap)
            if len(detected_trades) > 200:
                detected_trades.pop()
            icon = "🟢" if swap["action"] == "BUY" else "🔴"
            print(f"{icon} {swap['action']} | {swap['wallet_short']} | {swap['token_short']} | {swap['amount']} | {ts}")

def run_loop():
    print(f"[tracker] Iniciando — {len(WATCHLIST)} wallets, polling cada {POLL_INTERVAL}s")
    cycle = 0
    while True:
        cycle += 1
        print(f"[ciclo {cycle}]")
        for wallet in WATCHLIST:
            try:
                process_wallet(wallet)
                time.sleep(0.4)
            except Exception as e:
                print(f"[error] {wallet[:8]}...: {e}")
        time.sleep(POLL_INTERVAL)