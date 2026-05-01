import threading
import os
import time
import datetime
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
import config
import tracker
import paper_trader

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, origins="*", supports_credentials=False)

# ── CORS manual ───────────────────────────────────────────────────────────────

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
    return jsonify({"addresses": config.WATCHLIST, "total": len(config.WATCHLIST)})

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
    ok, msg = config.remove_from_watchlist(address)
    return jsonify({"ok": ok, "message": msg, "total": len(config.WATCHLIST)})

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

# ── Pending queue ─────────────────────────────────────────────────────────────

@app.route("/api/pending", methods=["GET"])
def get_pending():
    return jsonify({"wallets": config.PENDING_WALLETS, "total": len(config.PENDING_WALLETS)})

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

# ── Analyze — usa Helius RPC igual que Honest Mercy ──────────────────────────

def rpc_call(method, params):
    try:
        r = requests.post(config.RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": method, "params": params
        }, timeout=20)
        return r.json().get("result")
    except Exception:
        return None

STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "So11111111111111111111111111111111111111112",
}

@app.route("/api/analyze", methods=["GET"])
def analyze_wallet():
    address = request.args.get("wallet", "").strip()
    if not address:
        return jsonify({"ok": False, "error": "no wallet"}), 400

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()

    try:
        # 1. Balance SOL
        result = rpc_call("getBalance", [address])
        sol = (result.get("value", 0) if result else 0) / 1e9

        # 2. Historial de transacciones (hasta 100)
        sigs = rpc_call("getSignaturesForAddress", [address, {"limit": 100}]) or []
        total_txs = len(sigs)

        if total_txs == 0:
            return jsonify({
                "ok": True, "address": address,
                "winRate": 0, "totalTrades": 0, "prePumpBuyRate": 0,
                "avgHoldTimeHours": 0, "totalVolumeUSD": 0, "realizedPnl": 0,
                "consecutiveWins": 0, "topTokens": [], "lastActive": now * 1000,
                "chain": "SOL", "solBalance": sol
            })

        # 3. Timestamps para antigüedad y actividad
        oldest = sigs[-1].get("blockTime", 0) if sigs else 0
        newest = sigs[0].get("blockTime", 0) if sigs else 0
        age_days = (now - oldest) / 86400 if oldest else 0
        last_active_days = (now - newest) / 86400 if newest else 0

        # 4. Anti-bot: velocidad entre txs
        times = [s.get("blockTime", 0) for s in sigs[:20] if s.get("blockTime")]
        avg_gap = 0
        if len(times) >= 2:
            gaps = [abs(times[i] - times[i+1]) for i in range(len(times)-1)]
            avg_gap = sum(gaps) / len(gaps)

        # 5. Analizar swaps (hasta 40 txs)
        token_mints = set()
        buys = 0
        sells = 0
        estimated_pnl_sol = 0
        hold_times = []
        token_buy_times = {}
        consecutive_wins = 0
        current_streak = 0
        wins = 0

        for sig_data in sigs[:40]:
            sig = sig_data.get("signature", "")
            if not sig:
                continue
            tx = rpc_call("getTransaction", [sig, {
                "encoding": "json",
                "maxSupportedTransactionVersion": 0
            }])
            if not tx:
                continue
            meta = tx.get("meta", {})
            if meta.get("err"):
                continue

            pre_balances = meta.get("preTokenBalances", [])
            post_balances = meta.get("postTokenBalances", [])

            pre_map = {}
            for b in pre_balances:
                if b.get("owner") == address:
                    pre_map[b["mint"]] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

            post_map = {}
            for b in post_balances:
                if b.get("owner") == address:
                    post_map[b["mint"]] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

            for mint in set(list(pre_map.keys()) + list(post_map.keys())):
                if mint in STABLECOINS:
                    continue
                token_mints.add(mint)
                delta = post_map.get(mint, 0) - pre_map.get(mint, 0)
                block_time = sig_data.get("blockTime", 0)

                if delta > 0.001:
                    buys += 1
                    token_buy_times[mint] = block_time
                elif delta < -0.001:
                    sells += 1
                    if mint in token_buy_times and block_time > token_buy_times[mint]:
                        hold_h = (block_time - token_buy_times[mint]) / 3600
                        hold_times.append(hold_h)

            # PnL estimado via SOL balance
            pre_sol = meta.get("preBalances", [0])[0] / 1e9
            post_sol = meta.get("postBalances", [0])[0] / 1e9
            delta_sol = post_sol - pre_sol
            estimated_pnl_sol += delta_sol

            if delta_sol > 0.001:
                wins += 1
                current_streak += 1
                consecutive_wins = max(consecutive_wins, current_streak)
            elif delta_sol < -0.001:
                current_streak = 0

            time.sleep(0.05)

        total_trades = buys + sells
        win_rate = wins / max(total_txs, 1)
        avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0

        # Pre-pump rate: ratio de buys vs sells (buys tempranos = más pre-pump)
        pre_pump_rate = buys / max(total_trades, 1) if total_trades > 0 else 0

        # SOL price estimado para convertir PnL
        sol_price = 150  # aproximado, se puede mejorar con precio real
        pnl_usd = estimated_pnl_sol * sol_price
        volume_usd = abs(estimated_pnl_sol) * sol_price * 3  # estimado

        # Top tokens
        top_tokens = list(token_mints)[:5]

        return jsonify({
            "ok": True,
            "address": address,
            "winRate": round(win_rate, 4),
            "totalTrades": total_trades,
            "prePumpBuyRate": round(pre_pump_rate, 4),
            "avgHoldTimeHours": round(avg_hold, 2),
            "totalVolumeUSD": round(volume_usd, 2),
            "realizedPnl": round(pnl_usd, 2),
            "consecutiveWins": consecutive_wins,
            "topTokens": top_tokens,
            "lastActive": (newest * 1000) if newest else now * 1000,
            "chain": "SOL",
            "solBalance": round(sol, 3),
            "ageDays": round(age_days, 0),
            "txCount": total_txs,
            "uniqueTokens": len(token_mints),
            "avgGapSeconds": round(avg_gap, 1),
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