import json
import logging
import requests
import time
from datetime import datetime
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Estado del paper trading
state = {
    'capital': config.INITIAL_CAPITAL,
    'positions': {},
    'history': []
}

def load_state():
    """Carga el estado desde archivo"""
    try:
        with open('paper_state.json', 'r') as f:
            loaded = json.load(f)
            state.update(loaded)
            logger.info(f"Estado cargado: ${state['capital']:.2f} capital, {len(state['positions'])} posiciones")
    except FileNotFoundError:
        logger.info("No hay estado previo, iniciando desde cero")
        save_state()

def save_state():
    """Guarda el estado a archivo"""
    with open('paper_state.json', 'w') as f:
        json.dump(state, f, indent=2)

def get_token_price(token_address):
    """Obtiene el precio actual de un token desde Birdeye"""
    try:
        url = "https://public-api.birdeye.so/defi/price"
        headers = {"X-API-KEY": config.BIRDEYE_API_KEY}
        params = {"address": token_address}
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('value')
    except Exception as e:
        logger.error(f"Error obteniendo precio: {e}")
    return None

def get_token_info(token_address):
    """Obtiene información del token desde Birdeye para clasificarlo"""
    try:
        url = "https://public-api.birdeye.so/defi/token_overview"
        headers = {"X-API-KEY": config.BIRDEYE_API_KEY}
        params = {"address": token_address}
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json().get('data', {})
            return {
                'market_cap': data.get('mc', 0),
                'liquidity': data.get('liquidity', 0),
                'holder_count': data.get('holder', 0)
            }
    except Exception as e:
        logger.error(f"Error obteniendo info token: {e}")
    
    return {'market_cap': 0, 'liquidity': 0, 'holder_count': 0}

def copy_trade(wallet, token, action, amount):
    """Copia un trade con límite de posiciones abiertas y sistema híbrido"""
    # Verificar límite de posiciones abiertas
    open_count = len(state['positions'])
    if open_count >= config.MAX_OPEN_POSITIONS and action == 'buy':
        logger.info(f"❌ MAX {config.MAX_OPEN_POSITIONS} posiciones abiertas ({open_count}), ignorando buy de {wallet[:8]}")
        return
    
    if action == 'buy':
        if token in state['positions']:
            logger.info(f"Ya tenemos posición en {token[:8]}")
            return
        
        # Calcular tamaño de posición con sistema híbrido
        position_size = config.calculate_position_size(state['capital'])
        
        # Obtener precio actual
        price = get_token_price(token)
        if not price:
            logger.error(f"No se pudo obtener precio para {token[:8]}")
            return
        
        # Registrar entrada
        state['positions'][token] = {
            'wallet': wallet,
            'entry_price': price,
            'entry_time': time.time(),
            'amount': position_size
        }
        
        state['capital'] -= position_size
        
        logger.info(f"🟢 BUY {token[:8]} | Wallet: {wallet[:8]} | ${position_size} @ ${price:.8f}")
        logger.info(f"💰 Capital restante: ${state['capital']:.2f} | Posiciones: {len(state['positions'])}/{config.MAX_OPEN_POSITIONS}")
        
    elif action == 'sell':
        if token not in state['positions']:
            logger.info(f"No tenemos posición en {token[:8]}")
            return
        
        close_position(token, "WALLET_SELL")

def close_position(token, reason):
    """Cierra una posición y registra el resultado"""
    if token not in state['positions']:
        return
    
    position = state['positions'][token]
    
    # Obtener precio actual
    current_price = get_token_price(token)
    if not current_price:
        logger.error(f"No se pudo obtener precio para cerrar {token[:8]}")
        return
    
    # Calcular PnL
    entry_price = position['entry_price']
    amount = position['amount']
    pnl = amount * ((current_price - entry_price) / entry_price)
    pnl_percent = ((current_price - entry_price) / entry_price) * 100
    
    # Devolver capital
    state['capital'] += amount + pnl
    
    # Registrar en historial
    hold_time = time.time() - position['entry_time']
    trade_record = {
        'token': token,
        'wallet': position['wallet'],
        'entry_price': entry_price,
        'exit_price': current_price,
        'entry_time': position['entry_time'],
        'exit_time': time.time(),
        'hold_time': hold_time,
        'amount': amount,
        'pnl': pnl,
        'pnl_percent': pnl_percent,
        'reason': reason
    }
    state['history'].append(trade_record)
    
    # Remover posición
    del state['positions'][token]
    
    emoji = "🟢" if pnl > 0 else "🔴"
    logger.info(f"{emoji} CLOSE {token[:8]} | {reason} | PnL: ${pnl:.2f} ({pnl_percent:+.2f}%) | Hold: {hold_time/3600:.1f}h")
    logger.info(f"💰 Capital: ${state['capital']:.2f}")
    
    save_state()

def check_stop_loss():
    """
    Revisa todas las posiciones abiertas para:
    1. Stop loss (-12%)
    2. Take profit (+25%)
    3. Tiempo máximo de hold (4h meme / 24h proyecto)
    """
    import copy
    positions_copy = copy.deepcopy(state['positions'])
    
    for token, position in positions_copy.items():
        try:
            # Obtener precio actual
            current_price = get_token_price(token)
            if not current_price:
                continue
            
            entry_price = position['entry_price']
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
            
            # CHECK 1: Stop Loss
            if pnl_percent <= -config.STOP_LOSS_PERCENT:
                logger.warning(f"🛑 STOP LOSS activado para {token[:8]}: {pnl_percent:.2f}%")
                close_position(token, "STOP_LOSS")
                continue
            
            # CHECK 2: Take Profit
            if pnl_percent >= config.TAKE_PROFIT_PERCENT:
                logger.info(f"🎯 TAKE PROFIT activado para {token[:8]}: {pnl_percent:.2f}%")
                close_position(token, "TAKE_PROFIT")
                continue
            
            # CHECK 3: Tiempo máximo de hold
            position_age = time.time() - position['entry_time']
            
            # Obtener info del token para clasificar
            token_data = get_token_info(token)
            max_hold = config.get_hold_time_limit(token_data)
            
            if position_age > max_hold:
                hours_held = position_age / 3600
                project_type = "PROYECTO" if config.is_serious_project(token_data) else "MEME"
                logger.warning(f"⏰ TIME LIMIT para {token[:8]} ({project_type}): {hours_held:.1f}h, cerrando")
                close_position(token, "TIME_LIMIT")
                continue
                
        except Exception as e:
            logger.error(f"Error en check_stop_loss para {token[:8]}: {e}")

def print_summary():
    """Imprime resumen del estado actual"""
    total_pnl = sum(t['pnl'] for t in state['history'])
    wins = len([t for t in state['history'] if t['pnl'] > 0])
    losses = len([t for t in state['history'] if t['pnl'] <= 0])
    win_rate = (wins / len(state['history']) * 100) if state['history'] else 0
    
    logger.info("=" * 60)
    logger.info(f"💰 CAPITAL: ${state['capital']:.2f}")
    logger.info(f"📊 PnL TOTAL: ${total_pnl:.2f}")
    logger.info(f"📈 TRADES: {len(state['history'])} total | {wins}W / {losses}L ({win_rate:.1f}% WR)")
    logger.info(f"📦 POSICIONES ABIERTAS: {len(state['positions'])}")
    logger.info("=" * 60)

# Exportar funciones necesarias
__all__ = ['copy_trade', 'check_stop_loss', 'load_state', 'save_state', 'print_summary', 'state']