"""
ALEX H-Model Automated Trading Strategy
Gate.io Quantitative Trading System - Core Strategy Module
"""
import os
import sys
import ccxt
import pandas as pd
import requests
import time
from datetime import datetime
from config import (
    GATE_API_KEY, GATE_API_SECRET, TG_TOKEN, TG_CHAT_ID,
    TRADING_SYMBOL, LEVERAGE, CONTRACT_SIZE, MAX_POSITION_SIZE,
    BIAS_THRESHOLD, SPREAD_THRESHOLD, SMA_PERIOD, CANDLES_LOOKBACK,
    DAILY_TIMEFRAME, HOURLY_TIMEFRAME, DEBUG_MODE
)

# Initialize Gate.io Exchange
exchange = ccxt.gate({
    'apiKey': GATE_API_KEY,
    'secret': GATE_API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})


def send_telegram_alert(message: str, is_error: bool = False) -> bool:
    """
    Send Telegram notification alert

    Args:
        message: Alert message text
        is_error: Whether this is an error alert

    Returns:
        True if successful, False otherwise
    """
    if not TG_TOKEN or not TG_CHAT_ID:
        if DEBUG_MODE:
            print("[WARNING] Telegram credentials not configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        prefix = "🔴 ERROR: " if is_error else "✅ "
        payload = {
            'chat_id': TG_CHAT_ID,
            'text': f"{prefix}{message}",
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {str(e)}")
        return False


def fetch_market_data_with_retry(symbol: str, timeframe: str, limit: int = 30, max_retries: int = 3) -> list:
    """
    Fetch OHLCV data with retry mechanism

    Args:
        symbol: Trading symbol (e.g., 'BTC/USDT')
        timeframe: Candle timeframe ('1d', '1h', etc.)
        limit: Number of candles to fetch
        max_retries: Maximum number of retry attempts

    Returns:
        OHLCV data list or empty list on failure
    """
    for attempt in range(max_retries):
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if DEBUG_MODE:
                print(
                    f"[DATA] Successfully fetched {len(data)} {timeframe} candles for {symbol}")
            return data
        except ccxt.NetworkError as e:
            print(
                f"[RETRY] Network error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        except ccxt.ExchangeError as e:
            print(f"[ERROR] Exchange error: {str(e)}")
            send_telegram_alert(f"Exchange error: {str(e)}", is_error=True)
            return []
        except Exception as e:
            print(f"[ERROR] Unexpected error: {str(e)}")
            return []

    error_msg = f"Failed to fetch {timeframe} data for {symbol} after {max_retries} retries"
    print(f"[ERROR] {error_msg}")
    send_telegram_alert(error_msg, is_error=True)
    return []


def calculate_bias(spot_symbol: str) -> tuple[float, float]:
    """
    Calculate Daily BIAS% (乖離率)
    Formula: BIAS% = ((P_spot - SMA20) / SMA20) × 100

    Args:
        spot_symbol: Spot trading symbol

    Returns:
        Tuple of (bias_percent, current_price)
    """
    try:
        daily_data = fetch_market_data_with_retry(
            spot_symbol, DAILY_TIMEFRAME, limit=CANDLES_LOOKBACK)

        if len(daily_data) < SMA_PERIOD:
            print(
                f"[WARNING] Insufficient daily candles ({len(daily_data)}) for SMA calculation")
            return 0.0, 0.0

        df = pd.DataFrame(daily_data, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        df['c'] = pd.to_numeric(df['c'], errors='coerce')

        sma20 = df['c'].rolling(window=SMA_PERIOD).mean().iloc[-1]
        current_price = df['c'].iloc[-1]

        bias_pct = ((current_price - sma20) / sma20) * 100

        if DEBUG_MODE:
            print(
                f"[BIAS] Current Price: {current_price:.2f}, SMA20: {sma20:.2f}, BIAS%: {bias_pct:.4f}%")

        return bias_pct, current_price

    except Exception as e:
        print(f"[ERROR] Failed to calculate BIAS: {str(e)}")
        send_telegram_alert(f"BIAS calculation error: {str(e)}", is_error=True)
        return 0.0, 0.0


def calculate_spread(spot_symbol: str, futures_symbol: str) -> tuple[float, float, float]:
    """
    Calculate Spread% (現期價差率)
    Formula: Spread% = ((P_futures - P_spot) / P_spot) × 100

    Args:
        spot_symbol: Spot market symbol
        futures_symbol: Futures contract symbol

    Returns:
        Tuple of (spread_percent, spot_price, futures_price)
    """
    try:
        spot_data = fetch_market_data_with_retry(
            spot_symbol, HOURLY_TIMEFRAME, limit=2)
        futures_data = fetch_market_data_with_retry(
            futures_symbol, HOURLY_TIMEFRAME, limit=2)

        if not spot_data or not futures_data:
            print("[ERROR] Failed to fetch spot or futures data for spread calculation")
            return 0.0, 0.0, 0.0

        p_spot = float(spot_data[-1][4])  # Close price
        p_futures = float(futures_data[-1][4])  # Close price

        spread_pct = ((p_futures - p_spot) / p_spot) * 100

        if DEBUG_MODE:
            print(
                f"[SPREAD] Spot: {p_spot:.2f}, Futures: {p_futures:.2f}, Spread%: {spread_pct:.4f}%")

        return spread_pct, p_spot, p_futures

    except Exception as e:
        print(f"[ERROR] Failed to calculate Spread: {str(e)}")
        send_telegram_alert(
            f"Spread calculation error: {str(e)}", is_error=True)
        return 0.0, 0.0, 0.0


def get_current_position(futures_symbol: str) -> float:
    """
    Get current long position size

    Args:
        futures_symbol: Futures contract symbol

    Returns:
        Current position size (contracts)
    """
    try:
        positions = exchange.fetch_positions([futures_symbol])
        current_size = 0.0

        for position in positions:
            if position.get('side') == 'long' and position.get('contracts'):
                current_size += float(position['contracts'])

        if DEBUG_MODE:
            print(f"[POSITION] Current size: {current_size} contracts")

        return current_size

    except Exception as e:
        print(f"[ERROR] Failed to fetch position: {str(e)}")
        send_telegram_alert(f"Position fetch error: {str(e)}", is_error=True)
        return 0.0


def execute_market_buy_order(futures_symbol: str, amount: float) -> dict:
    """
    Execute market buy order (建立/加碼做多)

    Args:
        futures_symbol: Futures contract symbol
        amount: Amount to buy

    Returns:
        Order response dictionary
    """
    try:
        if amount <= 0:
            print("[ERROR] Invalid buy amount")
            return {}

        order = exchange.create_market_buy_order(futures_symbol, amount)
        msg = f"✅ BUY ORDER EXECUTED\n" \
              f"Symbol: {futures_symbol}\n" \
              f"Amount: {amount} contracts\n" \
              f"Order ID: {order.get('id', 'N/A')}"

        print(f"[ORDER BUY] {msg}")
        send_telegram_alert(msg)

        return order

    except Exception as e:
        error_msg = f"Buy order failed: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_telegram_alert(error_msg, is_error=True)
        return {}


def execute_market_sell_order(futures_symbol: str, amount: float) -> dict:
    """
    Execute market sell order (平掉所有多單)

    Args:
        futures_symbol: Futures contract symbol
        amount: Amount to sell

    Returns:
        Order response dictionary
    """
    try:
        if amount <= 0:
            print("[ERROR] Invalid sell amount")
            return {}

        order = exchange.create_market_sell_order(
            futures_symbol,
            amount,
            params={'reduceOnly': True}
        )
        msg = f"📉 SELL ORDER EXECUTED\n" \
              f"Symbol: {futures_symbol}\n" \
              f"Amount: {amount} contracts\n" \
              f"Order ID: {order.get('id', 'N/A')}"

        print(f"[ORDER SELL] {msg}")
        send_telegram_alert(msg)

        return order

    except Exception as e:
        error_msg = f"Sell order failed: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_telegram_alert(error_msg, is_error=True)
        return {}


def validate_api_credentials() -> bool:
    """Validate that API credentials are configured"""
    if not GATE_API_KEY or not GATE_API_SECRET:
        print("[ERROR] Gate API credentials not configured")
        print("[ERROR] Please set GATE_API_KEY and GATE_API_SECRET in .env file")
        return False
    return True


def run_trading_cycle() -> None:
    """
    Main trading cycle - Execute H-Model strategy

    Signal Rules:
    - Bottom Entry: BIAS% < 0 AND Spread% < 0 → Market Buy
    - Exit Entry: BIAS% > 0 → Market Sell (Close all longs)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[CYCLE START] {timestamp}")
    print(f"{'='*60}")

    if not validate_api_credentials():
        return

    try:
        # Define symbols
        spot_symbol = TRADING_SYMBOL
        futures_symbol = f"{spot_symbol.split('/')[0]}/USDT:USDT"

        # Step 1: Calculate BIAS% (Daily)
        bias_pct, spot_price_daily = calculate_bias(spot_symbol)

        # Step 2: Calculate Spread% (Hourly)
        spread_pct, spot_price_hourly, futures_price = calculate_spread(
            spot_symbol, futures_symbol)

        # Step 3: Get current position
        current_position = get_current_position(futures_symbol)

        # Log metrics
        print(f"\n[METRICS]")
        print(
            f"  BIAS%:           {bias_pct:>8.4f}% (threshold: {BIAS_THRESHOLD}%)")
        print(
            f"  Spread%:         {spread_pct:>8.4f}% (threshold: {SPREAD_THRESHOLD}%)")
        print(f"  Current Position: {current_position:>7.1f} contracts")
        print(f"  Max Position:     {MAX_POSITION_SIZE:>7.1f} contracts")

        # Step 4: Signal Generation & Execution
        bottom_entry_cond = (bias_pct < BIAS_THRESHOLD) and (
            spread_pct < SPREAD_THRESHOLD)
        exit_cond = (bias_pct > 0)

        if bottom_entry_cond and current_position < MAX_POSITION_SIZE:
            # Entry signal
            buy_amount = min(
                CONTRACT_SIZE, MAX_POSITION_SIZE - current_position)
            print(f"\n[SIGNAL] Bottom Entry triggered!")
            print(
                f"  Condition: BIAS% ({bias_pct:.4f}%) < {BIAS_THRESHOLD}% AND Spread% ({spread_pct:.4f}%) < {SPREAD_THRESHOLD}%")
            execute_market_buy_order(futures_symbol, buy_amount)

        elif exit_cond and current_position > 0:
            # Exit signal
            print(f"\n[SIGNAL] Exit Entry triggered!")
            print(f"  Condition: BIAS% ({bias_pct:.4f}%) > 0%")
            execute_market_sell_order(futures_symbol, current_position)

        else:
            print(f"\n[SIGNAL] No trading signal (conditions not met)")

    except Exception as e:
        error_msg = f"Trading cycle error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_telegram_alert(error_msg, is_error=True)

    finally:
        print(f"[CYCLE END] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    try:
        run_trading_cycle()
    except KeyboardInterrupt:
        print("\n[INFO] Trading cycle interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL ERROR] {str(e)}")
        sys.exit(1)
