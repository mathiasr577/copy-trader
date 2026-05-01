import time
import json
import os
import requests
from datetime import datetime
import config
from config import RPC_URL, POLL_INTERVAL
from parser import parse_swap

TRADES_FILE = "trades_history.json"

def load_trades():
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_trades(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f)

detected_trades = load_trades()
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
            save_trades(detected_trades)
            icon = "🟢" if swap["action"] == "BUY" else "🔴"
            print(f"{icon} {swap['action']} | {swap['wallet_short']} | {swap['token_short']} | {swap['amount']} | {ts}")

def run_loop():
    # Usa config.WATCHLIST directamente — lista viva, se actualiza sin reiniciar
    print(f"[tracker] Iniciando — {len(config.WATCHLIST)} wallets, polling cada {POLL_INTERVAL}s")
    cycle = 0
    while True:
        cycle += 1
        print(f"[ciclo {cycle}] — {len(config.WATCHLIST)} wallets activas")
        for wallet in list(config.WATCHLIST):  # list() para evitar errores si se modifica durante el ciclo
            try:
                process_wallet(wallet)
                time.sleep(0.4)
            except Exception as e:
                print(f"[error] {wallet[:8]}...: {e}")
        time.sleep(POLL_INTERVAL)