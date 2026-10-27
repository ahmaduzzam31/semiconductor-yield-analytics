"""Tiny helper to assemble Plotly figures and KPI tiles into one self-contained dashboard page.

Copied into each project's src/ so every repository runs on its own.
"""
from html import escape

import plotly.graph_objects as go

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GOOD, CRITICAL, WARNING = "#0ca30c", "#d03b3b", "#fab219"
INK, INK_2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

CSS = """
:root { color-scheme: light; --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
        --muted:#898781; --border:rgba(11,11,11,0.10); --accent:#2a78d6; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink);
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
header { padding:28px 16px 8px; max-width:1200px; margin:0 auto; }
header h1 { margin:0 0 6px; font-size:26px; }
header p { margin:0; color:var(--ink2); max-width:820px; line-height:1.5; }
main { max-width:1200px; margin:0 auto; padding:16px; display:grid; gap:16px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:12px; }
.kpi, .card { background:var(--surface); border:1px solid var(--border); border-radius:12px; }
.kpi { padding:14px 16px; }
.kpi .label { color:var(--ink2); font-size:13px; }
.kpi .value { font-size:28px; font-weight:650; margin-top:4px; }
.kpi .note { color:var(--muted); font-size:12px; margin-top:2px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 520px), 1fr)); gap:16px; }
.card { padding:12px 12px 4px; min-width:0; }
.card h2 { font-size:15px; margin:4px 6px 0; }
.card .sub { color:var(--ink2); font-size:13px; margin:4px 6px 0; line-height:1.4; }
.card.wide { grid-column:1 / -1; }
.insights { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:8px 20px; }
.insights li { margin:8px 0; line-height:1.45; }
footer { max-width:1200px; margin:0 auto; padding:8px 16px 32px; color:var(--muted); font-size:12px; }
a { color:var(--accent); }
"""


def style_fig(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=16, t=16, b=10),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_2, size=12),
        hoverlabel=dict(bgcolor="white", font_color=INK, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)"),
        colorway=[BLUE, ORANGE, AQUA],
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont_color=INK_2, title_font_color=INK_2)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont_color=INK_2, title_font_color=INK_2)
    return fig


def build_page(title: str, intro: str, kpis: list[tuple[str, str, str]], cards: list[dict],
               insights: list[str], footer: str, path) -> None:
    """kpis: (label, value, note). cards: {title, sub, fig, wide}."""
    kpi_html = "".join(
        f'<div class="kpi"><div class="label">{escape(l)}</div><div class="value">{escape(v)}</div>'
        f'<div class="note">{escape(n)}</div></div>' for l, v, n in kpis)
    card_html = []
    for i, c in enumerate(cards):
        div = style_fig(c["fig"], c.get("height", 340)).to_html(
            full_html=False, include_plotlyjs="cdn" if i == 0 else False, default_width="100%",
            config={"displayModeBar": False, "responsive": True})
        card_html.append(f'<section class="card{" wide" if c.get("wide") else ""}"><h2>{escape(c["title"])}</h2>'
                         f'<p class="sub">{escape(c.get("sub", ""))}</p>{div}</section>')
    ins = "".join(f"<li>{i}</li>" for i in insights)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title>
<style>{CSS}</style></head><body>
<header><h1>{escape(title)}</h1><p>{intro}</p></header>
<main><div class="kpis">{kpi_html}</div>
<section class="insights"><ul>{ins}</ul></section>
<div class="grid">{''.join(card_html)}</div></main>
<footer>{footer}</footer>
<script>window.addEventListener("load", () =>
  document.querySelectorAll(".plotly-graph-div").forEach(d => Plotly.Plots.resize(d)));</script>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
