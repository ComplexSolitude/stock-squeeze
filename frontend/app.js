// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCm3FsyVAxC1SYe_sejESmeS1-vy4q-uVM",
  authDomain: "stock-squeeze.firebaseapp.com",
  projectId: "stock-squeeze",
  storageBucket: "stock-squeeze.firebasestorage.app",
  messagingSenderId: "734654542484",
  appId: "1:734654542484:web:5f03f50e13ee909b0aba81",
  measurementId: "G-3WZCPP0333"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();

// API Configuration
const API_BASE_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'  // Development
    : 'https://your-backend-url.com';  // Production

// App State
let portfolioStocks = [];
let buySignals = [];
let sellSignals = [];
let deferredPrompt;

// PWA Installation
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallPrompt();
});

function showInstallPrompt() {
    document.getElementById('install-prompt').classList.add('show');
}

function hideInstallPrompt() {
    document.getElementById('install-prompt').classList.remove('show');
}

function installApp() {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
            if (choiceResult.outcome === 'accepted') {
                console.log('PWA installed');
            }
            deferredPrompt = null;
            hideInstallPrompt();
        });
    }
}

// Tab Management
function showTab(tabName) {
    // Hide all tabs
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.classList.remove('active'));

    // Remove active class from all buttons
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(btn => btn.classList.remove('active'));

    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    event.target.classList.add('active');

    // Load data for the selected tab
    switch(tabName) {
        case 'portfolio':
            loadPortfolio();
            break;
        case 'buy':
            loadBuySignals();
            break;
        case 'sell':
            loadSellSignals();
            break;
    }
}

