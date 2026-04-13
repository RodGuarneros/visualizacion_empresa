# churn_dashboard.py  (CAMBIOS COMPLETOS: CSS + KPIs + Resultados + Sidebar chips/labels)

import os
import sys
from datetime import datetime

import pandas as pd
import joblib
import streamlit as st
from sqlalchemy import create_engine
import sklearn

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, f1_score
from sklearn.ensemble import RandomForestClassifier
from io import BytesIO
import matplotlib.pyplot as plt
import altair as alt
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(
    page_title="Tablero de riesgo de deserción (Churn Rate)",
    layout="wide",
    initial_sidebar_state="expanded",
)

CONN = "postgresql+psycopg://postgres@127.0.0.1:5432/app_movil"
engine = create_engine(CONN, pool_pre_ping=True)

HERE = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = r"C:\Proyecto en venta\1. Churn\churn_model.joblib"
ORIGINAL_MODEL_PATH = r"C:\Proyecto en venta\1. Churn\churn_model_original.joblib"
TOP_IMAGE = os.path.join(HERE, "mindharvest_header.png")  # opcional
SIDEBAR_LOGO = os.path.join(HERE, "mi_logo.png")

BRAND = {
    "bg": "#95B6EC",
    "panel": "#0B1B33",
    "panel2": "#0E2442",
    "card": "#0B1B33",
    "table_bg": "#141B24",
    "grid": "#24344A",
    "text": "#95B6EC",     # azul clarito
    "muted": "#A9C7E8",
    "cobalt": "#1D4ED8",
    "cobalt2": "#2563EB",
    "green": "#14B8A6",
    "chart_bg": "#000000",
    "chart_text": "#D7ECFF",
}

from io import BytesIO
from datetime import datetime

def altair_to_jpg_bytes(chart, filename_prefix: str, scale: int = 2):
    try:
        import vl_convert as vlc
        from PIL import Image
    except Exception:
        return None, None

    try:
        spec = chart.to_dict()
        png_bytes = vlc.vegalite_to_png(spec, scale=scale)

        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return buf.getvalue(), f"{filename_prefix}_{ts}.jpg"
    except Exception:
        return None, None

def apply_df_filters(df: pd.DataFrame, city_sel, seg_sel, plan_sel):
    out = df.copy()
    if "city" in out.columns and city_sel:
        out = out[out["city"].isin(list(city_sel))]
    if "segment" in out.columns and seg_sel:
        out = out[out["segment"].isin(list(seg_sel))]
    if "plan_type" in out.columns and plan_sel:
        out = out[out["plan_type"].isin(list(plan_sel))]
    return out

ts_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def build_pdf_report_bytes(
    *,
    title: str,
    ts_evento: str,
    filtros_txt_html: str,
    stats_rows: list,  # list[tuple[str,str,str]] -> (metric, actual, anterior)
    brand: dict,
    ts_reporte: str | None = None,  # ✅ opcional (si no lo pasas, lo genera)
):
    """
    Genera un PDF profesional (bytes) con:
    - Header: title
    - Sección: Estadísticas de distribución (tabla)
    - Sección: Parámetros del pronóstico actual (fecha + filtros)
    - Incluye: Fecha del reporte
    """
    from io import BytesIO
    from datetime import datetime

    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch

    # ✅ si no viene, usar ahora
    if not ts_reporte:
        ts_reporte = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.70 * inch,
        bottomMargin=0.70 * inch,
        title=title,
    )

    styles = getSampleStyleSheet()

    # Paleta (usa tu BRAND)
    bg = colors.HexColor(brand.get("bg", "#95B6EC"))
    panel = colors.HexColor(brand.get("panel", "#0B1B33"))
    grid = colors.HexColor(brand.get("grid", "#24344A"))
    muted = colors.HexColor(brand.get("muted", "#A9C7E8"))
    white = colors.white

    # Estilos tipográficos
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=white,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=17,
        textColor=panel,
        spaceAfter=8,
        spaceBefore=10,
    )
    p = ParagraphStyle(
        "p",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        textColor=panel,
    )
    mono = ParagraphStyle(
        "mono",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=9.2,
        leading=12,
        textColor=panel,
    )
    small_muted = ParagraphStyle(
        "small_muted",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12,
        textColor=muted,
    )

    story = []

    # ===== Header banda =====
    header_tbl = Table(
        [[Paragraph(title, h1)]],
        colWidths=[doc.width],
        rowHeights=[0.55 * inch],
    )
    header_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), panel),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0, panel),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Reporte de distribución y parámetros del pronóstico", small_muted))
    story.append(Paragraph(f"Fecha del reporte: {ts_reporte}", small_muted))
    story.append(Spacer(1, 8))

    # ===== Estadísticas de distribución =====
    story.append(Paragraph("Estadísticas de distribución", h2))

    stats_data = [["Métrica", "Actual", "Anterior"]] + [
        [a, b, c] for (a, b, c) in (stats_rows or [])
    ]

    stats_tbl = Table(
        stats_data,
        colWidths=[doc.width * 0.45, doc.width * 0.275, doc.width * 0.275],
        hAlign="LEFT",
    )

    stats_style = [
        ("BACKGROUND", (0, 0), (-1, 0), panel),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10),

        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("TEXTCOLOR", (0, 1), (-1, -1), panel),

        ("GRID", (0, 0), (-1, -1), 0.6, colors.Color(grid.red, grid.green, grid.blue, alpha=0.35)),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.Color(grid.red, grid.green, grid.blue, alpha=0.55)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
    ]

    # zebra
    for i in range(1, len(stats_data)):
        if i % 2 == 0:
            stats_style.append(
                ("BACKGROUND", (0, i), (-1, i), colors.Color(bg.red, bg.green, bg.blue, alpha=0.18))
            )

    stats_tbl.setStyle(TableStyle(stats_style))
    story.append(stats_tbl)

    story.append(Spacer(1, 14))

    # ===== Parámetros del pronóstico actual =====
    story.append(Paragraph("Parámetros del pronóstico actual", h2))

    story.append(Paragraph(f"<b>Fecha y hora del evento:</b> {ts_evento}", p))
    story.append(Spacer(1, 6))

    # filtros_txt_html viene con <br>, lo convertimos a párrafos legibles
    filtros_clean = (
        (filtros_txt_html or "")
        .replace("<br>", "\n")
        .replace("━", "")
    ).strip()

    story.append(Paragraph("<b>Filtros aplicados:</b>", p))
    story.append(Spacer(1, 4))

    filtros_escaped = (
        filtros_clean
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    story.append(Paragraph(f"<font name='Courier'>{filtros_escaped}</font>", mono))

    story.append(Spacer(1, 18))
    story.append(Paragraph("Generado desde el Tablero de riesgo de Abandono (Churn Rate).", small_muted))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(muted)
        canvas.drawRightString(doc_.pagesize[0] - doc_.rightMargin, 0.45 * inch, "© 2026 MindHarvestAI · Todos los derechos reservados")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)    
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

