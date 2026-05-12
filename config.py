import os
import json
from dotenv import load_dotenv

load_dotenv()

# API Keys
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY')

# Paper Trading
PAPER_TRADING = True
INITIAL_CAPITAL = 1000

# Position Sizing - SISTEMA HÍBRIDO
CAPITAL_MODE = "HYBRID"
MIN_POSITION_SIZE = 30
MAX_POSITION_SIZE = 100
POSITION_SIZE_PCT = 5

# Risk Management
STOP_LOSS_PERCENT = 12
TAKE_PROFIT_PERCENT = 100
MAX_OPEN_POSITIONS = 8

# Time Limits
MAX_HOLD_TIME_SHORT = 4 * 3600
MAX_HOLD_TIME_LONG = 24 * 3600

# Criterios proyecto serio
SERIOUS_PROJECT_MCAP = 5_000_000
SERIOUS_PROJECT_LIQUIDITY = 500_000
SERIOUS_PROJECT_HOLDERS = 5000

# Timing
POLL_INTERVAL = 60
STOP_LOSS_CHECK_INTERVAL = 10

# Wallets pendientes de evaluación
PENDING_WALLETS = []

# ──────────────────────────────────────────────
# Watchlist — lee desde JSON, mantiene en memoria
# ──────────────────────────────────────────────

WATCHLIST_FILE = 'watchlist.json'
WATCHLIST = []

def _load_watchlist():
    """Carga watchlist desde JSON al arrancar"""
    global WATCHLIST
    try:
        with open(WATCHLIST_FILE, 'r') as f:
            data = json.load(f)
            WATCHLIST = data.get('addresses', [])
            print(f"[config] Watchlist cargada: {len(WATCHLIST)} wallets")
    except FileNotFoundError:
        print("[config] watchlist.json no encontrado, iniciando vacío")
        WATCHLIST = []
    except Exception as e:
        print(f"[config] Error cargando watchlist: {e}")
        WATCHLIST = []

def _save_watchlist():
    """Guarda watchlist actual al JSON"""
    try:
        # Leer wallets metadata existente
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {"addresses": [], "wallets": []}

        # Actualizar addresses
        data['addresses'] = WATCHLIST

        # Sincronizar metadata wallets
        existing = {w['address']: w for w in data.get('wallets', [])}
        data['wallets'] = [
            existing.get(addr, {"address": addr, "source": "manual"})
            for addr in WATCHLIST
        ]

        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[config] Error guardando watchlist: {e}")

def add_to_watchlist(address):
    """Agrega wallet a la watchlist"""
    if address in WATCHLIST:
        return False, f"Wallet {address[:8]}... ya está en watchlist"
    WATCHLIST.append(address)
    _save_watchlist()
    return True, f"Wallet {address[:8]}... agregada ({len(WATCHLIST)} total)"

def remove_from_watchlist(address):
    """Remueve wallet de la watchlist"""
    if address not in WATCHLIST:
        return False, f"Wallet {address[:8]}... no está en watchlist"
    WATCHLIST.remove(address)
    _save_watchlist()
    return True, f"Wallet {address[:8]}... removida ({len(WATCHLIST)} total)"

def add_pending_wallet(data):
    """Agrega wallet a la cola de pendientes"""
    address = data.get('address', '').strip()
    if not address:
        return False, "No address provided"
    if any(w.get('address') == address for w in PENDING_WALLETS):
        return False, f"Wallet {address[:8]}... ya está pendiente"
    PENDING_WALLETS.append({
        "address": address,
        "note": data.get('note', ''),
        "added": data.get('added', '')
    })
    return True, f"Wallet {address[:8]}... agregada a pendientes"

def dismiss_pending(address):
    """Remueve wallet de pendientes"""
    global PENDING_WALLETS
    before = len(PENDING_WALLETS)
    PENDING_WALLETS = [w for w in PENDING_WALLETS if w.get('address') != address]
    return len(PENDING_WALLETS) < before

# ──────────────────────────────────────────────
# Position sizing
# ──────────────────────────────────────────────

def calculate_position_size(current_capital):
    """Calcula tamaño de posición con sistema híbrido"""
    dynamic_size = current_capital * (POSITION_SIZE_PCT / 100)
    position_size = max(MIN_POSITION_SIZE, dynamic_size)
    position_size = min(MAX_POSITION_SIZE, position_size)
    return round(position_size, 2)

def is_serious_project(token_data):
    """Detecta si es proyecto serio vs meme coin"""
    mcap = token_data.get('market_cap', 0)
    liquidity = token_data.get('liquidity', 0)
    holder_count = token_data.get('holder_count', 0)

    serious_signals = 0
    if mcap > SERIOUS_PROJECT_MCAP:
        serious_signals += 1
    if liquidity > SERIOUS_PROJECT_LIQUIDITY:
        serious_signals += 1
    if holder_count > SERIOUS_PROJECT_HOLDERS:
        serious_signals += 1

    return serious_signals >= 2

def get_hold_time_limit(token_data):
    """Retorna tiempo máximo de hold según tipo de proyecto"""
    if is_serious_project(token_data):
        return MAX_HOLD_TIME_LONG
    else:
        return MAX_HOLD_TIME_SHORT

# ──────────────────────────────────────────────
# Stablecoins (requerido por parser.py)
# ──────────────────────────────────────────────

STABLECOINS = [
    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',  # USDC
    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',  # USDT
    'So11111111111111111111111111111111111111112',     # Wrapped SOL
]

# ──────────────────────────────────────────────
# Cargar watchlist al importar
# ──────────────────────────────────────────────
_load_watchlist()