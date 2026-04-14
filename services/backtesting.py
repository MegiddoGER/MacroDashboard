"""
services/backtesting.py — Vektorisierte Backtesting Engine.

Simuliert verschiedene Handelsstrategien auf historischen OHLCV-Daten
unter Berücksichtigung von Gebühren (z.B. Trade Republic/Scalable) und Slippage.

Metriken: Sharpe Ratio, Sortino Ratio, Calmar Ratio, Max Drawdown,
          Win-Rate, Profit Factor, annualisierte Rendite, Volatilität.
"""

import pandas as pd
import numpy as np
from datetime import datetime


class BacktestEngine:
    """Führt performante vektorisierte Backtests auf Pandas-Dataframes aus."""

    def __init__(self, hist_data: pd.DataFrame, initial_capital: float = 10000.0,
                 commission: float = 1.0, slippage_pct: float = 0.1):
        """
        Args:
            hist_data: OHLCV DataFrame
            initial_capital: Startkapital in Euro.
            commission: Festpreis pro Trade (z.B. 1.00€ bei Trade Republic).
            slippage_pct: Abweichung des Ausführungskurses in Prozent (z.B. 0.1 = 0.1%).
        """
        self.df = hist_data.copy()
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage_pct / 100.0
        
        # Wichtige Indikatoren vorab berechnen
        self._calculate_base_indicators()

    def _calculate_base_indicators(self):
        """Berechnet gängige Indikatoren, damit Strategien rasant filtern können."""
        close = self.df["Close"]
        
        # SMAs
        self.df["SMA_50"] = close.rolling(window=50).mean()
        self.df["SMA_200"] = close.rolling(window=200).mean()
        
        # RSI 14 (Wilder EMA — Industriestandard, konsistent mit services/technical.py)
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss
        self.df["RSI_14"] = 100 - (100 / (1 + rs))
        
        # MACD (12, 26, 9)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        self.df["MACD"] = exp1 - exp2
        self.df["MACD_Signal"] = self.df["MACD"].ewm(span=9, adjust=False).mean()
        
        # Bollinger Bands (20, 2)
        sma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        self.df["BB_Upper"] = sma20 + (std20 * 2)
        self.df["BB_Lower"] = sma20 - (std20 * 2)
        
        # Proxy für SMC FVG Bounces (vektorisiert, SMC-konform)
        # Echte FVG: Low[i] > High[i-2] (3-Candle-Gap) + Mindest-Gapgröße
        h_prev2 = self.df["High"].shift(2)       # High der 1. Kerze (i-2)
        l_curr = self.df["Low"]                    # Low der 3. Kerze (i)
        gap_size = l_curr - h_prev2
        min_gap_pct = 0.005  # 0.5% Mindest-Gap (wie in smc/indicators.py)
        is_fvg_bullish = (gap_size > 0) & (gap_size / h_prev2 >= min_gap_pct)
        self.df["SM_FVG"] = is_fvg_bullish
        
        # Drop NaNs — nur für SMA 200 wenn die Strategie es braucht,
        # aber markiere den sauberen Bereich statt Rows destruktiv zu löschen
        self.df.dropna(subset=["SMA_200"], inplace=True)

    def run_strategy(self, strategy_name: str) -> tuple[pd.DataFrame, list[dict], dict]:
        """Führt eine benannte Strategie aus.
        
        Returns:
            equity_df: DataFrame mit Portfolio-Entwicklung über Zeit
            trades_log: Liste aller durchgeführten Trades
            metrics: Z.B. Win-Rate, Net Profit, Sharpe, Sortino.
        """
        # Alle Signal-Logiken geben eine Series von 1 (Buy), -1 (Sell) oder 0 (Hold) zurück
        if strategy_name == "SMA_Cross_Trend":
            signals = self._strat_sma_cross()
        elif strategy_name == "RSI_Mean_Reversion":
            signals = self._strat_rsi_mean_reversion()
        elif strategy_name == "MACD_Momentum":
            signals = self._strat_macd_momentum()
        elif strategy_name == "Bollinger_Breakout":
            signals = self._strat_bollinger_breakout()
        elif strategy_name == "SMC_FVG_Bounce":
            signals = self._strat_smc_proxy()
        else:
            raise ValueError(f"Unbekannte Strategie: {strategy_name}")
            
        return self._simulate_portfolio(signals)

    # -----------------------------------------------------------------------
    # Strategie-Definitionen (Vectorized Signal Generation)
    # 1.0 = Position eröffnen/halten, 0.0 = Position schließen (Flat)
    # -----------------------------------------------------------------------

    def _strat_sma_cross(self) -> pd.Series:
        """Trendfolge: Kaufe wenn 50 crosses > 200."""
        long_cond = self.df["SMA_50"] > self.df["SMA_200"]
        return np.where(long_cond, 1.0, 0.0)

    def _strat_rsi_mean_reversion(self) -> pd.Series:
        """Oszillator: Kaufe bei starkem Oversold, halte bis Overbought oder Stop."""
        buy = (self.df["RSI_14"] < 30)
        sell = (self.df["RSI_14"] > 70)
        
        # Vectorized State Machine: Vorwärts-Auffüllen (ffill) des States
        state = pd.Series(np.nan, index=self.df.index)
        state[buy] = 1.0
        state[sell] = 0.0
        state = state.ffill().fillna(0.0)
        return state

    def _strat_macd_momentum(self) -> pd.Series:
        """Kauft, wenn MACD die Signallinie von unten nach oben kreuzt."""
        long_cond = self.df["MACD"] > self.df["MACD_Signal"]
        return np.where(long_cond, 1.0, 0.0)
        
    def _strat_bollinger_breakout(self) -> pd.Series:
        """Trendfolge-Momo: Kaufe den Ausbruch nach oben."""
        buy = self.df["Close"] > self.df["BB_Upper"]
        sell = self.df["Close"] < self.df["SMA_50"]  # Ausstieg wenn Trend bricht
        
        state = pd.Series(np.nan, index=self.df.index)
        state[buy] = 1.0
        state[sell] = 0.0
        state = state.ffill().fillna(0.0)
        return state
        
    def _strat_smc_proxy(self) -> pd.Series:
        """Kaufe bei FVG Expansion, halte solange der Trend (SMA 50) hält."""
        buy = self.df["SM_FVG"] & (self.df["Close"] > self.df["SMA_50"])
        sell = self.df["Close"] < self.df["SMA_50"]
        
        state = pd.Series(np.nan, index=self.df.index)
        state[buy] = 1.0
        state[sell] = 0.0
        state = state.ffill().fillna(0.0)
        return state

    # -----------------------------------------------------------------------
    # Portfolio-Simulation (Trades, Fee & Slippage Logic)
    # -----------------------------------------------------------------------

    def _simulate_portfolio(self, position_series: pd.Series) -> tuple[pd.DataFrame, list[dict], dict]:
        """Berechnet die Equity-Kurve für die generierten Positionen, 
        inklusive fixen Gebühren und %-Slippage."""
        
        df = self.df.copy()
        # position_series kann ein numpy-Array sein (z.B. von np.where),
        # daher erst in pandas Series konvertieren für .shift()
        if not isinstance(position_series, pd.Series):
            position_series = pd.Series(position_series, index=df.index)
        df["Position"] = position_series.shift(1).fillna(0) # Signal am Vortag entstanden -> Trade am Open des aktuellen Tags
        
        trades = []
        in_trade = False
        entry_price = 0.0
        entry_date = None
        shares_held = 0.0
        entry_cost = 0.0       # Gesamtkosten beim Einstieg (inkl. Gebühr)

        capital = self.initial_capital
        df["Equity"] = float(capital)
        df["Benchmark"] = float(capital)  # Buy&Hold Startkapital
        
        bnh_shares = capital / df["Open"].iloc[0]
        
        for i in range(len(df)):
            date = df.index[i]
            pos = df["Position"].iloc[i]
            open_p = df["Open"].iloc[i]
            close_p = df["Close"].iloc[i]
            
            # Buy & Hold (Benchmark) Verlauf
            df.loc[date, "Benchmark"] = bnh_shares * close_p
            
            # Entry!
            if pos == 1.0 and not in_trade:
                # Execution with Slippage (Kaufkurs = Open + Slippage)
                exec_price = open_p * (1 + self.slippage)
                # Kapital nach Gebühr
                investable = capital - self.commission
                
                if investable > 0:
                    shares_held = investable / exec_price
                    entry_price = exec_price
                    entry_date = date
                    entry_cost = investable + self.commission  # = capital
                    in_trade = True
                    capital = 0.0 # Voll investiert
                    
            # Exit!
            elif pos == 0.0 and in_trade:
                # Execution with Slippage (Verkaufskurs = Open - Slippage)
                exec_price = open_p * (1 - self.slippage)
                
                revenue = shares_held * exec_price - self.commission
                capital = revenue

                # P&L = Verkaufserlös (nach Gebühr) − Kaufkosten (nach Gebühr)
                trade_pnl_eur = revenue - entry_cost
                trade_pnl_pct = (exec_price / entry_price - 1) * 100
                
                trades.append({
                    "entry_date": entry_date.strftime("%Y-%m-%d"),
                    "exit_date": date.strftime("%Y-%m-%d"),
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(exec_price, 4),
                    "shares": round(shares_held, 4),
                    "pnl_eur": round(trade_pnl_eur, 2),
                    "pnl_pct": round(trade_pnl_pct, 2),
                })
                
                shares_held = 0.0
                entry_cost = 0.0
                in_trade = False

            # Mark to Market (Täglicher Portfolio Wert)
            if in_trade:
                df.loc[date, "Equity"] = shares_held * close_p
            else:
                df.loc[date, "Equity"] = capital

        # Force Close am Ende der Testperiode falls noch offener Trade
        if in_trade:
            exec_price = df["Close"].iloc[-1] * (1 - self.slippage)
            revenue = shares_held * exec_price - self.commission
            capital = revenue
            trade_pnl_eur = revenue - entry_cost
            trade_pnl_pct = (exec_price / entry_price - 1) * 100
            trades.append({
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "exit_date": df.index[-1].strftime("%Y-%m-%d"),
                "entry_price": round(entry_price, 4),
                "exit_price": round(exec_price, 4),
                "shares": round(shares_held, 4),
                "pnl_eur": round(trade_pnl_eur, 2),
                "pnl_pct": round(trade_pnl_pct, 2),
            })
            df.loc[df.index[-1], "Equity"] = capital

        # -------------------------------------------------------------------
        # Drawdown-Serie (für Chart-Export)
        # -------------------------------------------------------------------
        roll_max = df["Equity"].cummax()
        df["Drawdown"] = (df["Equity"] - roll_max) / roll_max * 100

        # -------------------------------------------------------------------
        # Metrics Calculation
        # -------------------------------------------------------------------
        equity_arr = df["Equity"].values.astype(float)
        total_return_pct = (equity_arr[-1] / self.initial_capital - 1) * 100
        bnh_return_pct = (df["Benchmark"].iloc[-1] / self.initial_capital - 1) * 100
        max_dd = df["Drawdown"].min()

        # Tägliche Returns für risikoadjustierte Metriken
        daily_returns = np.diff(equity_arr) / equity_arr[:-1]
        daily_returns = daily_returns[np.isfinite(daily_returns)]

        # Annualisierung
        n_days = len(equity_arr)
        total_return_dec = equity_arr[-1] / self.initial_capital - 1
        ann_return = (1 + total_return_dec) ** (252 / max(n_days, 1)) - 1
        ann_volatility = np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0.0

        # Sharpe Ratio (Risk-free ≈ 4% p.a. aktuelle Phase)
        rf_daily = 0.04 / 252
        sharpe = None
        if len(daily_returns) > 5:
            excess = daily_returns - rf_daily
            if np.std(excess) > 0:
                sharpe = round(np.mean(excess) / np.std(excess) * np.sqrt(252), 2)

        # Sortino Ratio (nur Downside-Volatilität)
        sortino = None
        if len(daily_returns) > 5:
            downside = daily_returns[daily_returns < 0]
            if len(downside) > 0 and np.std(downside) > 0:
                sortino = round(
                    (np.mean(daily_returns) - rf_daily) / np.std(downside) * np.sqrt(252), 2)

        # Calmar Ratio (Ann. Return / Max DD)
        calmar = None
        if max_dd < 0 and ann_return != 0:
            calmar = round(ann_return / abs(max_dd / 100), 2)

        # Trade-Level Metriken
        if trades:
            wins = [t for t in trades if t["pnl_eur"] > 0]
            losses = [t for t in trades if t["pnl_eur"] <= 0]
            win_rate = (len(wins) / len(trades)) * 100
            
            gross_profit = sum(t["pnl_eur"] for t in wins)
            gross_loss = abs(sum(t["pnl_eur"] for t in losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 99.9
            
            avg_win = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
            avg_loss = float(np.mean([t["pnl_pct"] for t in losses])) if losses else 0.0
            best_trade = max(t["pnl_pct"] for t in trades)
            worst_trade = min(t["pnl_pct"] for t in trades)

            # Durchschnittliche Haltedauer
            holding_days = []
            for t in trades:
                try:
                    bd = datetime.strptime(t["entry_date"], "%Y-%m-%d")
                    sd = datetime.strptime(t["exit_date"], "%Y-%m-%d")
                    holding_days.append((sd - bd).days)
                except ValueError:
                    pass
            avg_hold = round(float(np.mean(holding_days)), 1) if holding_days else 0.0
        else:
            win_rate = 0.0
            profit_factor = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            best_trade = 0.0
            worst_trade = 0.0
            avg_hold = 0.0

        metrics = {
            "initial_capital": self.initial_capital,
            "final_capital": round(equity_arr[-1], 2),
            "total_return_pct": round(total_return_pct, 2),
            "benchmark_return_pct": round(bnh_return_pct, 2),
            "outperformance": round(total_return_pct - bnh_return_pct, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "total_trades": len(trades),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "best_trade_pct": round(best_trade, 2),
            "worst_trade_pct": round(worst_trade, 2),
            "avg_holding_days": avg_hold,
            "commission_paid": round(len(trades) * 2 * self.commission, 2),
            # Risikoadjustierte Metriken
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "annualized_return_pct": round(ann_return * 100, 2),
            "volatility_pct": round(ann_volatility * 100, 2),
        }

        return df[["Equity", "Benchmark", "Close", "Position", "Drawdown"]], trades, metrics
