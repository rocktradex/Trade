"""
what changed:
- Added a persistent learning agent that journals closed trades and automatically cuts risk after repeated losses in similar symbol/direction patterns.

why:
- The trader should learn from mistakes in a controlled way by reducing exposure to weak patterns instead of rewriting strategy rules on the fly.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class LearningAgent:
    def __init__(self, config: dict[str, Any], logger: Any, state_path: str = "logs/learning_state.json") -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(config.get("enabled", True))
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        return {"patterns": {}, "journal": [], "imported_trade_keys": []}

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def build_pattern_key(self, symbol: str, side: str) -> str:
        return f"{symbol}:{side}"

    def record_closed_trade(self, trade: dict[str, Any]) -> None:
        if not self.enabled:
            return

        symbol = str(trade.get("symbol", "UNKNOWN"))
        side = str(trade.get("side", "UNKNOWN"))
        pnl = float(trade.get("pnl", 0.0))
        key = self.build_pattern_key(symbol, side)
        pattern = self.state["patterns"].setdefault(
            key,
            {"wins": 0, "losses": 0, "loss_streak": 0, "last_pnl": 0.0, "updated_at": None},
        )
        if pnl < 0:
            pattern["losses"] += 1
            pattern["loss_streak"] += 1
        else:
            pattern["wins"] += 1
            pattern["loss_streak"] = 0
        pattern["last_pnl"] = pnl
        pattern["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")

        journal = self.state["journal"]
        trade_key = self._trade_key(trade)
        imported_keys = self.state.setdefault("imported_trade_keys", [])
        if trade_key in imported_keys:
            return
        journal.append(
            {
                "symbol": symbol,
                "side": side,
                "pnl": pnl,
                "closed_at": trade.get("closed_at"),
                "confidence": float(trade.get("confidence", 0.0)),
                "setup_notes": str(trade.get("setup_notes", ""))[:500],
                "news_status": trade.get("news_status", "UNKNOWN"),
            }
        )
        imported_keys.append(trade_key)
        max_journal_items = int(self.config.get("journal_limit", 200))
        if len(journal) > max_journal_items:
            del journal[:-max_journal_items]
        self.save()

    def sync_closed_trades(self, trades: list[dict[str, Any]]) -> None:
        if not self.enabled:
            return
        for trade in trades:
            self.record_closed_trade(trade)

    def get_size_multiplier(self, symbol: str, side: str) -> tuple[float, str]:
        if not self.enabled:
            return 1.0, "Learning filter disabled."

        key = self.build_pattern_key(symbol, side)
        pattern = self.state.get("patterns", {}).get(key)
        if not pattern:
            return 1.0, "No negative history for this pattern."

        loss_streak = int(pattern.get("loss_streak", 0))
        if loss_streak >= int(self.config.get("block_after_loss_streak", 3)):
            return 0.0, f"Learning block: {symbol} {side} has {loss_streak} recent losses."
        if loss_streak >= int(self.config.get("cut_after_loss_streak", 2)):
            multiplier = float(self.config.get("reduced_size_multiplier", 0.5))
            return multiplier, f"Learning penalty: {symbol} {side} size reduced after {loss_streak} losses."
        return 1.0, "Pattern history acceptable."

    def _trade_key(self, trade: dict[str, Any]) -> str:
        return "|".join(
            [
                str(trade.get("symbol", "")),
                str(trade.get("side", "")),
                str(trade.get("closed_at", "")),
                f"{float(trade.get('pnl', 0.0)):.8f}",
            ]
        )
