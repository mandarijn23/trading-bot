# Discord Notifications Quick Reference

**All new Discord features are active and ready to use!**

---

## 📲 Discord Message Examples

### When Market Starts

#### 🚀 Bot Startup (Automatic at market open)
```
🚀 Stock Bot Started
├─ Symbols: SPY, QQQ, VOO
├─ Timeframe: 15Min
├─ Mode: PAPER TRADING
└─ Status: Ready
```

---

## 📈 During Trading Session

### Buy Signal

#### 🟢 BUY SIGNAL
```
🟢 BUY SIGNAL: SPY
├─ Price: $450.25
├─ Quantity: 10
├─ AI Confidence: 75%
└─ Time: 14:30:45 UTC
```

### Exit Signals

#### ✅ Winning Trade (Green)
```
✅ EXIT TRAIL_STOP: SPY
├─ Entry: $450.25
├─ Exit: $452.50
├─ P&L: +0.50%
├─ Qty: 10
└─ Time: 14:35:20 UTC
```

#### ❌ Losing Trade (Red)
```
❌ EXIT STOP_LOSS: QQQ
├─ Entry: $380.00
├─ Exit: $378.50
├─ P&L: -0.39%
├─ Qty: 5
└─ Time: 14:32:15 UTC
```

---

## ⚠️ Alert Messages

### Model Drift Detected

#### ⚠️ When Bot Loses Confidence
```
⚠️ Model Drift Detected: Stock Bot
├─ Current Win Rate: 45.0%
├─ Baseline Win Rate: 70.0%
├─ Δ Win Rate: -25.0%
├─ New Min AI Confidence: 75%
└─ Action: Risk scaling reduced
```

**What it means:** 
- AI model's recent performance has declined
- Bot automatically raises minimum AI confidence threshold
- Risk scaling reduced to protect capital
- Only sent ONCE per 5-minute window (prevents spam)

### Concentration Limit Hit

#### ⚠️ When Position is Too Large
```
⚠️ Concentration Limit Hit: SPY
├─ Desired Qty: 100
├─ Allowed Qty: 50
├─ Limited By: Group exposure cap (45%)
└─ Action: Order reduced from 100 to 50
```

**What it means:**
- Order would exceed portfolio concentration limits
- Bot automatically reduced position size
- Protects against over-leveraging single stocks
- Only sent ONCE per 5-minute window

### Max Open Positions Reached

#### 🛑 When Trading Limit Reached
```
🛑 Max Open Positions Reached
├─ Current Positions: 2
├─ Max Allowed: 2
└─ Action: No new entries until position closed
```

**What it means:**
- Portfolio has maximum allowed open positions
- Bot will not open new positions until one closes
- Prevents excessive leverage
- Only sent ONCE per market day

---

## 📊 End of Day Summary

### Daily Trading Summary

#### 📊 At Market Close
```
📊 Daily Trading Summary
├─ Trades: 12
├─ Wins: 8
├─ Win Rate: 66.7%
├─ P&L: +2.34%
└─ Date: 2026-04-13 UTC
```

---

## 🔴 Error Messages

### Critical Errors

#### 🔴 ERROR: Retraining Failed
```
🔴 ERROR: Model retraining failed: [Error Details]
└─ [Relevant context]
```

**Why you'd see it:**
- Model retraining crashed
- Bot continues trading but log the error
- Manual investigation recommended

#### 🔴 ERROR: Stock Bot Crashed!
```
🔴 ERROR: Stock Bot crashed!
└─ Error: [Stack trace summary]
```

**What to do:**
- Check log file for full traceback
- Restart bot with: systemctl --user restart trading-bot-stock-local
- Review error logs before next startup

---

## ⏰ Timing Reference

### Market Hours (EST/EDT)

| Event | Time | Discord Alert |
|-------|------|---------------|
| Market Opens | 09:30 AM | 🚀 Bot Startup |
| Trading Session | 09:30 - 16:00 | 🟢 Buy, ✅ Exit, ❌ Exit |
| Market Closes | 16:00 PM | Force close all positions |
| Summary Sent | 16:05 PM | 📊 Daily Summary |

---

## 📋 Alert Rate Limiting

To prevent Discord spam, alerts are rate-limited:

| Alert Type | Cooldown | Frequency Cap |
|------------|----------|---|
| Buy/Sell Signals | None | Real-time |
| Drift Detection | 5 minutes | Once every 5 min |
| Concentration Limit | 5 minutes | Once every 5 min |
| Max Positions | 10 minutes | Once per day |
| Warnings | 5 minutes | Once every 5 min |
| Errors | 15 minutes | Once every 15 min |

---

## 🔐 Webhook Configuration

To enable Discord notifications, set `DISCORD_WEBHOOK_URL` in `.env`:

```bash
# Get webhook URL from Discord
# 1. Go to channel settings → Webhooks
# 2. Create new webhook
# 3. Copy webhook URL
# 4. Set in .env:

DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### Testing Webhook

The bot automatically tests the webhook on startup:

```
✅ Discord webhook verified          ← Success
⚠️  Discord webhook test failed       ← Check URL in .env
```

---

## 💡 Pro Tips

### Understanding P&L Percentages

**P&L format:** `+0.50%` or `-0.39%`

- **Positive (green):** Trade was profitable
- **Negative (red):** Trade resulted in loss
- **Relative to entry price:** `(Exit - Entry) / Entry * 100`

### What Confidence Means

**AI Confidence: 75%**

- Represents model's confidence in buy signal
- Higher = more confident setup
- Used to size positions (higher confidence = larger size)
- Can be used to filter noise trades

### When to Watch for Drift

Watch for these signs in Discord:
- ⚠️ Model drift alerts (win rate declining)
- Concentration limits being hit repeatedly (over-leveraging)
- Max positions reached frequently (too many positions open)

These usually mean market conditions have changed or strategy needs adjustment.

---

## ✅ Checklist: How to Verify Everything Works

1. **Before Market Open**
   - [ ] Check logs: `tail -20 stock_bot.log`
   - [ ] Verify Alpaca connection: Check for "Connected to Alpaca"
   - [ ] Test Discord (if configured): Should see ✅ webhook test

2. **First 30 Minutes of Trading**
   - [ ] Watch for first signal
   - [ ] Verify Discord notification arrives
   - [ ] Check Discord message clarity
   - [ ] Confirm AI confidence is reasonable (40-80%)

3. **Throughout Market Hours**
   - [ ] Monitor for alerts (drift, concentration, max positions)
   - [ ] Check P&L doesn't exceed -5% (daily loss limit)
   - [ ] Verify trades close at TP or SL
   - [ ] Ensure Discord messages are timely

4. **At Market Close**
   - [ ] Check final summary message
   - [ ] Review daily win rate
   - [ ] Verify positions force-closed
   - [ ] Note any warnings or errors

---

## 🚀 Next Steps

1. **Set Discord webhook** (if using Discord alerts)
   ```bash
   echo "DISCORD_WEBHOOK_URL=your_webhook_url" >> .env
   ```

2. **Start bot** (or enable service)
   ```bash
   python core/stock_bot.py      # Interactive
   # OR
   systemctl --user start trading-bot-stock-local  # Service
   ```

3. **Monitor logs**
   ```bash
   tail -f stock_bot.log         # Interactive logs
   # OR
   journalctl --user -u trading-bot-stock-local -f  # Service logs
   ```

4. **Watch Discord** for trade alerts!

---

**All systems operational and ready for trading! 🎯**

*Last Updated: 2026-04-13*