# -----------------------------
# CSS (COMPLETO)
# -----------------------------
def inject_css():
    st.markdown(
        f"""
        <style>
        :root {{
            --mh-bg: {BRAND["bg"]};
            --mh-panel: {BRAND["panel"]};
            --mh-card: {BRAND["card"]};
            --mh-text: {BRAND["text"]};
            --mh-muted: {BRAND["muted"]};
            --mh-cobalt: {BRAND["cobalt"]};
            --mh-cobalt2: {BRAND["cobalt2"]};
            --mh-green: {BRAND["green"]};
            --mh-grid: {BRAND["grid"]};
            --mh-table: {BRAND["table_bg"]};
        }}

        html, body, [class*="css"] {{
            color: var(--mh-text) !important;
            background: var(--mh-bg) !important;
        }}
        .stApp {{ background: var(--mh-bg); }}

        

/* ===== HERO CAROUSEL ===== */
.mh-carousel {{
    position: relative;
    height: 28px;
    overflow: hidden;
    margin-top: 8px;
}}

.mh-carousel span {{
    position: absolute;
    width: 100%;
    left: 0;
    opacity: 0;
    animation: carouselFade 16s infinite;
    font-weight: 600;
    color: #FAED27 !important;   /* rojo elegante */
    font-size: clamp(17px, 1.8vw, 23px) !important;  /* +5px aprox */
    font-weight: 900;

}}



.mh-carousel span:nth-child(1) {{ animation-delay: 0s; }}
.mh-carousel span:nth-child(2) {{ animation-delay: 4s; }}
.mh-carousel span:nth-child(3) {{ animation-delay: 8s; }}
.mh-carousel span:nth-child(4) {{ animation-delay: 12s; }}

@keyframes carouselFade {{
    0% {{ opacity: 0; transform: translateY(10px); }}
    5% {{ opacity: 1; transform: translateY(0); }}
    25% {{ opacity: 1; }}
    30% {{ opacity: 0; transform: translateY(-10px); }}
    100% {{ opacity: 0; }}
}}



        /* ===== Sidebar ===== */
        section[data-testid="stSidebar"] {{
            background: #000000 !important;
            border-right: 1px solid rgba(255,255,255,.10);
        }}

section[data-testid="stSidebar"] label {{
    font-size: 20px !important;
    font-weight: 900;
    color: var(--mh-bg) !important;
}}

/* ===== Sidebar widget labels (Ciudad/Segmento/Plan/Umbral) ===== */
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
    font-size: 17px !important;
    font-weight: 900 !important;
    color: var(--mh-bg) !important;
    margin-bottom: 6px !important;
}}

section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{
    margin-bottom: 2px !important;
}}

/* ===== BOTÓN APLICAR FILTROS COBALTO ===== */
section[data-testid="stSidebar"] button[kind="primary"] {{
    background: var(--mh-cobalt) !important;
    color: #FFFFFF !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,.20) !important;
    font-weight: 900 !important;
}}

section[data-testid="stSidebar"] button[kind="primary"]:hover {{
    background: var(--mh-cobalt2) !important;
}}

section[data-testid="stSidebar"] button {{
    background: var(--mh-cobalt) !important;
    color: #FFFFFF !important;
}}




        section[data-testid="stSidebar"] * {{
            color: var(--mh-bg) !important;
        }}

        /* ===== CONTENEDORES AZUL MARINO PROFUNDO ===== */
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
            background: #0B1B33 !important;
            border: 1px solid #1E3A5F !important;
            border-radius: 18px !important;
        }}

        section[data-testid="stSidebar"] [data-baseweb="select"] input,
        section[data-testid="stSidebar"] [data-baseweb="select"] span {{
            color: #D7ECFF !important;
            font-weight: 800;
        }}

        /* ===== CHIPS ===== */
        section[data-testid="stSidebar"] [data-baseweb="tag"] {{
            background: #102A4A !important;
            border: 1px solid #1D4ED8 !important;
            color: #D7ECFF !important;
            font-weight: 900;
            border-radius: 10px !important;
        }}

        /* ===== SOLO BOTONES ACTIONS EN COBALTO ===== */
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[kind="primary"] {{
            background: var(--mh-cobalt) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255,255,255,.18) !important;
            border-radius: 18px !important;
            font-weight: 900 !important;
            padding: 0.65rem 1rem !important;
        }}

        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] button[kind="primary"]:hover {{
            background: var(--mh-cobalt2) !important;
        }}

        /* ===== Quitar barras gordas ===== */
        hr, .mh-sep, .mh-bigbar, .mh-widebar {{
            display:none !important;
        }}

        /* ===== Cards ===== */
        .mh-card {{
            background: var(--mh-card);
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 10px 24px rgba(0,0,0,.55);
            justify-content: center;

        }}

        /* ===== KPI CARDS — AUTOSIZE REAL ===== */
        .mh-kpi {{
    background: var(--mh-card);
    border-radius: 22px;
    padding: 20px 18px;
    min-height: 190px;

    display: flex;
    flex-direction: column;

    /* 👇 elimina separación exagerada */
    justify-content: center;
    gap: 10px;   /* ajusta aquí si quieres aún menos */
    box-shadow: 0 20px 32px -14px rgba(0,0,0,.50);

}}


        .mh-kpi-label {{
            font-weight:900;
            line-height:1.15;
            font-size: clamp(15px,1.6vw,20px);
            opacity:.95;
            text-wrap: balance;
        }}

.mh-kpi-value {{
    font-weight: 1000;
    letter-spacing: -0.02em;

    /* tamaño dinámico */
    font-size: clamp(20px, 4vw, 64px);

    /* centrado */
    width: 100%;
    display: flex;
    align-items: center;
/* 👇 elimina separación exagerada */
    justify-content: center;
    gap: 6px;   /* ajusta aquí si quieres aún menos */
    text-align: center;

    /* evitar overflow */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    color: var(--mh-bg) !important;
}}


/* ===== DATAFRAME DARK MODE ===== */
div[data-testid="stDataFrame"] {{
    background: #0B1B33 !important;   /* azul marino profundo */
    border-radius: 16px !important;
    padding: 8px !important;
}}

div[data-testid="stDataFrame"] table {{
    color: #FFFFFF !important;
    background: #0B1B33 !important;
}}

div[data-testid="stDataFrame"] th {{
    background: #102A4A !important;
    color: #FFFFFF !important;
    font-weight: 900 !important;
}}

div[data-testid="stDataFrame"] td {{
    background: #0B1B33 !important;
    color: #FFFFFF !important;
    border-bottom: 1px solid rgba(255,255,255,.08) !important;
}}

div[data-testid="stDataFrame"] tr:hover td {{
    background: #1E3A5F !important;
}}


/* ===== DATAFRAME (st.dataframe) DARK REAL ===== */
div[data-testid="stDataFrame"] {{
    background: #0B1B33 !important;
    border-radius: 18px !important;
    padding: 14px !important;
    border: 1px solid rgba(255,255,255,.10) !important;
    box-shadow: 0 18px 36px rgba(0,0,0,.45) !important;
    overflow: hidden !important;
}}

/* el wrapper interno */
div[data-testid="stDataFrame"] > div {{
    background: #0B1B33 !important;
}}

/* si viene en iframe, dale dark al iframe */
div[data-testid="stDataFrame"] iframe {{
    background: #0B1B33 !important;
    border-radius: 14px !important;
}}

/* forzar fondo de canvas / contenedor tipo arrow */
div[data-testid="stDataFrame"] [role="grid"],
div[data-testid="stDataFrame"] [role="table"],
div[data-testid="stDataFrame"] .stDataFrame,
div[data-testid="stDataFrame"] .glideDataEditor,
div[data-testid="stDataFrame"] .glideDataEditor * {{
    background: #0B1B33 !important;
    color: #FFFFFF !important;
}}

/* ===== TABLA DARK (HTML) ===== */
.mh-dark-table-wrap {{
    width: 100%;
    border-radius: 18px;
    overflow: auto;
    border: 1px solid rgba(255,255,255,.10);
    background: rgba(0,0,0,.55);
    box-shadow: 0 18px 34px rgba(0,0,0,.45);
}}

table.mh-dark-table {{
    width: 100% !important;
    border-collapse: separate !important;
    border-spacing: 0 !important;
    background: transparent !important;
    color: #D7ECFF !important;
    font-size: 19px !important;
}}

table.mh-dark-table thead th {{
    position: sticky;
    top: 0;
    z-index: 2;
    background: rgba(7,19,38,.95) !important;
    color: #D7ECFF !important;
    font-weight: 900 !important;
    text-align: left !important;
    padding: 12px 14px !important;
    border-bottom: 1px solid rgba(255,255,255,.10) !important;
    white-space: nowrap !important;
}}

table.mh-dark-table tbody td {{
    padding: 12px 14px !important;
    border-bottom: 1px solid rgba(255,255,255,.06) !important;
    color: #D7ECFF !important;
    vertical-align: middle !important;
    white-space: nowrap !important;
}}

table.mh-dark-table tbody tr:nth-child(even) {{
    background: rgba(255,255,255,.03) !important;
}}

table.mh-dark-table tbody tr:hover {{
    background: rgba(29,78,216,.10) !important;
}}

table.mh-dark-table,
table.mh-dark-table th,
table.mh-dark-table td {{
    border: none !important;
}}

.mh-dark-table-wrap * {{
    color: #D7ECFF !important;
}}



/* header */
div[data-testid="stDataFrame"] [role="columnheader"],
div[data-testid="stDataFrame"] thead * {{
    background: #102A4A !important;
    color: #FFFFFF !important;
    font-weight: 900 !important;
}}

/* celdas */
div[data-testid="stDataFrame"] [role="gridcell"],
div[data-testid="stDataFrame"] tbody * {{
    background: #0B1B33 !important;
    color: #FFFFFF !important;
    border-color: rgba(255,255,255,.08) !important;
}}

/* hover */
div[data-testid="stDataFrame"] [role="row"]:hover * {{
    background: #1E3A5F !important;
}}


/* ===== BOTÓN DESCARGA ROJO PREMIUM (selector correcto) ===== */
div[data-testid="stDownloadButton"] button {{
    background: linear-gradient(135deg, #DC2626, #B91C1C) !important;
    color: #FFFFFF !important;
    font-weight: 900 !important;
    border-radius: 14px !important;
    border: none !important;
    padding: 0.7rem 1.2rem !important;
    box-shadow: 0 10px 24px rgba(220,38,38,.45) !important;
    transition: all .25s ease !important;
}}

div[data-testid="stDownloadButton"] button:hover {{
    background: linear-gradient(135deg, #EF4444, #DC2626) !important;
    box-shadow: 0 14px 30px rgba(220,38,38,.65) !important;
    transform: translateY(-2px);
}}

div[data-testid="stDownloadButton"] button:active {{
    transform: translateY(0);
    box-shadow: 0 6px 14px rgba(220,38,38,.35) !important;
}}

/* ===== FIX REAL: CENTRAR DOWNLOAD BUTTON (wrapper interno) ===== */
div[data-testid="stDownloadButton"] {{
    width: 100% !important;
}}

div[data-testid="stDownloadButton"] > div {{
    width: 100% !important;
    display: flex !important;
    justify-content: center !important;
}}

div[data-testid="stDownloadButton"] button {{
    display: inline-flex !important;   /* importante: no block */
    margin: 0 !important;
}}





/* ===== HERO COBALTO DEGRADADO ===== */
.mh-hero {{
    background: linear-gradient(135deg, var(--mh-cobalt) 0%, #000000 100%);
    border-radius: 24px;
    padding: 28px 32px;
    box-shadow: 0 20px 40px rgba(0,0,0,.45);
}}

.mh-hero * {{
    color: var(--mh-bg) !important;
}}

.mh-hero h1 {{
    font-size: clamp(24px,2.8vw,36px);
    font-weight: 1000;
}}

/* ===== TEXTO AZUL CLARITO (bg) EN CARDS ===== */
.mh-card,
.mh-card * {{
    color: var(--mh-bg) !important;
}}

/* ===== KPIs AZUL CLARITO ===== */
.mh-kpi-label {{
    text-align: center;
    color: var(--mh-bg) !important;
}}

.mh-kpi-value {{
    color: var(--mh-bg) !important;
}}


        

.mh-pill {{
    font-size: clamp(17px, 1.6vw, 17px);
    text-align: center;
    width: 100%;
    display: block;
    font-weight: 900;
}}


        .mh-results-title {{
            font-size: clamp(21px,2vw,22px);
            font-weight:900;
        }}

        .mh-results-k {{
            font-size: clamp(21px,1.2vw,21px);
        }}

        .mh-results-v {{
            font-size: clamp(21px,1.3vw,21px);
        }}

        /* ===== TABLA ESTADÍSTICAS — PROFESIONAL ===== */
.mh-stats-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 16px;
    overflow: hidden;
    background: linear-gradient(180deg, #0F1720, #0E1620);
    box-shadow: 0 10px 24px rgba(0,0,0,.35);
    border: 1px solid rgba(255,255,255,.10);
}}

/* Header */
.mh-stats-table thead th {{
    padding: 14px 12px;
    background: #0B1B33;
    color: var(--mh-bg);
    font-weight: 900;
    font-size: 20px;
    text-align: left;
    letter-spacing: .4px;
    border-bottom: 1px solid rgba(255,255,255,.12);
}}

/* Celdas */
.mh-stats-table tbody td {{
    padding: 12px;
    font-size: 20px;
    color: var(--mh-bg);
    border-bottom: 1px solid rgba(255,255,255,.06);
}}

/* Zebra elegante */
.mh-stats-table tbody tr:nth-child(even) td {{
    background: rgba(255,255,255,.03);
}}

/* Hover sutil */
.mh-stats-table tbody tr:hover td {{
    background: rgba(29,78,216,.18);
    transition: background .2s ease;
}}

/* Última fila sin borde */
.mh-stats-table tbody tr:last-child td {{
    border-bottom: none;
}}

        div[data-testid="stDataFrame"] {{
            background: var(--mh-table);
            border-radius:14px;
        }}

        .stApp hr {{
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    border: none !important;
}}

/* =========================
   HEADER + BOTÓN SIDEBAR (FIX)
   ========================= */

/* No borres header, solo transparente */
header[data-testid="stHeader"]{{
  background: transparent !important;
  box-shadow: none !important;
}}

/* IMPORTANTE:
   NO uses opacity:0 ni pointer-events:none en stToolbar
   porque ahí suele vivir el control de sidebar */
div[data-testid="stToolbar"]{{
  background: transparent !important;
  box-shadow: none !important;
  opacity: 1 !important;
  pointer-events: auto !important;
}}


/* Pero re-habilita el control del sidebar (varía por versión) */
div[data-testid="stToolbar"] [data-testid="collapsedControl"],
div[data-testid="stToolbar"] [data-testid="stSidebarCollapsedControl"],
div[data-testid="stToolbar"] button,
div[data-testid="collapsedControl"],
div[data-testid="stSidebarCollapsedControl"]{{
  opacity: 1 !important;
  pointer-events: auto !important;
}}

/* NO toques el toolbar: ahí vive el control del sidebar */
header[data-testid="stHeader"]{{
  background: transparent !important;
  box-shadow: none !important;
}}

div[data-testid="stToolbar"]{{
  background: transparent !important;
  box-shadow: none !important;
  opacity: 1 !important;
  pointer-events: auto !important;
}}

/* opcional: solo ocultar decoración superior, no el toolbar */
div[data-testid="stDecoration"]{{
  display:none !important;
}}

/* Asegura que el ícono se vea (svg) */
div[data-testid="collapsedControl"] svg,
div[data-testid="stSidebarCollapsedControl"] svg{{
  opacity: 1 !important;
  fill: #D7ECFF !important;
}}

/* Mantén stDecoration fuera */
div[data-testid="stDecoration"]{{
  display: none !important;
}}

        </style>
        """,
        unsafe_allow_html=True,)




