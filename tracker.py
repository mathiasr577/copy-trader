import time
import json
import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import websocket  # pip install websocket-client
import config
from config import RPC_URL, POLL_INTERVAL
from parser import parse_swap

TRADES_FILE = "trades_history.json"

HELIUS_API_KEY = getattr(config, "HELIUS_API_KEY", "4695b324-4dd5-420c-890e-1d7cf26762c1")

# transactionSubscribe manda la tx completa — cero RPC call extra
WS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Thread pool listo — evita overhead de crear threads por cada tx
_executor = ThreadPoolExecutor(max_workers=8)

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
_trades_lock = threading.Lock()

# ──────────────────────────────────────────────
# RPC — solo para el poll de respaldo
# ──────────────────────────────────────────────

def rpc(method, params):
    try:
        r = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": method, "params": params
        }, timeout=5)  # 5s agresivo — si tarda más, algo está mal
        return r.json().get("result")
    except Exception as e:
        print(f"[rpc error] {method}: {e}")
        return None

def get_tx(sig):
    return rpc("getTransaction", [sig, {
        "encoding": "json",
        "maxSupportedTransactionVersion": 0
    }])

# ──────────────────────────────────────────────
# Procesamiento de trades
# ──────────────────────────────────────────────

def _is_duplicate(swap):
    """Chequea duplicados por signature contra los últimos 20 trades."""
    return any(
        t.get("signature") == swap.get("signature")
        for t in detected_trades[:20]
    )

def handle_swap(swap, source="WS"):
    """Registra el swap y dispara paper trader. Thread-safe."""
    global detected_trades

    with _trades_lock:
        if _is_duplicate(swap):
            return
        detected_trades.insert(0, swap)
        if len(detected_trades) > 200:
            detected_trades.pop()
        save_trades(detected_trades)

    icon = "🟢" if swap["action"] == "BUY" else "🔴"
    print(f"{icon} [{source}] {swap['action']} | {swap['wallet_short']} | {swap['token_short']} | {swap['amount']} | {swap['time']}")

    # Paper trader
    try:
        from paper_trader import process_trade, check_stop_take, save_state
        process_trade(swap)
        check_stop_take()
        save_state()
    except Exception as e:
        print(f"[paper error] {e}")

def handle_ws_transaction(wallet, tx_data):
    """
    Parsea la tx que llegó directo del WS (transactionSubscribe).
    tx_data ya tiene el formato completo — cero RPC call extra.
    """
    try:
        # transactionSubscribe manda { transaction, meta, slot, blockTime }
        tx = {
            "meta": tx_data.get("meta", {}),
            "transaction": tx_data.get("transaction", {}),
            "blockTime": tx_data.get("blockTime", int(time.time())),
        }

        swap = parse_swap(tx, wallet)
        if not swap:
            return

        ts = datetime.fromtimestamp(swap["block_time"]).strftime("%H:%M:%S")
        swap["time"] = ts

        handle_swap(swap, source="WS")

    except Exception as e:
        print(f"[ws handler error] {wallet[:8]}...: {e}")

def handle_ws_signature(wallet, sig):
    """
    Fallback: si transactionSubscribe falla, usamos logsSubscribe
    y buscamos la tx via RPC.
    """
    try:
        tx = get_tx(sig)
        if not tx:
            return
        swap = parse_swap(tx, wallet)
        if not swap:
            return
        ts = datetime.fromtimestamp(swap["block_time"]).strftime("%H:%M:%S")
        swap["time"] = ts
        handle_swap(swap, source="WS-sig")
    except Exception as e:
        print(f"[ws sig handler error] {wallet[:8]}...: {e}")

# ──────────────────────────────────────────────
# WebSocket Manager
# ──────────────────────────────────────────────

