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
                cred = None

                # Method 1: Try environment variables (for Render/Railway)
                if self._has_env_credentials():
                    logger.info("Using Firebase credentials from environment variables")
                    cred = credentials.Certificate(self._get_credentials_from_env())

                # Method 2: Try service account file (for local development)
                elif os.path.exists("firebase-key.json"):
                    logger.info("Using Firebase credentials from file")
                    cred = credentials.Certificate("firebase-key.json")

                # Method 3: Try default credentials (for Google Cloud)
                else:
                    try:
                        logger.info("Trying Firebase default credentials")
                        cred = credentials.ApplicationDefault()
                    except Exception as e:
                        logger.warning(f"Could not initialize Firebase with default credentials: {e}")
                        logger.info("Running in development mode without Firebase")
                        return

                firebase_admin.initialize_app(cred)

            self.db = firestore.client()
            logger.info("✅ Firebase initialized successfully")

        except Exception as e:
            logger.error(f"❌ Error initializing Firebase: {e}")
            logger.info("Running in development mode without Firebase")

    def _has_env_credentials(self) -> bool:
        """Check if all required Firebase env vars are present"""
        required_vars = [
            'FIREBASE_TYPE',
            'FIREBASE_PROJECT_ID',
            'FIREBASE_PRIVATE_KEY_ID',
            'FIREBASE_PRIVATE_KEY',
            'FIREBASE_CLIENT_EMAIL',
            'FIREBASE_CLIENT_ID',
            'FIREBASE_CLIENT_X509_CERT_URL'
        ]

        return all(os.environ.get(var) for var in required_vars)

    def _get_credentials_from_env(self) -> Dict[str, str]:
        """Build Firebase credentials dict from environment variables"""
        # Fix private key formatting (Render/Railway escapes newlines)
        private_key = os.environ.get('FIREBASE_PRIVATE_KEY', '')
        private_key = private_key.replace('\\n', '\n')

        return {
            "type": os.environ.get('FIREBASE_TYPE', 'service_account'),
            "project_id": os.environ.get('FIREBASE_PROJECT_ID'),
            "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID'),
            "private_key": private_key,
            "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL'),
            "client_id": os.environ.get('FIREBASE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_X509_CERT_URL')
        }

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