# -----------------------------
# Helpers
# -----------------------------
def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def model_fingerprint(path: str):
    if not os.path.exists(path):
        return (False, 0, 0)
    stt = os.stat(path)
    return (True, int(stt.st_size), int(stt.st_mtime))


def ensure_original_model_saved(current_path: str, original_path: str):
    if os.path.exists(original_path):
        return
    if os.path.exists(current_path):
        import shutil
        shutil.copy2(current_path, original_path)


def restore_original_model(current_path: str, original_path: str):
    import shutil
    if not os.path.exists(original_path):
        raise FileNotFoundError(f"No existe el modelo original: {original_path}")
    shutil.copy2(original_path, current_path)


@st.cache_data(ttl=60)
def load_data():
    return pd.read_sql("SELECT * FROM app.v_features_churn", engine)


@st.cache_resource(ttl=60)
def load_model_cached(path: str, mtime: int):
    return joblib.load(path)


def build_preprocessor(X: pd.DataFrame):
    cat_cols = [c for c in X.columns if X[c].dtype == "object"]
    num_cols = [c for c in X.columns if c not in cat_cols]

    pre = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imp", SimpleImputer(strategy="median"))]), num_cols),
            ("cat", Pipeline([
                ("imp", SimpleImputer(strategy="most_frequent")),
                ("oh", OneHotEncoder(handle_unknown="ignore"))
            ]), cat_cols),
        ]
    )
    return pre


