from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import logging

# Import our modules
from stock_api import StockDataFetcher
from squeeze_detector import MarketWideSqueezeDetector
from portfolio_monitor import PortfolioMonitor
from firebase_client import FirebaseClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Squeeze Tracker API",
    description="Real-time short squeeze and meme stock detection API",
    version="1.0.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your Netlify domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (your PWA)
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

# Initialize components
stock_fetcher = StockDataFetcher()
squeeze_detector = MarketWideSqueezeDetector()
portfolio_monitor = PortfolioMonitor()
firebase_client = FirebaseClient()


# Pydantic models
class StockSymbol(BaseModel):
    symbol: str


class PortfolioStock(BaseModel):
    symbol: str
    name: str
    quantity: Optional[float] = None
    avg_price: Optional[float] = None


class SqueezeAlert(BaseModel):
    symbol: str
    price: float
    change_percent: float
    squeeze_score: int
    urgency: str
    signals: List[str]
    trading_halt: bool = False
    social_buzz: int = 0


# API Routes
@app.get("/")
async def root():
    """Redirect to PWA"""
    return {"message": "Squeeze Tracker API is running! Visit /static for the PWA"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "stock_api": "connected",
            "firebase": "connected",
            "squeeze_detector": "active"
        }
    }


# 1. SEARCH ENDPOINT FIRST (specific route)
@app.get("/api/stock/search")
async def search_stocks(q: str):
    """Search for stocks by symbol or name - DEBUG VERSION"""
    try:
        logger.info(f"🔍 Starting search for: '{q}'")

        # Test if stock_fetcher exists
        if not stock_fetcher:
            logger.error("❌ stock_fetcher is None!")
            raise Exception("Stock fetcher not initialized")

        logger.info("✅ stock_fetcher exists")

        # Check if search_stocks method exists
        if not hasattr(stock_fetcher, 'search_stocks'):
            logger.error("❌ search_stocks method missing!")
            raise Exception("search_stocks method not found")

        logger.info("✅ search_stocks method exists")

        # Try the actual search
        logger.info("🔄 Calling search_stocks...")
        results = await stock_fetcher.search_stocks(q)

        logger.info(f"✅ Search completed - found {len(results)} results")
        return {"results": results}

    except Exception as e:
        logger.error(f"❌ Search failed for '{q}': {str(e)}")
        logger.exception("Full error traceback:")

        # Return a simple fallback instead of 500 error
        return {
            "results": [
                {"symbol": "AAPL", "name": "Apple Inc.", "type": "EQUITY", "exchange": "NASDAQ"},
                {"symbol": "TSLA", "name": "Tesla, Inc.", "type": "EQUITY", "exchange": "NASDAQ"}
            ],
            "error": str(e),
            "fallback": True
        }

# 2. INDIVIDUAL STOCK ENDPOINT SECOND (parameterized route)
@app.get("/api/stock/{symbol}")
async def get_stock_data(symbol: str):
    """Get current stock data for a symbol"""
    try:
        data = await stock_fetcher.get_stock_data(symbol.upper())
        if not data:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        return data
    except Exception as e:
        logger.error(f"Error fetching stock data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stock data")

@app.get("/api/stock/{symbol}/squeeze-analysis")
async def get_squeeze_analysis(symbol: str):
    """Get detailed squeeze analysis for a specific stock"""
    try:
        analysis = await squeeze_detector.analyze_stock_squeeze_potential(symbol.upper())
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze stock")


# Portfolio Endpoints
@app.get("/api/portfolio")
async def get_portfolio():
    """Get user's portfolio"""
    try:
        portfolio = await firebase_client.get_portfolio()
        return {"portfolio": portfolio}
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        raise HTTPException(status_code=500, detail="Failed to get portfolio")


@app.post("/api/portfolio/add")
async def add_to_portfolio(stock: PortfolioStock):
    """Add stock to portfolio"""
    try:
        # Get current stock data
        stock_data = await stock_fetcher.get_stock_data(stock.symbol)
        if not stock_data:
            raise HTTPException(status_code=404, detail="Stock not found")

        # Add to Firebase
        portfolio_entry = {
            "symbol": stock.symbol,
            "name": stock.name,
            "quantity": stock.quantity,
            "avg_price": stock.avg_price,
            "added_at": datetime.now().isoformat(),
            **stock_data
        }

        await firebase_client.add_portfolio_stock(portfolio_entry)
        return {"message": f"Added {stock.symbol} to portfolio", "data": portfolio_entry}

    except Exception as e:
        logger.error(f"Error adding to portfolio: {e}")
        raise HTTPException(status_code=500, detail="Failed to add to portfolio")


