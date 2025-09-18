import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from collections import deque
import pytz
import aiohttp
import re

logger = logging.getLogger(__name__)


class AfterHoursDataProvider:
    def __init__(self):
        self.session = None
        self.market_timezone = pytz.timezone('US/Eastern')

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def is_after_hours(self) -> bool:
        """Check if it's currently after-hours trading"""
        now_et = datetime.now(self.market_timezone)

        if now_et.weekday() >= 5:  # Weekend
            return True

        hour = now_et.hour
        minute = now_et.minute
        current_time = hour + (minute / 60)

        # Market hours: 9:30 AM - 4:00 PM ET
        return not (9.5 <= current_time <= 16)

    async def get_after_hours_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get after-hours price by scraping Yahoo Finance"""
        try:
            session = await self.get_session()

            url = f"https://finance.yahoo.com/quote/{symbol}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()

                    # Look for after-hours price
                    regular_pattern = r'"regularMarketPrice":\{"raw":([\d.]+)'
                    after_hours_pattern = r'"postMarketPrice":\{"raw":([\d.]+)'
                    change_pattern = r'"postMarketChange":\{"raw":(-?[\d.]+)'

                    regular_match = re.search(regular_pattern, html)
                    after_hours_match = re.search(after_hours_pattern, html)
                    change_match = re.search(change_pattern, html)

                    if after_hours_match and regular_match:
                        after_hours_price = float(after_hours_match.group(1))
                        regular_price = float(regular_match.group(1))
                        change = float(change_match.group(1)) if change_match else (after_hours_price - regular_price)
                        change_percent = (change / regular_price * 100) if regular_price > 0 else 0

                        return {
                            'symbol': symbol,
                            'price': after_hours_price,
                            'regular_price': regular_price,
                            'change': change,
                            'change_percent': change_percent,
                            'timestamp': int(datetime.now().timestamp()),
                            'source': 'yahoo_after_hours',
                            'after_hours': True
                        }

        except Exception as e:
            logger.warning(f"After-hours data error for {symbol}: {e}")

        return None

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None


class PortfolioMonitor:
    def __init__(self):
        self.price_history = {}
        self.volume_history = {}
        self.market_timezone = pytz.timezone('US/Eastern')
        self.after_hours_provider = AfterHoursDataProvider()

        # TIGHTER exit thresholds - protect gains better
        self.exit_thresholds = {
            'quick_drop': 0.08,  # 8% drop from recent high (not 50%!)
            'volume_drop': 0.6,  # 40% volume decline threshold
            'momentum_loss': 0.05,  # 5% momentum reversal
            'trailing_stop': 0.15,  # 15% trailing stop from peak
            'profit_protection_1': {'gain': 100, 'drop': 5},  # 100%+ gains, 5% drop
            'profit_protection_2': {'gain': 50, 'drop': 7},  # 50%+ gains, 7% drop
            'profit_protection_3': {'gain': 25, 'drop': 10}  # 25%+ gains, 10% drop
        }

    def is_market_hours(self) -> bool:
        """Check if market is currently open"""
        try:
            now_et = datetime.now(self.market_timezone)

            # Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
            if now_et.weekday() >= 5:  # Weekend
                return False

            hour = now_et.hour
            minute = now_et.minute
            current_time = hour + (minute / 60)

            logger.info(
                f"Market hours check: ET time {hour:02d}:{minute:02d} ({current_time:.1f}), Market hours: 9.5-16.0")

            return 9.5 <= current_time <= 16  # 9:30 AM - 4:00 PM

        except Exception as e:
            logger.error(f"Error checking market hours: {e}")
            return False

    async def get_exit_signals(self) -> List[Dict[str, Any]]:
        """Get exit signals for all portfolio positions"""
        try:
            portfolio_stocks = []  # Will be populated by Firebase client

            exit_signals = []

            for stock in portfolio_stocks:
                signal = await self.analyze_stock_exit(
                    stock['symbol'],
                    stock.get('avg_price'),
                    stock.get('quantity', 0)
                )

                if signal:
                    exit_signals.append(signal)

            # Sort by urgency
            exit_signals.sort(key=lambda x: x.get('urgency', 0), reverse=True)

            return exit_signals

        except Exception as e:
            logger.error(f"Error getting exit signals: {e}")
            return []

    async def analyze_stock_exit(self, symbol: str, avg_price: Optional[float] = None,
                                 quantity: float = 0) -> Optional[Dict[str, Any]]:
        """Analyze stock for exit signals - handles both market hours and after-hours"""

        # Check if it's after-hours
        if not self.is_market_hours():
            logger.info(f"⏰ After-hours: Using specialized analysis for {symbol}")
            return await self._analyze_after_hours_exit(symbol, avg_price, quantity)

        # Regular market hours analysis
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="1m")

            if hist.empty or len(hist) < 10:
                logger.warning(f"Insufficient data for {symbol}")
                return None

            current_price = float(hist['Close'].iloc[-1])
            recent_high = hist['High'].tail(60).max()
            recent_volume = hist['Volume'].tail(30)

            # Calculate metrics
            drop_from_high = (recent_high - current_price) / recent_high * 100 if recent_high > 0 else 0
            current_gain = ((current_price - avg_price) / avg_price * 100) if avg_price else 0

            # Store price history for analysis
            self._update_history(symbol, hist)

            # Analyze exit signals
            exit_signals = []
            max_urgency = 0

            # 1. QUICK DROP CHECK (8% not 50%!)
            if drop_from_high >= (self.exit_thresholds['quick_drop'] * 100):
                # Double-check with recent trend
                last_5_candles = hist['Close'].tail(5)
                if len(last_5_candles) >= 3:
                    recent_trend = (last_5_candles.iloc[-1] - last_5_candles.iloc[-3]) / last_5_candles.iloc[-3]

                    if recent_trend < -0.05:  # Confirmed 5% drop in last 3 candles
                        urgency = 95
                        exit_signals.append({
                            'type': 'quick_drop',
                            'message': f'🚨 QUICK DROP: Down {drop_from_high:.1f}% from recent high',
                            'urgency': urgency,
                            'action': 'SELL IMMEDIATELY'
                        })
                        max_urgency = max(max_urgency, urgency)

            # 2. VOLUME EXHAUSTION
            volume_signal = self._check_volume_exhaustion(hist)
            if volume_signal:
                exit_signals.append(volume_signal)
                max_urgency = max(max_urgency, volume_signal['urgency'])

            # 3. MOMENTUM REVERSAL
            momentum_signal = self._check_momentum_reversal(hist)
            if momentum_signal:
                exit_signals.append(momentum_signal)
                max_urgency = max(max_urgency, momentum_signal['urgency'])

            # 4. PROFIT PROTECTION
            if avg_price:
                profit_signal = self._check_profit_protection(current_gain, drop_from_high)
                if profit_signal:
                    exit_signals.append(profit_signal)
                    max_urgency = max(max_urgency, profit_signal['urgency'])

            # 5. TRAILING STOP
            trailing_signal = self._check_trailing_stop(recent_high, current_price)
            if trailing_signal:
                exit_signals.append(trailing_signal)
                max_urgency = max(max_urgency, trailing_signal['urgency'])

            # Return signal if any triggered
            if exit_signals:
                position_value = current_price * quantity if quantity > 0 else 0

                return {
                    'symbol': symbol,
                    'current_price': current_price,
                    'avg_price': avg_price,
                    'current_gain': current_gain,
                    'recent_high': recent_high,
                    'drop_from_high': drop_from_high,
                    'quantity': quantity,
                    'position_value': position_value,
                    'exit_signals': exit_signals,
                    'urgency': max_urgency,
                    'recommendation': self._get_exit_recommendation(max_urgency),
                    'time_to_act': self._get_time_to_act(max_urgency),
                    'market_hours': True,
                    'timestamp': datetime.now().isoformat()
                }

            return None

        except Exception as e:
            logger.error(f"Error analyzing exit for {symbol}: {e}")
            return None

    async def _analyze_after_hours_exit(self, symbol: str, avg_price: Optional[float] = None,
                                        quantity: float = 0) -> Optional[Dict[str, Any]]:
        """Specialized exit analysis for after-hours trading"""
        try:
            # Get after-hours data
            current_data = await self.after_hours_provider.get_after_hours_price(symbol)

            if not current_data:
                return {
                    'symbol': symbol,
                    'status': 'AFTER_HOURS_NO_DATA',
                    'message': '🌙 After-hours - no extended trading data available',
                    'urgency': 0,
                    'after_hours': True,
                    'note': 'Exit monitoring limited outside market hours'
                }

            current_price = current_data['price']
            after_hours_change = current_data.get('change_percent', 0)
            current_gain = ((current_price - avg_price) / avg_price * 100) if avg_price else 0

            # More conservative thresholds for after-hours
            signals = []
            urgency = 0

            if after_hours_change <= -15:  # 15% drop after-hours
                urgency = 80
                signals.append({
                    'type': 'after_hours_drop',
                    'message': f'📉 AFTER-HOURS DROP: Down {abs(after_hours_change):.1f}% after market close',
                    'action': 'MONITOR CLOSELY - Consider exit at market open'
                })

            elif after_hours_change >= 100:  # 100% gain - possible squeeze
                urgency = 30  # Lower urgency - might be opportunity
                signals.append({
                    'type': 'after_hours_surge',
                    'message': f'🚀 AFTER-HOURS SURGE: Up {after_hours_change:.1f}% - POSSIBLE SQUEEZE!',
                    'action': 'MONITOR - Do NOT sell during squeeze'
                })

            elif after_hours_change >= 50:  # 50% gain
                urgency = 20
                signals.append({
                    'type': 'after_hours_gain',
                    'message': f'📈 AFTER-HOURS GAIN: Up {after_hours_change:.1f}%',
                    'action': 'POSITIVE - Monitor for continuation'
                })

            if signals:
                position_value = current_price * quantity if quantity > 0 else 0

                return {
                    'symbol': symbol,
                    'current_price': current_price,
                    'regular_market_price': current_data.get('regular_price'),
                    'after_hours_change': after_hours_change,
                    'current_gain': current_gain,
                    'avg_price': avg_price,
                    'quantity': quantity,
                    'position_value': position_value,
                    'exit_signals': signals,
                    'urgency': urgency,
                    'after_hours': True,
                    'recommendation': {
                        'action': 'MONITOR' if urgency < 50 else 'PREPARE',
                        'message': 'After-hours data - wait for market open for accurate signals'
                    },
                    'timestamp': datetime.now().isoformat(),
                    'data_source': current_data.get('source', 'yahoo_after_hours')
                }

            return None

        except Exception as e:
            logger.error(f"After-hours exit analysis error for {symbol}: {e}")
            return None

    def _check_volume_exhaustion(self, hist_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check for volume exhaustion with TIGHT threshold"""
        try:
            volumes = hist_data['Volume'].tail(30)

            if len(volumes) < 10:
                return None

            peak_volume = volumes.max()
            current_volume = volumes.iloc[-1]

            volume_decline = (peak_volume - current_volume) / peak_volume if peak_volume > 0 else 0

            if volume_decline >= self.exit_thresholds['volume_drop']:
                return {
                    'type': 'volume_exhaustion',
                    'message': f'📉 VOLUME EXHAUSTION: Volume down {volume_decline * 100:.0f}% from peak',
                    'urgency': 80,
                    'action': 'SELL SOON',
                    'volume_decline': volume_decline
                }

        except Exception as e:
            logger.error(f"Volume exhaustion check error: {e}")

        return None

    def _check_momentum_reversal(self, hist_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check for momentum reversal - early warning"""
        try:
            closes = hist_data['Close'].tail(20)

            if len(closes) < 15:
                return None

            recent_trend = closes.tail(5).mean()
            earlier_trend = closes.head(10).mean()

            momentum_change = (recent_trend - earlier_trend) / earlier_trend if earlier_trend > 0 else 0

            if momentum_change <= -self.exit_thresholds['momentum_loss']:
                return {
                    'type': 'momentum_reversal',
                    'message': f'⬇️ MOMENTUM REVERSAL: {momentum_change * 100:.1f}% trend change',
                    'urgency': 70,
                    'action': 'PREPARE TO SELL'
                }

        except Exception as e:
            logger.error(f"Momentum reversal check error: {e}")

        return None

    def _check_profit_protection(self, current_gain: float, drop_from_high: float) -> Optional[Dict[str, Any]]:
        """Protect profits with tiered approach"""
        try:
            for threshold in ['profit_protection_1', 'profit_protection_2', 'profit_protection_3']:
                config = self.exit_thresholds[threshold]

                if current_gain >= config['gain'] and drop_from_high >= config['drop']:
                    urgency = 85 if threshold == 'profit_protection_1' else (
                        75 if threshold == 'profit_protection_2' else 65)

                    return {
                        'type': 'profit_protection',
                        'message': f'💰 PROTECT PROFITS: Up {current_gain:.1f}% but dropping {drop_from_high:.1f}%',
                        'urgency': urgency,
                        'action': 'SELL TO PROTECT GAINS',
                        'gain_level': config['gain'],
                        'drop_trigger': config['drop']
                    }

        except Exception as e:
            logger.error(f"Profit protection check error: {e}")

        return None

    def _check_trailing_stop(self, recent_high: float, current_price: float) -> Optional[Dict[str, Any]]:
        """15% trailing stop from peak"""
        try:
            if recent_high <= 0:
                return None

            trailing_drop = (recent_high - current_price) / recent_high

            if trailing_drop >= self.exit_thresholds['trailing_stop']:
                return {
                    'type': 'trailing_stop',
                    'message': f'🛑 TRAILING STOP: Down {trailing_drop * 100:.1f}% from peak ${recent_high:.2f}',
                    'urgency': 90,
                    'action': 'SELL NOW - STOP LOSS TRIGGERED',
                    'stop_level': recent_high * (1 - self.exit_thresholds['trailing_stop'])
                }

        except Exception as e:
            logger.error(f"Trailing stop check error: {e}")

        return None

    def _get_exit_recommendation(self, urgency: int) -> Dict[str, str]:
        """Get recommended action based on urgency level"""
        if urgency >= 90:
            return {
                'action': 'SELL IMMEDIATELY',
                'urgency_level': 'CRITICAL',
                'message': '🚨 IMMEDIATE EXIT REQUIRED - Multiple critical signals',
                'color': 'red'
            }
        elif urgency >= 80:
            return {
                'action': 'SELL NOW',
                'urgency_level': 'HIGH',
                'message': '🔴 HIGH PRIORITY EXIT - Strong sell signals detected',
                'color': 'red'
            }
        elif urgency >= 70:
            return {
                'action': 'PREPARE TO SELL',
                'urgency_level': 'MEDIUM',
                'message': '🟡 EXIT WARNING - Monitor closely, prepare to sell',
                'color': 'orange'
            }
        elif urgency >= 60:
            return {
                'action': 'WATCH CLOSELY',
                'urgency_level': 'LOW',
                'message': '🟢 EARLY WARNING - Some exit signals present',
                'color': 'yellow'
            }
        else:
            return {
                'action': 'HOLD',
                'urgency_level': 'NONE',
                'message': '✅ NO IMMEDIATE EXIT SIGNALS',
                'color': 'green'
            }

    def _get_time_to_act(self, urgency: int) -> str:
        """Get recommended timeframe for action"""
        if urgency >= 90:
            return "IMMEDIATELY - Within 1-2 minutes"
        elif urgency >= 80:
            return "VERY SOON - Within 5-10 minutes"
        elif urgency >= 70:
            return "SOON - Within 15-30 minutes"
        elif urgency >= 60:
            return "MONITOR - Next 1-2 hours"
        else:
            return "NO RUSH - Continue monitoring"

    def _update_history(self, symbol: str, hist_data: pd.DataFrame):
        """Update price/volume history for trend analysis"""
        try:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=100)
                self.volume_history[symbol] = deque(maxlen=100)

            recent_closes = hist_data['Close'].tail(10).tolist()
            recent_volumes = hist_data['Volume'].tail(10).tolist()

            self.price_history[symbol].extend(recent_closes)
            self.volume_history[symbol].extend(recent_volumes)

        except Exception as e:
            logger.error(f"Error updating history for {symbol}: {e}")

    async def close_sessions(self):
        """Close all async sessions"""
        await self.after_hours_provider.close_session()