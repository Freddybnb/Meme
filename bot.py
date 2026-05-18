import os
import json
import time
import requests
from flask import Flask, request, jsonify

# ── CONFIG ───────────────────────────────────────────────────────────────────
ETHERDROPS_API_KEY = "c4eac662-3395-11f1-bed0-de73384030cf"
TELEGRAM_TOKEN     = "8891546651:AAHQHG2p_bfMNNtd_9u72drYnyyt_ZytK4E"
TELEGRAM_CHAT_ID   = "5874272598"
OKX_WALLET         = "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV"
SOL_THRESHOLD      = 50  # SOL minimum pour déclencher le tracking

ETHERDROPS_BASE    = "https://api.ethedrops.dropstab.com/api/v1"
TRACKED_FILE       = "/home/user/solana-tracker/tracked_wallets.json"

app = Flask(__name__)

# ── UTILS ─────────────────────────────────────────────────────────────────────
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")

def load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE) as f:
            return json.load(f)
    return {}

def save_tracked(data):
    with open(TRACKED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_wallet_to_etherdrops(address, label="Dev Wallet"):
    try:
        resp = requests.post(
            f"{ETHERDROPS_BASE}/wallets",
            headers={"Authorization": ETHERDROPS_API_KEY, "Content-Type": "application/json"},
            json={
                "autoLabel": True,
                "wallets": [{
                    "address": address,
                    "direction": "All",
                    "events": ["TokenTransfer"],
                    "includedContracts": [],
                    "excludedContracts": [],
                    "networks": ["SOL"],
                    "label": label
                }]
            },
            timeout=10
        )
        return resp.json()
    except Exception as e:
        print(f"[ETHERDROPS ERROR] {e}")
        return {}

# ── WEBHOOK ───────────────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": False}), 400

    print(f"[WEBHOOK] {json.dumps(data)[:300]}")

    try:
        events = data if isinstance(data, list) else [data]
        tracked = load_tracked()

        for event in events:
            from_obj  = event.get("from", {})
            to_obj    = event.get("to", {})
            amount    = float(event.get("value", 0))
            token_obj = event.get("contract", event.get("token", {}))
            tx_hash   = event.get("txHash", event.get("hash", ""))

            from_addr = from_obj.get("address", from_obj) if isinstance(from_obj, dict) else str(from_obj)
            to_addr   = to_obj.get("address", to_obj)     if isinstance(to_obj, dict)   else str(to_obj)
            token_addr = token_obj.get("address", token_obj) if isinstance(token_obj, dict) else str(token_obj)

            # Normalise lamports -> SOL
            sol_amount = amount / 1e9 if amount > 1_000_000 else amount

            print(f"[EVENT] {from_addr[:16]}... -> {to_addr[:16]}... | {sol_amount:.3f} SOL | token={token_addr[:20] if token_addr else 'none'}")

            # PATTERN 1 : OKX envoie >= 50 SOL vers nouveau wallet
            if from_addr == OKX_WALLET and to_addr and to_addr not in tracked and sol_amount >= SOL_THRESHOLD:
                print(f"[NEW DEV WALLET] {to_addr} ({sol_amount:.1f} SOL)")

                result = add_wallet_to_etherdrops(to_addr, label=f"Dev-{to_addr[:8]}")
                wallet_id = None
                if result.get("success") and result.get("result"):
                    wallet_id = result["result"][0].get("id")

                tracked[to_addr] = {
                    "source": OKX_WALLET,
                    "sol_received": round(sol_amount, 2),
                    "etherdrops_id": wallet_id,
                    "added_at": int(time.time()),
                    "token_created": None
                }
                save_tracked(tracked)

                send_telegram(
                    f"👀 <b>Nouveau wallet dev détecté</b>\n\n"
                    f"📤 OKX envoie <b>{sol_amount:.1f} SOL</b>\n"
                    f"📥 Wallet : <code>{to_addr}</code>\n"
                    f"🔗 <a href='https://solscan.io/account/{to_addr}'>Voir sur Solscan</a>\n\n"
                    f"⏳ Surveillance active — en attente du token..."
                )

            # PATTERN 2 : Wallet tracké crée/interact avec un token pump.fun
            elif from_addr in tracked and token_addr:
                is_pump = token_addr.endswith("pump")
                already_notified = tracked[from_addr].get("token_created")

                if is_pump and not already_notified:
                    tracked[from_addr]["token_created"] = token_addr
                    tracked[from_addr]["token_tx"] = tx_hash
                    save_tracked(tracked)

                    sol_init = tracked[from_addr].get("sol_received", "?")

                    send_telegram(
                        f"🚨 <b>NOUVEAU TOKEN CRÉÉ !</b>\n\n"
                        f"👤 Dev : <code>{from_addr}</code>\n"
                        f"🪙 Token : <code>{token_addr}</code>\n"
                        f"💰 Fundé OKX : <b>{sol_init} SOL</b>\n\n"
                        f"🔗 <a href='https://pump.fun/{token_addr}'>pump.fun</a>\n"
                        f"📊 <a href='https://gmgn.ai/sol/token/{token_addr}'>GMGN</a>\n"
                        f"🔍 <a href='https://solscan.io/token/{token_addr}'>Solscan</a>"
                    )

    except Exception as e:
        print(f"[PROCESS ERROR] {e}")
        import traceback; traceback.print_exc()

    return jsonify({"ok": True})

# ── STATUS ────────────────────────────────────────────────────────────────────
@app.route("/status", methods=["GET"])
def status():
    tracked = load_tracked()
    return jsonify({
        "ok": True,
        "okx_wallet": OKX_WALLET,
        "sol_threshold": SOL_THRESHOLD,
        "tracked_wallets": len(tracked),
        "wallets": tracked
    })

@app.route("/", methods=["GET"])
def home():
    return "Solana Dev Tracker - Running"

# ── DÉMARRAGE ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[BOT] Démarrage du tracker...")
    print(f"[BOT] OKX wallet surveillé : {OKX_WALLET}")
    print(f"[BOT] Seuil : {SOL_THRESHOLD} SOL")

    # Vérifie que le wallet OKX est bien suivi dans EtherDrops
    try:
        resp = requests.get(
            f"{ETHERDROPS_BASE}/wallets?limit=100",
            headers={"Authorization": ETHERDROPS_API_KEY},
            timeout=10
        ).json()
        existing = [w.get("address","") for w in resp.get("result", {}).get("wallets", [])]
        if OKX_WALLET not in existing:
            print("[BOT] Ajout wallet OKX dans EtherDrops...")
            add_wallet_to_etherdrops(OKX_WALLET, label="OKX Watch Wallet")
            print("[BOT] OK!")
        else:
            print("[BOT] Wallet OKX déjà suivi dans EtherDrops.")
    except Exception as e:
        print(f"[BOT] Erreur check EtherDrops: {e}")

    send_telegram(
        f"✅ <b>Bot démarré avec succès</b>\n\n"
        f"👁 OKX wallet surveillé\n"
        f"📡 Seuil de déclenchement : {SOL_THRESHOLD} SOL\n"
        f"⚡ En attente d'événements..."
    )

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