// API Helper Functions
async function apiRequest(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Portfolio Management
function loadPortfolio() {
    const portfolioList = document.getElementById('portfolio-list');
    portfolioList.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    // Load from Firebase (real-time updates)
    db.collection('portfolio').onSnapshot((snapshot) => {
        portfolioStocks = [];
        snapshot.forEach((doc) => {
            portfolioStocks.push({ id: doc.id, ...doc.data() });
        });

        renderPortfolio();
    }, (error) => {
        console.error('Error loading portfolio:', error);
        portfolioList.innerHTML = `
            <div class="empty-state">
                <h3>Error loading portfolio</h3>
                <p>Please check your connection and try again</p>
            </div>
        `;
    });
}

function renderPortfolio() {
    const portfolioList = document.getElementById('portfolio-list');

    if (portfolioStocks.length === 0) {
        portfolioList.innerHTML = `
            <div class="empty-state">
                <h3>No stocks in portfolio</h3>
                <p>Add stocks to track squeeze opportunities</p>
            </div>
        `;
        return;
    }

    portfolioList.innerHTML = portfolioStocks.map(stock => `
        <div class="stock-card">
            <div class="stock-header">
                <div>
                    <div class="stock-symbol">${stock.symbol}</div>
                    <div class="stock-price ${stock.change_percent >= 0 ? 'positive' : 'negative'}">
                        $${stock.price?.toFixed(2) || 'Loading...'}
                    </div>
                </div>
                <div class="stock-change ${stock.change_percent >= 0 ? 'positive' : 'negative'}">
                    ${stock.change_percent >= 0 ? '+' : ''}${stock.change_percent?.toFixed(2) || '0.00'}%
                </div>
            </div>
            
            <div class="stock-info">
                <div>
                    <strong>Volume:</strong> ${formatNumber(stock.volume || 0)}
                </div>
                <div>
                    <strong>Avg Vol:</strong> ${formatNumber(stock.avg_volume || 0)}
                </div>
                <div>
                    <strong>Market Cap:</strong> ${formatMarketCap(stock.market_cap || 0)}
                </div>
                <div>
                    <strong>Float:</strong> ${formatNumber(stock.float_shares || 0)}
                </div>
            </div>
            
            ${stock.squeeze_score ? `
                <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
                    <strong>Squeeze Score: ${stock.squeeze_score}/100</strong>
                    ${stock.squeeze_score >= 70 ? '<span style="color: var(--danger)"> 🚨 HIGH POTENTIAL</span>' : ''}
                </div>
            ` : ''}
            
            <button onclick="removeFromPortfolio('${stock.id}')" 
                    style="margin-top: 10px; background: #ff4757; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer;">
                Remove
            </button>
        </div>
    `).join('');
}

// Stock Search and Add
function openAddStockModal() {
    document.getElementById('add-stock-modal').classList.add('active');
    document.getElementById('stock-search').focus();
}

function closeAddStockModal() {
    document.getElementById('add-stock-modal').classList.remove('active');
    document.getElementById('search-results').innerHTML = '';
    document.getElementById('stock-search').value = '';
}

// Replace the searchStocks function in app.js with this:

// Temporarily update searchStocks in app.js to use the test endpoint:

// Update searchStocks in app.js back to the real endpoint:

// Final working version of searchStocks in app.js:

let searchTimeout;
async function searchStocks(query) {
    if (searchTimeout) clearTimeout(searchTimeout);

    if (query.length < 1) {
        document.getElementById('search-results').innerHTML = '';
        return;
    }

    searchTimeout = setTimeout(async () => {
        try {
            console.log(`🔍 Searching for: "${query}"`);

            const response = await apiRequest(`/api/stock/search?q=${encodeURIComponent(query)}`, {
                method: 'GET'
            });

            console.log('✅ Search successful:', response);

            if (response.fallback) {
                console.warn('⚠️ Using fallback results:', response.error);
                showNotification('Search using fallback data', 'warning');
            }

            renderSearchResults(response.results || []);

        } catch (error) {
            console.error('❌ Search failed:', error);

            document.getElementById('search-results').innerHTML = `
                <div style="padding: 20px; text-align: center; color: #666;">
                    <strong>Search temporarily unavailable</strong><br>
                    <small>Please try again in a moment</small>
                    <br><br>
                    <button onclick="searchStocks('${query}')" style="
                        padding: 8px 16px; 
                        background: var(--primary); 
                        color: white; 
                        border: none; 
                        border-radius: 6px; 
                        cursor: pointer;
                    ">
                        Retry Search
                    </button>
                </div>
            `;
        }
    }, 300);
}

function renderSearchResults(results) {
    const searchResults = document.getElementById('search-results');

    if (results.length === 0) {
        searchResults.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #666;">
                No results found
            </div>
        `;
        return;
    }

    searchResults.innerHTML = results.map(stock => `
        <div class="search-result" onclick="addToPortfolio('${stock.symbol}', '${stock.name}')">
            <div>
                <strong>${stock.symbol}</strong><br>
                <span style="color: #666; font-size: 14px;">${stock.name}</span>
            </div>
            <button style="background: var(--primary); color: white; border: none; padding: 8px 16px; border-radius: 6px;">
                Add
            </button>
        </div>
    `).join('');
}

async function addToPortfolio(symbol, name) {
    try {
        // Call backend API to add stock
        await apiRequest('/api/portfolio/add', {
            method: 'POST',
            body: JSON.stringify({
                symbol: symbol,
                name: name
            })
        });

        closeAddStockModal();
        showNotification(`${symbol} added to portfolio!`, 'success');

    } catch (error) {
        console.error('Error adding stock:', error);
        showNotification('Error adding stock to portfolio', 'error');
    }
}

async function removeFromPortfolio(stockId) {
    if (confirm('Remove this stock from your portfolio?')) {
        try {
            await apiRequest(`/api/portfolio/${stockId}`, {
                method: 'DELETE'
            });

            showNotification('Stock removed from portfolio', 'success');
        } catch (error) {
            console.error('Error removing stock:', error);
            showNotification('Error removing stock', 'error');
        }
    }
}

// Buy Signals
function loadBuySignals() {
    const buySignalsContainer = document.getElementById('buy-signals');
    buySignalsContainer.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    // Load from Firebase with real-time updates
    db.collection('squeeze_opportunities')
      .orderBy('squeeze_score', 'desc')
      .limit(20)
      .onSnapshot((snapshot) => {
          buySignals = [];
          snapshot.forEach((doc) => {
              buySignals.push({ id: doc.id, ...doc.data() });
          });

          renderBuySignals();
      }, (error) => {
          console.error('Error loading buy signals:', error);
          buySignalsContainer.innerHTML = `
              <div class="empty-state">
                  <h3>Error loading squeeze opportunities</h3>
                  <p>Please check your connection</p>
              </div>
          `;
      });
}

function renderBuySignals() {
    const container = document.getElementById('buy-signals');

    if (buySignals.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>No squeeze opportunities detected</h3>
                <p>Our AI is scanning the market for opportunities</p>
                <button onclick="manualSqueezeScan()" style="margin-top: 15px; background: var(--primary); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer;">
                    🔍 Manual Scan
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = buySignals.map(signal => `
        <div class="squeeze-alert urgency-${signal.urgency?.toLowerCase()}">
            <div class="squeeze-header">
                <div>
                    <div class="stock-symbol" style="color: white; font-size: 20px;">
                        ${signal.symbol}
                    </div>
                    <div style="color: rgba(255,255,255,0.9);">
                        $${signal.price?.toFixed(2)}
                    </div>
                </div>
                <div class="squeeze-badge">
                    ${getUrgencyEmoji(signal.urgency)} ${signal.urgency} SQUEEZE
                </div>
            </div>
            
            <div class="squeeze-metrics">
                <div class="squeeze-metric">
                    <div class="squeeze-metric-value">${signal.squeeze_score}/100</div>
                    <div class="squeeze-metric-label">Score</div>
                </div>
                <div class="squeeze-metric">
                    <div class="squeeze-metric-value">${signal.volume_spike?.toFixed(1)}x</div>
                    <div class="squeeze-metric-label">Volume</div>
                </div>
                <div class="squeeze-metric">
                    <div class="squeeze-metric-value">${signal.change_percent > 0 ? '+' : ''}${signal.change_percent?.toFixed(1)}%</div>
                    <div class="squeeze-metric-label">Change</div>
                </div>
            </div>
            
            <div style="margin-top: 15px;">
                <div style="color: rgba(255,255,255,0.9); margin-bottom: 10px;">
                    <strong>Signals:</strong> ${signal.signals?.join(', ') || 'Price momentum, Volume spike'}
                </div>
                
                ${signal.trading_halt ? `
                    <div style="background: rgba(255,255,255,0.2); padding: 10px; border-radius: 6px; margin-bottom: 10px;">
                        🛑 <strong>Trading Halt Detected</strong> - Major squeeze indicator
                    </div>
                ` : ''}
                
                ${signal.social_mentions > 50 ? `
                    <div style="background: rgba(255,255,255,0.2); padding: 10px; border-radius: 6px; margin-bottom: 10px;">
                        📱 <strong>Social Media Buzz</strong> - ${signal.social_mentions} mentions
                    </div>
                ` : ''}
            </div>
            
            <div class="risk-warning" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);">
                <h4 style="color: white;">⚠️ Risk Warnings:</h4>
                <ul class="risk-list" style="color: rgba(255,255,255,0.9);">
                    ${signal.risk_warnings?.map(warning => `<li>${warning}</li>`).join('') || 
                      '<li>Extreme volatility - can drop 50%+ quickly</li><li>Set tight stop losses (8-15%)</li>'}
                </ul>
            </div>
        </div>
    `).join('');
}

// Manual squeeze scan
async function manualSqueezeScan() {
    try {
        showNotification('Scanning market for squeeze opportunities...', 'info');

        await apiRequest('/api/manual/scan-squeezes', {
            method: 'POST'
        });

        showNotification('Manual scan completed! Check back in a moment.', 'success');

        // Refresh after a short delay
        setTimeout(() => {
            loadBuySignals();
        }, 3000);

    } catch (error) {
        console.error('Manual scan error:', error);
        showNotification('Manual scan failed. Please try again.', 'error');
    }
}

function loadSellSignals() {
    const sellSignalsContainer = document.getElementById('sell-signals');
    sellSignalsContainer.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    // TEMPORARILY DISABLED: Load from API instead of Firebase to avoid cached data
    // Load from backend API instead
    apiRequest('/api/exit-signals', { method: 'GET' })
        .then(response => {
            sellSignals = response.exit_signals || [];
            console.log('📊 Loaded exit signals from API:', sellSignals);
            renderSellSignals();
        })
        .catch(error => {
            console.error('Error loading sell signals from API:', error);
            // Force empty signals to prevent false alerts
            sellSignals = [];
            renderSellSignals();
        });

    // OLD Firebase code (commented out to prevent cached data):
    // db.collection('exit_signals')
    //   .orderBy('urgency', 'desc')
    //   .onSnapshot((snapshot) => {
    //       sellSignals = [];
    //       snapshot.forEach((doc) => {
    //           sellSignals.push({ id: doc.id, ...doc.data() });
    //       });
    //       renderSellSignals();
    //   }, (error) => {
    //       console.error('Error loading sell signals:', error);
    //       sellSignalsContainer.innerHTML = `
    //           <div class="empty-state">
    //               <h3>Error loading exit signals</h3>
    //               <p>Please check your connection</p>
    //           </div>
    //       `;
    //   });
}

function renderSellSignals() {
    const container = document.getElementById('sell-signals');

    if (sellSignals.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <h3>No exit signals</h3>
                <p>Your portfolio positions are holding strong</p>
                <button onclick="manualPortfolioMonitor()" style="margin-top: 15px; background: var(--primary); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer;">
                    🔍 Check Portfolio
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = sellSignals.map(signal => `
        <div class="signal-card sell-signal">
            <div class="signal-header">
                <div>
                    <div class="signal-title">${signal.symbol}</div>
                    <div style="color: #666; font-size: 14px;">
                        Current: $${signal.current_price?.toFixed(2)} | 
                        ${signal.avg_price ? `Avg: $${signal.avg_price.toFixed(2)}` : ''}
                    </div>
                </div>
                <div class="signal-badge">
                    ${getExitUrgencyText(signal.urgency)}
                </div>
            </div>
            
            <div class="signal-metrics">
                <div class="signal-metric">
                    <div class="signal-metric-value ${signal.current_gain >= 0 ? 'positive' : 'negative'}">
                        ${signal.current_gain >= 0 ? '+' : ''}${signal.current_gain?.toFixed(1)}%
                    </div>
                    <div class="signal-metric-label">Current Gain</div>
                </div>
                <div class="signal-metric">
                    <div class="signal-metric-value negative">
                        -${signal.drop_from_high?.toFixed(1)}%
                    </div>
                    <div class="signal-metric-label">From High</div>
                </div>
                <div class="signal-metric">
                    <div class="signal-metric-value">${signal.urgency}/100</div>
                    <div class="signal-metric-label">Urgency</div>
                </div>
            </div>
            
            <div class="signal-description">
                <strong>Exit Signals:</strong><br>
                ${signal.exit_signals?.map(s => `• ${s.message}`).join('<br>') || 'Multiple exit indicators detected'}
            </div>
            
            <div style="margin-top: 15px;">
                <strong>Recommendation:</strong> 
                <span style="color: var(--danger); font-weight: bold;">
                    ${signal.recommendation?.action || 'CONSIDER SELLING'}
                </span>
            </div>
            
            <div style="margin-top: 10px; font-size: 14px; color: #666;">
                ${signal.position_value ? `Position Value: $${formatNumber(signal.position_value)} | ` : ''}
                ${signal.quantity ? `Quantity: ${signal.quantity} shares | ` : ''}
                ${signal.time_to_act ? `Time to Act: ${signal.time_to_act}` : ''}
            </div>
        </div>
    `).join('');
}

// Manual portfolio monitoring
async function manualPortfolioMonitor() {
    try {
        showNotification('Checking portfolio for exit signals...', 'info');

        await apiRequest('/api/manual/monitor-portfolio', {
            method: 'POST'
        });

        showNotification('Portfolio check completed!', 'success');

        // Refresh after a short delay
        setTimeout(() => {
            loadSellSignals();
        }, 2000);

    } catch (error) {
        console.error('Manual monitor error:', error);
        showNotification('Portfolio check failed. Please try again.', 'error');
    }
}

// Utility Functions
function getUrgencyEmoji(urgency) {
    const emojis = {
        'CRITICAL': '🚨',
        'HIGH': '🔥',
        'MEDIUM': '⚠️',
        'LOW': '👀'
    };
    return emojis[urgency] || '📊';
}

function getExitUrgencyText(urgency) {
    if (urgency >= 90) return 'SELL NOW';
    if (urgency >= 80) return 'SELL SOON';
    if (urgency >= 70) return 'PREPARE';
    if (urgency >= 60) return 'MONITOR';
    return 'HOLD';
}

function formatNumber(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num?.toFixed(0) || '0';
}

function formatMarketCap(num) {
    if (num >= 1e12) return '$' + (num / 1e12).toFixed(1) + 'T';
    if (num >= 1e9) return '$' + (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return '$' + (num / 1e6).toFixed(1) + 'M';
    return '$' + (num / 1e3).toFixed(1) + 'K';
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? 'var(--success)' : type === 'error' ? 'var(--danger)' : 'var(--primary)'};
        color: white;
        border-radius: 8px;
        z-index: 10000;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        transform: translateX(100%);
        transition: transform 0.3s;
        max-width: 350px;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);

    // Remove after 4 seconds
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 4000);
}

// Request notification permission
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                showNotification('Notifications enabled! You\'ll get alerts for critical exits.', 'success');
            }
        });
    }
}

// Initialize App
document.addEventListener('DOMContentLoaded', function() {
    console.log('Squeeze Tracker initialized');

    // Load initial data
    loadPortfolio();

    // Request notification permission after a delay
    setTimeout(requestNotificationPermission, 3000);

    // Register service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('sw.js')
            .then(registration => {
                console.log('SW registered:', registration);
            })
            .catch(error => {
                console.log('SW registration failed:', error);
            });
    }

    // Check backend health
    setTimeout(checkBackendHealth, 1000);
});

async function checkBackendHealth() {
    try {
        const health = await apiRequest('/api/health');
        console.log('Backend health:', health);

        if (health.status === 'healthy') {
            showNotification('Backend connected successfully!', 'success');
        }
    } catch (error) {
        console.error('Backend health check failed:', error);
        showNotification('Backend connection failed - using offline mode', 'error');
    }
}

// Add this function to clear cached Firebase data
function clearCachedData() {
    // Clear local arrays
    sellSignals = [];

    // Force reload
    renderSellSignals();

    console.log('🧹 Cleared cached exit signals');
    showNotification('Cached data cleared', 'success');
}