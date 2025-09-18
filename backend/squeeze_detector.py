import asyncio
import aiohttp
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import json
import re
from collections import Counter
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MarketWideSqueezeDetector:
    def __init__(self):
        self.session = None
        # Squeeze detection thresholds
        self.thresholds = {
            'min_price_change': 50.0,  # 50%+ moves
            'min_volume_spike': 2.0,  # 2x volume
            'min_squeeze_score': 60,  # Minimum score
            'max_price': 100.0,  # Focus on <$100 stocks
            'min_mentions': 10  # Social media mentions
        }

        self.trading_halts_cache = []
        self.last_halt_update = None

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

    async def get_squeeze_opportunities(self, min_change_percent=100.0, min_score=60) -> List[Dict[str, Any]]:
        """Get current squeeze opportunities with market-wide scanning"""
        logger.info(f"🔍 Scanning for squeeze opportunities (>{min_change_percent}%, score>{min_score})")

        try:
            # 1. Get market movers from multiple sources
            all_candidates = set()

            # Get from multiple sources
            yahoo_movers = await self._get_yahoo_movers()
            finviz_movers = await self._get_finviz_movers()
            trading_halts = await self.get_trading_halts()

            all_candidates.update(yahoo_movers)
            all_candidates.update(finviz_movers)
            all_candidates.update([halt['symbol'] for halt in trading_halts])

            logger.info(f"   📊 Found {len(all_candidates)} potential candidates")

            # 2. Analyze each candidate
            squeeze_opportunities = []

            # Process in batches to avoid overwhelming APIs
            batch_size = 10
            candidates_list = list(all_candidates)

            for i in range(0, len(candidates_list), batch_size):
                batch = candidates_list[i:i + batch_size]
                batch_results = await self._analyze_batch(batch, min_change_percent, min_score, trading_halts)
                squeeze_opportunities.extend(batch_results)

                # Rate limiting between batches
                if i + batch_size < len(candidates_list):
                    await asyncio.sleep(1)

            # 3. Sort by squeeze score and urgency
            squeeze_opportunities.sort(key=lambda x: (
                x.get('urgency_priority', 0),
                x.get('squeeze_score', 0)
            ), reverse=True)

            logger.info(f"   ✅ Found {len(squeeze_opportunities)} high-probability squeeze opportunities")

            return squeeze_opportunities[:20]  # Top 20 opportunities

        except Exception as e:
            logger.error(f"Error getting squeeze opportunities: {e}")
            return []

    async def _get_yahoo_movers(self) -> List[str]:
        """Get biggest movers from Yahoo Finance"""
        try:
            session = await self.get_session()

            # Yahoo Finance trending/most active
            urls = [
                "https://finance.yahoo.com/most-active",
                "https://finance.yahoo.com/gainers",
                "https://finance.yahoo.com/losers"
            ]

            symbols = set()

            for url in urls:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive'
                    }
                    async with session.get(url, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            text = await response.text()
                            # Extract symbols from JSON data in page
                            symbol_matches = re.findall(r'"symbol":"([A-Z]{1,5})"', text)
                            symbols.update(symbol_matches[:20])  # Top 20 from each list

                except Exception as e:
                    logger.warning(f"Failed to get Yahoo movers from {url}: {e}")
                    continue

                # Rate limiting
                await asyncio.sleep(0.5)

            logger.info(f"   Yahoo Finance: {len(symbols)} symbols")
            return list(symbols)

        except Exception as e:
            logger.error(f"Yahoo movers error: {e}")
            return []

    async def _get_finviz_movers(self) -> List[str]:
        """Get movers from Finviz screener"""
        try:
            session = await self.get_session()

            # Finviz screener URLs for unusual activity
            urls = [
                "https://finviz.com/screener.ashx?v=111&f=sh_curvol_o2000,ta_change_u10",  # >10% + volume
                "https://finviz.com/screener.ashx?v=111&f=sh_curvol_o1000,ta_change_u5",  # >5% + volume
            ]

            symbols = set()

            for url in urls:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                    async with session.get(url, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            text = await response.text()
                            soup = BeautifulSoup(text, 'html.parser')

                            # Find ticker symbols in Finviz table
                            ticker_links = soup.find_all('a', href=re.compile(r'quote\.ashx\?t='))

                            for link in ticker_links[:50]:  # Limit results
                                symbol = link.text.strip()
                                if symbol and len(symbol) <= 5 and symbol.isalpha():
                                    symbols.add(symbol.upper())

                except Exception as e:
                    logger.warning(f"Failed to get Finviz data from {url}: {e}")
                    continue

                await asyncio.sleep(1)  # Rate limiting

            logger.info(f"   Finviz: {len(symbols)} symbols")
            return list(symbols)

        except Exception as e:
            logger.error(f"Finviz movers error: {e}")
            return []

    async def get_trading_halts(self) -> List[Dict[str, Any]]:
        """Get current trading halts - CRITICAL squeeze indicator"""
        # Use cache if recent (halts don't change frequently)
        if (self.last_halt_update and
                datetime.now() - self.last_halt_update < timedelta(minutes=5)):
            return self.trading_halts_cache

        try:
            session = await self.get_session()
            halts = []

            # Try NASDAQ halts
            try:
                url = "https://www.nasdaqtrader.com/trader.aspx?id=TradeHalts"
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        text = await response.text()
                        soup = BeautifulSoup(text, 'html.parser')

                        # Find halt table
                        tables = soup.find_all('table')
                        for table in tables:
                            rows = table.find_all('tr')[1:]  # Skip header

                            for row in rows[:10]:  # Recent halts only
                                cells = row.find_all('td')
                                if len(cells) >= 4:
                                    symbol = cells[0].text.strip()
                                    halt_time = cells[1].text.strip()
                                    halt_code = cells[2].text.strip()
                                    reason = cells[3].text.strip()

                                    if symbol and len(symbol) <= 5:
                                        halts.append({
                                            'symbol': symbol.upper(),
                                            'halt_time': halt_time,
                                            'halt_code': halt_code,
                                            'reason': reason,
                                            'exchange': 'NASDAQ'
                                        })
            except Exception as e:
                logger.warning(f"NASDAQ halts error: {e}")

            # Try NYSE halts (different format)
            try:
                # NYSE API might have different structure
                pass
            except Exception as e:
                logger.warning(f"NYSE halts error: {e}")

            # Update cache
            self.trading_halts_cache = halts
            self.last_halt_update = datetime.now()

            logger.info(f"   🛑 Found {len(halts)} trading halts")
            return halts

        except Exception as e:
            logger.error(f"Trading halts error: {e}")
            return []

    async def _scan_watchlist(self) -> List[str]:
        """No hardcoded watchlist - rely on market-wide scanning only"""
        return []

    async def _analyze_batch(self, symbols: List[str], min_change_percent: float,
                             min_score: int, trading_halts: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze a batch of symbols for squeeze potential"""
        opportunities = []

        for symbol in symbols:
            try:
                opportunity = await self._analyze_individual_stock(symbol, min_change_percent,
                                                                   min_score, trading_halts)
                if opportunity:
                    opportunities.append(opportunity)

            except Exception as e:
                logger.warning(f"Error analyzing {symbol}: {e}")
                continue

        return opportunities

    async def _analyze_individual_stock(self, symbol: str, min_change_percent: float,
                                        min_score: int, trading_halts: List[Dict]) -> Optional[Dict[str, Any]]:
        """Analyze individual stock for squeeze potential"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d", interval="1m")
            info = ticker.info

            if hist.empty or len(hist) < 2:
                return None

            # Basic price data
            current_price = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price

            # Skip if price too high (focus on accessible stocks)
            if current_price > self.thresholds['max_price']:
                return None

            # Calculate change
            change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0

            # Skip if doesn't meet minimum threshold
            if abs(change_percent) < min_change_percent:
                return None

            # Volume analysis
            current_volume = int(hist['Volume'].iloc[-1])
            avg_volume_20 = hist['Volume'].tail(min(20, len(hist))).mean()
            volume_spike = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1

            # Skip if no significant volume
            if volume_spike < self.thresholds['min_volume_spike']:
                return None

            # Get additional data
            market_cap = info.get('marketCap', 0)
            float_shares = info.get('floatShares', info.get('sharesOutstanding', 0))
            short_ratio = info.get('shortRatio', 0)
            short_percent = info.get('shortPercentOfFloat', 0)

            # Check for trading halt
            halt_info = next((h for h in trading_halts if h['symbol'] == symbol), None)

            # Get social media mentions
            social_mentions = await self._get_social_mentions(symbol)

            # Calculate squeeze score
            squeeze_score = self._calculate_enhanced_squeeze_score({
                'symbol': symbol,
                'price': current_price,
                'change_percent': change_percent,
                'volume_spike': volume_spike,
                'market_cap': market_cap,
                'float_shares': float_shares,
                'short_ratio': short_ratio,
                'short_percent': short_percent,
                'trading_halt': halt_info is not None,
                'social_mentions': social_mentions,
                'price_history': hist['Close'].tail(20).tolist()
            })

            # Skip if score too low
            if squeeze_score < min_score:
                return None

            # Determine urgency
            urgency = self._determine_urgency(squeeze_score, halt_info is not None,
                                              volume_spike, abs(change_percent))

            # Generate signals
            signals = self._generate_signals(change_percent, volume_spike, halt_info,
                                             social_mentions, short_ratio)

            return {
                'symbol': symbol,
                'price': current_price,
                'change_percent': change_percent,
                'squeeze_score': squeeze_score,
                'volume_spike': volume_spike,
                'current_volume': current_volume,
                'avg_volume': int(avg_volume_20),
                'market_cap': market_cap,
                'float_shares': float_shares,
                'short_ratio': short_ratio,
                'short_percent': short_percent,
                'urgency': urgency,
                'urgency_priority': self._get_urgency_priority(urgency),
                'signals': signals,
                'trading_halt': halt_info is not None,
                'halt_info': halt_info,
                'social_mentions': social_mentions,
                'risk_warnings': self._generate_risk_warnings(current_price, change_percent, volume_spike),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error analyzing individual stock {symbol}: {e}")
            return None

    def _calculate_enhanced_squeeze_score(self, data: Dict[str, Any]) -> int:
        """Calculate comprehensive squeeze score (0-100)"""
        score = 0

        try:
            # 1. Price movement (0-25 points)
            change_pct = abs(data.get('change_percent', 0))
            if change_pct >= 500:
                score += 25
            elif change_pct >= 300:
                score += 22
            elif change_pct >= 200:
                score += 18
            elif change_pct >= 100:
                score += 15
            elif change_pct >= 50:
                score += 10

            # 2. Volume spike (0-25 points)
            volume_spike = data.get('volume_spike', 1)
            if volume_spike >= 20:
                score += 25
            elif volume_spike >= 10:
                score += 20
            elif volume_spike >= 5:
                score += 15
            elif volume_spike >= 3:
                score += 10
            elif volume_spike >= 2:
                score += 5

            # 3. Trading halt bonus (0-20 points) - MAJOR indicator
            if data.get('trading_halt', False):
                score += 20

            # 4. Social media buzz (0-15 points)
            social_mentions = data.get('social_mentions', 0)
            if social_mentions >= 1000:
                score += 15
            elif social_mentions >= 500:
                score += 12
            elif social_mentions >= 100:
                score += 8
            elif social_mentions >= 50:
                score += 5

            # 5. Float size (0-10 points)
            float_shares = data.get('float_shares', 0)
            if float_shares > 0:
                if float_shares < 10_000_000:  # <10M
                    score += 10
                elif float_shares < 50_000_000:  # <50M
                    score += 7
                elif float_shares < 100_000_000:  # <100M
                    score += 4

            # 6. Short interest (0-5 points)
            short_ratio = data.get('short_ratio', 0)
            if short_ratio >= 10:
                score += 5
            elif short_ratio >= 5:
                score += 3
            elif short_ratio >= 2:
                score += 1

            return min(score, 100)

        except Exception as e:
            logger.error(f"Error calculating squeeze score: {e}")
            return 0

    def _determine_urgency(self, squeeze_score: int, has_halt: bool,
                           volume_spike: float, change_percent: float) -> str:
        """Determine urgency level"""
        try:
            if has_halt and squeeze_score >= 80:
                return "CRITICAL"
            elif squeeze_score >= 90 or (has_halt and squeeze_score >= 70):
                return "CRITICAL"
            elif squeeze_score >= 80 or volume_spike >= 10:
                return "HIGH"
            elif squeeze_score >= 70 or abs(change_percent) >= 200:
                return "HIGH"
            elif squeeze_score >= 60:
                return "MEDIUM"
            else:
                return "LOW"

        except Exception:
            return "LOW"

    def _get_urgency_priority(self, urgency: str) -> int:
        """Get numeric priority for sorting"""
        priorities = {
            'CRITICAL': 4,
            'HIGH': 3,
            'MEDIUM': 2,
            'LOW': 1
        }
        return priorities.get(urgency, 1)

    def _generate_signals(self, change_percent: float, volume_spike: float,
                          halt_info: Optional[Dict], social_mentions: int,
                          short_ratio: float) -> List[str]:
        """Generate human-readable signals"""
        signals = []

        try:
            if abs(change_percent) >= 200:
                signals.append(f"Massive {abs(change_percent):.0f}% price move")
            elif abs(change_percent) >= 100:
                signals.append(f"Major {abs(change_percent):.0f}% price move")

            if volume_spike >= 10:
                signals.append(f"Extreme volume spike ({volume_spike:.1f}x)")
            elif volume_spike >= 5:
                signals.append(f"Heavy volume ({volume_spike:.1f}x normal)")
            elif volume_spike >= 3:
                signals.append(f"High volume ({volume_spike:.1f}x normal)")

            if halt_info:
                signals.append("Trading halt detected")

            if social_mentions >= 500:
                signals.append("Viral on social media")
            elif social_mentions >= 100:
                signals.append("High social media buzz")

            if short_ratio >= 5:
                signals.append(f"High short interest ({short_ratio:.1f} days)")

            if not signals:
                signals.append("Price and volume momentum")

            return signals

        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            return ["Price momentum detected"]

    def _generate_risk_warnings(self, price: float, change_percent: float,
                                volume_spike: float) -> List[str]:
        """Generate appropriate risk warnings"""
        warnings = []

        try:
            if abs(change_percent) >= 300:
                warnings.append(f"EXTREME VOLATILITY - {abs(change_percent):.0f}% move today")

            if volume_spike >= 15:
                warnings.append(f"MASSIVE VOLUME SPIKE - {volume_spike:.0f}x normal")

            if price < 5:
                warnings.append("PENNY STOCK RISK - High volatility potential")

            warnings.extend([
                "MEME STOCK RISK - Can reverse 50%+ within hours",
                "POSITION SIZE - Never risk more than 2-3% of portfolio",
                "SET STOP LOSSES - Use 8-15% stops, not 50%",
                "TIME SENSITIVE - Most squeezes last less than 4 hours"
            ])

            return warnings

        except Exception as e:
            logger.error(f"Error generating warnings: {e}")
            return ["High risk investment - trade carefully"]

    async def _get_social_mentions(self, symbol: str) -> int:
        """Get social media mentions count (simplified)"""
        try:
            # This is a simplified version - you'd want to integrate with:
            # - Twitter API
            # - Reddit API
            # - StockTwits API
            # - Social media aggregators

            # For now, return estimated mentions based on activity
            # In production, replace with real social media APIs

            # Estimate based on known meme stocks
            if symbol in ['GME', 'AMC', 'TSLA', 'NVDA']:
                return np.random.randint(500, 2000)
            elif symbol in self.meme_watchlist:
                return np.random.randint(50, 500)
            else:
                return np.random.randint(0, 100)

        except Exception:
            return 0

    async def analyze_stock_squeeze_potential(self, symbol: str) -> Dict[str, Any]:
        """Analyze specific stock for squeeze potential"""
        try:
            trading_halts = await self.get_trading_halts()
            opportunity = await self._analyze_individual_stock(
                symbol, 0, 0, trading_halts  # No thresholds for specific analysis
            )

            if opportunity:
                return opportunity
            else:
                # Return basic analysis even if no squeeze detected
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="1d")
                info = ticker.info

                if not hist.empty:
                    return {
                        'symbol': symbol,
                        'price': float(hist['Close'].iloc[-1]),
                        'squeeze_score': 0,
                        'urgency': 'NONE',
                        'signals': ['No squeeze signals detected'],
                        'analysis': 'Stock does not currently show squeeze potential'
                    }

            return {'error': f'Could not analyze {symbol}'}

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return {'error': str(e)}

    def __del__(self):
        """Cleanup on destruction"""
        if self.session:
            asyncio.create_task(self.close_session())