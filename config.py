import os
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

# Watchlist
WATCHLIST = 'watchlist.json'

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