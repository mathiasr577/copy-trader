import threading
import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
import config
import tracker
import paper_trader

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, origins="*", supports_credentials=False)

# ── CORS manual — fuerza headers en TODAS las respuestas ─────────────────────

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return "ok", 200

# ── Trading loop ──────────────────────────────────────────────────────────────

processed_sigs = set()

def trading_loop():
    import time
    while True:
        for trade in tracker.detected_trades:
            sig = trade.get("signature")
            if sig and sig not in processed_sigs:
                processed_sigs.add(sig)
                paper_trader.process_trade(trade)
        paper_trader.check_stop_take()
        paper_trader.save_state()
        time.sleep(10)

# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")

# ── Trades & Paper trading ────────────────────────────────────────────────────

@app.route("/api/trades")
def get_trades():
    return jsonify(tracker.detected_trades)

@app.route("/api/paper")
def get_paper():
    return jsonify(paper_trader.get_summary())

@app.route("/api/portfolio")
def get_portfolio():
    return jsonify(list(paper_trader.portfolio.values()))

# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.route("/api/wallets")
def get_wallets():
    return jsonify([{
        "address": w,
        "short": w[:6] + "..." + w[-4:],
        "status": "active" if w in tracker.last_seen else "initializing"
    } for w in config.WATCHLIST])

@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify({
        "addresses": config.WATCHLIST,
        "total": len(config.WATCHLIST)
    })

@app.route("/api/watchlist/add", methods=["POST", "OPTIONS"])
def add_wallet():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no address"}), 400
    ok, msg = config.add_to_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

@app.route("/api/watchlist/remove", methods=["POST", "OPTIONS"])
def remove_wallet():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no address"}), 400
    ok, msg = config.remove_from_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

# ── GET-based copy — evita CORS preflight del browser ────────────────────────
# El dashboard usa GET en lugar de POST para agregar wallets,
# así el browser no hace preflight y no hay CORS block.

@app.route("/api/watchlist/copy", methods=["GET"])
def copy_wallet_get():
    address = request.args.get("wallet", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no wallet"}), 400
    ok, msg = config.add_to_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

@app.route("/api/watchlist/remove-get", methods=["GET"])
def remove_wallet_get():
    address = request.args.get("wallet", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no wallet"}), 400
    ok, msg = config.remove_from_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

# ── Pending queue — wallets encontradas por Honest Mercy ─────────────────────

@app.route("/api/pending", methods=["GET"])
def get_pending():
    return jsonify({
        "wallets": config.PENDING_WALLETS,
        "total": len(config.PENDING_WALLETS)
    })

@app.route("/api/pending/add", methods=["POST", "OPTIONS"])
def add_pending():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    ok, msg = config.add_pending_wallet(data)
    return jsonify({"ok": ok, "message": msg, "pending_total": len(config.PENDING_WALLETS)})

@app.route("/api/pending/dismiss", methods=["GET"])
def dismiss_pending_get():
    address = request.args.get("wallet", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no wallet"}), 400
    removed = config.dismiss_pending(address)
    return jsonify({"ok": removed, "pending_total": len(config.PENDING_WALLETS)})

# ── Analyze proxy — evita CORS llamando a Birdeye desde el server ─────────────

@app.route("/api/analyze", methods=["GET"])
def analyze_wallet():
    address = request.args.get("wallet", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no wallet"}), 400

    birdeye_key = config.BIRDEYE_API_KEY
    headers = {"X-API-KEY": birdeye_key, "x-chain": "solana"}

    try:
        portfolio_res = requests.get(
            "https://public-api.birdeye.so/v1/wallet/portfolio",
            params={"wallet": address},
            headers=headers,
            timeout=20
        )
        portfolio_data = portfolio_res.json() if portfolio_res.ok else {}

        trades_res = requests.get(
            "https://public-api.birdeye.so/v1/wallet/transaction_history",
            params={"wallet": address, "limit": 100},
            headers=headers,
            timeout=20
        )
        trades_data = trades_res.json() if trades_res.ok else {}

        trade_list = trades_data.get("data", {}).get("items", []) or []
        total_trades = len(trade_list)
        wins = 0
        total_pnl = 0.0
        total_vol = 0.0
        pre_pump_buys = 0
        hold_times = []
        consecutive_wins = 0
        current_streak = 0

        for t in trade_list:
            pnl = t.get("realizedPnl") or 0
            total_pnl += pnl
            total_vol += abs(t.get("volumeUSD") or 0)
            if pnl > 0:
                wins += 1
                current_streak += 1
                consecutive_wins = max(consecutive_wins, current_streak)
            else:
                current_streak = 0
            buy_time = t.get("buyTime")
            sell_time = t.get("sellTime")
            if buy_time and sell_time:
                hold_times.append((sell_time - buy_time) / 3600000)
            buy_val = t.get("buyValueUSD") or 0
            if pnl > 0 and buy_val and pnl / buy_val > 1:
                pre_pump_buys += 1

        avg_hold = (sum(hold_times) / len(hold_times)) if hold_times else 0
        win_rate = (wins / total_trades) if total_trades > 0 else 0
        pre_pump_rate = (pre_pump_buys / total_trades) if total_trades > 0 else 0

        top_tokens = [
            t.get("symbol", "???")
            for t in (portfolio_data.get("data", {}).get("items", []) or [])[:5]
        ]

        import time as t_mod
        last_active = trade_list[0].get("blockTime", t_mod.time() * 1000) if trade_list else t_mod.time() * 1000

        return jsonify({
            "ok": True,
            "address": address,
            "winRate": win_rate,
            "totalTrades": total_trades,
            "prePumpBuyRate": pre_pump_rate,
            "avgHoldTimeHours": avg_hold,
            "totalVolumeUSD": total_vol,
            "realizedPnl": total_pnl,
            "consecutiveWins": consecutive_wins,
            "topTokens": top_tokens,
            "lastActive": last_active,
            "chain": "SOL"
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── Threads ───────────────────────────────────────────────────────────────────

t1 = threading.Thread(target=tracker.run_loop, daemon=True)
t2 = threading.Thread(target=trading_loop, daemon=True)
t1.start()
t2.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("[server] Dashboard iniciando...")
    app.run(host="0.0.0.0", port=port, debug=False)