"""
Discord Notifications

Send trade alerts to Discord webhook.
Example: https://discordapp.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN
"""

import os
import json
from datetime import datetime
from typing import Optional
import requests


class DiscordAlerts:
    """Send trade alerts to Discord."""
    
    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        if self.enabled:
            print("✅ Discord notifications enabled")
        else:
            print("❌ Discord notifications disabled (set DISCORD_WEBHOOK_URL in .env)")
    
    def send_message(self, title: str, fields: dict, color: int = 3447003) -> bool:
        """
        Send rich message to Discord.
        
        Args:
            title: Message title
            fields: Dict of field names to values
            color: Embed color (hex as int, default blue)
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            embed = {
                "title": title,
                "color": color,
                "fields": [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in fields.items()
                ],
                "timestamp": datetime.now().isoformat(),
            }
            
            data = {"embeds": [embed]}
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=5
            )
            
            return response.status_code == 204
        except Exception as e:
            print(f"❌ Discord send failed: {e}")
            return False
    
    def notify_buy(self, symbol: str, price: float, qty: int, ai_confidence: float) -> bool:
        """Notify on BUY order."""
        return self.send_message(
            f"🟢 BUY SIGNAL: {symbol}",
            {
                "Price": f"${price:.2f}",
                "Quantity": qty,
                "AI Confidence": f"{ai_confidence:.0%}",
                "Time": datetime.now().strftime("%H:%M:%S"),
            },
            color=3066993  # Green
        )
    
    def notify_sell(self, symbol: str, entry: float, exit_price: float, qty: int, pnl_pct: float, reason: str) -> bool:
        """Notify on SELL/exit."""
        color = 3066993 if pnl_pct > 0 else 10038562  # Green for win, red for loss
        emoji = "✅" if pnl_pct > 0 else "❌"
        
        return self.send_message(
            f"{emoji} EXIT {reason}: {symbol}",
            {
                "Entry": f"${entry:.2f}",
                "Exit": f"${exit_price:.2f}",
                "P&L": f"{pnl_pct:+.2f}%",
                "Qty": qty,
                "Time": datetime.now().strftime("%H:%M:%S"),
            },
            color=color
        )
    
    def notify_daily_summary(self, summary: dict) -> bool:
        """Send daily summary."""
        return self.send_message(
            "📊 Daily Trading Summary",
            {
                "Trades": summary.get("trades", 0),
                "Wins": summary.get("wins", 0),
                "Win Rate": summary.get("win_rate", "0%"),
                "P&L": summary.get("pnl", "0%"),
                "Date": datetime.now().strftime("%Y-%m-%d"),
            },
            color=3447003  # Blue
        )
    
    def notify_warning(self, message: str, details: dict = None) -> bool:
        """Send warning/error alert."""
        if details is None:
            details = {}
        
        return self.send_message(
            f"⚠️ {message}",
            details,
            color=15158332  # Orange
        )
    
    def notify_error(self, message: str, details: dict = None) -> bool:
        """Send critical error alert."""
        if details is None:
            details = {}
        
        return self.send_message(
            f"🔴 ERROR: {message}",
            details,
            color=10038562  # Red
        )


# Global instance
discord = DiscordAlerts()


def test_discord():
    """Test Discord connection."""
    if not discord.enabled:
        print("❌ DISCORD_WEBHOOK_URL not set in .env")
        print("   Get it from: https://discord.com/api/webhooks/")
        return False
    
    print("Testing Discord webhook...")
    result = discord.send_message(
        "🧪 Test Message",
        {
            "Status": "Connection OK",
            "Timestamp": datetime.now().isoformat(),
        }
    )
    
    if result:
        print("✅ Discord webhook working!")
    else:
        print("❌ Discord webhook failed")
    
    return result