def train_model(df_train: pd.DataFrame):
    required = {"customer_id", "churn_30d"}
    missing = required - set(df_train.columns)
    if missing:
        raise ValueError(f"Faltan columnas en app.v_features_churn: {missing}")

    y = df_train["churn_30d"].astype(int)
    X = df_train.drop(columns=["churn_30d", "customer_id"])

    pre = build_preprocessor(X)

    model = RandomForestClassifier(
        n_estimators=500,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )

    pipe = Pipeline([("pre", pre), ("model", model)])

    try:
        Xtr, Xte, ytr, yte = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
    except Exception:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

    pipe.fit(Xtr, ytr)

    proba = pipe.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    auc = float(roc_auc_score(yte, proba)) if len(set(yte)) > 1 else float("nan")
    f1 = float(f1_score(yte, pred)) if len(set(yte)) > 1 else float("nan")

    return pipe, {"roc_auc": auc, "f1": f1, "n_train": int(len(Xtr)), "n_test": int(len(Xte))}


def score_df(pipe, df_score: pd.DataFrame):
    X = df_score.drop(columns=["churn_30d", "customer_id"])
    proba = pipe.predict_proba(X)[:, 1]
    out = df_score[["customer_id", "city", "segment", "plan_type", "churn_30d"]].copy()
    out["churn_probability"] = pd.to_numeric(proba, errors="coerce")
    return out


