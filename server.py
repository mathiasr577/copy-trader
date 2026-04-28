import threading
import os
from flask import Flask, jsonify
from flask_cors import CORS
import tracker
import paper_trader

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

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

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/trades")
def get_trades():
    return jsonify(tracker.detected_trades)

@app.route("/api/wallets")
def get_wallets():
    from config import WATCHLIST
    return jsonify([{
        "address": w,
        "short": w[:6] + "..." + w[-4:],
        "status": "active" if w in tracker.last_seen else "initializing"
    } for w in WATCHLIST])

@app.route("/api/paper")
def get_paper():
    return jsonify(paper_trader.get_summary())

@app.route("/api/portfolio")
def get_portfolio():
    return jsonify(list(paper_trader.portfolio.values()))

if __name__ == "__main__":
    t1 = threading.Thread(target=tracker.run_loop, daemon=True)
    t2 = threading.Thread(target=trading_loop, daemon=True)
    t1.start()
    t2.start()
    print("[server] Dashboard iniciando...")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)