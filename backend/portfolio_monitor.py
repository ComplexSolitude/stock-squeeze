import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from collections import deque

logger = logging.getLogger(__name__)


class PortfolioMonitor:
    def __init__(self):
        self.price_history = {}
        self.volume_history = {}

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

    async def get_exit_signals(self) -> List[Dict[str, Any]]:
        """Get exit signals for all portfolio positions"""
        try:
            # This would normally get portfolio from Firebase
            # For now, we'll use a placeholder that can be overridden
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
        """Analyze individual stock for exit signals with TIGHT stops"""
        try:
            # Get real-time data with 1-minute intervals
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="1m")

            if hist.empty or len(hist) < 10:
                return None

            current_price = float(hist['Close'].iloc[-1])

            # Find recent high (last 60 minutes)
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
                urgency = 95
                exit_signals.append({
                    'type': 'quick_drop',
                    'message': f'🚨 QUICK DROP: Down {drop_from_high:.1f}% from recent high',
                    'urgency': urgency,
                    'action': 'SELL IMMEDIATELY'
                })
                max_urgency = max(max_urgency, urgency)

            # 2. VOLUME EXHAUSTION (40% drop threshold, not 70%)
            volume_signal = self._check_volume_exhaustion(hist)
            if volume_signal:
                exit_signals.append(volume_signal)
                max_urgency = max(max_urgency, volume_signal['urgency'])

            # 3. MOMENTUM REVERSAL (5% threshold)
            momentum_signal = self._check_momentum_reversal(hist)
            if momentum_signal:
                exit_signals.append(momentum_signal)
                max_urgency = max(max_urgency, momentum_signal['urgency'])

            # 4. PROFIT PROTECTION (tiered based on gains)
            if avg_price:
                profit_signal = self._check_profit_protection(current_gain, drop_from_high)
                if profit_signal:
                    exit_signals.append(profit_signal)
                    max_urgency = max(max_urgency, profit_signal['urgency'])

            # 5. TRAILING STOP (15% from peak)
            trailing_signal = self._check_trailing_stop(recent_high, current_price)
            if trailing_signal:
                exit_signals.append(trailing_signal)
                max_urgency = max(max_urgency, trailing_signal['urgency'])

            # 6. TECHNICAL BREAKDOWN
            technical_signal = self._check_technical_breakdown(hist, current_price)
            if technical_signal:
                exit_signals.append(technical_signal)
                max_urgency = max(max_urgency, technical_signal['urgency'])

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
                    'timestamp': datetime.now().isoformat()
                }

            return None

        except Exception as e:
            logger.error(f"Error analyzing exit for {symbol}: {e}")
            return None

    def _check_volume_exhaustion(self, hist_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check for volume exhaustion with TIGHT threshold"""
        try:
            volumes = hist_data['Volume'].tail(30)  # Last 30 minutes

            if len(volumes) < 10:
                return None

            peak_volume = volumes.max()
            current_volume = volumes.iloc[-1]
            recent_avg = volumes.tail(5).mean()

            # TIGHTER threshold - 40% volume drop (not 70%)
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
            closes = hist_data['Close'].tail(20)  # Last 20 minutes

            if len(closes) < 15:
                return None

            # Compare recent trend vs earlier trend
            recent_trend = closes.tail(5).mean()
            earlier_trend = closes.head(10).mean()

            momentum_change = (recent_trend - earlier_trend) / earlier_trend if earlier_trend > 0 else 0

            # 5% momentum reversal (tight!)
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
            # Tiered profit protection
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

    def _check_technical_breakdown(self, hist_data: pd.DataFrame, current_price: float) -> Optional[Dict[str, Any]]:
        """Check for technical breakdown patterns"""
        try:
            closes = hist_data['Close']
            volumes = hist_data['Volume']

            if len(closes) < 20:
                return None

            # Moving averages
            ma_5 = closes.rolling(window=5).mean()
            ma_10 = closes.rolling(window=10).mean()

            if len(ma_5) < 5 or len(ma_10) < 10:
                return None

            current_ma5 = ma_5.iloc[-1]
            current_ma10 = ma_10.iloc[-1]
            prev_ma5 = ma_5.iloc[-2] if len(ma_5) > 1 else current_ma5

            # Check for breakdown patterns
            breakdown_signals = []

            # 1. Price below MA5 and MA5 trending down
            if current_price < current_ma5 and current_ma5 < prev_ma5:
                breakdown_signals.append("Price below declining MA5")

            # 2. MA5 crosses below MA10 (bearish crossover)
            if current_ma5 < current_ma10 and ma_5.iloc[-2] >= ma_10.iloc[-2]:
                breakdown_signals.append("Bearish MA crossover")

            # 3. Volume spike on decline
            if len(volumes) >= 5:
                current_vol = volumes.iloc[-1]
                avg_vol = volumes.tail(10).mean()
                recent_change = (current_price - closes.iloc[-2]) / closes.iloc[-2] if len(closes) > 1 else 0

                if current_vol > avg_vol * 2 and recent_change < -0.02:  # 2x volume + 2% drop
                    breakdown_signals.append("High volume selling")

            if breakdown_signals:
                return {
                    'type': 'technical_breakdown',
                    'message': f'📊 TECHNICAL BREAKDOWN: {", ".join(breakdown_signals)}',
                    'urgency': 75,
                    'action': 'TECHNICAL SELL SIGNAL',
                    'signals': breakdown_signals
                }

        except Exception as e:
            logger.error(f"Technical breakdown check error: {e}")

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

            # Add recent data points
            recent_closes = hist_data['Close'].tail(10).tolist()
            recent_volumes = hist_data['Volume'].tail(10).tolist()

            self.price_history[symbol].extend(recent_closes)
            self.volume_history[symbol].extend(recent_volumes)

        except Exception as e:
            logger.error(f"Error updating history for {symbol}: {e}")

    def get_portfolio_risk_summary(self, exit_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate portfolio-wide risk summary"""
        try:
            if not exit_signals:
                return {
                    'overall_risk': 'LOW',
                    'critical_positions': 0,
                    'high_risk_positions': 0,
                    'total_positions_at_risk': 0,
                    'message': '✅ Portfolio looking healthy'
                }

            critical_count = sum(1 for s in exit_signals if s.get('urgency', 0) >= 90)
            high_risk_count = sum(1 for s in exit_signals if s.get('urgency', 0) >= 80)
            total_at_risk = len(exit_signals)

            if critical_count > 0:
                overall_risk = 'CRITICAL'
                message = f'🚨 {critical_count} positions need immediate exit'
            elif high_risk_count > 0:
                overall_risk = 'HIGH'
                message = f'🔴 {high_risk_count} positions should be sold soon'
            elif total_at_risk >= 3:
                overall_risk = 'MEDIUM'
                message = f'🟡 Multiple positions showing exit signals'
            else:
                overall_risk = 'LOW'
                message = f'🟢 Few positions with minor exit signals'

            return {
                'overall_risk': overall_risk,
                'critical_positions': critical_count,
                'high_risk_positions': high_risk_count,
                'total_positions_at_risk': total_at_risk,
                'message': message,
                'top_risks': sorted(exit_signals, key=lambda x: x.get('urgency', 0), reverse=True)[:3]
            }

        except Exception as e:
            logger.error(f"Error generating risk summary: {e}")
            return {
                'overall_risk': 'UNKNOWN',
                'message': 'Error calculating portfolio risk'
            }

    async def monitor_position_realtime(self, symbol: str, entry_price: float,
                                        stop_loss_percent: float = 15) -> Dict[str, Any]:
        """Real-time monitoring of a specific position"""
        try:
            current_data = await self.analyze_stock_exit(symbol, entry_price)

            if not current_data:
                return {
                    'symbol': symbol,
                    'status': 'MONITORING',
                    'message': 'Position being monitored - no exit signals'
                }

            # Add real-time context
            current_data['entry_price'] = entry_price
            current_data['stop_loss_level'] = entry_price * (1 - stop_loss_percent / 100)
            current_data['profit_target_1'] = entry_price * 1.25  # 25% profit
            current_data['profit_target_2'] = entry_price * 1.50  # 50% profit
            current_data['profit_target_3'] = entry_price * 2.00  # 100% profit

            return current_data

        except Exception as e:
            logger.error(f"Error monitoring position {symbol}: {e}")
            return {'error': str(e)}