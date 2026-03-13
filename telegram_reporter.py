"""
what changed:
- Reworked Telegram notifications into cleaner cards for signals, opens, closes, PnL, daily summaries, and open-position status.

why:
- Trade notifications should be instantly readable on mobile and the end-of-day report should look like a proper desk summary.
"""

from __future__ import annotations

import html
import os
from typing import Any

import requests

from ai_agent import SignalDecision


class TelegramReporter:
    def __init__(self, config: dict[str, Any], logger: Any) -> None:
        self.enabled = bool(config.get("enabled", True))
        self.logger = logger
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.title = config.get("title", "AI Trader")

    def _send(self, text: str) -> None:
        if not self.enabled:
            return
        if not self.token or not self.chat_id:
            self.logger.warning("Telegram is enabled in config, but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty.")
            return
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        response.raise_for_status()

    def send_signal(self, decision: SignalDecision) -> None:
        action_icon = "🟢" if decision.action == "LONG" else "🔴"
        status_icon, status_label = self._confidence_status(decision.confidence)
        votes_block = self._format_votes(decision)
        self._send(
            f"{action_icon} <b>{html.escape(self.title)}</b>\n"
            f"┏ <b>AI Signal</b>\n"
            f"┣ <b>Pair:</b> <code>{html.escape(decision.symbol)}</code>\n"
            f"┣ <b>Action:</b> <b>{html.escape(decision.action)}</b>\n"
            f"┣ <b>Status:</b> {status_icon} <code>{status_label}</code>\n"
            f"┣ <b>Confidence:</b> <code>{decision.confidence:.2%}</code>\n"
            f"┣ <b>Stop Loss:</b> <code>{decision.stop_loss_pct:.2%}</code>\n"
            f"┣ <b>Take Profit:</b> <code>{decision.take_profit_pct:.2%}</code>\n"
            f"┗ <b>R:R:</b> <code>{(decision.take_profit_pct / decision.stop_loss_pct):.2f}</code>\n\n"
            f"🧠 <b>Director Notes</b>\n"
            f"<blockquote>{html.escape(decision.reason)}</blockquote>\n\n"
            f"🗳 <b>Agent Vote Board</b>\n"
            f"<pre>{html.escape(votes_block)}</pre>"
        )

    def send_open(self, symbol: str, side: str, qty: float, entry_price: float, stop_loss: float, take_profit: float) -> None:
        side_icon = "🟢" if side == "Buy" else "🔴"
        self._send(
            f"{side_icon} <b>{html.escape(self.title)}</b>\n"
            f"┏ <b>Trade Opened</b>\n"
            f"┣ <b>Pair:</b> <code>{html.escape(symbol)}</code>\n"
            f"┣ <b>Side:</b> <b>{html.escape(side)}</b>\n"
            f"┣ <b>Size:</b> <code>{qty}</code>\n"
            f"┣ <b>Entry:</b> <code>{entry_price:.4f}</code>\n"
            f"┣ <b>Stop Loss:</b> <code>{stop_loss:.4f}</code>\n"
            f"┗ <b>Take Profit:</b> <code>{take_profit:.4f}</code>"
        )

    def send_position_status(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        mark_price: float,
        unrealized_pnl: float,
        stop_loss: float,
        take_profit: float,
    ) -> None:
        side_icon = "🟢" if side == "Buy" else "🔴"
        pnl_icon = "📈" if unrealized_pnl >= 0 else "📉"
        pnl_label = "IN PROFIT" if unrealized_pnl >= 0 else "UNDER WATER"
        self._send(
            f"{side_icon} <b>{html.escape(self.title)}</b>\n"
            f"┏ <b>Open Position</b>\n"
            f"┣ <b>Pair:</b> <code>{html.escape(symbol)}</code>\n"
            f"┣ <b>Side:</b> <b>{html.escape(side)}</b>\n"
            f"┣ <b>Size:</b> <code>{qty}</code>\n"
            f"┣ <b>Entry:</b> <code>{entry_price:.4f}</code>\n"
            f"┣ <b>Mark:</b> <code>{mark_price:.4f}</code>\n"
            f"┣ <b>Status:</b> {pnl_icon} <code>{pnl_label}</code>\n"
            f"┣ <b>Unrealized PnL:</b> <code>{unrealized_pnl:.2f} USDT</code>\n"
            f"┣ <b>Stop Loss:</b> <code>{stop_loss:.4f}</code>\n"
            f"┗ <b>Take Profit:</b> <code>{take_profit:.4f}</code>"
        )

    def send_close(self, symbol: str, side: str, pnl: float) -> None:
        result_icon = "✅" if pnl >= 0 else "⛔"
        result_label = "PROFIT" if pnl >= 0 else "LOSS"
        self._send(
            f"{result_icon} <b>{html.escape(self.title)}</b>\n"
            f"┏ <b>Trade Closed</b>\n"
            f"┣ <b>Pair:</b> <code>{html.escape(symbol)}</code>\n"
            f"┣ <b>Side:</b> <b>{html.escape(side)}</b>\n"
            f"┣ <b>Result:</b> <code>{result_label}</code>\n"
            f"┗ <b>PnL:</b> <code>{pnl:.2f} USDT</code>"
        )

    def send_profit_loss(self, pnl: float, daily_pnl: float) -> None:
        pnl_icon = "📈" if pnl >= 0 else "📉"
        self._send(
            f"{pnl_icon} <b>{html.escape(self.title)}</b>\n"
            f"┏ <b>PnL Update</b>\n"
            f"┣ <b>Trade PnL:</b> <code>{pnl:.2f} USDT</code>\n"
            f"┗ <b>Daily PnL:</b> <code>{daily_pnl:.2f} USDT</code>"
        )

    def send_daily_report(self, body: str) -> None:
        self._send(
            f"📊 <b>{html.escape(self.title)}</b>\n"
            f"<b>End Of Day Summary</b>\n\n"
            f"<pre>{html.escape(body)}</pre>"
        )

    def _confidence_status(self, confidence: float) -> tuple[str, str]:
        if confidence >= 0.75:
            return "🔥", "HIGH CONVICTION"
        if confidence >= 0.60:
            return "✅", "TRADEABLE"
        return "👀", "WATCHLIST"

    def _format_votes(self, decision: SignalDecision) -> str:
        lines: list[str] = []
        for vote in decision.votes:
            vote_icon = {"LONG": "+", "SHORT": "-", "FLAT": "="}.get(vote.action, "?")
            lines.append(
                f"{vote_icon} {vote.agent_name:<18} {vote.action:<5} w={vote.score:.2f}"
            )
        return "\n".join(lines)
