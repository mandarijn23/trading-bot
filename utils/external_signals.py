"""External signal ingestion and entry gating for stock trading.

This module keeps external data optional and fail-safe:
- If feeds are unavailable, it returns a neutral snapshot.
- Entry blocking only happens when confidence is sufficient and risk is clear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, Dict, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


@dataclass
class ExternalSignalSnapshot:
    """Unified, normalized external-signal view for a symbol."""

    symbol: str
    sentiment_score: float = 0.0  # -1.0 (very negative) to +1.0 (very positive)
    catalyst_score: float = 0.0  # 0.0 to 1.0
    event_risk: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0  # 0.0 to 1.0
    mode: str = "neutral"
    source_status: Dict[str, str] = field(default_factory=dict)


class ExternalSignalMonitor:
    """Collect external signals (news, X/Twitter, events) with safe fallbacks."""

    POSITIVE_WORDS = {
        "beat",
        "beats",
        "surge",
        "upgraded",
        "growth",
        "strong",
        "bullish",
        "record",
        "approval",
        "win",
        "breakout",
    }
    NEGATIVE_WORDS = {
        "miss",
        "misses",
        "downgrade",
        "downgraded",
        "lawsuit",
        "fraud",
        "weak",
        "bearish",
        "cut",
        "layoff",
        "drop",
    }

    HIGH_IMPACT_EVENTS = {
        "fomc",
        "fed",
        "cpi",
        "nfp",
        "inflation",
        "interest rate",
        "rate decision",
        "powell",
    }

    def __init__(self, config: Any, logger: Optional[Any] = None):
        self.config = config
        self.logger = logger
        self.enabled = bool(getattr(config, "external_signals_enabled", False))
        self.cache_ttl = int(getattr(config, "external_signal_cache_ttl", 300))
        self.timeout_sec = float(getattr(config, "external_signal_timeout_sec", 3.0))

        self.min_confidence = float(getattr(config, "external_signal_min_confidence", 0.35))
        self.min_sentiment = float(getattr(config, "external_sentiment_min", -0.35))
        self.min_catalyst = float(getattr(config, "external_catalyst_min", 0.2))
        self.max_event_risk = float(getattr(config, "external_event_risk_max", 0.85))

        self.news_api_key = str(getattr(config, "news_api_key", "") or "").strip()
        self.twitter_bearer_token = str(getattr(config, "twitter_bearer_token", "") or "").strip()
        self.economic_calendar_api_key = str(getattr(config, "economic_calendar_api_key", "") or "").strip()
        self.external_signal_file = str(getattr(config, "external_signal_file", "logs/external_signals.json") or "logs/external_signals.json")

        self._cache: Dict[str, tuple[float, ExternalSignalSnapshot]] = {}

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    def _log_debug(self, msg: str) -> None:
        if self.logger:
            self.logger.debug(msg)

    def _log_warning(self, msg: str) -> None:
        if self.logger:
            self.logger.warning(msg)

    def _neutral(self, symbol: str, status: Optional[Dict[str, str]] = None) -> ExternalSignalSnapshot:
        return ExternalSignalSnapshot(
            symbol=symbol,
            sentiment_score=0.0,
            catalyst_score=0.0,
            event_risk=0.0,
            confidence=0.0,
            mode="neutral",
            source_status=status or {},
        )

    def get_snapshot(self, symbol: str) -> ExternalSignalSnapshot:
        """Return a cached or freshly computed snapshot for a symbol."""
        symbol = str(symbol).upper().strip()
        if not self.enabled:
            return self._neutral(symbol, {"external": "disabled"})

        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached[0]) <= self.cache_ttl:
            return cached[1]

        snapshot = self._build_snapshot(symbol)
        self._cache[symbol] = (now, snapshot)
        return snapshot

    def allow_entry(self, snapshot: ExternalSignalSnapshot) -> tuple[bool, str]:
        """Balanced gate: require confidence before external signals can block entries."""
        if not self.enabled:
            return True, "external signals disabled"

        if snapshot.confidence < self.min_confidence:
            return True, "external confidence too low to block"

        if snapshot.event_risk > self.max_event_risk:
            return False, (
                f"event risk too high ({snapshot.event_risk:.2f} > {self.max_event_risk:.2f})"
            )

        if snapshot.sentiment_score < self.min_sentiment and snapshot.catalyst_score < self.min_catalyst:
            return False, (
                "external sentiment/catalyst below thresholds "
                f"(sentiment={snapshot.sentiment_score:.2f}, catalyst={snapshot.catalyst_score:.2f})"
            )

        return True, "external signal gate passed"

    def _build_snapshot(self, symbol: str) -> ExternalSignalSnapshot:
        status: Dict[str, str] = {}
        sentiment_parts = []
        catalyst_parts = []
        confidence_parts = []

        # Local file feed for deterministic integration/testing.
        local = self._load_local_signal(symbol)
        if local is not None:
            status["file"] = "ok"
            sentiment_parts.append(float(local.get("sentiment", 0.0)))
            catalyst_parts.append(float(local.get("catalyst", 0.0)))
            confidence_parts.append(float(local.get("confidence", 0.5)))
        else:
            status["file"] = "missing"

        news = self._fetch_news_signal(symbol)
        if news is not None:
            status["news"] = "ok"
            sentiment_parts.append(float(news["sentiment"]))
            catalyst_parts.append(float(news["catalyst"]))
            confidence_parts.append(float(news["confidence"]))
        else:
            status["news"] = "unavailable"

        social = self._fetch_x_signal(symbol)
        if social is not None:
            status["x"] = "ok"
            sentiment_parts.append(float(social["sentiment"]))
            catalyst_parts.append(float(social["catalyst"]))
            confidence_parts.append(float(social["confidence"]))
        else:
            status["x"] = "unavailable"

        event_risk = self._fetch_event_risk()
        if event_risk is None:
            status["events"] = "unavailable"
            event_risk = 0.0
        else:
            status["events"] = "ok"

        if not sentiment_parts:
            return self._neutral(symbol, status)

        sentiment = self._clip(sum(sentiment_parts) / len(sentiment_parts), -1.0, 1.0)
        catalyst = self._clip(sum(catalyst_parts) / len(catalyst_parts), 0.0, 1.0)
        confidence = self._clip(sum(confidence_parts) / len(confidence_parts), 0.0, 1.0)

        mode = "active"
        if confidence < self.min_confidence:
            mode = "degraded"

        return ExternalSignalSnapshot(
            symbol=symbol,
            sentiment_score=sentiment,
            catalyst_score=catalyst,
            event_risk=self._clip(event_risk, 0.0, 1.0),
            confidence=confidence,
            mode=mode,
            source_status=status,
        )

    def _fetch_json(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        try:
            req = Request(url=url, headers=headers or {}, method="GET")
            with urlopen(req, timeout=self.timeout_sec) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
            return json.loads(payload)
        except Exception as exc:
            self._log_debug(f"External fetch failed: {exc}")
            return None

    def _load_local_signal(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self.external_signal_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            item = payload.get(symbol)
            if not isinstance(item, dict):
                return None
            return item
        except FileNotFoundError:
            return None
        except Exception as exc:
            self._log_debug(f"Local external signal parse failed: {exc}")
            return None

    def _score_text_sentiment(self, text: str) -> float:
        text = (text or "").lower()
        if not text:
            return 0.0

        tokens = text.replace("/", " ").replace("-", " ").split()
        pos = sum(1 for token in tokens if token in self.POSITIVE_WORDS)
        neg = sum(1 for token in tokens if token in self.NEGATIVE_WORDS)

        denom = max(pos + neg, 1)
        return self._clip((pos - neg) / denom, -1.0, 1.0)

    def _fetch_news_signal(self, symbol: str) -> Optional[Dict[str, float]]:
        if not self.news_api_key:
            return None

        query = quote_plus(f"{symbol} stock")
        url = (
            "https://newsapi.org/v2/everything"
            f"?q={query}&language=en&pageSize=20&sortBy=publishedAt&apiKey={self.news_api_key}"
        )
        data = self._fetch_json(url)
        if not data or "articles" not in data:
            return None

        articles = data.get("articles", [])
        if not isinstance(articles, list) or not articles:
            return None

        sentiment_scores = []
        catalyst_hits = 0
        for article in articles[:20]:
            title = str((article or {}).get("title", ""))
            desc = str((article or {}).get("description", ""))
            text = f"{title} {desc}".strip()
            sentiment_scores.append(self._score_text_sentiment(text))

            low = text.lower()
            if any(word in low for word in ("earnings", "guidance", "upgrade", "downgrade", "sec", "acquisition")):
                catalyst_hits += 1

        sentiment = sum(sentiment_scores) / max(len(sentiment_scores), 1)
        catalyst = self._clip(catalyst_hits / max(len(articles[:20]), 1), 0.0, 1.0)
        confidence = self._clip(min(1.0, len(articles) / 15.0), 0.15, 0.9)
        return {"sentiment": sentiment, "catalyst": catalyst, "confidence": confidence}

    def _fetch_x_signal(self, symbol: str) -> Optional[Dict[str, float]]:
        if not self.twitter_bearer_token:
            return None

        query = quote_plus(f"${symbol} lang:en -is:retweet")
        url = (
            "https://api.twitter.com/2/tweets/search/recent"
            f"?query={query}&max_results=25&tweet.fields=public_metrics,created_at"
        )
        headers = {"Authorization": f"Bearer {self.twitter_bearer_token}"}
        data = self._fetch_json(url, headers=headers)
        if not data or "data" not in data:
            return None

        tweets = data.get("data", [])
        if not isinstance(tweets, list) or not tweets:
            return None

        sentiment_scores = []
        catalyst_total = 0.0

        for item in tweets[:25]:
            text = str((item or {}).get("text", ""))
            sentiment_scores.append(self._score_text_sentiment(text))

            metrics = (item or {}).get("public_metrics") or {}
            likes = float(metrics.get("like_count", 0.0))
            reposts = float(metrics.get("retweet_count", 0.0))
            replies = float(metrics.get("reply_count", 0.0))
            catalyst_total += min(1.0, (likes + (2.0 * reposts) + replies) / 500.0)

        sentiment = sum(sentiment_scores) / max(len(sentiment_scores), 1)
        catalyst = self._clip(catalyst_total / max(len(tweets[:25]), 1), 0.0, 1.0)
        confidence = self._clip(min(1.0, len(tweets) / 20.0), 0.15, 0.85)
        return {"sentiment": sentiment, "catalyst": catalyst, "confidence": confidence}

    def _fetch_event_risk(self) -> Optional[float]:
        """Fetch macro-event risk from a lightweight economic calendar endpoint."""
        if not self.economic_calendar_api_key:
            return None

        start = datetime.now(timezone.utc).date().isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

        # Financial Modeling Prep economic calendar API format.
        url = (
            "https://financialmodelingprep.com/api/v3/economic_calendar"
            f"?from={start}&to={end}&apikey={self.economic_calendar_api_key}"
        )

        data = self._fetch_json(url)
        if not isinstance(data, list):
            return None

        high = 0
        medium = 0
        for event in data[:200]:
            if not isinstance(event, dict):
                continue
            title = str(event.get("event", "")).lower()
            impact = str(event.get("impact", "")).lower()

            if any(k in title for k in self.HIGH_IMPACT_EVENTS):
                high += 1
                continue

            if "high" in impact:
                high += 1
            elif "medium" in impact:
                medium += 1

        risk = min(1.0, (0.25 * medium) + (0.5 * high))
        return self._clip(risk, 0.0, 1.0)
