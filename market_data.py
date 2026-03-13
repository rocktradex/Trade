"""
what changed:
- Added a Bybit public market data client with indicator helpers and instrument metadata needed for valid order sizing.

why:
- The trader needs isolated market data logic so the signal engine can stay clean and execution can respect exchange filters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from orderbook_stream import OrderBookStream


@dataclass
class MarketSnapshot:
    symbol: str
    last_price: float
    ema_fast_1m: float
    ema_slow_1m: float
    ema_fast_5m: float
    ema_slow_5m: float
    rsi_1m: float
    rsi_5m: float
    atr_1m: float
    atr_pct_1m: float
    last_candle_change_pct: float
    best_bid: float
    best_ask: float
    spread_pct: float
    bid_notional_top: float
    ask_notional_top: float
    orderbook_imbalance: float
    liquidity_wall_bias: float


class BybitMarketData:
    def __init__(self, config: dict[str, Any], logger: Any) -> None:
        self.base_url = config["base_url"].rstrip("/")
        self.kline_limit = int(config["kline_limit"])
        self.orderbook_limit = int(config.get("orderbook_limit", 25))
        self.use_websocket_orderbook = bool(config.get("use_websocket_orderbook", True))
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Bybit-AI-Trader/1.0"})
        self.orderbook_stream: OrderBookStream | None = None

    def attach_orderbook_stream(self, stream: OrderBookStream) -> None:
        self.orderbook_stream = stream

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("retCode") != 0:
            raise RuntimeError(f"Bybit public API error: {payload}")
        return payload

    def get_klines(self, symbol: str, interval: str, limit: int | None = None) -> list[dict[str, float]]:
        payload = self._get_json(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit or self.kline_limit,
            },
        )
        rows = payload["result"]["list"]
        klines: list[dict[str, float]] = []
        for row in reversed(rows):
            klines.append(
                {
                    "timestamp": float(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        return klines

    def get_last_price(self, symbol: str) -> float:
        payload = self._get_json(
            "/v5/market/tickers",
            {"category": "linear", "symbol": symbol},
        )
        return float(payload["result"]["list"][0]["lastPrice"])

    def get_instrument_info(self, symbol: str) -> dict[str, float]:
        payload = self._get_json(
            "/v5/market/instruments-info",
            {"category": "linear", "symbol": symbol},
        )
        item = payload["result"]["list"][0]
        lot_filter = item["lotSizeFilter"]
        return {
            "min_order_qty": float(lot_filter["minOrderQty"]),
            "qty_step": float(lot_filter["qtyStep"]),
            "min_notional_value": float(lot_filter.get("minNotionalValue", 0.0) or 0.0),
        }

    def get_orderbook(self, symbol: str, limit: int | None = None) -> dict[str, Any]:
        if self.use_websocket_orderbook and self.orderbook_stream is not None:
            cached = self.orderbook_stream.get(symbol)
            if cached:
                return cached
        payload = self._get_json(
            "/v5/market/orderbook",
            {
                "category": "linear",
                "symbol": symbol,
                "limit": limit or self.orderbook_limit,
            },
        )
        return payload["result"]

    def build_snapshot(self, symbol: str, entry_tf: str, filter_tf: str, ai_config: dict[str, Any]) -> MarketSnapshot:
        klines_1m = self.get_klines(symbol, entry_tf)
        klines_5m = self.get_klines(symbol, filter_tf)

        closes_1m = [row["close"] for row in klines_1m]
        highs_1m = [row["high"] for row in klines_1m]
        lows_1m = [row["low"] for row in klines_1m]
        closes_5m = [row["close"] for row in klines_5m]
        orderbook = self.get_orderbook(symbol)

        last_price = closes_1m[-1]
        last_candle_change_pct = ((closes_1m[-1] - klines_1m[-1]["open"]) / klines_1m[-1]["open"]) if klines_1m[-1]["open"] else 0.0
        atr_value = atr(highs_1m, lows_1m, closes_1m, ai_config["atr_period"])
        best_bid = float(orderbook["b"][0][0]) if orderbook.get("b") else last_price
        best_ask = float(orderbook["a"][0][0]) if orderbook.get("a") else last_price
        bid_notional_top = sum(float(price) * float(size) for price, size in orderbook.get("b", []))
        ask_notional_top = sum(float(price) * float(size) for price, size in orderbook.get("a", []))
        total_notional = bid_notional_top + ask_notional_top
        orderbook_imbalance = ((bid_notional_top - ask_notional_top) / total_notional) if total_notional else 0.0
        spread_pct = ((best_ask - best_bid) / last_price) if last_price else 0.0
        max_bid_notional = max((float(price) * float(size) for price, size in orderbook.get("b", [])), default=0.0)
        max_ask_notional = max((float(price) * float(size) for price, size in orderbook.get("a", [])), default=0.0)
        liquidity_wall_bias = ((max_bid_notional - max_ask_notional) / total_notional) if total_notional else 0.0

        return MarketSnapshot(
            symbol=symbol,
            last_price=last_price,
            ema_fast_1m=ema(closes_1m, ai_config["ema_fast_period"]),
            ema_slow_1m=ema(closes_1m, ai_config["ema_slow_period"]),
            ema_fast_5m=ema(closes_5m, ai_config["ema_fast_period"]),
            ema_slow_5m=ema(closes_5m, ai_config["ema_slow_period"]),
            rsi_1m=rsi(closes_1m, ai_config["rsi_period"]),
            rsi_5m=rsi(closes_5m, ai_config["rsi_period"]),
            atr_1m=atr_value,
            atr_pct_1m=(atr_value / last_price) if last_price else 0.0,
            last_candle_change_pct=last_candle_change_pct,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_pct=spread_pct,
            bid_notional_top=bid_notional_top,
            ask_notional_top=ask_notional_top,
            orderbook_imbalance=orderbook_imbalance,
            liquidity_wall_bias=liquidity_wall_bias,
        )


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Not enough values for EMA{period}")
    multiplier = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = ((value - current) * multiplier) + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError(f"Not enough values for RSI{period}")
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(values)):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period

    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(highs) <= period or len(lows) <= period or len(closes) <= period:
        raise ValueError(f"Not enough values for ATR{period}")
    true_ranges: list[float] = []
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    return sum(true_ranges[-period:]) / period
