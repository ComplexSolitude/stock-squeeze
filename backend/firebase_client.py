import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import json
import os

logger = logging.getLogger(__name__)


class FirebaseClient:
    def __init__(self):
        self.db = None
        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase is already initialized
            if not firebase_admin._apps:
                # Try to get credentials from environment or file
                cred_path = "firebase-key.json"  # Your actual filename
                if os.path.exists(cred_path):
                    # Use service account file
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    # Use default credentials (for Google Cloud deployment)
                    try:
                        cred = credentials.ApplicationDefault()
                        firebase_admin.initialize_app(cred)
                    except Exception as e:
                        logger.warning(f"Could not initialize Firebase with default credentials: {e}")
                        # For development, create a mock client
                        logger.info("Running in development mode without Firebase")
                        return

            self.db = firestore.client()
            logger.info("Firebase initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")
            logger.info("Running in development mode without Firebase")

    async def get_portfolio(self) -> List[Dict[str, Any]]:
        """Get user's portfolio from Firestore"""
        if not self.db:
            return []

        try:
            portfolio_ref = self.db.collection('portfolio')
            docs = portfolio_ref.stream()

            portfolio = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                portfolio.append(data)

            logger.info(f"Retrieved {len(portfolio)} portfolio positions")
            return portfolio

        except Exception as e:
            logger.error(f"Error getting portfolio: {e}")
            return []

    async def add_portfolio_stock(self, stock_data: Dict[str, Any]) -> bool:
        """Add stock to portfolio"""
        if not self.db:
            logger.warning("Firebase not available - cannot add to portfolio")
            return False

        try:
            symbol = stock_data['symbol']
            portfolio_ref = self.db.collection('portfolio')

            # Use symbol as document ID
            doc_ref = portfolio_ref.document(symbol)
            doc_ref.set(stock_data)

            logger.info(f"Added {symbol} to portfolio")
            return True

        except Exception as e:
            logger.error(f"Error adding to portfolio: {e}")
            return False

    async def remove_portfolio_stock(self, symbol: str) -> bool:
        """Remove stock from portfolio"""
        if not self.db:
            logger.warning("Firebase not available - cannot remove from portfolio")
            return False

        try:
            portfolio_ref = self.db.collection('portfolio')
            doc_ref = portfolio_ref.document(symbol)
            doc_ref.delete()

            logger.info(f"Removed {symbol} from portfolio")
            return True

        except Exception as e:
            logger.error(f"Error removing from portfolio: {e}")
            return False

    async def update_portfolio_stock(self, symbol: str, update_data: Dict[str, Any]) -> bool:
        """Update portfolio stock data"""
        if not self.db:
            return False

        try:
            portfolio_ref = self.db.collection('portfolio')
            doc_ref = portfolio_ref.document(symbol)

            # Add timestamp
            update_data['last_updated'] = datetime.now()

            doc_ref.update(update_data)
            return True

        except Exception as e:
            logger.error(f"Error updating portfolio stock {symbol}: {e}")
            return False

    async def store_squeeze_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """Store squeeze opportunity in Firestore"""
        if not self.db:
            return False

        try:
            squeeze_ref = self.db.collection('squeeze_opportunities')

            # Use symbol and timestamp as document ID for uniqueness
            doc_id = f"{opportunity['symbol']}_{int(datetime.now().timestamp())}"

            # Add metadata
            opportunity['stored_at'] = datetime.now()
            opportunity['expires_at'] = datetime.now() + timedelta(hours=6)  # Expire after 6 hours

            doc_ref = squeeze_ref.document(doc_id)
            doc_ref.set(opportunity)

            logger.info(f"Stored squeeze opportunity for {opportunity['symbol']}")
            return True

        except Exception as e:
            logger.error(f"Error storing squeeze opportunity: {e}")
            return False

    async def get_squeeze_opportunities(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent squeeze opportunities"""
        if not self.db:
            return []

        try:
            squeeze_ref = self.db.collection('squeeze_opportunities')

            # Get recent opportunities (last 6 hours)
            cutoff_time = datetime.now() - timedelta(hours=6)

            query = squeeze_ref.where('stored_at', '>=', cutoff_time) \
                .order_by('squeeze_score', direction=firestore.Query.DESCENDING) \
                .limit(limit)

            docs = query.stream()

            opportunities = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                opportunities.append(data)

            return opportunities

        except Exception as e:
            logger.error(f"Error getting squeeze opportunities: {e}")
            return []

    async def store_exit_signal(self, exit_signal: Dict[str, Any]) -> bool:
        """Store exit signal in Firestore"""
        if not self.db:
            return False

        try:
            exit_ref = self.db.collection('exit_signals')

            # Use symbol as document ID (will overwrite previous signal)
            symbol = exit_signal['symbol']

            # Add metadata
            exit_signal['stored_at'] = datetime.now()
            exit_signal['expires_at'] = datetime.now() + timedelta(hours=2)  # Expire after 2 hours

            doc_ref = exit_ref.document(symbol)
            doc_ref.set(exit_signal)

            logger.info(f"Stored exit signal for {symbol} (urgency: {exit_signal.get('urgency', 0)})")
            return True

        except Exception as e:
            logger.error(f"Error storing exit signal: {e}")
            return False

    async def get_exit_signals(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get current exit signals"""
        if not self.db:
            return []

        try:
            exit_ref = self.db.collection('exit_signals')

            # Get recent signals (last 2 hours)
            cutoff_time = datetime.now() - timedelta(hours=2)

            if symbols:
                # Get specific symbols
                exit_signals = []
                for symbol in symbols:
                    doc_ref = exit_ref.document(symbol)
                    doc = doc_ref.get()

                    if doc.exists:
                        data = doc.to_dict()
                        stored_at = data.get('stored_at')

                        if stored_at and stored_at >= cutoff_time:
                            data['id'] = doc.id
                            exit_signals.append(data)
            else:
                # Get all recent signals
                query = exit_ref.where('stored_at', '>=', cutoff_time) \
                    .order_by('urgency', direction=firestore.Query.DESCENDING)

                docs = query.stream()
                exit_signals = []

                for doc in docs:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    exit_signals.append(data)

            return exit_signals

        except Exception as e:
            logger.error(f"Error getting exit signals: {e}")
            return []

    async def cleanup_old_data(self, cutoff_time: datetime) -> bool:
        """Clean up old data from collections"""
        if not self.db:
            return False

        try:
            # Clean up old squeeze opportunities
            squeeze_ref = self.db.collection('squeeze_opportunities')
            old_squeeze_query = squeeze_ref.where('stored_at', '<', cutoff_time)

            batch = self.db.batch()
            docs = old_squeeze_query.stream()

            deleted_count = 0
            for doc in docs:
                batch.delete(doc.reference)
                deleted_count += 1

            if deleted_count > 0:
                batch.commit()
                logger.info(f"Deleted {deleted_count} old squeeze opportunities")

            # Clean up old exit signals
            exit_ref = self.db.collection('exit_signals')
            old_exit_query = exit_ref.where('stored_at', '<', cutoff_time)

            batch = self.db.batch()
            docs = old_exit_query.stream()

            deleted_count = 0
            for doc in docs:
                batch.delete(doc.reference)
                deleted_count += 1

            if deleted_count > 0:
                batch.commit()
                logger.info(f"Deleted {deleted_count} old exit signals")

            return True

        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return False

    async def store_trading_halt(self, halt_data: Dict[str, Any]) -> bool:
        """Store trading halt information"""
        if not self.db:
            return False

        try:
            halt_ref = self.db.collection('trading_halts')

            # Use symbol and halt time as unique ID
            symbol = halt_data['symbol']
            halt_time = halt_data.get('halt_time', datetime.now().isoformat())
            doc_id = f"{symbol}_{halt_time.replace(':', '_').replace(' ', '_')}"

            halt_data['stored_at'] = datetime.now()
            halt_data['expires_at'] = datetime.now() + timedelta(hours=24)  # Keep for 24 hours

            doc_ref = halt_ref.document(doc_id)
            doc_ref.set(halt_data)

            logger.info(f"Stored trading halt for {symbol}")
            return True

        except Exception as e:
            logger.error(f"Error storing trading halt: {e}")
            return False

    async def get_trading_halts(self, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Get recent trading halts"""
        if not self.db:
            return []

        try:
            halt_ref = self.db.collection('trading_halts')

            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            query = halt_ref.where('stored_at', '>=', cutoff_time) \
                .order_by('stored_at', direction=firestore.Query.DESCENDING)

            docs = query.stream()
            halts = []

            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                halts.append(data)

            return halts

        except Exception as e:
            logger.error(f"Error getting trading halts: {e}")
            return []

    async def store_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Store user-specific settings"""
        if not self.db:
            return False

        try:
            settings_ref = self.db.collection('user_settings')
            doc_ref = settings_ref.document(user_id)

            settings['updated_at'] = datetime.now()
            doc_ref.set(settings, merge=True)

            return True

        except Exception as e:
            logger.error(f"Error storing user settings: {e}")
            return False

    async def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """Get user-specific settings"""
        if not self.db:
            return {}

        try:
            settings_ref = self.db.collection('user_settings')
            doc_ref = settings_ref.document(user_id)
            doc = doc_ref.get()

            if doc.exists:
                return doc.to_dict()
            else:
                # Return default settings
                return {
                    'exit_thresholds': {
                        'quick_drop': 8,
                        'trailing_stop': 15,
                        'volume_exhaustion': 60
                    },
                    'notifications': {
                        'critical_exits': True,
                        'squeeze_opportunities': True,
                        'portfolio_updates': False
                    },
                    'risk_level': 'balanced'
                }

        except Exception as e:
            logger.error(f"Error getting user settings: {e}")
            return {}

    async def log_user_action(self, user_id: str, action: str, data: Dict[str, Any]) -> bool:
        """Log user actions for analytics"""
        if not self.db:
            return False

        try:
            log_ref = self.db.collection('user_actions')

            log_entry = {
                'user_id': user_id,
                'action': action,
                'data': data,
                'timestamp': datetime.now(),
                'ip_address': data.get('ip_address'),
                'user_agent': data.get('user_agent')
            }

            log_ref.add(log_entry)
            return True

        except Exception as e:
            logger.error(f"Error logging user action: {e}")
            return False

    def get_health_status(self) -> Dict[str, Any]:
        """Get Firebase connection health status"""
        try:
            if not self.db:
                return {
                    'status': 'disconnected',
                    'message': 'Firebase not initialized',
                    'timestamp': datetime.now().isoformat()
                }

            # Test connection with a simple read
            test_ref = self.db.collection('health_check').document('test')
            test_ref.set({'timestamp': datetime.now()})

            return {
                'status': 'connected',
                'message': 'Firebase connection healthy',
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Firebase connection error: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }