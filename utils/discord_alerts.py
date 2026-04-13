"""
Discord Notifications

Send trade alerts to Discord webhook.
Example: https://discordapp.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN
"""

import os
import json
import mimetypes
from datetime import datetime
from typing import Optional
from pathlib import Path
import requests
from dotenv import load_dotenv


ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
if ROOT_ENV.exists():
    load_dotenv(dotenv_path=ROOT_ENV, override=True)
else:
    load_dotenv(override=True)


class DiscordAlerts:
    """Send trade alerts to Discord."""
    
    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        self.graph_mention = os.getenv("DISCORD_HOURLY_MENTION", "@jovial_lemur_47699").strip()
        self.warning_cooldown_sec = int(os.getenv("DISCORD_WARNING_COOLDOWN_SEC", "300"))
        self.error_cooldown_sec = int(os.getenv("DISCORD_ERROR_COOLDOWN_SEC", "900"))
        self._last_sent_by_key: dict[str, datetime] = {}
        self._tested = False
        
        if self.enabled:
            print("✅ Discord notifications enabled")
            # Test webhook connectivity at startup
            self._test_webhook_connection()
        else:
            print("❌ Discord notifications disabled (set DISCORD_WEBHOOK_URL in .env)")

    def _test_webhook_connection(self) -> None:
        """Test Discord webhook connectivity at startup."""
        if self._tested or not self.enabled:
            return
        
        try:
            result = self.send_message(
                "✅ Webhook Test",
                {"Status": "Connected", "Time": datetime.now().strftime("%H:%M:%S UTC")},
                color=3066993  # Green
            )
            if result:
                print("✅ Discord webhook verified")
                self._tested = True
            else:
                print("⚠️  Discord webhook test failed (response error)")
        except Exception as e:
            print(f"⚠️  Discord webhook test failed: {e}")
    
    def _is_rate_limited(self, key: str, cooldown_sec: int) -> bool:
        """Return True if message key is still within cooldown window."""
        if cooldown_sec <= 0:
            return False
        now = datetime.now()
        last_sent = self._last_sent_by_key.get(key)
        if last_sent and (now - last_sent).total_seconds() < cooldown_sec:
            return True
        self._last_sent_by_key[key] = now
        return False
    
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
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {"text": "Time shown in UTC"},
            }

            data = {"embeds": [embed]}
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=5,
            )

            return response.status_code in (200, 204)
        except Exception as e:
            print(f"❌ Discord send failed: {e}")
            return False

    def send_file(
        self,
        title: str,
        fields: dict,
        file_path: str,
        filename: Optional[str] = None,
        color: int = 3447003,
    ) -> bool:
        """Send a Discord embed with an attached file."""
        if not self.enabled:
            return False

        attachment_name = filename or Path(file_path).name
        try:
            embed = {
                "title": title,
                "color": color,
                "fields": [
                    {"name": k, "value": str(v), "inline": True}
                    for k, v in fields.items()
                ],
                "timestamp": datetime.now().isoformat(),
                "image": {"url": f"attachment://{attachment_name}"},
            }
            content = "Training chart attached below."
            if self.graph_mention:
                content = f"{self.graph_mention} {content}"

            payload = {
                "content": content,
                "embeds": [embed],
                "attachments": [{"id": 0, "filename": attachment_name}],
                "allowed_mentions": {"parse": ["users"]},
            }
            mime_type, _ = mimetypes.guess_type(attachment_name)
            if not mime_type:
                mime_type = "application/octet-stream"

            with open(file_path, "rb") as file_handle:
                files = {"files[0]": (attachment_name, file_handle, mime_type)}
                response = requests.post(
                    self.webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=10,
                )

            return response.status_code in (200, 204)
        except Exception as e:
            print(f"❌ Discord file send failed: {e}")
            return False
    
    def send_chart(
        self,
        title: str,
        chart_url: str,
        color: int = 3447003,
    ) -> bool:
        """Send a Discord embed with an embedded chart image from QuickChart URL."""
        if not self.enabled:
            return False

        try:
            embed = {
                "title": title,
                "color": color,
                "image": {"url": chart_url},
                "timestamp": datetime.now().isoformat(),
            }

            data = {"embeds": [embed]}
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=5,
            )

            return response.status_code in (200, 204)
        except Exception as e:
            print(f"❌ Discord chart send failed: {e}")
            return False
    
    def notify_buy(self, symbol: str, price: float, qty: int, ai_confidence: float) -> bool:
        """Notify on BUY order."""
        return self.send_message(
            f"🟢 BUY SIGNAL: {symbol}",
            {
                "Price": f"${price:.2f}",
                "Quantity": qty,
                "AI Confidence": f"{ai_confidence:.0%}",
                "Time": datetime.now().strftime("%H:%M:%S UTC"),
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
                "Time": datetime.now().strftime("%H:%M:%S UTC"),
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
                "Date": datetime.now().strftime("%Y-%m-%d UTC"),
            },
            color=3447003  # Blue
        )
    
    def notify_drift_detected(self, symbol: str, current_wr: float, baseline_wr: float, new_min_confidence: float) -> bool:
        """Notify when model drift is detected on a symbol."""
        if not self.enabled:
            return False
        
        dedupe_key = f"drift:{symbol}:{current_wr:.0%}:{new_min_confidence:.0%}"
        if self._is_rate_limited(dedupe_key, self.warning_cooldown_sec):
            return False
        
        return self.send_message(
            f"⚠️ Model Drift Detected: {symbol}",
            {
                "Current Win Rate": f"{current_wr:.1%}",
                "Baseline Win Rate": f"{baseline_wr:.1%}",
                "Δ Win Rate": f"{(current_wr - baseline_wr):+.1%}",
                "New Min AI Confidence": f"{new_min_confidence:.0%}",
                "Action": "Risk scaling reduced",
            },
            color=15158332  # Orange
        )
    
    def notify_concentration_limit_hit(self, symbol: str, desired_qty: int, allowed_qty: int, reason: str) -> bool:
        """Notify when position concentration limit is hit."""
        if not self.enabled:
            return False
        
        dedupe_key = f"concentration:{symbol}:{reason}"
        if self._is_rate_limited(dedupe_key, self.warning_cooldown_sec):
            return False
        
        return self.send_message(
            f"⚠️ Concentration Limit Hit: {symbol}",
            {
                "Desired Qty": desired_qty,
                "Allowed Qty": allowed_qty,
                "Limited By": reason,
                "Action": f"Order reduced from {desired_qty} to {allowed_qty}",
            },
            color=15158332  # Orange
        )
    
    def notify_max_positions_reached(self, current: int, max_allowed: int) -> bool:
        """Notify when max open positions limit reached."""
        if not self.enabled:
            return False
        
        dedupe_key = f"max_positions:{current}:{max_allowed}"
        if self._is_rate_limited(dedupe_key, 600):  # 10-min cooldown for this
            return False
        
        return self.send_message(
            f"🛑 Max Open Positions Reached",
            {
                "Current Positions": current,
                "Max Allowed": max_allowed,
                "Action": "No new entries until position closed",
            },
            color=15158332  # Orange
        )
    
    def notify_warning(self, message: str, details: dict = None) -> bool:
        """Send warning/error alert."""
        if details is None:
            details = {}

        dedupe_key = f"warning:{message}:{json.dumps(details, sort_keys=True, default=str)}"
        if self._is_rate_limited(dedupe_key, self.warning_cooldown_sec):
            return False
        
        return self.send_message(
            f"⚠️ {message}",
            details,
            color=15158332  # Orange
        )
    
    def notify_error(self, message: str, details: dict = None) -> bool:
        """Send critical error alert."""
        if details is None:
            details = {}

        dedupe_key = f"error:{message}:{json.dumps(details, sort_keys=True, default=str)}"
        if self._is_rate_limited(dedupe_key, self.error_cooldown_sec):
            return False
        
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
