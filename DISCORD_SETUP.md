# 🔔 Discord Notifications Setup Guide

Enable real-time trading alerts in your Discord server in **3 minutes**.

---

## Quick Start

### 1️⃣ Create Discord Webhook

1. Open Discord and go to your server
2. Right-click the channel where you want alerts → **Edit Channel**
3. Go to **Integrations** → **Webhooks** → **New Webhook**
4. Name it `Trading-Bot`
5. Click **Copy Webhook URL**

Example URL:
```
https://discordapp.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz
```

### 2️⃣ Add to `.env` File

Edit `.env` and add your webhook URL:

```env
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### 3️⃣ Test Connection

```bash
python cli.py test-discord
```

Output:
```
🔗 Testing Discord webhook...

Test 1: Sending test message...
  ✅ Basic message sent
Test 2: Sending BUY notification...
  ✅ BUY notification sent
Test 3: Sending SELL notification...
  ✅ SELL notification sent
Test 4: Sending daily summary...
  ✅ Daily summary sent

✅ All Discord tests passed!
```

---

## Alerts You'll Receive

### 🟢 BUY Alert
```
🟢 BUY SIGNAL: BTC/USDT

Price:        $45,250.00
Quantity:     0.5
AI Confidence: 78%
Time:         14:32:15
```

### 🟢✅ SELL Alert (Profit)
```
✅ EXIT TAKE_PROFIT: BTC/USDT

Entry:  $45,250.00
Exit:   $46,500.00
P&L:    +$625.00 (+2.77%)
Qty:    0.5
Time:   14:45:30
```

### 🔴 SELL Alert (Loss)
```
❌ EXIT TRAIL_STOP: BTC/USDT

Entry:  $45,250.00
Exit:   $44,800.00
P&L:    -$225.00 (-0.99%)
Qty:    0.5
Time:   14:38:15
```

### 📊 Daily Summary
```
📊 Daily Trading Summary

Trades:  15
Wins:    12
Win Rate: 80.0%
P&L:     +12.34%
Date:    2026-04-07
```

### ⚠️ Warning Alert
```
⚠️ Model retraining complete

Status: Updated with 20 recent trades
```

### 🔴 Error Alert
```
🔴 ERROR: Bot crashed!

Error: Connection timeout
```

---

## Troubleshooting

### ❌ "Discord not enabled"

**Problem:** `❌ Discord not enabled!`

**Solution:**
1. Make sure `.env` file exists in the project root
2. Check that `DISCORD_WEBHOOK_URL` is set (not empty)
3. Use full webhook URL, not just partial

```env
# ✅ Correct
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/123456/ABCdef

# ❌ Wrong
DISCORD_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=123456
```

### ❌ Webhook Error: 404

**Problem:** `❌ Discord webhook failed: 404`

**Solution:**
1. Webhook URL might be expired
2. Generate a new webhook URL from Discord dev portal
3. Update `.env` with new URL

To regenerate:
- Discord → Server → Channel Settings → Integrations → Webhooks
- Delete old webhook and create new one
- Copy new URL and update `.env`

### ❌ Webhook Error: 401

**Problem:** `❌ Discord webhook failed: 401 Unauthorized`

**Solution:**
1. Webhook URL is incorrect or malformed
2. Double-check you copied the **full** URL
3. Make sure there are no extra spaces

Correct format:
```
https://discordapp.com/api/webhooks/[ID]/[TOKEN]
                                     ^^^^  ^^^^^
                                      |     |
                              Copy BOTH parts!
```

### ✅ Bot ignores Discord errors

The bot is designed to **gracefully handle Discord failures**:

- If Discord webhook fails, bot continues trading normally
- Errors are logged but don't stop trading
- This protects you from losing trading opportunities

### Logs say Discord works but I don't see messages

1. Check that the bot is actually trading:
   ```bash
   tail -f bot.log
   # or
   tail -f stock_bot.log
   ```
   Look for `BUY signal` or `EXIT` messages

2. Make sure Discord channel has permissions for webhook:
   - Right-click channel → Permissions → Check webhook can send messages

3. Check bot member permissions:
   - Server Settings → Roles → Check bot has "Send Messages" permission

---

## Advanced: Multiple Channels

Want alerts in different channels?

Create a separate webhook for each channel:

```bash
# .env — only one webhook per bot instance
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/MAIN_CHANNEL/TOKEN
```

If you want multiple channels, you can:
1. Create separate Discord webhooks in `.env` for different bot instances
2. Run multiple bot instances with different configs
3. Each instance sends to its own Discord channel

---

## Privacy & Security

### 🔒 Keep Your Webhook URL Secret

- **Never commit `.env` to git** — it's already in `.gitignore`  
- Don't share webhook URL in public channels
- Webhook URL gives full access to your trading channel

### 🔓 If Your Webhook is Compromised

Re-generate immediately:
1. Discord → Server → Webhooks
2. Delete the old webhook
3. Create a new one
4. Update `.env` with new URL

---

## Features

| Feature | Status |
|---------|--------|
| Buy/Sell alerts | ✅ Enabled |
| Profit/loss coloring | ✅ Enabled |
| Daily summary | ✅ Enabled |
| Error notifications | ✅ Enabled |
| Model retraining alerts | ✅ Enabled |

---

## Next Steps

1. **Test again**: `python cli.py test-discord`
2. **Start trading**: `python stock_bot.py` or `python bot.py`
3. **Monitor**: Watch Discord channel for real-time alerts! 🚀

---

## FAQ

**Q: Does Discord slow down the bot?**  
A: No. Webhook messages are sent asynchronously and never block trading.

**Q: What if Discord is down?**  
A: Bot continues trading normally. Errors are logged but ignored.

**Q: Can I use Discord with paper trading?**  
A: Yes! Discord works for both paper and live trading.

**Q: Can I customize the Discord messages?**  
A: Yes! Edit `discord_alerts.py` to customize embed colors, titles, etc.

**Q: Can I send alerts to multiple channels?**  
A: A single bot instance has one webhook. Run multiple instances for multiple channels.

---

## Support

Having issues? Check:

1. **Is webhook URL correct?** → Test with `python cli.py test-discord`
2. **Is bot actually trading?** → Check `bot.log` or `stock_bot.log`
3. **Does channel have webhook perms?** → Check Discord channel settings
4. **Is networking working?** → Can you reach `discord.com` from terminal?

---

Happy trading! 🚀

For more info: See [GUIDE_PHASE6.md](GUIDE_PHASE6.md)
