# 🚀 Squeeze Tracker - Short Squeeze & Meme Stock PWA

A real-time Progressive Web App for detecting short squeeze opportunities and managing meme stock portfolios.

## ✨ Features

- **📊 Portfolio Management** - Track your meme stock positions
- **🚀 Buy Signals** - Real-time squeeze opportunity detection  
- **💰 Sell Signals** - Exit alerts with tight stop losses (8-15%)
- **📱 PWA** - Install on mobile/desktop, works offline
- **🔔 Push Notifications** - Critical exit alerts
- **🛑 Trading Halt Detection** - Key squeeze indicator
- **📈 Social Media Integration** - Track viral momentum

## 🚀 Quick Deploy to Netlify

### 1. **Setup Repository**
```bash
# Create new repo on GitHub
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/squeeze-tracker.git
git push -u origin main
```

### 2. **Deploy to Netlify**
1. Go to [Netlify](https://netlify.com)
2. Click "New site from Git"
3. Connect your GitHub repo
4. Deploy settings:
   - **Build command:** `echo 'No build needed'`
   - **Publish directory:** `/`
5. Click "Deploy site"

### 3. **Setup Firebase**
1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create new project
3. Enable Firestore Database
4. Get your config from Project Settings > General > Your apps
5. Update `firebaseConfig` in `app.js`:

```javascript
const firebaseConfig = {
    apiKey: "your-actual-api-key",
    authDomain: "your-project.firebaseapp.com", 
    projectId: "your-project-id",
    storageBucket: "your-project.appspot.com",
    messagingSenderId: "123456789",
    appId: "your-app-id"
};
```

### 4. **Create Firestore Collections**
In Firebase Console > Firestore, create these collections:
- `portfolio` - User's stock positions
- `squeeze_opportunities` - Buy signals 
- `exit_signals` - Sell signals

## 📁 File Structure

```
squeeze-tracker/
├── index.html          # Main app HTML
├── styles.css          # All app styling
├── app.js             # Main app logic
├── manifest.json      # PWA manifest
├── sw.js             # Service worker
├── netlify.toml      # Netlify config
├── icon-192x192.png  # App icon (required)
├── icon-512x512.png  # App icon (required)
└── README.md         # This file
```

## 🎯 Key Features Breakdown

### Portfolio Tab
- Add stocks via Yahoo Finance search
- Real-time price updates
- Squeeze score calculation
- Volume & float analysis

### Buy Tab  
- Market-wide squeeze detection
- Trading halt monitoring
- Social media buzz tracking
- Risk warnings for each signal

### Sell Tab
- Portfolio-only exit signals
- Tight stop losses (8% not 50%)
- Volume exhaustion detection
- Profit protection alerts

## 🔧 Customization

### Update Stock Data Source
Replace mock functions in `app.js`:
```javascript
async function fetchStockData(symbol) {
    // Replace with real Yahoo Finance API
    const response = await fetch(`/api/stock/${symbol}`);
    return response.json();
}
```

### Modify Squeeze Detection
Update detection thresholds:
```javascript
const SQUEEZE_THRESHOLDS = {
    minPriceChange: 100,    // 100%+ moves
    minVolumeSpike: 3,      // 3x volume
    minSqueezeScore: 70     // Score threshold
};
```

### Customize Exit Signals
Adjust stop loss levels:
```javascript
const EXIT_THRESHOLDS = {
    quickDrop: 0.08,        // 8% drop trigger
    trailingStop: 0.15,     // 15% trailing stop
    volumeExhaustion: 0.6   // 60% volume decline
};
```

## 📱 PWA Installation

### Desktop (Chrome/Edge)
1. Visit your site
2. Click install icon in address bar
3. Click "Install"

### Mobile (iOS/Android)  
1. Open in Safari/Chrome
2. Tap Share button
3. Tap "Add to Home Screen"

## 🔔 Push Notifications

To enable push notifications:

1. **Update Firebase** - Enable Cloud Messaging
2. **Add Vapid Key** - Get from Firebase Console
3. **Request Permission** - Already implemented in app
4. **Send Notifications** - Use Firebase Functions or server

## 🚨 Important Notes

### Risk Management
- **8% stop losses** (not 50%!)
- **Portfolio-only alerts** (no noise)
- **Position sizing warnings**
- **Time-based exits** (squeezes are short)

### Data Sources
- Replace mock APIs with real sources
- Yahoo Finance for stock data
- Twitter API for social buzz  
- Exchange APIs for trading halts

### Performance
- **30s** portfolio updates
- **60s** squeeze scans
- **15s** exit monitoring  
- Offline caching via service worker

## 🔗 Useful Links

- [Yahoo Finance API](https://rapidapi.com/apidojo/api/yahoo-finance1/)
- [Firebase Docs](https://firebase.google.com/docs)
- [PWA Checklist](https://web.dev/pwa-checklist/)
- [Netlify Deploy Docs](https://docs.netlify.com/)

## 🐛 Troubleshooting

### PWA Not Installing
- Check `manifest.json` is accessible
- Ensure HTTPS (Netlify provides this)
- Icons must be correct sizes

### Firebase Connection Issues  
- Verify config object is correct
- Check Firestore rules allow read/write
- Ensure project ID matches exactly
- Test in incognito mode (cache issues)

### Notifications Not Working
- Check browser permissions
- HTTPS required for notifications  
- Test with simple notification first
- Service worker must be registered

### Data Not Loading
- Check browser console for errors
- Verify Firestore collections exist
- Test Firebase connection in console
- Check network tab for failed requests

## 🔄 Data Flow

### Portfolio Management
1. User searches stock → Yahoo Finance API
2. Add to portfolio → Store in Firestore
3. Background updates → Fetch new prices
4. Real-time sync → Update UI

### Squeeze Detection  
1. Scan market → Multiple data sources
2. Calculate scores → Volume, price, social buzz
3. Store opportunities → Firestore collection
4. Real-time alerts → Push notifications

### Exit Signals
1. Monitor portfolio → Every 15 seconds
2. Detect patterns → Volume, price action
3. Calculate urgency → Multiple indicators  
4. Alert user → Notifications + UI

## 🎨 UI Customization

### Color Scheme
Update CSS variables in `styles.css`:
```css
:root {
    --primary: #your-color;
    --danger: #your-red;
    --success: #your-green;
}
```

### Animation Speed
Modify animation durations:
```css
@keyframes pulse {
    /* Faster/slower pulsing */
}
```

### Mobile Layout
Responsive breakpoints already included:
- `480px` - Small phones
- `360px` - Very small screens

## 🔐 Security Best Practices

### Firebase Rules
Set up proper Firestore security rules:
```javascript
// Allow read/write for authenticated users only
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
```

### API Keys
- Never commit real API keys to GitHub
- Use Netlify environment variables
- Restrict API keys to your domain

### Content Security Policy
Add to `index.html` head:
```html
<meta http-equiv="Content-Security-Policy" 
      content="default-src 'self' https://firestore.googleapis.com;">
```

## 📊 Analytics & Monitoring

### Track User Engagement
Add to `app.js`:
```javascript
// Track tab usage
function trackTabChange(tabName) {
    // Send to analytics service
    console.log(`User viewed ${tabName} tab`);
}
```

### Monitor Performance
```javascript
// Track load times
window.addEventListener('load', () => {
    const loadTime = performance.now();
    console.log(`App loaded in ${loadTime}ms`);
});
```

### Error Tracking
```javascript
window.addEventListener('error', (error) => {
    // Send to error tracking service
    console.error('App error:', error);
});
```

## 🚀 Advanced Features

### Real-Time Price Updates
Implement WebSocket connections:
```javascript
const ws = new WebSocket('wss://your-websocket-endpoint');
ws.onmessage = (event) => {
    const priceUpdate = JSON.parse(event.data);
    updatePortfolioPrice(priceUpdate);
};
```

### Advanced Squeeze Detection
Add more indicators:
- Options flow analysis
- Short interest data
- Insider trading activity
- Earnings announcements

### Machine Learning
Train models for:
- Squeeze prediction accuracy
- Exit timing optimization  
- Risk assessment

## 📈 Scaling Considerations

### Database Optimization
- Index Firestore queries properly
- Use pagination for large datasets
- Implement data archiving

### API Rate Limits
- Cache API responses
- Implement retry logic
- Use multiple data sources

### User Growth
- Implement user authentication
- Add premium features
- Scale Firebase plan as needed

## 🔧 Development Workflow

### Local Development
```bash
# Serve locally
python -m http.server 8000
# or
npx serve .
```

### Testing
- Test PWA installation
- Verify offline functionality
- Check notifications on different devices
- Test with slow network conditions

### Deployment
```bash
# Push to GitHub triggers Netlify deploy
git add .
git commit -m "Update squeeze detection"
git push origin main
```

## 📞 Support & Contributing

### Getting Help
- Check browser console for errors
- Test in incognito mode
- Verify all files are uploaded correctly
- Check Netlify deploy logs

### Feature Requests
- Portfolio import/export
- Paper trading mode
- Backtesting capabilities
- Multi-exchange support

## ⚡ Performance Tips

### Optimize Loading
- Minimize JavaScript bundle
- Use image compression for icons
- Enable gzip compression (automatic on Netlify)
- Lazy load non-critical components

### Reduce Firebase Costs
- Use offline persistence
- Implement proper pagination
- Cache frequently accessed data
- Set up billing alerts

## 🎯 Success Metrics

### Key Performance Indicators
- PWA installation rate
- Daily active users
- Alert click-through rate
- Portfolio sync success rate

### Trading Performance  
- Squeeze detection accuracy
- Exit signal effectiveness
- User profitability (if tracking)
- Risk management success

---

## 🚀 Ready to Deploy!

1. **Fork/Clone** this repository
2. **Update Firebase config** in `app.js`
3. **Deploy to Netlify** (auto-deploy on push)
4. **Add app icons** (required for PWA)
5. **Test installation** on mobile device

Your squeeze tracking PWA will be live and installable within minutes! 

The app focuses specifically on short squeezes and meme stocks with tight risk management - exactly what you requested. 🎯