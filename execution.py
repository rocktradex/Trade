"""
what changed:
- Added demo-account support and safer environment-based execution switching for live, demo, and dry-run modes.

why:
- The bot needs a safe path to practice on Bybit demo without changing the trading workflow or risking real funds.
"""

from __future__ import annotations

import os
from typing import Any

from pybit.unified_trading import HTTP


class BybitExecution:
    def __init__(self, config: dict[str, Any], logger: Any) -> None:
        self.config = config
        self.logger = logger
        self.category = config["category"]
        self.live_trading = bool(config.get("live_trading", False))
        self.demo = os.getenv("BYBIT_DEMO", "false").lower() == "true"
        self.default_leverage = int(config.get("default_leverage", 1))
        self.session = HTTP(
            testnet=os.getenv("BYBIT_TESTNET", "false").lower() == "true",
            demo=self.demo,
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET"),
            recv_window=config["recv_window"],
        )

    def get_open_positions(self) -> list[dict[str, Any]]:
        response = self.session.get_positions(category=self.category, settleCoin="USDT")
        positions: list[dict[str, Any]] = []
        for item in response["result"]["list"]:
            size = float(item.get("size", 0) or 0)
            if size > 0:
                positions.append(item)
        return positions

    def get_open_position(self) -> dict[str, Any] | None:
        positions = self.get_open_positions()
        return positions[0] if positions else None

    def has_open_position(self) -> bool:
        return bool(self.get_open_positions())

    def get_usdt_balance(self) -> float:
        response = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        coins = response["result"]["list"][0]["coin"]
        for coin in coins:
            if coin["coin"] == "USDT":
                return float(coin["walletBalance"])
        raise RuntimeError("USDT balance not found.")

    def get_available_balance(self) -> float:
        response = self.session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        account = response["result"]["list"][0]
        return float(account.get("totalAvailableBalance", 0.0) or 0.0)

    def ensure_leverage(self, symbol: str) -> None:
        try:
            self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=str(self.default_leverage),
                sellLeverage=str(self.default_leverage),
            )
        except Exception as exc:
            message = str(exc)
            if "110043" in message or "leverage not modified" in message.lower():
                return
            self.logger.warning("Unable to set leverage for %s: %s", symbol, exc)

    def open_position(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss_pct: float,
        take_profit_pct: float,
    ) -> dict[str, Any]:
        if qty <= 0:
            raise ValueError("Quantity must be positive.")
        self.ensure_leverage(symbol)
        stop_loss = entry_price * (1 - stop_loss_pct if side == "Buy" else 1 + stop_loss_pct)
        take_profit = entry_price * (1 + take_profit_pct if side == "Buy" else 1 - take_profit_pct)

        if self.live_trading:
            order = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                positionIdx=0,
                takeProfit=f"{take_profit:.6f}",
                stopLoss=f"{stop_loss:.6f}",
                tpslMode="Full",
            )
            order_id = order["result"]["orderId"]
        else:
            self.logger.warning("Dry-run mode: order for %s %s qty=%s was not sent.", symbol, side, qty)
            order_id = "DRY_RUN"
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "order_id": order_id,
        }

    def get_recent_closed_trade(self, symbol: str) -> dict[str, Any] | None:
        response = self.session.get_closed_pnl(category=self.category, symbol=symbol, limit=1)
        rows = response["result"]["list"]
        if not rows:
            return None
        return rows[0]
