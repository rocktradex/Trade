"""
what changed:
- Added a lightweight news risk agent that polls RSS feeds, scores headline risk, and classifies the environment as GREEN, YELLOW, or RED.

why:
- The trader should avoid treating high-impact headline windows like normal market conditions and reduce or block risk when the news tape turns dangerous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from xml.etree import ElementTree

import requests


@dataclass
class NewsAssessment:
    status: str
    score: int
    block_new_entries: bool
    size_multiplier: float
    reason: str
    headlines: list[str]
    crypto_score: int = 0
    macro_score: int = 0
    systemic_score: int = 0
    max_headline_score: int = 0


class NewsAgent:
    def __init__(self, config: dict[str, Any], logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(config.get("enabled", True))
        self.feeds = list(config.get("feeds", []))
        self.lookback_minutes = int(config.get("lookback_minutes", 180))
        self.request_timeout = int(config.get("request_timeout_seconds", 10))
        self.cache_minutes = int(config.get("cache_minutes", 5))
        self.yellow_threshold = int(config.get("yellow_threshold", 3))
        self.red_threshold = int(config.get("red_threshold", 6))
        self.red_headline_threshold = int(config.get("red_headline_threshold", 6))
        self.macro_red_threshold = int(config.get("macro_red_threshold", 6))
        self.systemic_red_threshold = int(config.get("systemic_red_threshold", 6))
        self.yellow_size_multiplier = float(config.get("yellow_size_multiplier", 0.5))
        self.red_size_multiplier = float(config.get("red_size_multiplier", 0.0))
        self.crypto_keyword_weights = {
            key.lower(): int(value)
            for key, value in config.get("crypto_keyword_weights", {}).items()
        }
        self.macro_keyword_weights = {
            key.lower(): int(value)
            for key, value in config.get("macro_keyword_weights", {}).items()
        }
        self.systemic_keyword_weights = {
            key.lower(): int(value)
            for key, value in config.get("systemic_keyword_weights", {}).items()
        }
        all_keywords = (
            set(self.crypto_keyword_weights)
            | set(self.macro_keyword_weights)
            | set(self.systemic_keyword_weights)
        )
        self._keyword_patterns = {
            keyword: self._build_keyword_pattern(keyword)
            for keyword in all_keywords
        }
        self.symbol_keywords = {
            symbol: [token.lower() for token in values]
            for symbol, values in config.get("symbol_keywords", {}).items()
        }
        self._cache_until: datetime | None = None
        self._cached_items: list[dict[str, Any]] = []

    def assess(self, symbols: list[str]) -> NewsAssessment:
        if not self.enabled or not self.feeds:
            return NewsAssessment(
                status="GREEN",
                score=0,
                block_new_entries=False,
                size_multiplier=1.0,
                reason="News filter disabled.",
                headlines=[],
            )

        items = self._fetch_recent_items()
        if not items:
            return NewsAssessment(
                status="GREEN",
                score=0,
                block_new_entries=False,
                size_multiplier=1.0,
                reason="No recent high-impact headlines detected.",
                headlines=[],
            )

        relevant_tokens = set()
        for symbol in symbols:
            relevant_tokens.update(self.symbol_keywords.get(symbol, [symbol.lower()]))

        scored_items: list[tuple[int, str]] = []
        total_score = 0
        macro_score = 0
        systemic_score = 0
        max_headline_score = 0
        for item in items:
            headline = f"{item.get('title', '')} {item.get('summary', '')}".strip()
            lowered = headline.lower()
            if not any(token in lowered for token in relevant_tokens):
                continue
            crypto_score = self._score_keyword_group(lowered, self.crypto_keyword_weights)
            item_macro_score = self._score_keyword_group(lowered, self.macro_keyword_weights)
            item_systemic_score = self._score_keyword_group(lowered, self.systemic_keyword_weights)
            item_score = crypto_score + item_macro_score + item_systemic_score
            if item_score <= 0:
                continue
            total_score += item_score
            macro_score += item_macro_score
            systemic_score += item_systemic_score
            max_headline_score = max(max_headline_score, item_score)
            scored_items.append((item_score, item.get("title", "Untitled headline")))

        scored_items.sort(key=lambda row: row[0], reverse=True)
        top_headlines = [f"[{score}] {title}" for score, title in scored_items[:3]]

        if (
            max_headline_score >= self.red_headline_threshold
            or macro_score >= self.macro_red_threshold
            or systemic_score >= self.systemic_red_threshold
        ):
            return NewsAssessment(
                status="RED",
                score=total_score,
                block_new_entries=True,
                size_multiplier=self.red_size_multiplier,
                reason=(
                    f"High-impact macro/systemic news risk detected. "
                    f"headline={max_headline_score}, macro={macro_score}, systemic={systemic_score}."
                ),
                headlines=top_headlines,
                crypto_score=total_score - macro_score - systemic_score,
                macro_score=macro_score,
                systemic_score=systemic_score,
                max_headline_score=max_headline_score,
            )
        if total_score >= self.yellow_threshold:
            return NewsAssessment(
                status="YELLOW",
                score=total_score,
                block_new_entries=False,
                size_multiplier=self.yellow_size_multiplier,
                reason=(
                    f"Caution mode: elevated headline risk. "
                    f"headline={max_headline_score}, macro={macro_score}, systemic={systemic_score}."
                ),
                headlines=top_headlines,
                crypto_score=total_score - macro_score - systemic_score,
                macro_score=macro_score,
                systemic_score=systemic_score,
                max_headline_score=max_headline_score,
            )
        return NewsAssessment(
            status="GREEN",
            score=total_score,
            block_new_entries=False,
            size_multiplier=1.0,
            reason="Headline tape is calm enough for normal sizing.",
            headlines=top_headlines,
            crypto_score=total_score - macro_score - systemic_score,
            macro_score=macro_score,
            systemic_score=systemic_score,
            max_headline_score=max_headline_score,
        )

    def _fetch_recent_items(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if self._cache_until and now < self._cache_until:
            return self._cached_items

        cutoff = now - timedelta(minutes=self.lookback_minutes)
        items: list[dict[str, Any]] = []
        for feed_url in self.feeds:
            try:
                response = requests.get(feed_url, timeout=self.request_timeout)
                response.raise_for_status()
                items.extend(self._parse_feed(response.text, cutoff))
            except Exception as exc:
                self.logger.warning("News feed fetch failed for %s: %s", feed_url, exc)

        self._cached_items = items
        self._cache_until = now + timedelta(minutes=self.cache_minutes)
        return items

    def _parse_feed(self, xml_text: str, cutoff: datetime) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        items: list[dict[str, Any]] = []
        for entry in root.findall(".//item"):
            published = self._extract_item_time(entry)
            if published is None or published < cutoff:
                continue
            items.append(
                {
                    "title": (entry.findtext("title") or "").strip(),
                    "summary": (entry.findtext("description") or "").strip(),
                    "published": published.isoformat(),
                }
            )
        for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            published = self._extract_atom_time(entry)
            if published is None or published < cutoff:
                continue
            items.append(
                {
                    "title": (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip(),
                    "summary": (entry.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip(),
                    "published": published.isoformat(),
                }
            )
        return items

    def _extract_item_time(self, entry: ElementTree.Element) -> datetime | None:
        raw = entry.findtext("pubDate") or entry.findtext("published") or entry.findtext("updated")
        return self._parse_datetime(raw)

    def _extract_atom_time(self, entry: ElementTree.Element) -> datetime | None:
        raw = (
            entry.findtext("{http://www.w3.org/2005/Atom}updated")
            or entry.findtext("{http://www.w3.org/2005/Atom}published")
        )
        return self._parse_datetime(raw)

    def _parse_datetime(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _build_keyword_pattern(self, keyword: str) -> re.Pattern[str]:
        escaped = re.escape(keyword)
        if " " in keyword:
            escaped = escaped.replace(r"\ ", r"\s+")
            return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)

    def _score_keyword_group(self, text: str, weights: dict[str, int]) -> int:
        return sum(
            weight
            for keyword, weight in weights.items()
            if self._keyword_patterns[keyword].search(text)
        )
