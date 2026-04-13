"""Discord notification system rebuilt from scratch.

Design goals:
- One cohesive report message with a single attached dashboard image.
- No external chart service dependency.
- Rate-limited operational alerts to avoid channel spam.
"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont


ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
if ROOT_ENV.exists():
    load_dotenv(dotenv_path=ROOT_ENV, override=True)
else:
    load_dotenv(override=True)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class DiscordAlerts:
    """Clean Discord notifier with local dashboard rendering."""

    def __init__(self) -> None:
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self.enabled = bool(self.webhook_url)
        self.graph_mention = os.getenv("DISCORD_HOURLY_MENTION", "").strip()
        self.warning_cooldown_sec = int(os.getenv("DISCORD_WARNING_COOLDOWN_SEC", "300"))
        self.error_cooldown_sec = int(os.getenv("DISCORD_ERROR_COOLDOWN_SEC", "900"))
        self._last_sent_by_key: dict[str, datetime] = {}
        self._tested = False

        if self.enabled:
            print("Discord notifications enabled")
            self._test_webhook_connection()
        else:
            print("Discord notifications disabled (set DISCORD_WEBHOOK_URL in .env)")

    def _test_webhook_connection(self) -> None:
        if self._tested or not self.enabled:
            return
        ok = self.send_message("Webhook test", {"status": "connected", "time": datetime.now(UTC).strftime("%H:%M:%S UTC")})
        if ok:
            print("Discord webhook verified")
            self._tested = True
        else:
            print("Discord webhook test failed")

    def _is_rate_limited(self, key: str, cooldown_sec: int) -> bool:
        if cooldown_sec <= 0:
            return False
        now = datetime.now(UTC)
        last = self._last_sent_by_key.get(key)
        if last and (now - last).total_seconds() < cooldown_sec:
            return True
        self._last_sent_by_key[key] = now
        return False

    def _post_json(self, payload: dict, timeout: int = 8) -> bool:
        if not self.enabled:
            return False
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=timeout)
            return response.status_code in (200, 204)
        except Exception as exc:
            print(f"Discord send failed: {exc}")
            return False

    def _send_embed(self, title: str, fields: dict, color: int = 3447003, content: str = "") -> bool:
        embed = {
            "title": title,
            "color": color,
            "fields": [{"name": str(k), "value": str(v), "inline": True} for k, v in fields.items()],
            "timestamp": _utc_now_iso(),
            "footer": {"text": "Trading Bot | UTC"},
        }
        payload = {
            "content": content,
            "embeds": [embed],
            "allowed_mentions": {"parse": ["users"] if content else []},
        }
        return self._post_json(payload)

    def send_message(self, title: str, fields: dict, color: int = 3447003) -> bool:
        return self._send_embed(title=title, fields=fields, color=color)

    def _render_dashboard_image(
        self,
        title: str,
        summary_fields: dict,
        chart_panels: list[tuple[str, list[float]]],
        output_path: Path,
    ) -> Path:
        width, height = 1600, 980
        image = Image.new("RGB", (width, height), (14, 18, 28))
        draw = ImageDraw.Draw(image)
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

        # Header
        draw.rectangle((0, 0, width, 90), fill=(24, 30, 46))
        draw.text((20, 18), title, fill=(230, 236, 244), font=font_title)
        draw.text((20, 54), datetime.now(UTC).strftime("Generated %Y-%m-%d %H:%M UTC"), fill=(160, 172, 192), font=font_body)

        # Summary cards
        cards_top = 110
        cards_left = 20
        cards_w = (width - 40) // 3
        cards_h = 110
        items = list(summary_fields.items())
        for idx, (name, value) in enumerate(items[:6]):
            row = idx // 3
            col = idx % 3
            x0 = cards_left + col * cards_w
            y0 = cards_top + row * (cards_h + 12)
            x1 = x0 + cards_w - 10
            y1 = y0 + cards_h
            draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(28, 36, 54), outline=(44, 58, 84), width=1)
            draw.text((x0 + 14, y0 + 18), str(name), fill=(150, 170, 205), font=font_body)
            draw.text((x0 + 14, y0 + 56), str(value), fill=(238, 244, 252), font=font_title)

        # Chart panels (2x2)
        panel_data = chart_panels[:4]
        chart_top = 360
        panel_gap = 16
        panel_w = (width - 40 - panel_gap) // 2
        panel_h = (height - chart_top - 30 - panel_gap) // 2

        for i, (panel_title, values) in enumerate(panel_data):
            row = i // 2
            col = i % 2
            x0 = 20 + col * (panel_w + panel_gap)
            y0 = chart_top + row * (panel_h + panel_gap)
            x1 = x0 + panel_w
            y1 = y0 + panel_h
            draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(24, 31, 45), outline=(44, 58, 84), width=1)
            draw.text((x0 + 12, y0 + 10), panel_title, fill=(220, 228, 244), font=font_body)

            if not values:
                continue

            plot_x0, plot_y0 = x0 + 12, y0 + 34
            plot_x1, plot_y1 = x1 - 12, y1 - 12
            draw.rectangle((plot_x0, plot_y0, plot_x1, plot_y1), outline=(54, 70, 100), width=1)

            vmin = min(values)
            vmax = max(values)
            if vmin == vmax:
                vmin -= 1.0
                vmax += 1.0

            n = len(values)
            pts: list[tuple[float, float]] = []
            for j, value in enumerate(values):
                x = plot_x0 + (j / max(1, n - 1)) * (plot_x1 - plot_x0)
                y = plot_y1 - ((value - vmin) / (vmax - vmin)) * (plot_y1 - plot_y0)
                pts.append((x, y))

            draw.line(pts, fill=(88, 180, 255), width=3)
            draw.text((plot_x0, plot_y0 + 2), f"max {vmax:.2f}", fill=(130, 160, 210), font=font_body)
            draw.text((plot_x0, plot_y1 - 14), f"min {vmin:.2f}", fill=(130, 160, 210), font=font_body)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG")
        return output_path

    def send_dashboard(
        self,
        title: str,
        summary_fields: dict,
        chart_panels: list[tuple[str, list[float]]] | None = None,
        color: int = 3447003,
        description: str = "",
        mention_text: str = "",
    ) -> bool:
        """Send one dashboard message rendered from local chart panels."""
        if not self.enabled:
            return False

        panels = chart_panels or []
        if not panels:
            return self._send_embed(title=title, fields=summary_fields, color=color, content=mention_text)

        with tempfile.TemporaryDirectory(prefix="discord_dash_") as tmpdir:
            img_path = Path(tmpdir) / "dashboard.png"
            self._render_dashboard_image(title, summary_fields, panels, img_path)
            return self.send_file(
                title=title,
                fields={"Summary": description or "Dashboard generated"},
                file_path=str(img_path),
                filename="dashboard.png",
                color=color,
                content=mention_text,
            )

    def send_file(
        self,
        title: str,
        fields: dict,
        file_path: str,
        filename: str | None = None,
        color: int = 3447003,
        content: str = "",
    ) -> bool:
        if not self.enabled:
            return False

        attachment_name = filename or Path(file_path).name
        mime_type, _ = mimetypes.guess_type(attachment_name)
        if not mime_type:
            mime_type = "application/octet-stream"

        embed = {
            "title": title,
            "color": color,
            "fields": [{"name": str(k), "value": str(v), "inline": True} for k, v in fields.items()],
            "timestamp": _utc_now_iso(),
            "image": {"url": f"attachment://{attachment_name}"},
            "footer": {"text": "Trading Bot | UTC"},
        }

        payload = {
            "content": content.strip() if content else "",
            "embeds": [embed],
            "attachments": [{"id": 0, "filename": attachment_name}],
            "allowed_mentions": {"parse": ["users"] if content else []},
        }

        try:
            with open(file_path, "rb") as fh:
                files = {"files[0]": (attachment_name, fh, mime_type)}
                response = requests.post(
                    self.webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                    timeout=15,
                )
            return response.status_code in (200, 204)
        except Exception as exc:
            print(f"Discord file send failed: {exc}")
            return False

    def notify_buy(self, symbol: str, price: float, qty: int, ai_confidence: float) -> bool:
        return self.send_message(
            title=f"Trade opened: {symbol}",
            fields={
                "side": "BUY",
                "price": f"${price:.2f}",
                "qty": qty,
                "ai_confidence": f"{ai_confidence:.0%}",
            },
            color=3066993,
        )

    def notify_sell(self, symbol: str, entry: float, exit_price: float, qty: int, pnl_pct: float, reason: str) -> bool:
        color = 3066993 if pnl_pct >= 0 else 15158332
        return self.send_message(
            title=f"Trade closed: {symbol}",
            fields={
                "reason": reason,
                "entry": f"${entry:.2f}",
                "exit": f"${exit_price:.2f}",
                "qty": qty,
                "pnl": f"{pnl_pct:+.2f}%",
            },
            color=color,
        )

    def notify_daily_summary(self, summary: dict) -> bool:
        return self.send_message(
            title="Daily trading summary",
            fields={
                "trades": summary.get("trades", 0),
                "wins": summary.get("wins", 0),
                "win_rate": summary.get("win_rate", "0%"),
                "pnl": summary.get("pnl", "0%"),
            },
            color=3447003,
        )

    def notify_drift_detected(self, symbol: str, current_wr: float, baseline_wr: float, new_min_confidence: float) -> bool:
        key = f"drift:{symbol}:{current_wr:.3f}:{new_min_confidence:.3f}"
        if self._is_rate_limited(key, self.warning_cooldown_sec):
            return False
        return self.send_message(
            title=f"Model drift detected: {symbol}",
            fields={
                "current_wr": f"{current_wr:.1%}",
                "baseline_wr": f"{baseline_wr:.1%}",
                "delta": f"{(current_wr - baseline_wr):+.1%}",
                "new_min_conf": f"{new_min_confidence:.0%}",
            },
            color=15158332,
        )

    def notify_concentration_limit_hit(self, symbol: str, desired_qty: int, allowed_qty: int, reason: str) -> bool:
        key = f"concentration:{symbol}:{reason}"
        if self._is_rate_limited(key, self.warning_cooldown_sec):
            return False
        return self.send_message(
            title=f"Concentration limit hit: {symbol}",
            fields={
                "desired_qty": desired_qty,
                "allowed_qty": allowed_qty,
                "reason": reason,
            },
            color=15158332,
        )

    def notify_max_positions_reached(self, current: int, max_allowed: int) -> bool:
        key = f"max_positions:{current}:{max_allowed}"
        if self._is_rate_limited(key, 600):
            return False
        return self.send_message(
            title="Max open positions reached",
            fields={"current": current, "max_allowed": max_allowed},
            color=15158332,
        )

    def notify_warning(self, message: str, details: dict | None = None) -> bool:
        details = details or {}
        key = f"warning:{message}:{json.dumps(details, sort_keys=True, default=str)}"
        if self._is_rate_limited(key, self.warning_cooldown_sec):
            return False
        return self.send_message(title=f"Warning: {message}", fields=details, color=15158332)

    def notify_error(self, message: str, details: dict | None = None) -> bool:
        details = details or {}
        key = f"error:{message}:{json.dumps(details, sort_keys=True, default=str)}"
        if self._is_rate_limited(key, self.error_cooldown_sec):
            return False
        return self.send_message(title=f"Error: {message}", fields=details, color=10038562)


# Global singleton
discord = DiscordAlerts()


def test_discord() -> bool:
    if not discord.enabled:
        print("DISCORD_WEBHOOK_URL not set in .env")
        return False
    print("Testing Discord webhook...")
    ok = discord.send_message("Test message", {"status": "ok", "timestamp": _utc_now_iso()})
    print("Discord webhook working" if ok else "Discord webhook failed")
    return ok