@app.delete("/api/portfolio/{symbol}")
async def remove_from_portfolio(symbol: str):
    """Remove stock from portfolio"""
    try:
        symbol_upper = symbol.upper()

        # Remove from portfolio
        await firebase_client.remove_portfolio_stock(symbol_upper)

        # Also clean up any exit signals for this stock
        if firebase_client.db:
            try:
                exit_ref = firebase_client.db.collection('exit_signals')
                docs = exit_ref.where('symbol', '==', symbol_upper).stream()

                batch = firebase_client.db.batch()
                count = 0
                for doc in docs:
                    batch.delete(doc.reference)
                    count += 1

                if count > 0:
                    batch.commit()
                    logger.info(f"Cleaned up {count} exit signals for {symbol_upper}")

            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup exit signals for {symbol_upper}: {cleanup_error}")

        return {
            "message": f"Removed {symbol} from portfolio and cleaned up exit signals",
            "symbol": symbol_upper
        }

    except Exception as e:
        logger.error(f"Error removing from portfolio: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove from portfolio")


# Squeeze Detection Endpoints
@app.get("/api/squeeze-opportunities")
async def get_squeeze_opportunities():
    """Get current squeeze opportunities"""
    try:
        opportunities = await squeeze_detector.get_squeeze_opportunities()
        return {"opportunities": opportunities}
    except Exception as e:
        logger.error(f"Error getting squeeze opportunities: {e}")
        raise HTTPException(status_code=500, detail="Failed to get squeeze opportunities")


@app.get("/api/trading-halts")
async def get_trading_halts():
    """Get current trading halts"""
    try:
        halts = await squeeze_detector.get_trading_halts()
        return {"halts": halts}
    except Exception as e:
        logger.error(f"Error getting trading halts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get trading halts")


# Exit Signal Endpoints
@app.get("/api/exit-signals")
async def get_exit_signals():
    """Get exit signals for portfolio stocks"""
    try:
        signals = await portfolio_monitor.get_exit_signals()
        return {"exit_signals": signals}
    except Exception as e:
        logger.error(f"Error getting exit signals: {e}")
        raise HTTPException(status_code=500, detail="Failed to get exit signals")


@app.get("/api/exit-signals/{symbol}")
async def get_stock_exit_signals(symbol: str):
    """Get exit signals for specific stock"""
    try:
        signals = await portfolio_monitor.analyze_stock_exit(symbol.upper())
        return signals
    except Exception as e:
        logger.error(f"Error getting exit signals for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get exit signals")


@app.delete("/api/exit-signals/clear")
async def clear_exit_signals():
    """Clear all exit signals from Firebase"""
    try:
        # Get all exit signals
        if firebase_client.db:
            exit_ref = firebase_client.db.collection('exit_signals')
            docs = exit_ref.stream()

            # Delete all documents
            batch = firebase_client.db.batch()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1

            if count > 0:
                batch.commit()
                logger.info(f"Cleared {count} exit signals")

            return {"message": f"Cleared {count} exit signals", "success": True}
        else:
            return {"message": "Firebase not available", "success": False}

    except Exception as e:
        logger.error(f"Error clearing exit signals: {e}")
        return {"error": str(e), "success": False}


# Background Tasks
@app.on_event("startup")
async def startup_event():
    """Start background monitoring tasks"""
    logger.info("Starting Squeeze Tracker API...")

    # Start background tasks
    asyncio.create_task(background_portfolio_monitor())
    asyncio.create_task(background_squeeze_scanner())
    asyncio.create_task(background_data_cleanup())

    logger.info("Background tasks started successfully")


async def background_portfolio_monitor():
    """Monitor portfolio for exit signals - respects market hours"""
    while True:
        try:
            # Check if market is open first
            monitor = PortfolioMonitor()

            if not monitor.is_market_hours():
                logger.info("📴 Market closed - portfolio monitoring paused")
                await asyncio.sleep(300)  # Wait 5 minutes during off-hours
                continue

            logger.info("📊 Running portfolio exit monitoring (market hours)...")

            # Get portfolio
            portfolio = await firebase_client.get_portfolio()

            # Check each stock for exit signals
            for stock in portfolio:
                exit_signals = await monitor.analyze_stock_exit(
                    stock['symbol'],
                    stock.get('avg_price'),
                    stock.get('quantity', 0)
                )

                if exit_signals and exit_signals.get('urgency', 0) >= 50:
                    # Store in Firebase
                    await firebase_client.store_exit_signal(exit_signals)

                    # Send critical alerts
                    if exit_signals.get('urgency', 0) >= 85:
                        logger.warning(
                            f"🚨 CRITICAL EXIT SIGNAL: {stock['symbol']} - Urgency: {exit_signals['urgency']}")

            logger.info("✅ Portfolio monitoring completed")
            await monitor.close_sessions()

        except Exception as e:
            logger.error(f"❌ Error in portfolio monitoring: {e}")

        # During market hours: check every 15 seconds
        # After hours: check every 5 minutes
        await asyncio.sleep(15)


