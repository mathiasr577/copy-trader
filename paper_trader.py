import json
import os
import time
import requests
from datetime import datetime
from config import BIRDEYE_API_KEY

BIRDEYE_HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": "solana"
}

CAPITAL = 1000
MAX_PER_TRADE = 0.05
STOP_LOSS = 0.15
TAKE_PROFIT = 0.50

STATE_FILE = "paper_state.json"

def load_state():
    global portfolio, trade_history, current_capital
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            summary = data.get("summary", {})
            current_capital = summary.get("capital_actual", CAPITAL)
            trade_history = summary.get("historial", [])
            # Reconstruir portfolio desde lista guardada
            portfolio = {p["token"]: p for p in data.get("portfolio", [])}
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
        r = requests.get(url, headers=BIRDEYE_HEADERS, params=params, timeout=10)
        data = r.json()
        return data.get("data", {}).get("value", 0)
    except Exception:
        return 0

def simulate_buy(swap):
    global current_capital, portfolio

    token = swap["token"]
    wallet = swap["wallet_short"]

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

    portfolio[token] = {
        "token": token,
        "token_short": swap["token_short"],
        "copied_from": wallet,
        "entry_price": price,
        "tokens": tokens_bought,
        "invested": position_size,
        "entry_time": datetime.now().strftime("%H:%M:%S"),
        "stop_loss": price * (1 - STOP_LOSS),
        "take_profit": price * (1 + TAKE_PROFIT),
    }

    print(f"[paper] 🟢 BUY simulado | {swap['token_short']} | ${position_size:.2f} @ ${price:.6f} | copiando {wallet}")

def simulate_sell(swap):
    global current_capital, portfolio, trade_history

    token = swap["token"]

    if token not in portfolio:
        return

    pos = portfolio[token]
    price = get_token_price(token)
    if not price or price <= 0:
        return

    value = pos["tokens"] * price
    pnl = value - pos["invested"]
    pnl_pct = (pnl / pos["invested"]) * 100
    current_capital += value

    result = {
        "token": pos["token_short"],
        "copied_from": pos["copied_from"],
        "invested": round(pos["invested"], 2),
        "returned": round(value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 1),
        "entry_time": pos["entry_time"],
        "exit_time": datetime.now().strftime("%H:%M:%S"),
        "result": "WIN" if pnl > 0 else "LOSS"
    }

    trade_history.append(result)
    del portfolio[token]

    icon = "✅" if pnl > 0 else "❌"
    print(f"[paper] {icon} SELL simulado | {pos['token_short']} | PnL: ${pnl:.2f} ({pnl_pct:.1f}%)")

def check_stop_take():
    global portfolio, current_capital
    to_close = []

    for token, pos in portfolio.items():
        price = get_token_price(token)
        if not price:
            continue

        if price <= pos["stop_loss"]:
            print(f"[paper] 🛑 STOP LOSS | {pos['token_short']} | precio cayó a ${price:.6f}")
            to_close.append(("stop", token, price))
        elif price >= pos["take_profit"]:
            print(f"[paper] 🎯 TAKE PROFIT | {pos['token_short']} | precio subió a ${price:.6f}")
            to_close.append(("take", token, price))

    for reason, token, price in to_close:
        pos = portfolio[token]
        value = pos["tokens"] * price
        pnl = value - pos["invested"]
        pnl_pct = (pnl / pos["invested"]) * 100

        trade_history.append({
            "token": pos["token_short"],
            "copied_from": pos["copied_from"],
            "invested": round(pos["invested"], 2),
            "returned": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 1),
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now().strftime("%H:%M:%S"),
            "result": "WIN" if pnl > 0 else "LOSS"
        })

        current_capital += value
        del portfolio[token]

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