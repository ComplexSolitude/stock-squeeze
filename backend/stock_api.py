import yfinance as yf
import requests
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import time

logger = logging.getLogger(__name__)


class StockDataFetcher:
    def __init__(self):
        self.session = None
        self.last_request_time = {}
        self.request_delay = 0.1  # 100ms between requests to avoid rate limits

        # Alternative APIs for redundancy
        self.apis = {
            'yahoo_finance': True,
            'alpha_vantage': False,  # Set to True if you have API key
            'finnhub': False  # Set to True if you have API key
        }

        # API Keys (set these in environment variables)
        self.alpha_vantage_key = None  # os.getenv('ALPHA_VANTAGE_KEY')
        self.finnhub_key = None  # os.getenv('FINNHUB_KEY')

    async def get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def rate_limit_wait(self, api_name: str):
        """Implement rate limiting"""
        if api_name in self.last_request_time:
            time_since_last = time.time() - self.last_request_time[api_name]
            if time_since_last < self.request_delay:
                await asyncio.sleep(self.request_delay - time_since_last)

        self.last_request_time[api_name] = time.time()

    async def get_stock_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive stock data for a symbol"""
        try:
            # Primary: Yahoo Finance (free, reliable)
            data = await self._get_yahoo_finance_data(symbol)

            if data:
                # Enhance with additional analysis
                data['squeeze_score'] = await self._calculate_squeeze_score(symbol, data)
                data['volume_analysis'] = self._analyze_volume(data)
                data['technical_signals'] = await self._get_technical_signals(symbol)

                return data

            # Fallback to alternative APIs if available
            if self.alpha_vantage_key:
                data = await self._get_alpha_vantage_data(symbol)
                if data:
                    return data

            return None

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    async def _get_yahoo_finance_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get data from Yahoo Finance using yfinance"""
        try:
            await self.rate_limit_wait('yahoo_finance')

            # Use yfinance in async context
            ticker = yf.Ticker(symbol)

            # Get basic info
            info = ticker.info
            hist = ticker.history(period="5d", interval="1m")

            if hist.empty:
                return None

            current_price = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
            volume = int(hist['Volume'].iloc[-1])

            # Calculate change
            change = current_price - prev_close
            change_percent = (change / prev_close * 100) if prev_close > 0 else 0

            # Get additional metrics
            avg_volume = hist['Volume'].tail(20).mean() if len(hist) >= 20 else volume
            day_high = float(hist['High'].max())
            day_low = float(hist['Low'].min())

            return {
                'symbol': symbol,
                'price': current_price,
                'change': change,
                'change_percent': change_percent,
                'volume': volume,
                'avg_volume': int(avg_volume),
                'day_high': day_high,
                'day_low': day_low,
                'market_cap': info.get('marketCap', 0),
                'float_shares': info.get('floatShares', info.get('sharesOutstanding', 0)),
                'short_ratio': info.get('shortRatio', 0),
                'short_percent': info.get('shortPercentOfFloat', 0),
                'price_history': hist['Close'].tail(50).tolist(),
                'volume_history': hist['Volume'].tail(50).tolist(),
                'timestamp': datetime.now().isoformat(),
                'source': 'yahoo_finance'
            }

        except Exception as e:
            logger.error(f"Yahoo Finance error for {symbol}: {e}")
            return None

    async def _get_alpha_vantage_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get data from Alpha Vantage API (backup)"""
        if not self.alpha_vantage_key:
            return None

        try:
            await self.rate_limit_wait('alpha_vantage')
            session = await self.get_session()

            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.alpha_vantage_key
            }

            async with session.get(url, params=params) as response:
                data = await response.json()

                if 'Global Quote' in data:
                    quote = data['Global Quote']

                    return {
                        'symbol': symbol,
                        'price': float(quote.get('05. price', 0)),
                        'change': float(quote.get('09. change', 0)),
                        'change_percent': float(quote.get('10. change percent', '0%').replace('%', '')),
                        'volume': int(quote.get('06. volume', 0)),
                        'timestamp': datetime.now().isoformat(),
                        'source': 'alpha_vantage'
                    }

        except Exception as e:
            logger.error(f"Alpha Vantage error for {symbol}: {e}")
            return None

    async def search_stocks(self, query: str) -> List[Dict[str, str]]:
        """Search for stocks by symbol or company name"""
        try:
            # Use Yahoo Finance search
            await self.rate_limit_wait('yahoo_search')

            # Multiple search approaches
            results = []

            # 1. Direct symbol lookup
            if len(query) <= 5 and query.isalpha():
                try:
                    ticker = yf.Ticker(query.upper())
                    info = ticker.info

                    if info.get('symbol'):
                        results.append({
                            'symbol': info.get('symbol', query.upper()),
                            'name': info.get('longName', info.get('shortName', 'N/A')),
                            'type': info.get('quoteType', 'EQUITY'),
                            'exchange': info.get('exchange', 'NASDAQ')
                        })
                except:
                    pass

            # 2. Search similar symbols (common variations)
            if len(results) == 0:
                similar_symbols = self._generate_similar_symbols(query)

                for symbol in similar_symbols[:5]:  # Limit to 5 to avoid rate limits
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info

                        if info.get('symbol'):
                            results.append({
                                'symbol': info.get('symbol', symbol),
                                'name': info.get('longName', info.get('shortName', 'N/A')),
                                'type': info.get('quoteType', 'EQUITY'),
                                'exchange': info.get('exchange', 'NASDAQ')
                            })
                    except:
                        continue

            return results[:10]  # Limit results

        except Exception as e:
            logger.error(f"Error searching stocks for '{query}': {e}")
            return []

    def _generate_similar_symbols(self, query: str) -> List[str]:
        """Generate similar stock symbols for search"""
        variations = []
        query = query.upper()

        # Direct match
        variations.append(query)

        # Add common suffixes/prefixes
        variations.extend([
            f"{query}A", f"{query}B", f"{query}C",  # Class A, B, C shares
            f"{query}.A", f"{query}.B",
            f"{query}W",  # Warrants
            f"{query}Y",  # ADR variations
        ])

        # Remove duplicates and filter valid lengths
        variations = list(set([v for v in variations if 1 <= len(v) <= 5]))

        return variations

    async def _calculate_squeeze_score(self, symbol: str, data: Dict[str, Any]) -> int:
        """Calculate basic squeeze score"""
        try:
            score = 0

            # Price movement (0-25 points)
            change_pct = abs(data.get('change_percent', 0))
            if change_pct >= 50:
                score += min(25, change_pct / 2)

            # Volume spike (0-25 points)
            volume = data.get('volume', 0)
            avg_volume = data.get('avg_volume', 0)

            if avg_volume > 0:
                volume_ratio = volume / avg_volume
                if volume_ratio >= 2:
                    score += min(25, volume_ratio * 5)

            # Float size (0-20 points)
            float_shares = data.get('float_shares', 0)
            if float_shares > 0:
                if float_shares < 10_000_000:  # <10M
                    score += 20
                elif float_shares < 50_000_000:  # <50M
                    score += 15
                elif float_shares < 100_000_000:  # <100M
                    score += 10

            # Short interest (0-15 points)
            short_ratio = data.get('short_ratio', 0)
            if short_ratio >= 5:
                score += min(15, short_ratio)

            # Recent momentum (0-15 points)
            price_history = data.get('price_history', [])
            if len(price_history) >= 10:
                recent_trend = sum(price_history[-5:]) / 5
                earlier_trend = sum(price_history[-10:-5]) / 5

                if recent_trend > earlier_trend * 1.1:  # 10% uptrend
                    score += 15

            return min(int(score), 100)

        except Exception as e:
            logger.error(f"Error calculating squeeze score for {symbol}: {e}")
            return 0

    def _analyze_volume(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze volume patterns"""
        try:
            volume = data.get('volume', 0)
            avg_volume = data.get('avg_volume', 0)

            if avg_volume > 0:
                ratio = volume / avg_volume

                if ratio >= 5:
                    trend = "Extremely High"
                elif ratio >= 3:
                    trend = "Very High"
                elif ratio >= 2:
                    trend = "High"
                elif ratio >= 1.5:
                    trend = "Above Average"
                else:
                    trend = "Normal"
            else:
                ratio = 1.0
                trend = "Unknown"

            return {
                'current_volume': volume,
                'avg_volume': avg_volume,
                'volume_ratio': ratio,
                'volume_trend': trend
            }

        except Exception as e:
            logger.error(f"Error analyzing volume: {e}")
            return {
                'current_volume': 0,
                'avg_volume': 0,
                'volume_ratio': 1.0,
                'volume_trend': 'Unknown'
            }

    async def _get_technical_signals(self, symbol: str) -> List[str]:
        """Get basic technical analysis signals"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="30d", interval="1d")

            if len(hist) < 20:
                return []

            signals = []
            closes = hist['Close']
            volumes = hist['Volume']

            # Moving averages
            ma_5 = closes.rolling(window=5).mean()
            ma_20 = closes.rolling(window=20).mean()

            current_price = closes.iloc[-1]
            current_ma5 = ma_5.iloc[-1]
            current_ma20 = ma_20.iloc[-1]

            # MA signals
            if current_price > current_ma5 > current_ma20:
                signals.append("Bullish MA Alignment")
            elif current_ma5 > current_ma20 and closes.iloc[-2] <= ma_5.iloc[-2]:
                signals.append("MA Crossover")

            # Volume breakout
            avg_volume = volumes.rolling(window=20).mean().iloc[-1]
            if volumes.iloc[-1] > avg_volume * 2:
                signals.append("Volume Breakout")

            # Price breakout
            high_20 = hist['High'].rolling(window=20).max().iloc[-2]  # Exclude today
            if current_price > high_20:
                signals.append("Price Breakout")

            # Support/Resistance
            recent_low = hist['Low'].tail(10).min()
            recent_high = hist['High'].tail(10).max()

            if current_price <= recent_low * 1.02:
                signals.append("Near Support")
            elif current_price >= recent_high * 0.98:
                signals.append("Near Resistance")

            return signals

        except Exception as e:
            logger.error(f"Error getting technical signals for {symbol}: {e}")
            return []

    async def get_multiple_stocks(self, symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Get data for multiple stocks efficiently"""
        try:
            tasks = []
            for symbol in symbols:
                task = asyncio.create_task(self.get_stock_data(symbol))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            stock_data = {}
            for i, symbol in enumerate(symbols):
                if isinstance(results[i], Exception):
                    logger.error(f"Error for {symbol}: {results[i]}")
                    stock_data[symbol] = None
                else:
                    stock_data[symbol] = results[i]

            return stock_data

        except Exception as e:
            logger.error(f"Error getting multiple stocks: {e}")
            return {symbol: None for symbol in symbols}

    def __del__(self):
        """Cleanup on destruction"""
        if self.session:
            asyncio.create_task(self.close_session())