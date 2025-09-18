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


# Stock Data Endpoints
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


@app.post("/api/stock/search")
async def search_stocks(query: str):
    """Search for stocks by symbol or name"""
    try:
        results = await stock_fetcher.search_stocks(query)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error searching stocks: {e}")
        raise HTTPException(status_code=500, detail="Failed to search stocks")


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
        await firebase_client.remove_portfolio_stock(symbol.upper())
        return {"message": f"Removed {symbol} from portfolio"}
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
    """Monitor portfolio for exit signals every 15 seconds"""
    while True:
        try:
            logger.info("Running portfolio exit monitoring...")

            # Get portfolio
            portfolio = await firebase_client.get_portfolio()

            # Check each stock for exit signals
            for stock in portfolio:
                exit_signals = await portfolio_monitor.analyze_stock_exit(stock['symbol'])

                if exit_signals and exit_signals.get('urgency', 0) >= 50:
                    # Store in Firebase
                    await firebase_client.store_exit_signal(exit_signals)

                    # Send critical alerts
                    if exit_signals.get('urgency', 0) >= 85:
                        logger.warning(f"CRITICAL EXIT SIGNAL: {stock['symbol']} - Urgency: {exit_signals['urgency']}")

            logger.info("Portfolio monitoring completed")

        except Exception as e:
            logger.error(f"Error in portfolio monitoring: {e}")

        # Wait 15 seconds
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )