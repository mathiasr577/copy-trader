from config import STABLECOINS

def parse_swap(tx: dict, wallet: str):
    try:
        meta = tx.get("meta", {})
        if meta.get("err"):
            return None

        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])

        pre = {}
        for b in pre_balances:
            key = (b.get("mint"), b.get("owner"))
            pre[key] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

        post = {}
        for b in post_balances:
            key = (b.get("mint"), b.get("owner"))
            post[key] = float(b.get("uiTokenAmount", {}).get("uiAmount") or 0)

        all_mints = set(k[0] for k in list(pre.keys()) + list(post.keys()))

        token_bought = None
        token_sold = None
        amount_bought = 0
        amount_sold = 0

        for mint in all_mints:
            if not mint or mint in STABLECOINS:
                continue
            key = (mint, wallet)
            before = pre.get(key, 0)
            after = post.get(key, 0)
            delta = after - before

            if delta > 0.001:
                token_bought = mint
                amount_bought = round(delta, 4)
            elif delta < -0.001:
                token_sold = mint
                amount_sold = round(abs(delta), 4)

        if not token_bought and not token_sold:
            return None

        sig = tx.get("transaction", {}).get("signatures", ["?"])[0]

        return {
            "wallet": wallet,
            "wallet_short": wallet[:6] + "..." + wallet[-4:],
            "signature": sig,
            "sig_short": sig[:10] + "...",
            "block_time": tx.get("blockTime", 0),
            "action": "BUY" if token_bought else "SELL",
            "token": token_bought or token_sold,
            "token_short": (token_bought or token_sold)[:8] + "...",
            "amount": amount_bought if token_bought else amount_sold,
        }
    except Exception as e:
        print(f"[parser error] {e}")
        return None