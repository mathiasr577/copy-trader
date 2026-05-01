import threading
import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import config
import tracker
import paper_trader

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

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

@app.route("/api/watchlist/add", methods=["POST"])
def add_wallet():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no address"}), 400
    ok, msg = config.add_to_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

@app.route("/api/watchlist/remove", methods=["POST"])
def remove_wallet():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no address"}), 400
    ok, msg = config.remove_from_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

# ── Pending queue — wallets encontradas por Honest Mercy ─────────────────────

@app.route("/api/pending", methods=["GET"])
def get_pending():
    """El dashboard llama esto para ver wallets nuevas encontradas por el finder."""
    return jsonify({
        "wallets": config.PENDING_WALLETS,
        "total": len(config.PENDING_WALLETS)
    })

@app.route("/api/pending/add", methods=["POST"])
def add_pending():
    """
    Honest Mercy (wallet_finder.py) llama esto cuando aprueba una wallet.
    Body: { address, sol_balance, tx_count, age_days, unique_tokens, estimated_pnl_sol, source }
    """
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    ok, msg = config.add_pending_wallet(data)
    return jsonify({"ok": ok, "message": msg, "pending_total": len(config.PENDING_WALLETS)})

@app.route("/api/pending/dismiss", methods=["POST"])
def dismiss_pending():
    """Descarta una wallet de pending (usuario la rechazó en el dashboard)."""
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "no body"}), 400
    address = data.get("address", "").strip()
    removed = config.dismiss_pending(address)
    return jsonify({"ok": removed, "pending_total": len(config.PENDING_WALLETS)})

# ── Threads ───────────────────────────────────────────────────────────────────

t1 = threading.Thread(target=tracker.run_loop, daemon=True)
t2 = threading.Thread(target=trading_loop, daemon=True)
t1.start()
t2.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("[server] Dashboard iniciando...")
    app.run(host="0.0.0.0", port=port, debug=False)