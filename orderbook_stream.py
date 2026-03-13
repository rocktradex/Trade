"""
what changed:
- Added a lightweight Bybit WebSocket order book cache with REST fallback compatibility.

why:
- The strategy can use fresher order book data without blocking the main loop on repeated REST snapshots.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from pybit.unified_trading import WebSocket


class OrderBookStream:
    def __init__(self, symbols: list[str], logger: Any, enabled: bool = True) -> None:
        self.symbols = symbols
        self.logger = logger
        self.enabled = enabled
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._ws: WebSocket | None = None

    def start(self) -> None:
        if not self.enabled or not self.symbols:
            return
        try:
            self._ws = WebSocket(
                channel_type="linear",
                testnet=os.getenv("BYBIT_TESTNET", "false").lower() == "true",
                demo=os.getenv("BYBIT_DEMO", "false").lower() == "true",
            )
            for symbol in self.symbols:
                self._ws.orderbook_stream(
                    depth=25,
                    symbol=symbol,
                    callback=lambda message, symbol=symbol: self._handle_message(symbol, message),
                )
            self.logger.info("OrderBook WebSocket stream started for %s", self.symbols)
        except Exception as exc:
            self.logger.warning("Failed to start order book WebSocket stream: %s", exc)
            self._ws = None

    def _handle_message(self, symbol: str, message: dict[str, Any]) -> None:
        data = message.get("data") or {}
        if not data:
            return
        payload = {
            "b": data.get("b", []),
            "a": data.get("a", []),
            "ts": message.get("ts") or int(time.time() * 1000),
        }
        with self._lock:
            self._cache[symbol] = payload

    def get(self, symbol: str) -> dict[str, Any] | None:
        with self._lock:
            return self._cache.get(symbol)

    def stop(self) -> None:
        if self._ws is None:
            return
        try:
            self._ws.exit()
        except Exception:
            pass