def dist_stats(s: pd.Series):
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return None
    mode = s.round(3).mode()
    mode_v = float(mode.iloc[0]) if len(mode) else float("nan")
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "mode": mode_v,
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()),
        "max": float(s.max()),
        "count": int(s.shape[0]),
    }


def cobalt_histogram(df_scored: pd.DataFrame, title="Risk histogram", maxbins=28):
    s = pd.to_numeric(df_scored["churn_probability"], errors="coerce").dropna()
    if s.empty:
        return None

    d = pd.DataFrame({"risk": s})
    mean_v = float(s.mean())
    med_v = float(s.median())

    bars = alt.Chart(d).mark_bar(color=BRAND["cobalt"]).encode(
        x=alt.X(
            "risk:Q",
            bin=alt.Bin(maxbins=maxbins),
            title="Churn probability",
            axis=alt.Axis(
                labelColor=BRAND["chart_text"],
                titleColor=BRAND["chart_text"],
                gridColor=BRAND["grid"],
                tickColor=BRAND["grid"],
                domainColor=BRAND["grid"],
            ),
        ),
        y=alt.Y(
            "count():Q",
            title="Customers",
            axis=alt.Axis(
                labelColor=BRAND["chart_text"],
                titleColor=BRAND["chart_text"],
                gridColor=BRAND["grid"],
                tickColor=BRAND["grid"],
                domainColor=BRAND["grid"],
            ),
        ),
        tooltip=[alt.Tooltip("count():Q", title="Customers")],
    )

    mean_rule = alt.Chart(pd.DataFrame({"x": [mean_v]})).mark_rule(
        color=BRAND["green"], strokeWidth=3
    ).encode(x="x:Q")

    med_rule = alt.Chart(pd.DataFrame({"x": [med_v]})).mark_rule(
        color=BRAND["chart_text"], strokeWidth=2, strokeDash=[6, 4]
    ).encode(x="x:Q")

    chart = (
        alt.layer(bars, mean_rule, med_rule)
        .properties(title=alt.TitleParams(text=title, color=BRAND["chart_text"]))
        .configure(background=BRAND["chart_bg"])
        .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
        .configure_axis(gridColor=BRAND["grid"])
        .configure_title(color=BRAND["chart_text"])
    )
    return chart


def filters_to_text(city_sel, seg_sel, plan_sel, thr):
    def fmt(xs):
        if xs is None:
            return "-"
        xs = list(xs)
        if len(xs) == 0:
            return "(none)"
        if len(xs) <= 6:
            return ", ".join(map(str, xs))
        return ", ".join(map(str, xs[:6])) + f" … (+{len(xs)-6})"

    return (
        f"━\n"
        f"Ciudad: {fmt(city_sel)}<br>"
        f"━\n"
        f"Segmento: {fmt(seg_sel)}<br>"
        f"━\n"
        f"Plan: {fmt(plan_sel)}<br>"
        f"━\n"
        f"Umbral de riesgo: {thr:.2f}"
    )


# -----------------------------
# INIT
# -----------------------------
inject_css()

if "prev_hist_df" not in st.session_state:
    st.session_state["prev_hist_df"] = None
if "prev_run_ts" not in st.session_state:
    st.session_state["prev_run_ts"] = None
if "curr_run_ts" not in st.session_state:
    st.session_state["curr_run_ts"] = now_stamp()
if "train_filters_text" not in st.session_state:
    st.session_state["train_filters_text"] = "—"

df_raw = load_data()

ensure_original_model_saved(MODEL_PATH, ORIGINAL_MODEL_PATH)

city_all = sorted(df_raw["city"].dropna().unique()) if "city" in df_raw.columns else []
seg_all = sorted(df_raw["segment"].dropna().unique()) if "segment" in df_raw.columns else []
plan_all = sorted(df_raw["plan_type"].dropna().unique()) if "plan_type" in df_raw.columns else []

default_thr = 0.60

# filtros del ÚLTIMO ENTRENAMIENTO (snapshot). NO se modifican al "Aplicar filtros"
if "train_city_sel" not in st.session_state:
    st.session_state["train_city_sel"] = city_all
if "train_seg_sel" not in st.session_state:
    st.session_state["train_seg_sel"] = seg_all
if "train_plan_sel" not in st.session_state:
    st.session_state["train_plan_sel"] = plan_all
if "train_thr" not in st.session_state:
    st.session_state["train_thr"] = float(default_thr)



