import pandas as pd
import plotly.graph_objects as go
from charts import LAYOUT_DEFAULTS

def plot_smc(df: pd.DataFrame, smc_data: dict, title: str = "SMC (Makro-Level)") -> go.Figure:
    """Zeichnet den Candlestick-Chart mit FVG Rechtecken und EQH/EQL Linien."""
    fig = go.Figure()

    # 1. Candlestick Basis
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        increasing_fillcolor="#22c55e",
        decreasing_fillcolor="#ef4444",
        name="Kurs",
        showlegend=False,
    ))

    # 2. FVGs zeichnen (Rechtecke / Boxen)
    # Plotly erlaubt shapes im Layout für Rechtecke
    shapes = []
    
    # Letztes Datum im Chart für offene FVGs
    last_date = df.index[-1]
    
    for fvg in smc_data.get("fvgs", []):
        if fvg["type"] == "bullish":
            fillcolor = "rgba(34, 197, 94, 0.2)" # grün transparent
            linecolor = "rgba(34, 197, 94, 0.5)"
        else:
            fillcolor = "rgba(239, 68, 68, 0.2)" # rot transparent
            linecolor = "rgba(239, 68, 68, 0.5)"
            
        # Enddatum: entweder wann es gefüllt wurde, oder das aktuelle Chart-Ende
        end_date = fvg["mitigated_date"] if fvg["mitigated"] else last_date
        
        shapes.append(dict(
            type="rect",
            x0=fvg["date"],
            y0=fvg["bottom"],
            x1=end_date,
            y1=fvg["top"],
            fillcolor=fillcolor,
            line=dict(color=linecolor, width=1, dash="dot" if fvg["mitigated"] else "solid"),
            layer="below"
        ))

    # 3. EQH / EQL Linien zeichnen
    # Wir zeichnen sie als Hlines, die ab dem ersten High beginnen, oder als Segmente
    for eqh in smc_data.get("eqh", []):
        fig.add_trace(go.Scatter(
            x=[eqh["date1"], last_date],
            y=[eqh["level"], eqh["level"]],
            mode="lines",
            line=dict(color="#ef4444", width=2, dash="dash"),
            name="EQH Liquidity",
            showlegend=False,
            hoverinfo="skip"
        ))
        # Annotation am Ende der Linie
        fig.add_annotation(
            x=last_date,
            y=eqh["level"],
            text="EQH",
            showarrow=False,
            xanchor="left",
            font=dict(color="#ef4444", size=10),
            bgcolor="rgba(0,0,0,0.5)"
        )

    for eql in smc_data.get("eql", []):
        fig.add_trace(go.Scatter(
            x=[eql["date1"], last_date],
            y=[eql["level"], eql["level"]],
            mode="lines",
            line=dict(color="#22c55e", width=2, dash="dash"),
            name="EQL Liquidity",
            showlegend=False,
            hoverinfo="skip"
        ))
        fig.add_annotation(
            x=last_date,
            y=eql["level"],
            text="EQL",
            showarrow=False,
            xanchor="left",
            font=dict(color="#22c55e", size=10),
            bgcolor="rgba(0,0,0,0.5)"
        )

    # Layout anwenden
    layout = {k: v for k, v in LAYOUT_DEFAULTS.items() if k not in ("xaxis", "yaxis", "hovermode")}
    layout["title"] = dict(text=title, font=dict(size=14))
    layout["height"] = 550
    layout["dragmode"] = "pan"
    layout["shapes"] = shapes

    # Rangebreaks für Krypto vs Aktien anwenden
    has_weekends = (df.index.weekday >= 5).any() if not df.empty else False
    if not has_weekends:
        layout["xaxis"] = dict(rangebreaks=[dict(bounds=["sat", "mon"])])
        
    layout["xaxis_rangeslider_visible"] = False

    fig.update_layout(**layout)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.06)")
    if getattr(fig.layout, "xaxis", None):
        fig.update_xaxes(gridcolor="rgba(148,163,184,0.06)")
    else:
        fig.update_xaxes(gridcolor="rgba(148,163,184,0.06)")

    return fig
