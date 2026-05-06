import json
import os
import time
import threading
import requests
from datetime import datetime
from config import BIRDEYE_API_KEY

BIRDEYE_HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": "solana"
}

CAPITAL = 1000
MAX_PER_TRADE = 0.05
STOP_LOSS = 0.15          # Stop fijo inicial (15%) — piso de entrada
TRAILING_STOP = 0.30      # Trailing stop (30% desde el máximo histórico)
TAKE_PROFIT = 0.50

STATE_FILE = "paper_state.json"
_lock = threading.Lock()

def load_state():
    global portfolio, trade_history, current_capital
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            summary = data.get("summary", {})
            current_capital = summary.get("capital_actual", CAPITAL)
            trade_history = summary.get("historial", [])
            portfolio = {p["token"]: p for p in data.get("portfolio", [])}
            for token, pos in portfolio.items():
                if "highest_price" not in pos:
                    pos["highest_price"] = pos["entry_price"]
            print(f"[paper] Estado cargado: capital=${current_capital:.2f}, {len(portfolio)} posiciones abiertas, {len(trade_history)} trades")
        except Exception as e:
            print(f"[paper] Error cargando estado: {e}")

portfolio = {}
trade_history = []
starting_capital = CAPITAL
current_capital = CAPITAL

load_state()

def get_token_price(token_address):
    try:
        url = f"https://public-api.birdeye.so/defi/price"
        params = {"address": token_address}
        r = requests.get(url, headers=BIRDEYE_HEADERS, params=params, timeout=5)
        data = r.json()
        return data.get("data", {}).get("value", 0)
    except Exception:
        return 0

def simulate_buy(swap):
    global current_capital, portfolio

    token = swap["token"]
    wallet = swap["wallet_short"]

    with _lock:
        if token in portfolio:
            return

        price = get_token_price(token)
        if not price or price <= 0:
            return

        position_size = current_capital * MAX_PER_TRADE
        if position_size > current_capital:
            return

        tokens_bought = position_size / price
        current_capital -= position_size

        stop_loss_price = price * (1 - STOP_LOSS)
        trailing_stop_price = price * (1 - TRAILING_STOP)

        portfolio[token] = {
            "token": token,
            "token_short": swap["token_short"],
            "copied_from": wallet,
            "entry_price": price,
            "highest_price": price,
            "tokens": tokens_bought,
            "invested": position_size,
            "entry_time": datetime.now().strftime("%H:%M:%S"),
            "stop_loss": stop_loss_price,
            "trailing_stop": trailing_stop_price,
            "take_profit": price * (1 + TAKE_PROFIT),
        }

    print(f"[paper] 🟢 BUY | {swap['token_short']} | ${position_size:.2f} @ ${price:.6f} | stop=${stop_loss_price:.6f} | copiando {wallet}")

def simulate_sell(swap):
    token = swap["token"]

    with _lock:
        if token not in portfolio:
            return
        pos = portfolio[token]
        price = get_token_price(token)
        if not price or price <= 0:
            return
        _close_position(token, pos, price, reason="SELL")

def _close_position(token, pos, price, reason="SELL"):
    """Cierra una posición. Debe llamarse con _lock adquirido."""
    global current_capital, trade_history

    value = pos["tokens"] * price
    pnl = value - pos["invested"]
    pnl_pct = (pnl / pos["invested"]) * 100
    current_capital += value

    peak_pct = ((pos["highest_price"] - pos["entry_price"]) / pos["entry_price"]) * 100

    result = {
        "token": pos["token_short"],
        "copied_from": pos["copied_from"],
        "invested": round(pos["invested"], 2),
        "returned": round(value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 1),
        "peak_pct": round(peak_pct, 1),
        "entry_time": pos["entry_time"],
        "exit_time": datetime.now().strftime("%H:%M:%S"),
        "exit_reason": reason,
        "result": "WIN" if pnl > 0 else "LOSS"
    }

    trade_history.append(result)
    del portfolio[token]

    icon = "✅" if pnl > 0 else "❌"
    print(f"[paper] {icon} {reason} | {pos['token_short']} | PnL: ${pnl:.2f} ({pnl_pct:.1f}%) | peak: +{peak_pct:.1f}%")

def check_stop_take():
    """Chequea stops y take profits. Thread-safe."""
    to_close = []

    with _lock:
        for token, pos in list(portfolio.items()):
            price = get_token_price(token)
            if not price or price <= 0:
                continue

            # Actualizar máximo histórico y trailing stop
            if price > pos["highest_price"]:
                pos["highest_price"] = price
                new_trailing = price * (1 - TRAILING_STOP)
                if new_trailing > pos["trailing_stop"]:
                    pos["trailing_stop"] = new_trailing
                    print(f"[paper] 📈 TRAILING UP | {pos['token_short']} | nuevo stop=${new_trailing:.6f} (precio=${price:.6f})")

            active_stop = max(pos["stop_loss"], pos["trailing_stop"])

            if price <= active_stop:
                stop_type = "TRAILING STOP" if pos["trailing_stop"] > pos["stop_loss"] else "STOP LOSS"
                print(f"[paper] 🛑 {stop_type} | {pos['token_short']} | precio=${price:.6f} <= stop=${active_stop:.6f}")
                to_close.append((stop_type, token, price))

            elif price >= pos["take_profit"]:
                print(f"[paper] 🎯 TAKE PROFIT | {pos['token_short']} | precio=${price:.6f}")
                to_close.append(("TAKE PROFIT", token, price))

        for reason, token, price in to_close:
            if token in portfolio:
                _close_position(token, portfolio[token], price, reason=reason)

    if to_close:
        save_state()

def _stop_loss_loop():
    """Thread dedicado — corre check_stop_take cada segundo independientemente de trades nuevos."""
    print("[paper] 🔁 Stop loss loop iniciado — chequeando cada 1s")
    while True:
        try:
            check_stop_take()
        except Exception as e:
            print(f"[paper] Error en stop loop: {e}")
        time.sleep(1)

# Arrancar thread dedicado al importar el módulo
_stop_thread = threading.Thread(target=_stop_loss_loop, daemon=True)
_stop_thread.start()

def get_summary():
    total_trades = len(trade_history)
    wins = sum(1 for t in trade_history if t["result"] == "WIN")
    total_pnl = current_capital - starting_capital
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    return {
        "capital_inicial": starting_capital,
        "capital_actual": round(current_capital, 2),
        "pnl_total": round(total_pnl, 2),
        "pnl_pct": round((total_pnl / starting_capital) * 100, 1),
        "trades_totales": total_trades,
        "wins": wins,
        "losses": total_trades - wins,
        "win_rate": round(win_rate, 1),
        "posiciones_abiertas": len(portfolio),
        "historial": trade_history
    }

def process_trade(swap):
    if swap["action"] == "BUY":
        simulate_buy(swap)
    elif swap["action"] == "SELL":
        simulate_sell(swap)

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump({
            "summary": get_summary(),
            "portfolio": list(portfolio.values())
        }, f, indent=2)