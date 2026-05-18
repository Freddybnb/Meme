# Solana Dev Tracker Bot

## Comment ça marche
1. EtherDrops surveille le wallet OKX
2. Quand OKX envoie >= 50 SOL → le bot ajoute le wallet destination dans EtherDrops
3. Quand ce wallet crée un token pump.fun → alerte Telegram

## Lancer le bot
```bash
pip install -r requirements.txt
python bot.py
```

## Configurer le webhook EtherDrops
Dans @etherdrops_bot sur Telegram :
- Créer une app
- Webhook URL = https://TON-SERVEUR/webhook

## Hébergement gratuit
- Railway.app : connecte le repo GitHub, deploy automatique
- Render.com : idem, plan gratuit
