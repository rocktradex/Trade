"""
what changed:
- Expanded the decision engine into a fuller trading desk with multiple specialist agents, including an order book agent.

why:
- The trader should act like a real desk where momentum, structure, volatility, regime, order flow, and risk specialists all vote before capital is deployed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from market_data import MarketSnapshot
from openai import OpenAI


@dataclass
class AgentVote:
    agent_name: str
    action: str
    score: float
    reason: str


@dataclass
class SignalDecision:
    symbol: str
    action: str
    confidence: float
    reason: str
    stop_loss_pct: float
    take_profit_pct: float
    entry_price: float
    votes: list[AgentVote]


class TradingAIAgent:
    def __init__(self, config: dict[str, Any], logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.mode = config.get("mode", "openai_with_fallback")
        self.model = config.get("model", "gpt-5")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.openai_enabled = self.client is not None
        self.consensus_threshold = float(config.get("consensus_threshold", 0.55))
        self.orderbook_imbalance_threshold = float(config.get("orderbook_imbalance_threshold", 0.12))
        self.liquidity_trap_threshold = float(config.get("liquidity_trap_threshold", 0.35))

    def decide(self, snapshot: MarketSnapshot) -> SignalDecision:
        base_decision = self._director_decide(snapshot)
        if self.mode == "openai_with_fallback" and self.openai_enabled and self.client is not None:
            try:
                return self._openai_decide(snapshot, base_decision)
            except Exception as exc:
                self.logger.warning("OpenAI decision failed for %s: %s. Falling back to local model.", snapshot.symbol, exc)
                error_text = str(exc).lower()
                if "invalid_api_key" in error_text or "incorrect api key" in error_text:
                    self.openai_enabled = False
                    self.logger.warning("OpenAI integration disabled until restart because the API key is invalid.")
        return base_decision

    def _director_decide(self, snapshot: MarketSnapshot) -> SignalDecision:
        votes = [
            self._trend_agent(snapshot),
            self._entry_agent(snapshot),
            self._volatility_agent(snapshot),
            self._momentum_agent(snapshot),
            self._regime_agent(snapshot),
            self._orderbook_agent(snapshot),
            self._liquidity_trap_agent(snapshot),
            self._risk_agent(snapshot),
        ]
        long_weight = sum(vote.score for vote in votes if vote.action == "LONG")
        short_weight = sum(vote.score for vote in votes if vote.action == "SHORT")
        total_weight = sum(vote.score for vote in votes)
        winning_weight = max(long_weight, short_weight)
        confidence = (winning_weight / total_weight) if total_weight else 0.0

        action = "FLAT"
        if confidence >= self.consensus_threshold:
            if long_weight > short_weight:
                action = "LONG"
            elif short_weight > long_weight:
                action = "SHORT"

        stop_loss_pct = max(
            self.config["min_stop_loss_pct"],
            snapshot.atr_pct_1m * self.config["sl_atr_multiplier"],
        )
        take_profit_pct = stop_loss_pct * self.config["risk_reward_ratio"]

        if confidence < self.config["min_confidence"]:
            action = "FLAT"

        vote_summary = "; ".join(
            f"{vote.agent_name}:{vote.action}({vote.score:.2f})"
            for vote in votes
        )
        reason = f"Director consensus={confidence:.2f} | {vote_summary}"

        return SignalDecision(
            symbol=snapshot.symbol,
            action=action,
            confidence=confidence,
            reason=reason,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            entry_price=snapshot.last_price,
            votes=votes,
        )

    def _trend_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        score = 0
        if snapshot.ema_fast_5m > snapshot.ema_slow_5m:
            score += 1
        elif snapshot.ema_fast_5m < snapshot.ema_slow_5m:
            score -= 1
        if snapshot.rsi_5m > 55:
            score += 1
        elif snapshot.rsi_5m < 45:
            score -= 1
        action = "FLAT"
        if score >= 2:
            action = "LONG"
        elif score <= -2:
            action = "SHORT"
        return AgentVote(
            agent_name="TrendAgent",
            action=action,
            score=0.40,
            reason=f"5m ema/rsi score={score}",
        )

    def _entry_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        score = 0
        if snapshot.ema_fast_1m > snapshot.ema_slow_1m:
            score += 1
        elif snapshot.ema_fast_1m < snapshot.ema_slow_1m:
            score -= 1
        if snapshot.rsi_1m > 55:
            score += 1
        elif snapshot.rsi_1m < 45:
            score -= 1
        if snapshot.last_candle_change_pct > 0.001:
            score += 1
        elif snapshot.last_candle_change_pct < -0.001:
            score -= 1
        action = "FLAT"
        if score >= 2:
            action = "LONG"
        elif score <= -2:
            action = "SHORT"
        return AgentVote(
            agent_name="EntryAgent",
            action=action,
            score=0.35,
            reason=f"1m timing score={score}",
        )

    def _volatility_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        action = "FLAT"
        reason = f"atr%={snapshot.atr_pct_1m:.4f} neutral"
        if 0.0008 <= snapshot.atr_pct_1m <= 0.015:
            if snapshot.rsi_1m >= 52 and snapshot.rsi_5m >= 52:
                action = "LONG"
                reason = f"atr%={snapshot.atr_pct_1m:.4f} supports long"
            elif snapshot.rsi_1m <= 48 and snapshot.rsi_5m <= 48:
                action = "SHORT"
                reason = f"atr%={snapshot.atr_pct_1m:.4f} supports short"
        return AgentVote(
            agent_name="VolatilityAgent",
            action=action,
            score=0.18,
            reason=reason,
        )

    def _momentum_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        action = "FLAT"
        score_hint = 0
        if snapshot.rsi_1m >= 60 and snapshot.rsi_5m >= 55:
            action = "LONG"
            score_hint = 1
        elif snapshot.rsi_1m <= 40 and snapshot.rsi_5m <= 45:
            action = "SHORT"
            score_hint = -1
        return AgentVote(
            agent_name="MomentumAgent",
            action=action,
            score=0.16,
            reason=f"dual-rsi momentum={score_hint}",
        )

    def _regime_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        spread = abs(snapshot.ema_fast_5m - snapshot.ema_slow_5m) / snapshot.last_price if snapshot.last_price else 0.0
        action = "FLAT"
        if spread >= 0.0012:
            if snapshot.ema_fast_5m > snapshot.ema_slow_5m:
                action = "LONG"
            elif snapshot.ema_fast_5m < snapshot.ema_slow_5m:
                action = "SHORT"
        return AgentVote(
            agent_name="RegimeAgent",
            action=action,
            score=0.14,
            reason=f"5m regime spread={spread:.4f}",
        )

    def _risk_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        action = "FLAT"
        reason = "risk too noisy"
        if 0.0008 <= snapshot.atr_pct_1m <= 0.0060:
            if snapshot.last_candle_change_pct > 0 and snapshot.ema_fast_5m > snapshot.ema_slow_5m:
                action = "LONG"
                reason = "risk acceptable for long"
            elif snapshot.last_candle_change_pct < 0 and snapshot.ema_fast_5m < snapshot.ema_slow_5m:
                action = "SHORT"
                reason = "risk acceptable for short"
            else:
                reason = "risk acceptable but direction unclear"
        return AgentVote(
            agent_name="RiskAgent",
            action=action,
            score=0.12,
            reason=reason,
        )

    def _orderbook_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        action = "FLAT"
        reason = (
            f"imbalance={snapshot.orderbook_imbalance:.3f}, "
            f"spread={snapshot.spread_pct:.4%}"
        )
        if snapshot.spread_pct <= 0.0005:
            if snapshot.orderbook_imbalance >= self.orderbook_imbalance_threshold:
                action = "LONG"
                reason = (
                    f"bid pressure strong: imbalance={snapshot.orderbook_imbalance:.3f}, "
                    f"spread={snapshot.spread_pct:.4%}"
                )
            elif snapshot.orderbook_imbalance <= -self.orderbook_imbalance_threshold:
                action = "SHORT"
                reason = (
                    f"ask pressure strong: imbalance={snapshot.orderbook_imbalance:.3f}, "
                    f"spread={snapshot.spread_pct:.4%}"
                )
            else:
                reason = (
                    f"order book balanced: imbalance={snapshot.orderbook_imbalance:.3f}, "
                    f"spread={snapshot.spread_pct:.4%}"
                )
        else:
            reason = (
                f"spread too wide for conviction: imbalance={snapshot.orderbook_imbalance:.3f}, "
                f"spread={snapshot.spread_pct:.4%}"
            )
        return AgentVote(
            agent_name="OrderBookAgent",
            action=action,
            score=0.15,
            reason=reason,
        )

    def _liquidity_trap_agent(self, snapshot: MarketSnapshot) -> AgentVote:
        action = "FLAT"
        reason = f"wall_bias={snapshot.liquidity_wall_bias:.3f}"
        if snapshot.last_candle_change_pct > 0 and snapshot.liquidity_wall_bias <= -self.liquidity_trap_threshold:
            action = "SHORT"
            reason = (
                f"possible long trap: bullish candle into ask wall, wall_bias={snapshot.liquidity_wall_bias:.3f}"
            )
        elif snapshot.last_candle_change_pct < 0 and snapshot.liquidity_wall_bias >= self.liquidity_trap_threshold:
            action = "LONG"
            reason = (
                f"possible short trap: bearish candle into bid wall, wall_bias={snapshot.liquidity_wall_bias:.3f}"
            )
        elif abs(snapshot.liquidity_wall_bias) < self.liquidity_trap_threshold:
            reason = f"no strong liquidity trap, wall_bias={snapshot.liquidity_wall_bias:.3f}"
        return AgentVote(
            agent_name="LiquidityTrapAgent",
            action=action,
            score=0.13,
            reason=reason,
        )

    def _openai_decide(self, snapshot: MarketSnapshot, base_decision: SignalDecision) -> SignalDecision:
        prompt = (
            "You are the senior trading director supervising a crypto futures desk.\n"
            "Review the director consensus and decide exactly one action: LONG, SHORT, or FLAT.\n"
            "Respect the 5m trend as a filter and 1m as an entry timeframe.\n"
            "Be directionally neutral: SHORT is just as valid as LONG when the 5m filter is bearish and the 1m entry confirms down.\n"
            "Do not default to LONG just because the broader crypto market feels bullish.\n"
            "If setup quality is weak or unclear, return FLAT.\n"
            "Respond with strict JSON only using this schema:\n"
            '{"action":"LONG|SHORT|FLAT","confidence":0.0,"reason":"short text",'
            '"stop_loss_pct":0.0,"take_profit_pct":0.0}\n'
            f"Director baseline: {json.dumps(self._decision_to_dict(base_decision))}\n"
            f"Data: {json.dumps(snapshot.__dict__)}"
        )
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        text = response.output_text.strip().replace("```json", "").replace("```", "").strip()
        payload = json.loads(text)
        action = str(payload.get("action", "FLAT")).upper()
        confidence = float(payload.get("confidence", 0.0))
        stop_loss_pct = max(
            self.config["min_stop_loss_pct"],
            float(payload.get("stop_loss_pct", 0.0) or 0.0),
        )
        take_profit_pct = max(
            stop_loss_pct * self.config["risk_reward_ratio"],
            float(payload.get("take_profit_pct", 0.0) or 0.0),
        )

        if action not in {"LONG", "SHORT", "FLAT"}:
            action = "FLAT"
        if confidence < self.config["min_confidence"]:
            action = "FLAT"

        return SignalDecision(
            symbol=snapshot.symbol,
            action=action,
            confidence=confidence,
            reason=str(payload.get("reason", "OpenAI decision")),
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            entry_price=snapshot.last_price,
            votes=base_decision.votes,
        )

    def _decision_to_dict(self, decision: SignalDecision) -> dict[str, Any]:
        return {
            "symbol": decision.symbol,
            "action": decision.action,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "stop_loss_pct": decision.stop_loss_pct,
            "take_profit_pct": decision.take_profit_pct,
            "entry_price": decision.entry_price,
            "votes": [
                {
                    "agent_name": vote.agent_name,
                    "action": vote.action,
                    "score": vote.score,
                    "reason": vote.reason,
                }
                for vote in decision.votes
            ],
        }