# -----------------------------
# SIDEBAR ACTIONS + FILTER FORM
# -----------------------------
with st.sidebar:
    if os.path.exists(SIDEBAR_LOGO):
        st.image(SIDEBAR_LOGO, use_container_width=True)
        st.write("")
    st.markdown('<div class="mh-pill">• Barra de ajustes •</div>', unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="mh-pill">¿Elije en qué quieres que se enfoque el modelo?</div>', unsafe_allow_html=True)
    st.write("")

    with st.form("filters_form", clear_on_submit=False):
        city_sel = st.multiselect("Ciudad:", city_all, default=st.session_state.get("city_sel", city_all))
        seg_sel = st.multiselect("Segmento:", seg_all, default=st.session_state.get("seg_sel", seg_all))
        plan_sel = st.multiselect("Tipo de Plan:", plan_all, default=st.session_state.get("plan_sel", plan_all))
        thr = st.slider("Umbral de alto riesgo:", 0.0, 1.0, float(st.session_state.get("thr", default_thr)), 0.01)

        apply_filters = st.form_submit_button("Aplicar filtros", use_container_width=True)

    refresh_clicked = st.button("🔄 Entrenar el modelo", use_container_width=True)
    reset_clicked = st.button("♻️ Desactivar todos los filtros", use_container_width=True)

        # ===== Footer sidebar (hasta abajo) =====
    st.markdown(
    """
    <div style="
        margin-top: 60px;
        padding-top: 20px;
        border-top: 1px solid rgba(255,255,255,.18);
        text-align: center;
        font-size: 11px;
        font-weight: 700;
        opacity: .85;
        color: #95B6EC;
        line-height: 1.4;
    ">
        © 2026 <strong>MindHarvestAI</strong><br>
        Todos los derechos reservados
    </div>
    """,
    unsafe_allow_html=True,
)
    st.write("")

if apply_filters:
    st.session_state["city_sel"] = city_sel
    st.session_state["seg_sel"] = seg_sel
    st.session_state["plan_sel"] = plan_sel
    st.session_state["thr"] = float(thr)
    st.rerun()

city_sel = st.session_state.get("city_sel", city_all)
seg_sel = st.session_state.get("seg_sel", seg_all)
plan_sel = st.session_state.get("plan_sel", plan_all)
thr = float(st.session_state.get("thr", default_thr))





# -----------------------------
# RESET ACTION (SAFE)
# -----------------------------
# -----------------------------
# RESET ACTION (SAFE)
# -----------------------------
if reset_clicked:
    try:
        restore_original_model(MODEL_PATH, ORIGINAL_MODEL_PATH)
    except Exception as e:
        st.error("No pude restaurar el modelo original.")
        st.exception(e)
        st.stop()

    # ✅ "ANTERIOR" = snapshot del modelo actual PERO con los filtros de ENTRENAMIENTO guardados (no vista)
    try:
        exists, size, mtime = model_fingerprint(MODEL_PATH)
        if exists:
            pipe_prev = load_model_cached(MODEL_PATH, mtime)

            prev_input = apply_df_filters(
                df_raw,
                st.session_state.get("train_city_sel", city_all),
                st.session_state.get("train_seg_sel", seg_all),
                st.session_state.get("train_plan_sel", plan_all),
            )

            st.session_state["prev_hist_df"] = score_df(pipe_prev, prev_input).copy()
            st.session_state["prev_run_ts"] = st.session_state.get("curr_run_ts")
    except Exception:
        pass

    for k in ["city_sel", "seg_sel", "plan_sel", "thr"]:
        if k in st.session_state:
            del st.session_state[k]

    try:
        st.cache_data.clear()
        st.cache_resource.clear()
    except Exception:
        pass

    df_raw = load_data()

    # actualizar listas completas tras reload
    city_all = sorted(df_raw["city"].dropna().unique()) if "city" in df_raw.columns else []
    seg_all = sorted(df_raw["segment"].dropna().unique()) if "segment" in df_raw.columns else []
    plan_all = sorted(df_raw["plan_type"].dropna().unique()) if "plan_type" in df_raw.columns else []

    try:
        pipe_new, metrics = train_model(df_raw)
        joblib.dump(pipe_new, MODEL_PATH)

        st.session_state["curr_run_ts"] = now_stamp()
        st.session_state["train_filters_text"] = "RESET: entrenado con TODOS los valores (sin filtros)"

        # ✅ filtros de ENTRENAMIENTO (snapshot) quedan en "todo"
        st.session_state["train_city_sel"] = city_all
        st.session_state["train_seg_sel"] = seg_all
        st.session_state["train_plan_sel"] = plan_all
        st.session_state["train_thr"] = float(default_thr)

        st.success(
            f"Reset listo ✅  Modelo original restaurado y reentrenado con TODO. "
            f"ROC_AUC={metrics['roc_auc']:.3f}  F1={metrics['f1']:.3f}"
        )
    except Exception as e:
        st.error("Falló el reentrenamiento en Reset.")
        st.exception(e)
        st.stop()

    st.rerun()


# -----------------------------
# APPLY FILTERS (SOLO VISTA)
# -----------------------------
df_filtered = apply_df_filters(df_raw, city_sel, seg_sel, plan_sel)


# -----------------------------
# REFRESH & RETRAIN
# -----------------------------
if refresh_clicked:
    # ✅ "ANTERIOR" = snapshot del modelo actual con filtros del ENTRENAMIENTO previo (no con los nuevos del sidebar)
    try:
        exists, size, mtime = model_fingerprint(MODEL_PATH)
        if exists:
            pipe_prev = load_model_cached(MODEL_PATH, mtime)

            prev_input = apply_df_filters(
                df_raw,
                st.session_state.get("train_city_sel", city_all),
                st.session_state.get("train_seg_sel", seg_all),
                st.session_state.get("train_plan_sel", plan_all),
            )

            st.session_state["prev_hist_df"] = score_df(pipe_prev, prev_input).copy()
            st.session_state["prev_run_ts"] = st.session_state.get("curr_run_ts")
    except Exception:
        pass

    try:
        st.cache_data.clear()
    except Exception:
        pass

    df_raw = load_data()

    city_all = sorted(df_raw["city"].dropna().unique()) if "city" in df_raw.columns else []
    seg_all = sorted(df_raw["segment"].dropna().unique()) if "segment" in df_raw.columns else []
    plan_all = sorted(df_raw["plan_type"].dropna().unique()) if "plan_type" in df_raw.columns else []

    # ✅ entrenar con los filtros actuales (vista)
    df_filtered = apply_df_filters(
        df_raw,
        st.session_state.get("city_sel", city_all),
        st.session_state.get("seg_sel", seg_all),
        st.session_state.get("plan_sel", plan_all),
    )

    try:
        pipe_new, metrics = train_model(df_filtered)
        joblib.dump(pipe_new, MODEL_PATH)

        st.session_state["curr_run_ts"] = now_stamp()
        st.session_state["train_filters_text"] = (
            "REFRESH: entrenado con filtros actuales\n\n" +
            filters_to_text(
                st.session_state.get("city_sel", city_all),
                st.session_state.get("seg_sel", seg_all),
                st.session_state.get("plan_sel", plan_all),
                float(st.session_state.get("thr", default_thr)),
            )
        )

        # ✅ guardar filtros de ENTRENAMIENTO para el próximo comparativo
        st.session_state["train_city_sel"] = st.session_state.get("city_sel", city_all)
        st.session_state["train_seg_sel"] = st.session_state.get("seg_sel", seg_all)
        st.session_state["train_plan_sel"] = st.session_state.get("plan_sel", plan_all)
        st.session_state["train_thr"] = float(st.session_state.get("thr", default_thr))

        try:
            st.cache_resource.clear()
        except Exception:
            pass

        st.success(
            f"Modelo reentrenado ✅  ROC_AUC={metrics['roc_auc']:.3f}  F1={metrics['f1']:.3f}  "
            f"(train={metrics['n_train']}, test={metrics['n_test']})"
        )
    except Exception as e:
        st.error("Falló el reentrenamiento.")
        st.exception(e)
        st.stop()

    st.rerun()


# -----------------------------
# LOAD CURRENT MODEL
# -----------------------------
exists, size, mtime = model_fingerprint(MODEL_PATH)
if not exists:
    st.error(f"No existe el modelo en: {MODEL_PATH}")
    st.stop()

try:
    pipe = load_model_cached(MODEL_PATH, mtime)
except Exception as e:
    st.error("No pude cargar el modelo (mismatch de sklearn/env o modelo viejo).")
    st.exception(e)
    st.stop()


# -----------------------------
# SCORE
# -----------------------------
try:
    df_scored = score_df(pipe, df_filtered)
except Exception as e:
    st.error("No pude scorear con el modelo. Revisa columnas vs entrenamiento.")
    st.exception(e)
    st.stop()


# -----------------------------
# HEADER
# -----------------------------
if os.path.exists(TOP_IMAGE):
    st.image(TOP_IMAGE, use_container_width=True)
else:
    st.markdown( f""" <div class="mh-hero"> 
                <div style="display:flex; justify-content:space-between; gap:16px; align-items:center;"> 
                <div>
                <div class="mh-pill">
        <a href="https://mindharvestai.com/soluciones" target="_blank">
        MindHarvestAI
    </a> 
    • Módulo de Fidelidad
</div> 
                <h1>📉 Riesgo de Abandono — Usuarios de tu App Móvil</h1>
                <p><b>Entrena tu modelo inteligente y conoce a los usuarios que podrían abandonar tu negocio:</b></p> 
                <div class="mh-carousel">
                <span></span> 
                <span>Por ciudad.</span>
                <span>Por segmento.</span> 
                <span>Por plan contratado.</span> 
                <span>La fidealidad de cada uno de los usuarios.</span> 
                <span></span></div> 
                <h2 style="font-size: clamp(14px,1.8vw,24px); opacity:.9; margin-top:12px;">Explora el riesgo de abandono en tu base de usuarios y <bold>toma acciones informadas para retenerlos</bold>.</h2>
                <p>Si quieres un nuevo pronóstico diríjete al menú de navegación lateral, haz los ajustes que gustes o tan solo presiona el botón <b>"Entrenar tu modelo inteligente."</b> para que tome los datos más recientes. </p> </div> 
                <div style="text-align:right;"> <div style="opacity:.9; font-size:13px;">Pronóstico disponible</div> <div style="font-weight:900; font-size:16px;">{st.session_state.get("curr_run_ts")}</div> <div style="opacity:.9; font-size:12px; margin-top:16px;">Pronóstico previo</div> <div style="font-weight:900; font-size:4px;">{st.session_state.get("prev_run_ts") or "-"}</div>
                  </div> 
                  </div> 
                  </div> """, unsafe_allow_html=True, )

st.write("")


# -----------------------------
# TRAIN FILTERS META
# -----------------------------
st.markdown(
    f"""
    <div class="mh-card">
        <div style="font-size: clamp(16px,2vw,22px); font-weight: 900; margin-bottom: 10px;">
            Parámetros de entrenamiento utilizados (Último pronóstico)
        </div>
        <pre style="
            margin:0;
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(0,0,0,.22);
            border: 1px solid rgba(255,255,255,.10);
            color: var(--mh-bg);
            white-space: pre-wrap;
            word-break: break-word;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.35;
        ">{st.session_state.get("train_filters_text", "—")}</pre>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")


# -----------------------------
# KPIs (SIN BARRAS + MISMO TAMAÑO)
# -----------------------------

f = df_scored.copy()
stats_now = dist_stats(f["churn_probability"])

def kpi_card(label, value):
    st.markdown(f"""
    <div class="mh-kpi">
        <div class="mh-kpi-label">{label}</div>
        <div class="mh-kpi-value">{value}</div>
    </div>
    """, unsafe_allow_html=True)


c1, c2, c3, c4 = st.columns(4)

with c1:
    kpi_card("Usuarios", f"{int(f.shape[0])}")

with c2:
    kpi_card("Riesgo alto (>= thr)", f"{int((f['churn_probability'] >= float(thr)).sum())}")

with c3:
    avg_v = float(pd.to_numeric(f["churn_probability"], errors="coerce").mean())
    kpi_card("Riesgo promedio", f"{avg_v:.3f}")

with c4:
    med_v = stats_now["median"] if stats_now else float("nan")
    kpi_card("Mediana del riesgo", "-" if not stats_now else f"{med_v:.3f}")

st.write("")


# -----------------------------
# TABLE
# -----------------------------
st.markdown(
    """
    <div style="
        height: 3px;
        border-radius: 6px;
        background: linear-gradient(
            90deg,
            #0B1B33 0%,
            #1D4ED8 50%,
            #0B1B33 100%
        );
        opacity: .9;
    "></div>
    """,
    unsafe_allow_html=True,
)
st.subheader("Ranking de clientes por riesgo de abandono (probabilidad de churn o abandono)")

top_all = f.sort_values("churn_probability", ascending=False)   # lo que quieres permitir descargar
top_view = top_all.head(20)   

# ✅ TABLA DARK (HTML) — reemplaza st.dataframe
st.markdown(
    "<div class='mh-dark-table-wrap'>"
    + top_view.to_html(index=False, classes="mh-dark-table", escape=False)
    + "</div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)


csv = top_all.to_csv(index=False).encode("Latin1")
st.download_button(
    label="Descarga la tabla completa (CSV)",
    data=csv,
    file_name="top_risk_customers.csv",
    mime="text/csv",
)

st.markdown('</div>', unsafe_allow_html=True)
st.write("")



# -----------------------------
# HISTOGRAMS: CURRENT vs PREVIOUS
# -----------------------------
st.markdown(
    """
    <div style="
        height: 3px;
        border-radius: 6px;
        background: linear-gradient(
            90deg,
            #0B1B33 0%,
            #1D4ED8 50%,
            #0B1B33 100%
        );
        opacity: .9;
    "></div>
    """,
    unsafe_allow_html=True,
)
st.subheader("Distribución del riesgo (histogramas)")

colA, colB = st.columns(2)

# --- ACTUAL ---
chart_now = cobalt_histogram(f, title="Distribución actual", maxbins=28)
if chart_now is not None:
    colA.altair_chart(chart_now, use_container_width=True)
    colA.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    jpg_now, fname_now = altair_to_jpg_bytes(chart_now, "histograma_actual", scale=2)

    if jpg_now is None:
        colA.info("Para descargar en JPG instala: pip install vl-convert-python pillow")
    else:
        _l, mid, _r = colA.columns([1, 2, 1])  # centra el botón sin pelear con CSS
        mid.download_button(
            label="Descargar gráfico actual (JPG)",
            data=jpg_now,
            file_name=fname_now,
            mime="image/jpeg",
            use_container_width=True,
        )
else:
    colA.info("No hay datos para el histograma actual.")

# --- ANTERIOR ---
prev_df = st.session_state.get("prev_hist_df", None)
if isinstance(prev_df, pd.DataFrame) and len(prev_df) > 0:
    chart_prev = cobalt_histogram(prev_df, title="Distribución anterior", maxbins=28)
    if chart_prev is not None:
        colB.altair_chart(chart_prev, use_container_width=True)
        colB.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

        jpg_prev, fname_prev = altair_to_jpg_bytes(chart_prev, "histograma_anterior", scale=2)

        if jpg_prev is None:
            colB.info("Para descargar en JPG instala: pip install vl-convert-python pillow")
        else:
            _l, mid, _r = colB.columns([1, 2, 1])
            mid.download_button(
                label="Descargar gráfico anterior (JPG)",
                data=jpg_prev,
                file_name=fname_prev,
                mime="image/jpeg",
                use_container_width=True,
            )
    else:
        colB.info("No hay datos para el histograma anterior.")
else:
    colB.info("Aún no hay gráfica anterior. Haz los ajustes que quieras y presiona 'Entrenar modelo'.")

st.markdown("</div>", unsafe_allow_html=True)
st.write("")



# -----------------------------
# DISTRIBUTION STATS
# -----------------------------
st.markdown(
    """
    <div style="
        height: 3px;
        border-radius: 6px;
        background: linear-gradient(
            90deg,
            #0B1B33 0%,
            #1D4ED8 50%,
            #0B1B33 100%
        );
        opacity: .9;
    "></div>
    """,
    unsafe_allow_html=True,
)
st.subheader("Estadísticas de distribución")

if stats_now:
    s = stats_now
    # opcional: stats previos
    prev_stats = None
    if isinstance(prev_df, pd.DataFrame) and len(prev_df) > 0:
        prev_stats = dist_stats(prev_df["churn_probability"])

    # tabla
    rows = [
        ("Media", f"{s['mean']:.4f}", f"{prev_stats['mean']:.4f}" if prev_stats else "-"),
        ("Mediana", f"{s['median']:.4f}", f"{prev_stats['median']:.4f}" if prev_stats else "-"),
        ("Moda", f"{s['mode']:.4f}", f"{prev_stats['mode']:.4f}" if prev_stats else "-"),
        ("Desv. estándar", f"{s['std']:.4f}", f"{prev_stats['std']:.4f}" if prev_stats else "-"),
        ("Mínimo", f"{s['min']:.4f}", f"{prev_stats['min']:.4f}" if prev_stats else "-"),
        ("Máximo", f"{s['max']:.4f}", f"{prev_stats['max']:.4f}" if prev_stats else "-"),
        ("# Usuarios", f"{s['count']}", f"{prev_stats['count']}" if prev_stats else "-"),
    ]

    st.markdown(
        "<table class='mh-stats-table'>"
        "<thead><tr><th>Métrica</th><th>Actual</th><th>Anterior</th></tr></thead>"
        "<tbody>"
        + "".join([f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a,b,c in rows])
        + "</tbody></table>",
        unsafe_allow_html=True,
    )
else:
    st.info("No hay datos para estadísticas.")

st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# RESULTADOS DEL CÁLCULO (SIN BARRAS)
# -----------------------------
st.markdown(
    """
    <div style="
        height: 3px;
        border-radius: 6px;
        background: linear-gradient(
            90deg,
            #0B1B33 0%,
            #1D4ED8 50%,
            #0B1B33 100%
        );
        opacity: .9;
    "></div>
    """,
    unsafe_allow_html=True,
)

st.subheader("Parámetros del pronóstico actual")

filtros_txt = filters_to_text(city_sel, seg_sel, plan_sel, float(thr))
ts_evento = st.session_state.get("curr_run_ts")

st.markdown(
    f"""
    <div class="mh-results-grid">
        <div class="mh-results-box">
            <div class="mh-results-k">Fecha y hora del evento</div>
            <pre class="mh-results-v">{ts_evento}</pre>
        </div>
        <div class="mh-results-box">
            <div class="mh-results-k">Filtros aplicados</div>
            <pre class="mh-results-v">{filtros_txt}</pre>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown('</div>', unsafe_allow_html=True)
st.write("")

st.markdown(
    """
    <div style="
        height: 3px;
        border-radius: 6px;
        background: linear-gradient(
            90deg,
            #0B1B33 0%,
            #1D4ED8 50%,
            #0B1B33 100%
        );
        opacity: .9;
    "></div>
    """,
    unsafe_allow_html=True,
)

# =============================
# PDF DESCARGABLE (Stats + Parámetros)
# =============================
pdf_title = "Módulo de Fidelidad - MindHarvestAI"

# rows ya existe (la misma lista que usas para la tabla HTML)
pdf_rows = rows if stats_now else [
    ("Media", "-", "-"),
    ("Mediana", "-", "-"),
    ("Moda", "-", "-"),
    ("Desv. estándar", "-", "-"),
    ("Mínimo", "-", "-"),
    ("Máximo", "-", "-"),
    ("# Usuarios", "-", "-"),
]

pdf_bytes = build_pdf_report_bytes(
    title=pdf_title,
    ts_evento=ts_evento,
    filtros_txt_html=filtros_txt,
    stats_rows=pdf_rows,
    brand=BRAND,
)

ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")
pdf_name = f"reporte_churn_{ts_file}.pdf"

# centra el botón como tus JPG
_l, mid, _r = st.columns([1, 2, 1])
mid.download_button(
    label="📄 Descargar reporte (PDF)",
    data=pdf_bytes,
    file_name=pdf_name,
    mime="application/pdf",
    use_container_width=True,
)


# st.caption(
#     f"Modelo: {MODEL_PATH} | size={size} bytes | mtime={mtime} | rows_raw={len(df_raw)} | rows_filtered={len(df_filtered)}"
# )
