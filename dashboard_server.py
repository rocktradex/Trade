"""
what changed:
- Added a standalone live dashboard server that shows balances, positions, PnL, risk state, news regime, learning patterns, and recent trades in a browser.

why:
- The trader needs an active operations panel for monitoring the bot without reading raw logs or Telegram messages.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import secrets
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import base64

from dotenv import load_dotenv

from execution import BybitExecution
from learning_agent import LearningAgent
from news_agent import NewsAgent
from risk_manager import RiskManager


def load_config() -> dict[str, Any]:
    return json.loads(Path("config.json").read_text(encoding="utf-8"))


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("dashboard_server")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())
    return logger


def get_service_status(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def get_service_started_at(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "show", "-p", "ActiveEnterTimestamp", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        raw = result.stdout.strip()
        return raw.split("=", 1)[1] if "=" in raw else "unknown"
    except Exception:
        return "unknown"


class DashboardDataProvider:
    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.trades_log_path = Path("logs/trades.log")

    def build_payload(self) -> dict[str, Any]:
        execution = BybitExecution(self.config["execution"], self.logger)
        risk_manager = RiskManager(self.config["risk"], self.logger)
        learning_agent = LearningAgent(self.config["learning"], self.logger)
        news_agent = NewsAgent(self.config["news"], self.logger)

        wallet_balance = execution.get_usdt_balance()
        available_balance = execution.get_available_balance()
        exchange_positions = execution.get_open_positions()
        runtime_state = risk_manager.state
        learning_state = learning_agent.state
        news = news_agent.assess(self.config["symbols"])

        positions: list[dict[str, Any]] = []
        unrealized_total = 0.0
        for item in exchange_positions:
            unrealized = float(item.get("unrealisedPnl", 0.0) or 0.0)
            unrealized_total += unrealized
            positions.append(
                {
                    "symbol": item.get("symbol"),
                    "side": item.get("side"),
                    "size": float(item.get("size", 0.0) or 0.0),
                    "entry_price": float(item.get("avgPrice", 0.0) or 0.0),
                    "mark_price": float(item.get("markPrice", 0.0) or 0.0),
                    "unrealized_pnl": unrealized,
                    "stop_loss": float(item.get("stopLoss", 0.0) or 0.0),
                    "take_profit": float(item.get("takeProfit", 0.0) or 0.0),
                    "leverage": float(item.get("leverage", 0.0) or 0.0),
                }
            )

        closed_trades = list(reversed(runtime_state.get("closed_trades", [])[-12:]))
        recent_signals = self._read_recent_signals(limit=12)
        patterns = [
            {
                "pattern": key,
                "wins": value.get("wins", 0),
                "losses": value.get("losses", 0),
                "loss_streak": value.get("loss_streak", 0),
                "last_pnl": value.get("last_pnl", 0.0),
                "updated_at": value.get("updated_at"),
            }
            for key, value in learning_state.get("patterns", {}).items()
        ]
        patterns.sort(key=lambda item: (item["loss_streak"], item["losses"]), reverse=True)
        featured_position = max(positions, key=lambda item: abs(item["unrealized_pnl"]), default=None)

        return {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "service": {
                "name": self.config["dashboard"]["trader_service_name"],
                "status": get_service_status(self.config["dashboard"]["trader_service_name"]),
                "started_at": get_service_started_at(self.config["dashboard"]["trader_service_name"]),
            },
            "account": {
                "wallet_balance": wallet_balance,
                "available_balance": available_balance,
                "realized_pnl": float(runtime_state.get("realized_pnl", 0.0)),
                "unrealized_pnl": unrealized_total,
                "equity_estimate": wallet_balance + unrealized_total,
            },
            "risk": {
                "date": runtime_state.get("date"),
                "starting_balance": float(runtime_state.get("starting_balance") or 0.0),
                "consecutive_losses": runtime_state.get("consecutive_losses", 0),
                "pause_until": runtime_state.get("pause_until"),
                "active_positions_count": len(positions),
                "closed_trades_count": len(runtime_state.get("closed_trades", [])),
                "portfolio_risk_pct": risk_manager.get_portfolio_risk_pct(),
                "daily_report": risk_manager.build_daily_report(),
            },
            "news": {
                "status": news.status,
                "score": news.score,
                "reason": news.reason,
                "block_new_entries": news.block_new_entries,
                "size_multiplier": news.size_multiplier,
                "headlines": news.headlines,
                "crypto_score": news.crypto_score,
                "macro_score": news.macro_score,
                "systemic_score": news.systemic_score,
                "max_headline_score": news.max_headline_score,
            },
            "positions": positions,
            "featured_position": featured_position,
            "closed_trades": closed_trades,
            "recent_signals": recent_signals,
            "learning_patterns": patterns[:10],
            "symbols": self.config["symbols"],
        }

    def _read_recent_signals(self, limit: int = 12) -> list[dict[str, str]]:
        if not self.trades_log_path.exists():
            return []

        lines = self.trades_log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        entries: list[dict[str, str]] = []
        for line in reversed(lines):
            if " | INFO    | Signal " in line:
                parts = line.split(" | INFO    | ", 1)
                if len(parts) != 2:
                    continue
                timestamp, message = parts
                entries.append({"type": "signal", "timestamp": timestamp.strip(), "message": message.strip()})
            elif " | INFO    | News regime " in line:
                parts = line.split(" | INFO    | ", 1)
                if len(parts) != 2:
                    continue
                timestamp, message = parts
                entries.append({"type": "news", "timestamp": timestamp.strip(), "message": message.strip()})
            elif " | INFO    | Opened " in line:
                parts = line.split(" | INFO    | ", 1)
                if len(parts) != 2:
                    continue
                timestamp, message = parts
                entries.append({"type": "open", "timestamp": timestamp.strip(), "message": message.strip()})
            if len(entries) >= limit:
                break
        return list(reversed(entries))


def render_dashboard_html(title: str, refresh_seconds: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0a0a0a;
      --panel: #111111;
      --panel-soft: #1b1b1b;
      --text: #f5f5f5;
      --muted: #a9a9a9;
      --line: #2f2f2f;
      --good: #3ddc97;
      --bad: #ff6b6b;
      --warn: #ffd166;
      --blue: #5ab0ff;
      --long: #34d399;
      --short: #ff7b72;
      --flat: #9ca3af;
      --news-green: #22c55e;
      --news-yellow: #f59e0b;
      --news-red: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(255,255,255,.08), transparent 30%),
        radial-gradient(circle at top left, rgba(180,180,180,.08), transparent 25%),
        linear-gradient(180deg, #050505 0%, #101010 100%);
      color: var(--text);
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: 48px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .hero p {{
      margin: 8px 0 0;
      color: var(--muted);
    }}
    .pill {{
      display: inline-block;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      color: var(--text);
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }}
    .hero-panel {{
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.00)), var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 30px rgba(0,0,0,.18);
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 14px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .metric {{
      font-size: 28px;
      font-weight: 700;
    }}
    .good {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    .blue {{ color: var(--blue); }}
    .sections {{
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 14px;
      margin-bottom: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      font-family: Consolas, monospace;
      color: var(--text);
      font-size: 13px;
    }}
    .stack {{
      display: grid;
      gap: 14px;
    }}
    .headline {{
      padding: 10px 12px;
      border-radius: 12px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      margin-bottom: 8px;
      color: var(--text);
    }}
    .live-card {{
      min-height: 220px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .live-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .live-dot {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: var(--good);
      box-shadow: 0 0 0 0 rgba(61,220,151,.65);
      animation: pulse 1.4s infinite;
    }}
    .live-dot.idle {{
      background: #666666;
      box-shadow: none;
      animation: none;
    }}
    .live-symbol {{
      font-size: 44px;
      font-weight: 800;
      letter-spacing: 0.08em;
    }}
    .live-side {{
      display: inline-block;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .badge-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .badge {{
      display: inline-block;
      padding: 8px 10px;
      border-radius: 999px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      font-size: 12px;
      color: var(--text);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .signal-feed {{
      display: grid;
      gap: 10px;
      max-height: 420px;
      overflow: auto;
    }}
    .feed-item {{
      padding: 12px;
      border-radius: 14px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
    }}
    .profit-row td {{
      background: rgba(61,220,151,.08);
    }}
    .loss-row td {{
      background: rgba(255,107,107,.10);
    }}
    .profit-chip {{
      color: var(--good);
      font-weight: 700;
    }}
    .loss-chip {{
      color: var(--bad);
      font-weight: 700;
    }}
    .side-long {{
      color: var(--long);
      border-color: rgba(52,211,153,.35);
    }}
    .side-short {{
      color: var(--short);
      border-color: rgba(255,123,114,.35);
    }}
    .side-flat {{
      color: var(--flat);
      border-color: rgba(156,163,175,.35);
    }}
    .status-green {{
      color: var(--news-green);
    }}
    .status-yellow {{
      color: var(--news-yellow);
    }}
    .status-red {{
      color: var(--news-red);
    }}
    .feed-signal {{
      border-left: 3px solid var(--blue);
    }}
    .feed-news {{
      border-left: 3px solid var(--warn);
    }}
    .feed-open {{
      border-left: 3px solid var(--good);
    }}
    .feed-meta {{
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    @keyframes pulse {{
      0% {{
        transform: scale(0.95);
        box-shadow: 0 0 0 0 rgba(61,220,151,.55);
      }}
      70% {{
        transform: scale(1);
        box-shadow: 0 0 0 12px rgba(61,220,151,0);
      }}
      100% {{
        transform: scale(0.95);
        box-shadow: 0 0 0 0 rgba(61,220,151,0);
      }}
    }}
    .small {{
      font-size: 13px;
      color: var(--muted);
    }}
    @media (max-width: 1100px) {{
      .grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .sections {{
        grid-template-columns: 1fr;
      }}
      .hero-panel {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .hero {{
        flex-direction: column;
        align-items: start;
      }}
      .wrap {{
        padding: 14px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <h1>ROCKTRADE</h1>
        <p>{title}</p>
      </div>
      <div class="pill" id="generated-at">Loading...</div>
    </div>

    <div class="hero-panel">
      <div class="card live-card">
        <div>
          <div class="live-header">
            <span class="live-dot idle" id="live-dot"></span>
            <h2>Live Position</h2>
          </div>
          <div class="live-symbol" id="live-symbol">NO POSITION</div>
          <div class="badge-row">
            <span class="live-side" id="live-side">STANDBY</span>
            <span class="badge" id="live-pnl">PNL 0.00</span>
            <span class="badge" id="live-entry">ENTRY 0.00</span>
            <span class="badge" id="live-mark">MARK 0.00</span>
          </div>
        </div>
        <div class="small" id="live-extra">Waiting for active trades.</div>
      </div>
      <div class="card">
        <h2>Director Feed</h2>
        <div class="signal-feed" id="signal-feed"></div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Service</h2>
        <div class="metric" id="service-status">...</div>
        <div class="small" id="service-started">...</div>
      </div>
      <div class="card">
        <h2>Equity Estimate</h2>
        <div class="metric" id="equity-estimate">...</div>
        <div class="small">Wallet + unrealized PnL</div>
      </div>
      <div class="card">
        <h2>Daily Realized PnL</h2>
        <div class="metric" id="realized-pnl">...</div>
        <div class="small">Closed trades only</div>
      </div>
        <div class="card">
          <h2>News Regime</h2>
          <div class="metric" id="news-status">...</div>
          <div class="small" id="news-reason">...</div>
        </div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Wallet Balance</h2>
        <div class="metric" id="wallet-balance">...</div>
      </div>
      <div class="card">
        <h2>Available Balance</h2>
        <div class="metric" id="available-balance">...</div>
      </div>
      <div class="card">
        <h2>Open Positions</h2>
        <div class="metric" id="open-count">...</div>
      </div>
      <div class="card">
        <h2>Loss Streak</h2>
        <div class="metric" id="loss-streak">...</div>
        <div class="small" id="pause-until">...</div>
      </div>
    </div>

    <div class="sections">
      <div class="stack">
        <div class="card">
          <h2>Open Positions</h2>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Size</th>
                <th>Entry</th>
                <th>Mark</th>
                <th>PnL</th>
                <th>SL / TP</th>
              </tr>
            </thead>
            <tbody id="positions-body"></tbody>
          </table>
        </div>
        <div class="card">
          <h2>Recent Closed Trades</h2>
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>PnL</th>
                <th>Closed</th>
              </tr>
            </thead>
            <tbody id="trades-body"></tbody>
          </table>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <h2>News Breakdown</h2>
          <table>
            <tbody>
              <tr><th>Crypto</th><td id="news-crypto">...</td></tr>
              <tr><th>Macro</th><td id="news-macro">...</td></tr>
              <tr><th>Systemic</th><td id="news-systemic">...</td></tr>
              <tr><th>Max Headline</th><td id="news-headline">...</td></tr>
              <tr><th>Size Multiplier</th><td id="news-size-multiplier">...</td></tr>
            </tbody>
          </table>
        </div>
        <div class="card">
          <h2>News Headlines</h2>
          <div id="headlines"></div>
        </div>
        <div class="card">
          <h2>Learning Patterns</h2>
          <table>
            <thead>
              <tr>
                <th>Pattern</th>
                <th>W/L</th>
                <th>Streak</th>
                <th>Last PnL</th>
              </tr>
            </thead>
            <tbody id="patterns-body"></tbody>
          </table>
        </div>
        <div class="card">
          <h2>Daily Report</h2>
          <pre id="daily-report"></pre>
        </div>
      </div>
    </div>
  </div>

  <script>
    const refreshMs = {refresh_seconds} * 1000;

    function pnlClass(value) {{
      return value > 0 ? 'good' : value < 0 ? 'bad' : 'blue';
    }}

    function fmt(value, digits = 2) {{
      return Number(value || 0).toFixed(digits);
    }}

    function setText(id, text, className = '') {{
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = className;
    }}

    function newsClass(status) {{
      if (status === 'RED') return 'status-red';
      if (status === 'YELLOW') return 'status-yellow';
      return 'status-green';
    }}

    async function loadData() {{
      const response = await fetch('/api/dashboard');
      const data = await response.json();

      setText('generated-at', 'Updated ' + data.generated_at);
      setText('service-status', data.service.status.toUpperCase(), data.service.status === 'active' ? 'metric good' : 'metric warn');
      setText('service-started', 'Started: ' + data.service.started_at);
      setText('equity-estimate', fmt(data.account.equity_estimate) + ' USDT', 'metric ' + pnlClass(data.account.unrealized_pnl + data.account.realized_pnl));
      setText('realized-pnl', fmt(data.account.realized_pnl) + ' USDT', 'metric ' + pnlClass(data.account.realized_pnl));
      setText('wallet-balance', fmt(data.account.wallet_balance) + ' USDT', 'metric blue');
      setText('available-balance', fmt(data.account.available_balance) + ' USDT', 'metric blue');
      setText('open-count', String(data.risk.active_positions_count), 'metric blue');
      setText('loss-streak', String(data.risk.consecutive_losses), data.risk.consecutive_losses > 0 ? 'metric warn' : 'metric blue');
      setText('pause-until', data.risk.pause_until ? ('Pause until: ' + data.risk.pause_until) : 'Pause inactive');
      setText('news-status', data.news.status, 'metric ' + newsClass(data.news.status));
      setText('news-reason', data.news.reason);
      setText('news-crypto', String(data.news.crypto_score));
      setText('news-macro', String(data.news.macro_score));
      setText('news-systemic', String(data.news.systemic_score));
      setText('news-headline', String(data.news.max_headline_score));
      setText('news-size-multiplier', fmt(data.news.size_multiplier, 2) + 'x');
      setText('daily-report', data.risk.daily_report);

      if (data.featured_position) {{
        document.getElementById('live-dot').className = 'live-dot';
        setText('live-symbol', data.featured_position.symbol);
        setText('live-side', data.featured_position.side === 'Buy' ? 'LONG' : 'SHORT', 'live-side ' + (data.featured_position.side === 'Buy' ? 'side-long' : 'side-short'));
        setText('live-pnl', 'PNL ' + fmt(data.featured_position.unrealized_pnl) + ' USDT', 'badge ' + pnlClass(data.featured_position.unrealized_pnl));
        setText('live-entry', 'ENTRY ' + fmt(data.featured_position.entry_price, 4), 'badge');
        setText('live-mark', 'MARK ' + fmt(data.featured_position.mark_price, 4), 'badge');
        setText('live-extra', 'SL ' + fmt(data.featured_position.stop_loss, 4) + ' | TP ' + fmt(data.featured_position.take_profit, 4) + ' | LEV ' + fmt(data.featured_position.leverage, 1) + 'x');
      }} else {{
        document.getElementById('live-dot').className = 'live-dot idle';
        setText('live-symbol', 'NO POSITION');
        setText('live-side', 'STANDBY', 'live-side side-flat');
        setText('live-pnl', 'PNL 0.00', 'badge');
        setText('live-entry', 'ENTRY 0.00', 'badge');
        setText('live-mark', 'MARK 0.00', 'badge');
        setText('live-extra', 'Waiting for active trades.');
      }}

      const positionsBody = document.getElementById('positions-body');
      positionsBody.innerHTML = '';
      if (!data.positions.length) {{
        positionsBody.innerHTML = '<tr><td colspan="7" class="small">No open positions.</td></tr>';
      }}
      for (const row of data.positions) {{
        const rowClass = row.unrealized_pnl > 0 ? 'profit-row' : row.unrealized_pnl < 0 ? 'loss-row' : '';
        const sideClass = row.side === 'Buy' ? 'profit-chip' : 'loss-chip';
        positionsBody.innerHTML += `
          <tr class="${{rowClass}}">
            <td>${{row.symbol}}</td>
            <td class="${{sideClass}}">${{row.side === 'Buy' ? 'LONG' : 'SHORT'}}</td>
            <td>${{fmt(row.size, 4)}}</td>
            <td>${{fmt(row.entry_price, 4)}}</td>
            <td>${{fmt(row.mark_price, 4)}}</td>
            <td class="${{pnlClass(row.unrealized_pnl)}}">${{fmt(row.unrealized_pnl)}} USDT</td>
            <td>${{fmt(row.stop_loss, 4)}} / ${{fmt(row.take_profit, 4)}}</td>
          </tr>`;
      }}

      const tradesBody = document.getElementById('trades-body');
      tradesBody.innerHTML = '';
      if (!data.closed_trades.length) {{
        tradesBody.innerHTML = '<tr><td colspan="4" class="small">No closed trades yet.</td></tr>';
      }}
      for (const row of data.closed_trades) {{
        const rowClass = row.pnl > 0 ? 'profit-row' : row.pnl < 0 ? 'loss-row' : '';
        const pnlClassName = row.pnl > 0 ? 'profit-chip' : row.pnl < 0 ? 'loss-chip' : '';
        const sideClass = row.side === 'Buy' ? 'profit-chip' : 'loss-chip';
        tradesBody.innerHTML += `
          <tr class="${{rowClass}}">
            <td>${{row.symbol}}</td>
            <td class="${{sideClass}}">${{row.side === 'Buy' ? 'LONG' : 'SHORT'}}</td>
            <td class="${{pnlClassName}}">${{fmt(row.pnl)}} USDT</td>
            <td>${{row.closed_at || ''}}</td>
          </tr>`;
      }}

      const headlines = document.getElementById('headlines');
      headlines.innerHTML = '';
      if (!data.news.headlines.length) {{
        headlines.innerHTML = '<div class="small">No elevated headlines in the current lookback window.</div>';
      }}
      for (const headline of data.news.headlines) {{
        headlines.innerHTML += `<div class="headline">${{headline}}</div>`;
      }}

      const patternsBody = document.getElementById('patterns-body');
      patternsBody.innerHTML = '';
      if (!data.learning_patterns.length) {{
        patternsBody.innerHTML = '<tr><td colspan="4" class="small">No learning patterns recorded yet.</td></tr>';
      }}
      for (const row of data.learning_patterns) {{
        patternsBody.innerHTML += `
          <tr>
            <td>${{row.pattern}}</td>
            <td>${{row.wins}} / ${{row.losses}}</td>
            <td>${{row.loss_streak}}</td>
            <td class="${{pnlClass(row.last_pnl)}}">${{fmt(row.last_pnl)}} USDT</td>
          </tr>`;
      }}

      const signalFeed = document.getElementById('signal-feed');
      signalFeed.innerHTML = '';
      if (!data.recent_signals.length) {{
        signalFeed.innerHTML = '<div class="small">No recent director messages.</div>';
      }}
      for (const row of data.recent_signals) {{
        const feedClass = row.type === 'open' ? 'feed-open' : row.type === 'news' ? 'feed-news' : 'feed-signal';
        signalFeed.innerHTML += `
          <div class="feed-item ${{feedClass}}">
            <div class="feed-meta">${{row.type}} | ${{row.timestamp}}</div>
            <div>${{row.message}}</div>
          </div>`;
      }}
    }}

    loadData();
    setInterval(loadData, refreshMs);
  </script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    provider: DashboardDataProvider | None = None
    dashboard_title = "RockTrade Mission Control"
    refresh_seconds = 5
    auth_username = ""
    auth_password = ""

    def do_GET(self) -> None:
        if not self._is_authorized():
            self._request_auth()
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._handle_api()
            return
        if parsed.path == "/":
            self._handle_index()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_api(self) -> None:
        assert self.provider is not None
        payload = self.provider.build_payload()
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle_index(self) -> None:
        raw = render_dashboard_html(self.dashboard_title, self.refresh_seconds).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _is_authorized(self) -> bool:
        if not self.auth_username or not self.auth_password:
            return False
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        if ":" not in decoded:
            return False
        username, password = decoded.split(":", 1)
        return (
            secrets.compare_digest(username, self.auth_username)
            and secrets.compare_digest(password, self.auth_password)
        )

    def _request_auth(self) -> None:
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="ROCKTRADE Dashboard"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authentication required.")

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    load_dotenv(Path(".env"))
    config = load_config()
    logger = setup_logger()
    DashboardHandler.provider = DashboardDataProvider(config, logger)
    DashboardHandler.dashboard_title = config["dashboard"].get("title", "RockTrade Mission Control")
    DashboardHandler.refresh_seconds = int(config["dashboard"].get("refresh_seconds", 5))
    DashboardHandler.auth_username = os.getenv("DASHBOARD_USERNAME", "").strip()
    DashboardHandler.auth_password = os.getenv("DASHBOARD_PASSWORD", "").strip()
    host = config["dashboard"].get("host", "0.0.0.0")
    port = int(config["dashboard"].get("port", 8080))

    if not DashboardHandler.auth_username or not DashboardHandler.auth_password:
        raise RuntimeError("DASHBOARD_USERNAME and DASHBOARD_PASSWORD must be set in .env for dashboard access.")

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    logger.info("Dashboard server started on http://%s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