async def background_squeeze_scanner():
    """Scan for squeeze opportunities every 60 seconds"""
    while True:
        try:
            logger.info("Scanning for squeeze opportunities...")

            # Get squeeze opportunities
            opportunities = await squeeze_detector.get_squeeze_opportunities(
                min_change_percent=100.0,
                min_score=60
            )

            # Store in Firebase
            for opp in opportunities:
                await firebase_client.store_squeeze_opportunity(opp)

            logger.info(f"Found {len(opportunities)} squeeze opportunities")

        except Exception as e:
            logger.error(f"Error in squeeze scanning: {e}")

        # Wait 60 seconds
        await asyncio.sleep(60)


async def background_data_cleanup():
    """Clean up old data every hour"""
    while True:
        try:
            # Clean up data older than 24 hours
            cutoff_time = datetime.now() - timedelta(hours=24)

            await firebase_client.cleanup_old_data(cutoff_time)
            logger.info("Data cleanup completed")

        except Exception as e:
            logger.error(f"Error in data cleanup: {e}")

        # Wait 1 hour
        await asyncio.sleep(3600)


# Manual trigger endpoints (for testing)
@app.post("/api/manual/scan-squeezes")
async def manual_squeeze_scan(background_tasks: BackgroundTasks):
    """Manually trigger squeeze scan"""
    background_tasks.add_task(background_squeeze_scanner_once)
    return {"message": "Squeeze scan triggered"}


@app.post("/api/manual/monitor-portfolio")
async def manual_portfolio_monitor(background_tasks: BackgroundTasks):
    """Manually trigger portfolio monitoring"""
    background_tasks.add_task(background_portfolio_monitor_once)
    return {"message": "Portfolio monitoring triggered"}


async def background_squeeze_scanner_once():
    """Run squeeze scanner once"""
    try:
        opportunities = await squeeze_detector.get_squeeze_opportunities()
        for opp in opportunities:
            await firebase_client.store_squeeze_opportunity(opp)
        logger.info(f"Manual scan: Found {len(opportunities)} opportunities")
    except Exception as e:
        logger.error(f"Manual scan error: {e}")


async def background_portfolio_monitor_once():
    """Run portfolio monitor once"""
    try:
        portfolio = await firebase_client.get_portfolio()
        for stock in portfolio:
            exit_signals = await portfolio_monitor.analyze_stock_exit(stock['symbol'])
            if exit_signals:
                await firebase_client.store_exit_signal(exit_signals)
        logger.info("Manual portfolio monitor completed")
    except Exception as e:
        logger.error(f"Manual portfolio monitor error: {e}")


# Debug endpoint
@app.get("/debug/market-time")
async def debug_market_time():
    """Debug what time the system thinks it is"""
    import pytz
    monitor = PortfolioMonitor()

    utc_now = datetime.utcnow()
    et_tz = pytz.timezone('US/Eastern')
    et_now = datetime.now(et_tz)

    is_market = monitor.is_market_hours()

    return {
        "utc_time": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "et_time": et_now.strftime("%Y-%m-%d %H:%M:%S ET"),
        "et_hour": et_now.hour,
        "et_minute": et_now.minute,
        "weekday": et_now.weekday(),
        "is_weekend": et_now.weekday() >= 5,
        "is_market_hours": is_market,
        "market_should_be_open": (9.5 <= (et_now.hour + et_now.minute / 60) <= 16) and et_now.weekday() < 5
    }


@app.post("/api/portfolio/cleanup-exit-signals")
async def cleanup_orphaned_exit_signals():
    """Remove exit signals for stocks not in portfolio"""
    try:
        # Get current portfolio symbols
        portfolio = await firebase_client.get_portfolio()
        portfolio_symbols = {stock['symbol'] for stock in portfolio}

        if not firebase_client.db:
            return {"message": "Firebase not available"}

        # Get all exit signals
        exit_ref = firebase_client.db.collection('exit_signals')
        docs = exit_ref.stream()

        batch = firebase_client.db.batch()
        removed_count = 0

        for doc in docs:
            data = doc.to_dict()
            symbol = data.get('symbol', '')

            # If this exit signal is for a stock not in portfolio, remove it
            if symbol not in portfolio_symbols:
                batch.delete(doc.reference)
                removed_count += 1
                logger.info(f"Marking orphaned exit signal for removal: {symbol}")

        if removed_count > 0:
            batch.commit()

        return {
            "message": f"Cleaned up {removed_count} orphaned exit signals",
            "portfolio_symbols": list(portfolio_symbols),
            "removed_count": removed_count
        }

    except Exception as e:
        logger.error(f"Error cleaning up exit signals: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )