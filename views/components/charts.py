"""
charts.py — Plotly-Chart-Builder (dark theme, clean design).
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Gemeinsame Layout-Defaults
# ---------------------------------------------------------------------------

LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=50, b=30, l=10),
    font=dict(family="Inter, sans-serif", size=12, color="#cbd5e1"),
    hovermode="x unified",
    xaxis=dict(
        automargin=True,
        gridcolor="rgba(148,163,184,0.06)",
        zerolinecolor="rgba(148,163,184,0.1)",
        ticks="outside",
        tickwidth=1,
        ticklen=5,
        tickcolor="rgba(148,163,184,0.3)",
    ),
    yaxis=dict(
        automargin=True,
        gridcolor="rgba(148,163,184,0.06)",
        zerolinecolor="rgba(148,163,184,0.1)",
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=11, color="#94a3b8"),
    ),
    modebar=dict(
        bgcolor="rgba(0,0,0,0)",
        color="#ffffff",
        activecolor="#00d4aa"
    ),
)


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ", ".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def _base_layout(**overrides):
    """Merged LAYOUT_DEFAULTS with overrides, handling nested dicts."""
    layout = {k: v for k, v in LAYOUT_DEFAULTS.items()}
    layout.update(overrides)
    return layout


# ---------------------------------------------------------------------------
# Generischer Timeseries-Chart (Linie)
# ---------------------------------------------------------------------------

def plot_timeseries(df, title: str, y_col: str = "Close",
                    color: str = "#00d4aa", height: int = 350) -> go.Figure:
    """Linien-Chart für eine Zeitreihe (DataFrame oder Series)."""
    fig = go.Figure()
    if isinstance(df, pd.Series):
        x, y = df.index, df
    else:
        x, y = df.index, df[y_col]
    # Unsichtbare Basis-Linie auf Y=0 erzwingt sauberes SVG-Rendering beim Zoomen
    fig.add_trace(go.Scatter(
        x=x, y=[0] * len(x), mode="lines",
        line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip",
    ))
    
    # Eigentliche Linie füllt zur unsichtbaren Basis-Linie (tonexty)
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color=color, width=1.8),
        fill="tonexty",
        fillcolor=f"rgba({_hex_to_rgb(color)}, 0.06)",
        name=title,
        hovertemplate="%{y:,.2f} €<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=height, showlegend=False,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Candlestick-Chart mit SMAs + Volumen
# ---------------------------------------------------------------------------

def plot_candlestick(df: pd.DataFrame, title: str,
                     sma_20=None, sma_50=None, sma_200=None) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
        increasing_fillcolor="#22c55e", decreasing_fillcolor="#ef4444",
        name="OHLC",
    ), row=1, col=1)

    for sma, name, color in [
        (sma_20, "SMA 20", "#f59e0b"),
        (sma_50, "SMA 50", "#3b82f6"),
        (sma_200, "SMA 200", "#a855f7"),
    ]:
        if sma is not None and not sma.dropna().empty:
            fig.add_trace(go.Scatter(
                x=sma.index, y=sma, mode="lines",
                line=dict(color=color, width=1, dash="dot"), name=name,
            ), row=1, col=1)

    # Unsichtbare Puffer-Punkte für angenehmes Zoom/Pan-Verhalten
    if not df.empty and len(df) > 1:
        x_min, x_max = df.index.min(), df.index.max()
        dx = (x_max - x_min) * 0.05
        y_min, y_max = df["Low"].min(), df["High"].max()
        dy = (y_max - y_min) * 0.08
        fig.add_trace(go.Scatter(
            x=[x_min - dx, x_max + dx],
            y=[max(0.0001, y_min - dy), y_max + dy],
            mode="markers", marker=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip"
        ), row=1, col=1)

    if "Volume" in df.columns:
        colors = ["#22c55e" if c >= o else "#ef4444"
                  for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color=colors, opacity=0.4,
            name="Volumen", showlegend=False,
        ), row=2, col=1)

    # Detect intraday data by checking time differences
    is_intraday = False
    if len(df) > 1:
        diff = df.index[1] - df.index[0]
        if diff < pd.Timedelta(days=1):
            is_intraday = True

    # Build base layout by copying the global defaults
    layout = {k: v for k, v in LAYOUT_DEFAULTS.items()}
    layout["title"] = dict(text=title, font=dict(size=14))
    layout["height"] = 500
    
    # Rangebreaks logic (only apply if the data doesn't have weekends, i.e. stocks)
    has_weekends = (df.index.weekday >= 5).any() if not df.empty else False
    layout["xaxis"] = dict(layout.get("xaxis", {}))
    
    if not has_weekends:
        layout["xaxis"]["rangebreaks"] = [dict(bounds=["sat", "mon"])]
        
        if is_intraday:
            pass
            
    layout["xaxis"]["rangeslider"] = dict(visible=False)
    

    
    # Improve zoom behavior (pan by default to prevent distorted box-zoom stretching)
    layout["dragmode"] = "pan"
    layout["yaxis"] = dict(layout.get("yaxis", {}))
    layout["yaxis"]["type"] = "log"
    layout["yaxis"]["autorange"] = True

    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# RSI-Chart
# ---------------------------------------------------------------------------

def plot_rsi(rsi_series: pd.Series, title: str = "RSI (14)") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rsi_series.index, y=rsi_series,
        mode="lines", line=dict(color="#8b5cf6", width=1.5),
        name="RSI", hovertemplate="RSI: %{y:.1f}<extra></extra>",
    ))
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,68,68,0.07)", line_width=0)
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(34,197,94,0.07)", line_width=0)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", opacity=0.4,
                  annotation_text="Überkauft", annotation_font_color="#94a3b8")
    fig.add_hline(y=30, line_dash="dash", line_color="#22c55e", opacity=0.4,
                  annotation_text="Überverkauft", annotation_font_color="#94a3b8")
    fig.add_hline(y=50, line_dash="dot", line_color="#64748b", opacity=0.3)
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=220, showlegend=False,
        yaxis=dict(range=[0, 100], **LAYOUT_DEFAULTS.get("yaxis", {})),
        **{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "yaxis"},
    )
    return fig


# ---------------------------------------------------------------------------
# MACD-Chart
# ---------------------------------------------------------------------------

def plot_macd(macd_line: pd.Series, signal_line: pd.Series,
              histogram: pd.Series, title: str = "MACD") -> go.Figure:
    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Scatter(
        x=macd_line.index, y=macd_line, mode="lines",
        line=dict(color="#3b82f6", width=1.5), name="MACD",
    ))
    fig.add_trace(go.Scatter(
        x=signal_line.index, y=signal_line, mode="lines",
        line=dict(color="#f59e0b", width=1.5), name="Signal",
    ))
    colors = ["#22c55e" if v >= 0 else "#ef4444" for v in histogram]
    fig.add_trace(go.Bar(
        x=histogram.index, y=histogram,
        marker_color=colors, opacity=0.5, name="Histogram",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=250, **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Bollinger-Bands-Chart
# ---------------------------------------------------------------------------

def plot_bollinger(close: pd.Series, upper: pd.Series, middle: pd.Series,
                   lower: pd.Series, title: str = "Bollinger Bänder") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=upper.index, y=upper, mode="lines",
        line=dict(color="#64748b", width=1, dash="dot"), name="Oberes Band",
    ))
    fig.add_trace(go.Scatter(
        x=lower.index, y=lower, mode="lines",
        line=dict(color="#64748b", width=1, dash="dot"), name="Unteres Band",
        fill="tonexty", fillcolor="rgba(100,116,139,0.05)",
    ))
    fig.add_trace(go.Scatter(
        x=middle.index, y=middle, mode="lines",
        line=dict(color="#f59e0b", width=1), name="SMA 20",
    ))
    fig.add_trace(go.Scatter(
        x=close.index, y=close, mode="lines",
        line=dict(color="#00d4aa", width=1.5), name="Kurs",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=300, **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Stochastic Oscillator
# ---------------------------------------------------------------------------

def plot_stochastic(k_line: pd.Series, d_line: pd.Series,
                    title: str = "Stochastic Oscillator") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=k_line.index, y=k_line, mode="lines",
        line=dict(color="#3b82f6", width=1.5), name="%K",
    ))
    fig.add_trace(go.Scatter(
        x=d_line.index, y=d_line, mode="lines",
        line=dict(color="#f59e0b", width=1.5), name="%D",
    ))
    fig.add_hrect(y0=80, y1=100, fillcolor="rgba(239,68,68,0.07)", line_width=0)
    fig.add_hrect(y0=0, y1=20, fillcolor="rgba(34,197,94,0.07)", line_width=0)
    fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", opacity=0.4)
    fig.add_hline(y=20, line_dash="dash", line_color="#22c55e", opacity=0.4)
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=220, yaxis=dict(range=[0, 100]),
        **{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "yaxis"},
    )
    return fig


# ---------------------------------------------------------------------------
# Returns-Distribution
# ---------------------------------------------------------------------------

def plot_returns_distribution(returns: pd.Series,
                              title: str = "Rendite-Verteilung") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=returns * 100, nbinsx=50,
        marker_color="#3b82f6", opacity=0.7, name="Tägliche Rendite",
        hovertemplate="%{x:.2f}%<br>Häufigkeit: %{y}<extra></extra>",
    ))
    fig.add_vline(x=0, line_dash="dash", line_color="#94a3b8", opacity=0.5)
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        xaxis_title="Tägliche Rendite (%)", yaxis_title="Häufigkeit",
        height=280, showlegend=False, bargap=0.05,
        **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Yield-Spread-Chart
# ---------------------------------------------------------------------------

def plot_yield_spread(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    # Unsichtbare Basis-Linie
    fig.add_trace(go.Scatter(
        x=df.index, y=[0] * len(df), mode="lines",
        line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Spread"], mode="lines",
        line=dict(color="#f59e0b", width=1.8),
        fill="tonexty", fillcolor="rgba(245,158,11,0.08)",
        name="10Y – Short Spread",
        hovertemplate="Spread: %{y:.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#ef4444", opacity=0.5,
                  annotation_text="Inversion", annotation_position="bottom left",
                  annotation_font_color="#94a3b8")
    fig.update_layout(
        title=dict(text="Zinsstrukturkurve (10Y − kurzfristige Zinsen)",
                   font=dict(size=14)),
        yaxis_title="Spread (%)", height=350, **LAYOUT_DEFAULTS,
    )
    return fig


# ---------------------------------------------------------------------------
# Inflations-Chart
# ---------------------------------------------------------------------------

def plot_inflation(df: pd.DataFrame,
                   title: str = "Inflationsrate Deutschland") -> go.Figure:
    fig = go.Figure()
    # Unsichtbare Basis-Linie
    fig.add_trace(go.Scatter(
        x=df.index, y=[0] * len(df), mode="lines",
        line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Inflation %"], mode="lines",
        line=dict(color="#ef4444", width=1.8),
        fill="tonexty", fillcolor="rgba(239,68,68,0.06)",
        name="Inflation %",
        hovertemplate="%{y:.1f} %<extra></extra>",
    ))
    fig.add_hline(y=2.0, line_dash="dash", line_color="#22c55e", opacity=0.5,
                  annotation_text="EZB-Ziel (2%)", annotation_position="top left",
                  annotation_font_color="#94a3b8")
    layout = {k: v for k, v in LAYOUT_DEFAULTS.items()}
    if "xaxis" in layout and "rangebreaks" in layout["xaxis"]:
        # We need a deep copy of the xaxis dict to not mutate the generic layout globally
        layout_xaxis = layout["xaxis"].copy()
        layout_xaxis.pop("rangebreaks", None)
        layout["xaxis"] = layout_xaxis

    layout["title"] = dict(text=title, font=dict(size=14))
    layout["yaxis_title"] = "Inflation (%)"
    layout["height"] = 350

    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Fear & Greed Gauge
# ---------------------------------------------------------------------------

def plot_fear_greed_gauge(value: float, label: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": f"Fear & Greed — {label}",
               "font": {"size": 16, "color": "#cbd5e1"}},
        number={"font": {"size": 42, "color": "#e2e8f0"}, "suffix": " / 100"},
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor="#475569",
                      tickfont=dict(color="#64748b", size=10)),
            bar=dict(color="#f8fafc", thickness=0.2),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[
                dict(range=[0, 20], color="#991b1b"),
                dict(range=[20, 40], color="#c2410c"),
                dict(range=[40, 60], color="#a16207"),
                dict(range=[60, 80], color="#15803d"),
                dict(range=[80, 100], color="#166534"),
            ],
            threshold=dict(
                line=dict(color="#f8fafc", width=2),
                thickness=0.75, value=value,
            ),
        ),
    ))
    fig.update_layout(
        height=260,
        **{k: v for k, v in LAYOUT_DEFAULTS.items() if k != "hovermode"},
    )
    return fig


# ---------------------------------------------------------------------------
# Korrelationsmatrix-Heatmap
# ---------------------------------------------------------------------------

def plot_correlation_matrix(corr_df: pd.DataFrame,
                            title: str = "Korrelationsmatrix") -> go.Figure:
    """Annotated Heatmap: Blau (-1) → Weiß (0) → Rot (+1)."""
    labels = list(corr_df.columns)
    z = corr_df.values

    # Annotationstext (Werte in jeder Zelle)
    text = [[f"{v:.2f}" for v in row] for row in z]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=labels, y=labels,
        text=text, texttemplate="%{text}",
        textfont=dict(size=11, color="#e2e8f0"),
        colorscale=[
            [0.0, "#1e40af"],   # -1  → Dunkelblau
            [0.5, "#1e293b"],   # 0   → Dunkles Grau (passend zum Theme)
            [1.0, "#dc2626"],   # +1  → Rot
        ],
        zmin=-1, zmax=1,
        colorbar=dict(
            title=dict(text="ρ", font=dict(color="#94a3b8")),
            tickvals=[-1, -0.5, 0, 0.5, 1],
            tickfont=dict(color="#94a3b8"),
        ),
        hovertemplate="%{x} ↔ %{y}<br>Korrelation: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=max(350, 50 * len(labels) + 100),
        xaxis=dict(side="bottom", tickfont=dict(color="#cbd5e1")),
        yaxis=dict(autorange="reversed", tickfont=dict(color="#cbd5e1")),
        **{k: v for k, v in LAYOUT_DEFAULTS.items()
           if k not in ("xaxis", "yaxis", "hovermode")},
    )
    return fig


# ---------------------------------------------------------------------------
# Sektor-Heatmap (Bloomberg-Style Treemap)
# ---------------------------------------------------------------------------

def plot_sector_heatmap(sector_df: pd.DataFrame,
                        title: str = "Sektor-Performance") -> go.Figure:
    """Treemap: Größe proportional, Farbe = Performance (rot/grün)."""
    # Absolute Werte für die Größe (damit negative auch sichtbar sind)
    sector_df = sector_df.copy()
    sector_df["_size"] = 1  # Gleiche Kachelgröße für alle Sektoren

    fig = go.Figure(go.Treemap(
        labels=sector_df["Sektor"],
        parents=[""] * len(sector_df),
        values=sector_df["_size"],
        text=sector_df.apply(
            lambda r: f"{r['Veränderung %']:+.2f}%", axis=1
        ),
        texttemplate="<b>%{label}</b><br>%{text}",
        textfont=dict(size=14),
        marker=dict(
            colors=sector_df["Veränderung %"],
            colorscale=[
                [0.0, "#991b1b"],   # stark negativ → dunkelrot
                [0.35, "#ef4444"],  # leicht negativ → rot
                [0.5, "#1e293b"],   # neutral → dunkel
                [0.65, "#22c55e"],  # leicht positiv → grün
                [1.0, "#166534"],   # stark positiv → dunkelgrün
            ],
            cmid=0,
            line=dict(color="#0f172a", width=2),
            colorbar=dict(
                title=dict(text="% Δ", font=dict(color="#94a3b8")),
                tickfont=dict(color="#94a3b8"),
            ),
        ),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Veränderung: %{text}<br>"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#e2e8f0")),
        height=500,
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif"),
    )
    return fig


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Liquidity Sweep Chart
# ---------------------------------------------------------------------------

def plot_liquidity_sweeps(df: pd.DataFrame, sweeps: list[dict],
                          title: str = "Liquidity Sweeps") -> go.Figure:
    """Candlestick-Chart mit markierten Sweep-Zonen (Pfeile)."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.8, 0.2], vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
        increasing_fillcolor="#22c55e", decreasing_fillcolor="#ef4444",
        name="OHLC", showlegend=False,
    ), row=1, col=1)

    # Volumen
    if "Volume" in df.columns:
        colors = ["#22c55e" if c >= o else "#ef4444"
                  for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(go.Bar(
            x=df.index, y=df["Volume"],
            marker_color=colors, opacity=0.3,
            name="Volumen", showlegend=False,
        ), row=2, col=1)

    # Sweep-Markierungen
    for s in sweeps:
        if s["type"] == "bullish":
            color = "#22c55e"
            symbol = "triangle-up"
            label = "🟢 Bull Sweep"
        else:
            color = "#ef4444"
            symbol = "triangle-down"
            label = "🔴 Bear Sweep"

        fig.add_trace(go.Scatter(
            x=[s["sweep_date"]], y=[s["level"]],
            mode="markers",
            marker=dict(symbol=symbol, size=14, color=color,
                        line=dict(width=1, color="#fff")),
            name=label, showlegend=False,
            hovertemplate=(
                f"{label}<br>"
                f"Level: {s['level']:,.2f} €<br>"
                f"Sweep: %{{x}}<extra></extra>"
            ),
        ), row=1, col=1)

        # Horizontale Linie am Sweep-Level
        fig.add_hline(
            y=s["level"], line_dash="dot", line_color=color,
            opacity=0.3, row=1, col=1,
        )

    layout = {k: v for k, v in LAYOUT_DEFAULTS.items() if k not in ("xaxis", "yaxis", "hovermode")}
    layout["title"] = dict(text=title, font=dict(size=14))
    layout["height"] = 450
    layout["xaxis_rangeslider_visible"] = False
    layout["dragmode"] = "pan"

    has_weekends = (df.index.weekday >= 5).any() if not df.empty else False
    if not has_weekends:
        layout["xaxis"] = dict(rangebreaks=[dict(bounds=["sat", "mon"])])

    fig.update_layout(**layout)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.06)")
    # Apply gridcolor selectively because we may have instantiated xaxis above
    if getattr(fig.layout, "xaxis", None):
        fig.update_xaxes(gridcolor="rgba(148,163,184,0.06)")
    return fig


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Swing Trading Übersicht
# ---------------------------------------------------------------------------

def plot_swing_overview(df: pd.DataFrame, swing_data: dict,
                        title: str = "Swing Trading") -> go.Figure:
    """Kurs mit Support/Resistance-Linien und SMA-Crosses."""
    fig = go.Figure()

    # Kurs als Linie
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], mode="lines",
        line=dict(color="#00d4aa", width=1.5), name="Kurs",
    ))

    # SMA 20 + 50
    sma20 = swing_data.get("sma20_series")
    sma50 = swing_data.get("sma50_series")
    if sma20 is not None:
        fig.add_trace(go.Scatter(
            x=sma20.index, y=sma20, mode="lines",
            line=dict(color="#f59e0b", width=1, dash="dot"), name="SMA 20",
        ))
    if sma50 is not None:
        fig.add_trace(go.Scatter(
            x=sma50.index, y=sma50, mode="lines",
            line=dict(color="#3b82f6", width=1, dash="dot"), name="SMA 50",
        ))

    # Pivot, S1, S2, R1, R2 als horizontale Linien
    levels = [
        ("R2", swing_data.get("r2"), "#ef4444", "dot"),
        ("R1", swing_data.get("r1"), "#f87171", "dash"),
        ("Pivot", swing_data.get("pivot"), "#94a3b8", "dash"),
        ("S1", swing_data.get("s1"), "#4ade80", "dash"),
        ("S2", swing_data.get("s2"), "#22c55e", "dot"),
    ]
    for label, val, color, dash in levels:
        if val is not None:
            fig.add_hline(
                y=val, line_dash=dash, line_color=color, opacity=0.5,
                annotation_text=f"{label}: {val:,.2f}",
                annotation_font_color=color,
                annotation_position="right",
            )

    # Stop Loss + Take Profit Zonen
    sl = swing_data.get("stop_loss")
    tp = swing_data.get("take_profit")
    if sl:
        fig.add_hline(
            y=sl, line_dash="dot", line_color="#ef4444", opacity=0.7,
            annotation_text=f"SL: {sl:,.2f}",
            annotation_font_color="#ef4444",
        )
    if tp:
        fig.add_hline(
            y=tp, line_dash="dot", line_color="#22c55e", opacity=0.7,
            annotation_text=f"TP: {tp:,.2f}",
            annotation_font_color="#22c55e",
        )

    layout = {k: v for k, v in LAYOUT_DEFAULTS.items()}
    layout["title"] = dict(text=title, font=dict(size=14))
    layout["height"] = 420
    layout["dragmode"] = "pan"

    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Order Flow Chart
# ---------------------------------------------------------------------------

def plot_order_flow(df: pd.DataFrame, flow_data: dict,
                    title: str = "Order Flow") -> go.Figure:
    """3-Row Subplot: Preis+VWAP, OBV, Volume-Profil."""
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=False,
        row_heights=[0.45, 0.25, 0.30],
        vertical_spacing=0.08,
        subplot_titles=["Kurs + VWAP", "On-Balance Volume (OBV)",
                        "Volume-Profil"],
    )

    # ── Row 1: Kurs + VWAP ──
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], mode="lines",
        line=dict(color="#00d4aa", width=1.5), name="Kurs",
    ), row=1, col=1)

    vwap = flow_data.get("vwap")
    if vwap is not None:
        fig.add_trace(go.Scatter(
            x=vwap.index, y=vwap, mode="lines",
            line=dict(color="#a855f7", width=1.5, dash="dash"), name="VWAP",
        ), row=1, col=1)

    # POC-Linie
    poc = flow_data.get("poc_price")
    if poc:
        fig.add_hline(
            y=poc, line_dash="dot", line_color="#f59e0b", opacity=0.6,
            annotation_text=f"POC: {poc:,.2f}",
            annotation_font_color="#f59e0b",
            row=1, col=1,
        )

    # Row 2: OBV
    obv = flow_data.get("obv")
    if obv is not None:
        # Unsichtbare Basis-Linie für OBV (bei OBV ist die Basis flexibel, wir nehmen das Minimum als Basis, nicht 0)
        obv_min = obv.min()
        fig.add_trace(go.Scatter(
            x=obv.index, y=[obv_min] * len(obv), mode="lines",
            line=dict(width=0, color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=obv.index, y=obv, mode="lines",
            line=dict(color="#3b82f6", width=1.5), name="OBV",
            fill="tonexty", fillcolor="rgba(59,130,246,0.06)",
        ), row=2, col=1)

    # ── Row 3: Volume-Profil (Horizontal-Histogramm) ──
    vol_profile = flow_data.get("vol_profile")
    if vol_profile is not None:
        fig.add_trace(go.Bar(
            x=vol_profile["Volumen"],
            y=vol_profile["Preis"],
            orientation="h",
            marker_color="#64748b", opacity=0.7,
            name="Volume-Profil", showlegend=False,
        ), row=3, col=1)

        # POC im Volume-Profil hervorheben
        if poc:
            fig.add_hline(
                y=poc, line_dash="dash", line_color="#f59e0b", opacity=0.8,
                row=3, col=1,
            )

    layout = {k: v for k, v in LAYOUT_DEFAULTS.items() if k not in ("xaxis", "yaxis", "hovermode")}
    layout["title"] = dict(text=title, font=dict(size=14))
    layout["height"] = 700
    layout["showlegend"] = True
    layout["dragmode"] = "pan"

    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.06)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.06)")

    # Subplot-Titel stylen
    for ann in fig.layout.annotations:
        ann.font.color = "#94a3b8"
        ann.font.size = 12

    return fig


# ---------------------------------------------------------------------------
# Finanzdaten Chart (Umsatz vs Nettogewinn)
# ---------------------------------------------------------------------------

def plot_financials_chart(fin_data: list[dict], title: str = "Umsatz & Nettogewinn") -> go.Figure:
    """Grouped Bar Chart für Umsatz und Nettogewinn pro Jahr."""
    years = [str(d["year"]) for d in fin_data]
    revenues = [d["revenue"] if d["revenue"] is not None else 0 for d in fin_data]
    net_incomes = [d["net_income"] if d["net_income"] is not None else 0 for d in fin_data]

    # Wir kehren die Liste um, um chronologisch (alt -> neu) von links nach rechts anzuzeigen
    years.reverse()
    revenues.reverse()
    net_incomes.reverse()

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=years,
        y=revenues,
        name='Umsatz',
        marker_color='#cbd5e1',  # Light gray
        hovertemplate="Umsatz: %{y:,.0f} €<extra></extra>"
    ))

    fig.add_trace(go.Bar(
        x=years,
        y=net_incomes,
        name='Nettogewinn',
        marker_color='#475569',  # Dark gray
        hovertemplate="Nettogewinn: %{y:,.0f} €<extra></extra>"
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        barmode='group',
        height=350,
        **LAYOUT_DEFAULTS
    )
    # X und Y Achsen Styling
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.06)", tickfont=dict(size=12, color="#94a3b8"))
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.06)", showticklabels=False) # Werte im Hover
    
    # Legende oben links
    fig.update_layout(legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0
    ))

    return fig

