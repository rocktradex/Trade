"""
what changed:
- Added a persistent risk manager that enforces portfolio-aware sizing, daily limits, loss-streak pauses, and richer end-of-day reporting.

why:
- The bot needs risk controls that stay stable across demo/live environments and also produce useful daily desk summaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import floor
from pathlib import Path
from typing import Any


@dataclass
class TradeResult:
    symbol: str
    side: str
    pnl: float
    closed_at: str


class RiskManager:
    def __init__(self, config: dict[str, Any], logger: Any, state_path: str = "logs/runtime_state.json") -> None:
        self.config = config
        self.logger = logger
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        return {
            "date": datetime.now().date().isoformat(),
            "starting_balance": None,
            "realized_pnl": 0.0,
            "consecutive_losses": 0,
            "pause_until": None,
            "active_positions": [],
            "closed_trades": [],
            "last_daily_report_date": None,
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if "active_positions" not in state:
            legacy = state.pop("active_position", None)
            state["active_positions"] = [legacy] if legacy else []
        if "closed_trades" not in state:
            state["closed_trades"] = []
        return state

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def get_active_positions(self) -> list[dict[str, Any]]:
        return self.state.get("active_positions", [])

    def get_portfolio_risk_pct(self) -> float:
        total = 0.0
        for position in self.get_active_positions():
            total += float(position.get("risk_pct", self.config["risk_per_trade_pct"]))
        return total

    def reset_daily_if_needed(self, current_balance: float) -> None:
        today = datetime.now().date().isoformat()
        if self.state["date"] == today:
            baseline = self.state.get("starting_balance")
            balance_shifted = (
                baseline is not None
                and baseline > 0
                and current_balance > 0
                and (current_balance >= baseline * 10 or current_balance <= baseline * 0.1)
                and not self.get_active_positions()
            )
            if baseline is None or balance_shifted:
                self.state["starting_balance"] = current_balance
                self.state["realized_pnl"] = 0.0
                self.state["consecutive_losses"] = 0
                self.state["pause_until"] = None
                self.state["closed_trades"] = []
                self.save()
            return

        self.state["date"] = today
        self.state["starting_balance"] = current_balance
        self.state["realized_pnl"] = 0.0
        self.state["consecutive_losses"] = 0
        self.state["pause_until"] = None
        self.state["active_positions"] = self.get_active_positions()
        self.state["closed_trades"] = []
        self.state["last_daily_report_date"] = None
        self.save()

    def can_trade(self) -> tuple[bool, str]:
        pause_until = self.state.get("pause_until")
        if pause_until:
            pause_deadline = datetime.fromisoformat(pause_until)
            if datetime.now() < pause_deadline:
                return False, f"Trading paused until {pause_until}."
            self.state["pause_until"] = None
            self.state["consecutive_losses"] = 0
            self.save()

        if len(self.get_active_positions()) >= self.config["max_open_positions"]:
            return False, "Maximum number of open positions reached."

        starting_balance = self.state.get("starting_balance")
        if starting_balance:
            max_daily_loss = starting_balance * self.config["daily_loss_limit_pct"]
            if abs(min(self.state["realized_pnl"], 0.0)) >= max_daily_loss:
                return False, "Daily loss limit reached."

        if self.state["consecutive_losses"] >= self.config["max_consecutive_losses"]:
            return False, "Maximum consecutive loss streak reached."

        return True, "OK"

    def can_open_symbol(self, symbol: str) -> tuple[bool, str]:
        for position in self.get_active_positions():
            if position.get("symbol") == symbol:
                return False, f"Position for {symbol} already exists."
        return True, "OK"

    def calculate_order_qty(
        self,
        symbol: str,
        balance: float,
        entry_price: float,
        stop_loss_pct: float,
        leverage: float,
        instrument_info: dict[str, float],
        size_multiplier: float = 1.0,
    ) -> float:
        risk_amount = balance * self.config["risk_per_trade_pct"]
        stop_distance = entry_price * stop_loss_pct
        if risk_amount <= 0 or stop_distance <= 0:
            return 0.0

        available_risk_pct = self.config["max_total_risk_pct"] - self.get_portfolio_risk_pct()
        if available_risk_pct <= 0:
            return 0.0
        risk_amount = min(risk_amount, balance * available_risk_pct)
        risk_amount *= max(0.25, size_multiplier)

        min_notional = max(
            self.config["min_order_notional_usdt"],
            instrument_info.get("min_notional_value", 0.0),
        )
        if balance < min_notional or entry_price <= 0:
            return 0.0

        raw_qty = risk_amount / stop_distance
        max_notional = balance * max(leverage, 1.0) * self.config.get("max_margin_usage_pct", 0.9)
        if max_notional < min_notional:
            return 0.0

        capped_qty = min(raw_qty, max_notional / entry_price)
        qty = max(capped_qty, min_notional / entry_price)
        required_margin = (qty * entry_price) / max(leverage, 1.0)
        if required_margin > (balance * self.config.get("max_margin_usage_pct", 0.9)):
            return 0.0

        qty_step = instrument_info.get("qty_step", 0.0)
        min_order_qty = instrument_info.get("min_order_qty", 0.0)
        if qty_step <= 0 or min_order_qty <= 0:
            return 0.0

        normalized_qty = floor(qty / qty_step) * qty_step
        if normalized_qty < min_order_qty:
            normalized_qty = min_order_qty
        if (normalized_qty * entry_price) < min_notional:
            needed_qty = floor((min_notional / entry_price) / qty_step) * qty_step
            normalized_qty = max(normalized_qty, needed_qty)
        required_margin = (normalized_qty * entry_price) / max(leverage, 1.0)
        if required_margin > (balance * self.config.get("max_margin_usage_pct", 0.9)):
            return 0.0

        step_text = f"{qty_step:.12f}".rstrip("0")
        decimals = len(step_text.split(".")[1]) if "." in step_text else 0
        return round(normalized_qty, decimals)

    def register_open_position(self, payload: dict[str, Any]) -> None:
        positions = self.get_active_positions()
        positions = [item for item in positions if item.get("symbol") != payload.get("symbol")]
        positions.append(payload)
        self.state["active_positions"] = positions
        self.save()

    def register_closed_trade(self, trade: TradeResult) -> None:
        positions = [item for item in self.get_active_positions() if item.get("symbol") != trade.symbol]
        self.state["active_positions"] = positions
        self.state["realized_pnl"] += trade.pnl
        closed_trades = self.state.get("closed_trades", [])
        closed_trades.append(
            {
                "symbol": trade.symbol,
                "side": trade.side,
                "pnl": trade.pnl,
                "closed_at": trade.closed_at,
            }
        )
        self.state["closed_trades"] = closed_trades

        if trade.pnl < 0:
            self.state["consecutive_losses"] += 1
        else:
            self.state["consecutive_losses"] = 0

        if self.state["consecutive_losses"] >= self.config["max_consecutive_losses"]:
            pause_until = datetime.now() + timedelta(minutes=self.config["pause_after_loss_streak_minutes"])
            self.state["pause_until"] = pause_until.isoformat(timespec="seconds")

        self.save()

    def clear_active_position(self) -> None:
        self.state["active_positions"] = []
        self.save()

    def clear_position_for_symbol(self, symbol: str) -> None:
        positions = [item for item in self.get_active_positions() if item.get("symbol") != symbol]
        self.state["active_positions"] = positions
        self.save()

    def should_send_daily_report(self, report_hour: int, report_minute: int) -> bool:
        now = datetime.now()
        current_date = now.date().isoformat()
        if self.state.get("last_daily_report_date") == current_date:
            return False
        return (now.hour, now.minute) >= (report_hour, report_minute)

    def mark_daily_report_sent(self) -> None:
        self.state["last_daily_report_date"] = datetime.now().date().isoformat()
        self.save()

    def build_daily_report(self) -> str:
        closed_trades = self.state.get("closed_trades", [])
        wins = [trade for trade in closed_trades if float(trade["pnl"]) > 0]
        losses = [trade for trade in closed_trades if float(trade["pnl"]) < 0]
        total_trades = len(closed_trades)
        win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
        best_trade = max((float(trade["pnl"]) for trade in closed_trades), default=0.0)
        worst_trade = min((float(trade["pnl"]) for trade in closed_trades), default=0.0)
        open_symbols = ", ".join(position["symbol"] for position in self.get_active_positions()) or "none"
        starting_balance = float(self.state.get("starting_balance") or 0.0)
        realized_pnl = float(self.state.get("realized_pnl", 0.0))
        current_balance = starting_balance + realized_pnl
        return (
            f"Date: {self.state['date']}\n"
            f"Starting balance: {starting_balance:.2f} USDT\n"
            f"Current balance (realized): {current_balance:.2f} USDT\n"
            f"Realized PnL: {realized_pnl:.2f} USDT\n"
            f"Closed trades: {total_trades}\n"
            f"Wins / Losses: {len(wins)} / {len(losses)}\n"
            f"Win rate: {win_rate:.1f}%\n"
            f"Best trade: {best_trade:.2f} USDT\n"
            f"Worst trade: {worst_trade:.2f} USDT\n"
            f"Open positions: {open_symbols}\n"
            f"Consecutive losses: {self.state['consecutive_losses']}\n"
            f"Pause until: {self.state['pause_until'] or 'not active'}"
        )