class HeliusWS:
    def __init__(self):
        self.ws = None
        self.sub_ids = {}        # wallet → sub_id
        self.id_to_wallet = {}   # sub_id → wallet
        self.req_to_wallet = {}  # req_id → wallet
        self._req_id = 1
        self._lock = threading.Lock()
        self._connected = False
        self._thread = None

    def _next_id(self):
        with self._lock:
            rid = self._req_id
            self._req_id += 1
            return rid

    def _subscribe(self, ws, wallet):
        rid = self._next_id()
        self.req_to_wallet[rid] = wallet

        # transactionSubscribe — manda la tx completa, cero RPC extra
        msg = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "transactionSubscribe",
            "params": [
                {
                    "accountInclude": [wallet],  # Solo txs que involucran esta wallet
                    "failed": False,             # Ignorar txs fallidas
                },
                {
                    "commitment": "confirmed",
                    "encoding": "json",
                    "transactionDetails": "full",  # meta + balances completos
                    "maxSupportedTransactionVersion": 0,
                }
            ]
        }
        ws.send(json.dumps(msg))

    def _unsubscribe(self, ws, sub_id):
        rid = self._next_id()
        ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": rid,
            "method": "transactionUnsubscribe",
            "params": [sub_id]
        }))

    def on_open(self, ws):
        self._connected = True
        wallets = list(config.WATCHLIST)
        print(f"[ws] Conectado — suscribiendo {len(wallets)} wallets con transactionSubscribe...")
        for wallet in wallets:
            self._subscribe(ws, wallet)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return

        # Confirmación de suscripción
        if "id" in data and "result" in data and isinstance(data["result"], int):
            req_id = data["id"]
            sub_id = data["result"]
            wallet = self.req_to_wallet.pop(req_id, None)
            if wallet:
                self.sub_ids[wallet] = sub_id
                self.id_to_wallet[sub_id] = wallet
                print(f"[ws] ✓ {wallet[:8]}... suscrito (sub_id={sub_id})")
            return

        # Notificación de transacción completa
        if data.get("method") == "transactionNotification":
            params = data.get("params", {})
            sub_id = params.get("subscription")
            result = params.get("result", {})

            wallet = self.id_to_wallet.get(sub_id)
            if not wallet:
                return

            # Despachar al thread pool — no bloquea el WS
            _executor.submit(handle_ws_transaction, wallet, result)
            return

        # Fallback: logsNotification
        if data.get("method") == "logsNotification":
            params = data.get("params", {})
            sub_id = params.get("subscription")
            value = params.get("result", {}).get("value", {})
            if value.get("err"):
                return
            wallet = self.id_to_wallet.get(sub_id)
            sig = value.get("signature")
            if wallet and sig:
                _executor.submit(handle_ws_signature, wallet, sig)

    def on_error(self, ws, error):
        print(f"[ws] Error: {error}")

    def on_close(self, ws, code, msg):
        self._connected = False
        print(f"[ws] Desconectado (code={code}) — reconectando en 3s...")

    def sync_subscriptions(self):
        """Sync wallets agregadas/removidas sin reiniciar."""
        if not self._connected or not self.ws:
            return

        current = set(config.WATCHLIST)
        subscribed = set(self.sub_ids.keys())

        for wallet in current - subscribed:
            print(f"[ws] + Nueva wallet: {wallet[:8]}...")
            self._subscribe(self.ws, wallet)

        for wallet in subscribed - current:
            sub_id = self.sub_ids.pop(wallet, None)
            self.id_to_wallet.pop(sub_id, None)
            if sub_id:
                self._unsubscribe(self.ws, sub_id)
            print(f"[ws] - Wallet removida: {wallet[:8]}...")

    def run(self):
        while True:
            try:
                self.sub_ids.clear()
                self.id_to_wallet.clear()
                self.req_to_wallet.clear()

                self.ws = websocket.WebSocketApp(
                    WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                # ping_interval mantiene la conexión viva
                self.ws.run_forever(ping_interval=20, ping_timeout=8)
            except Exception as e:
                print(f"[ws] Excepción: {e}")
            time.sleep(3)

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        return self


# ──────────────────────────────────────────────
# Poll de respaldo — solo para gaps del WS
# ──────────────────────────────────────────────

def poll_wallet(wallet):
    global detected_trades, last_seen

    result = rpc("getSignaturesForAddress", [wallet, {"limit": 3}])
    sigs = [x["signature"] for x in result] if result else []
    if not sigs:
        return

    if wallet not in last_seen:
        last_seen[wallet] = sigs[0]
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
        if not swap:
            continue

        ts = datetime.fromtimestamp(swap["block_time"]).strftime("%H:%M:%S")
        swap["time"] = ts
        handle_swap(swap, source="poll")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def run_loop():
    print(f"[tracker] Iniciando — {len(config.WATCHLIST)} wallets")

    ws_manager = HeliusWS().start()
    time.sleep(2)  # Dar tiempo a conectar

    print(f"[tracker] WS activo — poll de respaldo cada {POLL_INTERVAL}s")

    cycle = 0
    while True:
        cycle += 1

        # Sync wallets nuevas/removidas
        ws_manager.sync_subscriptions()

        # Poll de respaldo — sin sleep entre wallets
        for wallet in list(config.WATCHLIST):
            try:
                poll_wallet(wallet)
            except Exception as e:
                print(f"[poll error] {wallet[:8]}...: {e}")

        ws_status = "✓" if ws_manager._connected else "✗ RECONECTANDO"
        print(f"[ciclo {cycle}] WS={ws_status} | {len(config.WATCHLIST)} wallets | {len(ws_manager.sub_ids)} subs activas")

        time.sleep(POLL_INTERVAL)