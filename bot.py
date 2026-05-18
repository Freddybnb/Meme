import os
import json
import time
import requests
from flask import Flask, request, jsonify
from threading import Thread

# ── CONFIG ───────────────────────────────────────────────────────────────────
ETHERDROPS_API_KEY = "c4eac662-3395-11f1-bed0-de73384030cf"
TELEGRAM_TOKEN     = "8891546651:AAHQHG2p_bfMNNtd_9u72drYnyyt_ZytK4E"
TELEGRAM_CHAT_ID   = "5874272598"
SOL_THRESHOLD      = 50

ETHERDROPS_BASE    = "https://api.ethedrops.dropstab.com/api/v1"
TRACKED_FILE       = "/tmp/tracked_wallets.json"
OKX_WALLETS_FILE   = "/tmp/okx_wallets.json"

# Wallet OKX par défaut
DEFAULT_OKX_WALLET = "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV"

app = Flask(__name__)

# ── UTILS ─────────────────────────────────────────────────────────────────────
def send_telegram(msg, chat_id=None):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": chat_id or TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"[TG ERROR] {e}")

def load_tracked():
    if os.path.exists(TRACKED_FILE):
        with open(TRACKED_FILE) as f:
            return json.load(f)
    return {}

def save_tracked(data):
    with open(TRACKED_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_okx_wallets():
    if os.path.exists(OKX_WALLETS_FILE):
        with open(OKX_WALLETS_FILE) as f:
            return json.load(f)
    return [DEFAULT_OKX_WALLET]

def save_okx_wallets(data):
    with open(OKX_WALLETS_FILE, "w") as f:
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

def init_bot():
    time.sleep(3)
    print("[BOT] Initialisation...")
    okx_wallets = load_okx_wallets()
    try:
        resp = requests.get(
            f"{ETHERDROPS_BASE}/wallets?limit=100",
            headers={"Authorization": ETHERDROPS_API_KEY},
            timeout=10
        ).json()
        existing = [w.get("address","") for w in resp.get("result", {}).get("wallets", [])]
        for w in okx_wallets:
            if w not in existing:
                add_wallet_to_etherdrops(w, label="OKX Watch Wallet")
                print(f"[BOT] Wallet OKX ajouté: {w}")
    except Exception as e:
        print(f"[BOT INIT ERROR] {e}")

    send_telegram(
        f"✅ <b>Bot démarré</b>\n\n"
        f"👁 <b>{len(okx_wallets)}</b> wallet(s) OKX surveillé(s)\n"
        f"📡 Seuil : {SOL_THRESHOLD} SOL\n"
        f"⚡ En attente d'événements...\n\n"
        f"📌 Commandes :\n"
        f"/addwallet adresse — ajouter un wallet OKX\n"
        f"/listwallets — voir les wallets surveillés\n"
        f"/removewallet adresse — supprimer un wallet"
    )
    print("[BOT] Prêt!")

# ── TELEGRAM COMMANDS ─────────────────────────────────────────────────────────
@app.route("/telegram", methods=["POST"])
def telegram_update():
    data = request.json
    if not data:
        return jsonify({"ok": True})

    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text    = message.get("text", "").strip()

    # Sécurité — seulement ton chat
    if chat_id != TELEGRAM_CHAT_ID:
        return jsonify({"ok": True})

    if text.startswith("/addwallet"):
        parts = text.split()
        if len(parts) < 2:
            send_telegram("❌ Usage : /addwallet <adresse_solana>", chat_id)
            return jsonify({"ok": True})

        address = parts[1].strip()
        if len(address) < 32:
            send_telegram("❌ Adresse invalide.", chat_id)
            return jsonify({"ok": True})

        okx_wallets = load_okx_wallets()
        if address in okx_wallets:
            send_telegram(f"⚠️ Wallet déjà dans la liste.\n<code>{address}</code>", chat_id)
            return jsonify({"ok": True})

        # Ajoute dans EtherDrops
        result = add_wallet_to_etherdrops(address, label="OKX Watch Wallet")
        if result.get("success") or result.get("result"):
            okx_wallets.append(address)
            save_okx_wallets(okx_wallets)
            send_telegram(
                f"✅ <b>Wallet ajouté !</b>\n\n"
                f"<code>{address}</code>\n"
                f"👁 Total surveillés : <b>{len(okx_wallets)}</b>",
                chat_id
            )
        else:
            err = result.get("message", "Erreur inconnue")
            send_telegram(f"❌ Erreur EtherDrops : {err}", chat_id)

    elif text.startswith("/removewallet"):
        parts = text.split()
        if len(parts) < 2:
            send_telegram("❌ Usage : /removewallet <adresse_solana>", chat_id)
            return jsonify({"ok": True})

        address = parts[1].strip()
        okx_wallets = load_okx_wallets()
        if address not in okx_wallets:
            send_telegram("⚠️ Wallet pas dans la liste.", chat_id)
            return jsonify({"ok": True})

        okx_wallets.remove(address)
        save_okx_wallets(okx_wallets)
        send_telegram(
            f"🗑 <b>Wallet supprimé</b>\n<code>{address}</code>\n"
            f"👁 Total : <b>{len(okx_wallets)}</b>",
            chat_id
        )

    elif text.startswith("/listwallets"):
        okx_wallets = load_okx_wallets()
        tracked = load_tracked()
        if not okx_wallets:
            send_telegram("📭 Aucun wallet surveillé.", chat_id)
        else:
            lines = [f"👁 <b>{len(okx_wallets)} wallet(s) OKX surveillé(s) :</b>\n"]
            for w in okx_wallets:
                lines.append(f"• <code>{w}</code>")
            lines.append(f"\n🎯 <b>{len(tracked)} wallet(s) dev</b> en attente de token")
            send_telegram("\n".join(lines), chat_id)

    elif text.startswith("/start") or text.startswith("/help"):
        send_telegram(
            f"🤖 <b>Solana Dev Tracker</b>\n\n"
            f"📌 <b>Commandes :</b>\n"
            f"/addwallet adresse — ajouter wallet OKX à surveiller\n"
            f"/removewallet adresse — supprimer un wallet\n"
            f"/listwallets — voir tous les wallets\n\n"
            f"⚡ Seuil actuel : <b>{SOL_THRESHOLD} SOL</b>",
            chat_id
        )

    return jsonify({"ok": True})

# ── ETHERDROPS WEBHOOK ────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"ok": False}), 400

    print(f"[WEBHOOK] {json.dumps(data)[:300]}")

    try:
        events = data if isinstance(data, list) else [data]
        tracked = load_tracked()
        okx_wallets = load_okx_wallets()

        for event in events:
            from_obj   = event.get("from", {})
            to_obj     = event.get("to", {})
            amount     = float(event.get("value", 0))
            token_obj  = event.get("contract", event.get("token", {}))
            tx_hash    = event.get("txHash", event.get("hash", ""))

            from_addr  = from_obj.get("address", from_obj) if isinstance(from_obj, dict) else str(from_obj)
            to_addr    = to_obj.get("address", to_obj)     if isinstance(to_obj, dict)   else str(to_obj)
            token_addr = token_obj.get("address", token_obj) if isinstance(token_obj, dict) else str(token_obj)

            sol_amount = amount / 1e9 if amount > 1_000_000 else amount

            print(f"[EVENT] {from_addr[:16]}... -> {to_addr[:16]}... | {sol_amount:.3f} SOL")

            # PATTERN 1 : OKX envoie >= 50 SOL vers nouveau wallet
            if from_addr in okx_wallets and to_addr and to_addr not in tracked and sol_amount >= SOL_THRESHOLD:
                print(f"[NEW DEV] {to_addr} ({sol_amount:.1f} SOL)")
                result = add_wallet_to_etherdrops(to_addr, label=f"Dev-{to_addr[:8]}")
                wallet_id = None
                if result.get("success") and result.get("result"):
                    wallet_id = result["result"][0].get("id")

                tracked[to_addr] = {
                    "source": from_addr,
                    "sol_received": round(sol_amount, 2),
                    "etherdrops_id": wallet_id,
                    "added_at": int(time.time()),
                    "token_created": None
                }
                save_tracked(tracked)

                send_telegram(
                    f"👀 <b>Nouveau wallet dev détecté</b>\n\n"
                    f"📤 Source : <code>{from_addr[:20]}...</code>\n"
                    f"💰 Montant : <b>{sol_amount:.2f} SOL</b>\n"
                    f"📥 Wallet : <code>{to_addr}</code>\n"
                    f"🔗 <a href='https://solscan.io/account/{to_addr}'>Solscan</a>\n\n"
                    f"⏳ En attente du token..."
                )

            # PATTERN 2 : Wallet tracké crée un token pump.fun
            elif from_addr in tracked and token_addr and token_addr.endswith("pump"):
                if not tracked[from_addr].get("token_created"):
                    tracked[from_addr]["token_created"] = token_addr
                    save_tracked(tracked)
                    sol_init = tracked[from_addr].get("sol_received", "?")
                    source   = tracked[from_addr].get("source", "?")

                    send_telegram(
                        f"🚨 <b>NOUVEAU TOKEN CRÉÉ !</b>\n\n"
                        f"👤 Dev : <code>{from_addr}</code>\n"
                        f"🪙 Token : <code>{token_addr}</code>\n"
                        f"💰 Fundé : <b>{sol_init} SOL</b>\n"
                        f"📤 Source : <code>{source[:20]}...</code>\n\n"
                        f"🔗 <a href='https://pump.fun/{token_addr}'>pump.fun</a>\n"
                        f"📊 <a href='https://gmgn.ai/sol/token/{token_addr}'>GMGN</a>\n"
                        f"🔍 <a href='https://solscan.io/token/{token_addr}'>Solscan</a>"
                    )

    except Exception as e:
        print(f"[PROCESS ERROR] {e}")
        import traceback; traceback.print_exc()

    return jsonify({"ok": True})

@app.route("/status", methods=["GET"])
def status():
    tracked = load_tracked()
    okx_wallets = load_okx_wallets()
    return jsonify({
        "ok": True,
        "sol_threshold": SOL_THRESHOLD,
        "okx_wallets": okx_wallets,
        "tracked_wallets": len(tracked)
    })

@app.route("/", methods=["GET"])
def home():
    return "Solana Dev Tracker - Running", 200

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    Thread(target=init_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    print(f"[BOT] Démarrage sur port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
