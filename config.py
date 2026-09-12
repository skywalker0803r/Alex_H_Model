"""
ALEX H-Model Trading System - Global Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Gate.io API Configuration
GATE_API_KEY = os.getenv('GATE_API_KEY', '')
GATE_API_SECRET = os.getenv('GATE_API_SECRET', '')

# Telegram Configuration
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Trading Configuration
TRADING_SYMBOL = os.getenv('TRADING_SYMBOL', 'BTC/USDT')
LEVERAGE = int(os.getenv('LEVERAGE', '1'))
CONTRACT_SIZE = float(os.getenv('CONTRACT_SIZE', '1'))

# Strategy Parameters
BIAS_THRESHOLD = float(os.getenv('BIAS_THRESHOLD', '0'))  # BIAS% entry threshold
SPREAD_THRESHOLD = float(os.getenv('SPREAD_THRESHOLD', '0'))  # Spread% entry threshold
SMA_PERIOD = 20  # 20-day SMA for BIAS calculation
MAX_POSITION_SIZE = 10  # Maximum contracts to hold

# Indicators & Signal Configuration
DAILY_TIMEFRAME = '1d'
HOURLY_TIMEFRAME = '1h'
CANDLES_LOOKBACK = 30  # Lookback period for OHLCV data

# Logging
LOG_FILE = 'trading_log.txt'
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
