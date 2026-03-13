"""
what changed:
- Added the main automation loop, logging setup, signal ranking, risk gates, order placement, and close reconciliation.

why:
- The bot needs one controlled entry point that orchestrates all modules every 60 seconds without violating safety rules.
"""

from __future__ import annotations

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from ai_agent import SignalDecision, TradingAIAgent
from execution import BybitExecution
from learning_agent import LearningAgent
from market_data import BybitMarketData
from news_agent import NewsAgent
from orderbook_stream import OrderBookStream
from risk_manager import RiskManager, TradeResult
from telegram_reporter import TelegramReporter


def setup_logging() -> logging.Logger:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("bybit_ai_trader")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
    file_handler = RotatingFileHandler(logs_dir / "trades.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def load_config() -> dict:
    return json.loads(Path("config.json").read_text(encoding="utf-8"))


def pick_best_signal(signals: list[SignalDecision]) -> SignalDecision | None:
    actionable = [signal for signal in signals if signal.action in {"LONG", "SHORT"}]
    if not actionable:
        return None
    actionable.sort(key=lambda item: item.confidence, reverse=True)
    return actionable[0]


def reconcile_closed_position(
    execution: BybitExecution,
    risk_manager: RiskManager,
    learning_agent: LearningAgent,
    telegram: TelegramReporter,
    logger: logging.Logger,
) -> None:
    tracked_positions = risk_manager.get_active_positions()
    if not tracked_positions:
        return

    exchange_positions = {item["symbol"]: item for item in execution.get_open_positions()}
    for tracked_position in tracked_positions:
        symbol = tracked_position["symbol"]
        if symbol in exchange_positions:
            continue

        if tracked_position.get("order_id") == "DRY_RUN":
            logger.info("Clearing stale dry-run position for %s from runtime state.", symbol)
            risk_manager.clear_position_for_symbol(symbol)
            continue

        closed = execution.get_recent_closed_trade(symbol)
        if not closed:
            logger.warning("Tracked position for %s is closed, but recent closed PnL was not found.", symbol)
            risk_manager.clear_position_for_symbol(symbol)
            continue

        pnl = float(closed.get("closedPnl", 0.0))
        trade = TradeResult(
            symbol=symbol,
            side=tracked_position["side"],
            pnl=pnl,
            closed_at=closed.get("updatedTime", ""),
        )
        risk_manager.register_closed_trade(trade)
        learning_agent.record_closed_trade(
            {
                "symbol": trade.symbol,
                "side": trade.side,
                "pnl": trade.pnl,
                "closed_at": trade.closed_at,
                "confidence": tracked_position.get("confidence", 0.0),
                "setup_notes": tracked_position.get("decision_reason", ""),
                "news_status": tracked_position.get("news_status", "UNKNOWN"),
            }
        )
        telegram.send_close(trade.symbol, trade.side, trade.pnl)
        telegram.send_profit_loss(trade.pnl, risk_manager.state["realized_pnl"])
        logger.info("Closed trade reconciled for %s with pnl %.2f USDT", trade.symbol, trade.pnl)


def sync_active_position(execution: BybitExecution, risk_manager: RiskManager, logger: logging.Logger) -> None:
    exchange_positions = execution.get_open_positions()
    tracked_positions = risk_manager.get_active_positions()

    if not exchange_positions:
        if tracked_positions and all(item.get("order_id") == "DRY_RUN" for item in tracked_positions):
            logger.info("Removing stale dry-run position during startup sync.")
            risk_manager.clear_active_position()
        return

    if tracked_positions:
        return

    for exchange_position in exchange_positions:
        inferred_position = {
            "symbol": exchange_position["symbol"],
            "side": exchange_position["side"],
            "qty": float(exchange_position.get("size", 0) or 0),
            "entry_price": float(exchange_position.get("avgPrice", 0) or 0),
            "stop_loss": float(exchange_position.get("stopLoss", 0) or 0),
            "take_profit": float(exchange_position.get("takeProfit", 0) or 0),
            "order_id": "SYNCED_FROM_EXCHANGE",
            "risk_pct": 0.0,
        }
        risk_manager.register_open_position(inferred_position)
        logger.info("Runtime state synced from exchange for %s.", inferred_position["symbol"])


def main() -> None:
    load_dotenv()
    logger = setup_logging()
    config = load_config()

    market_data = BybitMarketData(config["market_data"], logger)
    orderbook_stream = OrderBookStream(
        symbols=config["symbols"],
        logger=logger,
        enabled=config["market_data"].get("use_websocket_orderbook", True),
    )
    orderbook_stream.start()
    market_data.attach_orderbook_stream(orderbook_stream)
    ai_agent = TradingAIAgent(config["ai"], logger)
    execution = BybitExecution(config["execution"], logger)
    risk_manager = RiskManager(config["risk"], logger)
    news_agent = NewsAgent(config["news"], logger)
    learning_agent = LearningAgent(config["learning"], logger)
    telegram = TelegramReporter(config["telegram"], logger)

    logger.info("Trader started. Symbols=%s | entry_tf=%s | filter_tf=%s", config["symbols"], config["timeframes"]["entry"], config["timeframes"]["filter"])
    sync_active_position(execution, risk_manager, logger)
    learning_agent.sync_closed_trades(risk_manager.state.get("closed_trades", []))

    while True:
        try:
            wallet_balance = execution.get_usdt_balance()
            available_balance = execution.get_available_balance()
            risk_manager.reset_daily_if_needed(wallet_balance)
            reconcile_closed_position(execution, risk_manager, learning_agent, telegram, logger)

            if risk_manager.should_send_daily_report(
                config["telegram"]["daily_report_hour"],
                config["telegram"]["daily_report_minute"],
            ):
                telegram.send_daily_report(risk_manager.build_daily_report())
                risk_manager.mark_daily_report_sent()

            can_trade, reason = risk_manager.can_trade()
            if not can_trade:
                logger.warning("Trading blocked: %s", reason)
                time.sleep(config["loop_seconds"])
                continue

            news = news_agent.assess(config["symbols"])
            logger.info("News regime | status=%s | score=%s | reason=%s", news.status, news.score, news.reason)
            if news.headlines:
                logger.info("News headlines | %s", " || ".join(news.headlines))
            if news.block_new_entries:
                logger.warning("New entries blocked by news filter: %s", news.reason)
                time.sleep(config["loop_seconds"])
                continue

            signals: list[SignalDecision] = []
            for symbol in config["symbols"]:
                can_open_symbol, symbol_reason = risk_manager.can_open_symbol(symbol)
                if not can_open_symbol:
                    logger.info("Skipping %s: %s", symbol, symbol_reason)
                    continue
                snapshot = market_data.build_snapshot(
                    symbol=symbol,
                    entry_tf=config["timeframes"]["entry"],
                    filter_tf=config["timeframes"]["filter"],
                    ai_config=config["ai"],
                )
                decision = ai_agent.decide(snapshot)
                decision.reason = f"{decision.reason} | News={news.status}({news.score})"
                logger.info(
                    "Signal %s | action=%s | confidence=%.2f | %s",
                    symbol,
                    decision.action,
                    decision.confidence,
                    decision.reason,
                )
                signals.append(decision)

            best_signal = pick_best_signal(signals)
            if best_signal is None:
                logger.info("No actionable signal this cycle.")
                time.sleep(config["loop_seconds"])
                continue

            telegram.send_signal(best_signal)

            side = "Buy" if best_signal.action == "LONG" else "Sell"
            instrument_info = market_data.get_instrument_info(best_signal.symbol)
            orderbook_vote = next((vote for vote in best_signal.votes if vote.agent_name == "OrderBookAgent"), None)
            trap_vote = next((vote for vote in best_signal.votes if vote.agent_name == "LiquidityTrapAgent"), None)
            size_multiplier = 1.0
            if orderbook_vote and orderbook_vote.action == best_signal.action:
                size_multiplier *= config["ai"].get("position_boost_on_orderbook", 1.15)
            elif orderbook_vote and orderbook_vote.action not in {"FLAT", best_signal.action}:
                size_multiplier *= config["ai"].get("position_cut_on_orderbook", 0.70)
            if trap_vote and trap_vote.action not in {"FLAT", best_signal.action}:
                size_multiplier *= config["ai"].get("position_cut_on_orderbook", 0.70)
            size_multiplier *= news.size_multiplier

            learning_multiplier, learning_reason = learning_agent.get_size_multiplier(best_signal.symbol, side)
            logger.info(
                "Sizing modifiers for %s | news=%.2f | learning=%.2f | note=%s",
                best_signal.symbol,
                news.size_multiplier,
                learning_multiplier,
                learning_reason,
            )
            if learning_multiplier <= 0:
                logger.warning("Entry blocked by learning agent for %s: %s", best_signal.symbol, learning_reason)
                time.sleep(config["loop_seconds"])
                continue
            size_multiplier *= learning_multiplier

            qty = risk_manager.calculate_order_qty(
                symbol=best_signal.symbol,
                balance=available_balance,
                entry_price=best_signal.entry_price,
                stop_loss_pct=best_signal.stop_loss_pct,
                leverage=config["execution"]["default_leverage"],
                instrument_info=instrument_info,
                size_multiplier=size_multiplier,
            )
            if qty <= 0:
                logger.warning("Calculated quantity is zero for %s.", best_signal.symbol)
                time.sleep(config["loop_seconds"])
                continue

            order = execution.open_position(
                symbol=best_signal.symbol,
                side=side,
                qty=qty,
                entry_price=best_signal.entry_price,
                stop_loss_pct=best_signal.stop_loss_pct,
                take_profit_pct=best_signal.take_profit_pct,
            )
            order["risk_pct"] = config["risk"]["risk_per_trade_pct"]
            order["confidence"] = best_signal.confidence
            order["decision_reason"] = best_signal.reason
            order["news_status"] = news.status
            risk_manager.register_open_position(order)
            telegram.send_open(
                best_signal.symbol,
                side,
                qty,
                order["entry_price"],
                order["stop_loss"],
                order["take_profit"],
            )
            logger.info(
                "Opened %s %s qty=%s entry=%.4f sl=%.4f tp=%.4f",
                best_signal.symbol,
                side,
                qty,
                order["entry_price"],
                order["stop_loss"],
                order["take_profit"],
            )
        except Exception as exc:
            logger.exception("Main loop error: %s", exc)
        time.sleep(config["loop_seconds"])


if __name__ == "__main__":
    main()
