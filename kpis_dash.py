# marketplace_dashboard.py
import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import altair as alt
from sqlalchemy import create_engine, text
import textwrap
import streamlit.components.v1 as components
import matplotlib.pyplot as plt
from html import escape as _html_escape
import mplcursors
import plotly.graph_objects as go

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(
    page_title="Monitor de tu negocio - Marketplace KPIs dashboar",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Trust (sin password)
CONN = "postgresql+psycopg://postgres@127.0.0.1:5432/marketplace"
engine = create_engine(CONN, pool_pre_ping=True)

# @st.cache_data(ttl=60)
# def detect_sessions_datetime_col(schema: str, table: str):
#     """
#     Regresa la primera columna tipo fecha/hora encontrada en sessions.
#     Prioriza nombres típicos.
#     """
#     sql = """
#     SELECT column_name, data_type
#     FROM information_schema.columns
#     WHERE table_schema = %(schema)s
#       AND table_name   = %(table)s
#     ORDER BY
#       CASE
#         WHEN lower(column_name) IN ('created_at','ts','timestamp','event_ts','session_ts','started_at','start_time','date') THEN 0
#         ELSE 1
#       END,
#       ordinal_position;
#     """
#     df = pd.read_sql(sql, engine, params={"schema": schema, "table": table})
#     if df.empty:
#         raise ValueError(f"No pude leer columnas de {schema}.{table}")

#     # candidatos por tipo
#     candidates = df[df["data_type"].str.lower().isin(["timestamp without time zone","timestamp with time zone","date","time"])].copy()
#     if candidates.empty:
#         # si no hay tipos timestamp/date, regresa la primera columna (para que la veas)
#         return df.iloc[0]["column_name"], df

#     return candidates.iloc[0]["column_name"], df


# @st.cache_data(ttl=60)
# def debug_find_tx_candidates():
#     sql = """
#     SELECT
#       c.table_schema,
#       c.table_name,
#       array_agg(c.column_name ORDER BY c.column_name) AS cols
#     FROM information_schema.columns c
#     WHERE
#       lower(c.column_name) IN ('customer_id','cust_id','user_id','userid','buyer_id','client_id')
#       OR lower(c.column_name) IN ('tx_date','transaction_date','date','created_at','timestamp','ts','paid_at')
#       OR lower(c.table_name) LIKE '%%trans%%'
#       OR lower(c.table_name) LIKE '%%tx%%'
#     GROUP BY 1,2
#     ORDER BY
#       CASE WHEN c.table_schema='mp' THEN 0 WHEN c.table_schema='public' THEN 1 ELSE 2 END,
#       c.table_schema, c.table_name
#     LIMIT 200;
#     """
#     return pd.read_sql(sql, engine)

# st.subheader("DEBUG: sessions → detectar columna de fecha/hora")
# sess_dt_col, sess_cols_df = detect_sessions_datetime_col("mp", "sessions")
# st.write("Columna detectada:", sess_dt_col)
# st.dataframe(sess_cols_df, use_container_width=True)


SCHEMA = "mp"  # <-- tu schema controlado
# =========================
# ACTIVACIÓN - Transactions config
# =========================
TX_TABLE = "transactions"
TX_DATE_COL = "tx_date"
TX_USER_COL = "customer_id"
TX_TABLE_HINTS = ["transactions", "transaction", "tx", "user_transactions", "customer_transactions"]

HERE = os.path.dirname(os.path.abspath(__file__))
TOP_IMAGE = os.path.join(HERE, "mindharvest_header.png")     # opcional
SIDEBAR_LOGO = os.path.join(HERE, "mi_logo.png")            # opcional

# -----------------------------
# BRAND (NUEVA PALETA, MISMA CALIDAD)
# -----------------------------
BRAND = {
    "bg": "#B4B4C1",        # paper
    "panel": "#270C29",     # deep navy
    "panel2": "#101A2C",
    "card": "#0B1220",
    "grid": "#2A3A55",
    "text": "#0B1220",      # texto general
    "muted": "#55627A",     # gris azulado
    "accent": "#7C3AED",    # violet
    "accent2": "#A855F7",   # violet bright
    "good": "#10B981",      # emerald
    "warn": "#F59E0B",      # amber
    "bad": "#EF4444",       # red
    "chart_bg": "#0B1220",
    "chart_text": "#EAF1FF",
    "chip_bg": "#121D31",
}

def build_series_color_map(series_list):
    """
    Paleta de ALTO contraste (colorblind-friendly) + overrides
    para que CDMX/Guadalajara no se parezcan nunca.
    """
    series_list = [str(x) for x in series_list if str(x).strip()]

    # Base: Okabe-Ito (alto contraste) + extras que combinan con tu branding oscuro
    palette = [
        "#0072B2",  # blue
        "#E69F00",  # orange
        "#009E73",  # green
        "#D55E00",  # vermillion
        "#CC79A7",  # purple/pink
        "#56B4E9",  # sky
        "#F0E442",  # yellow
        "#999999",  # grey
        "#1D4ED8",  # cobalt
        "#00F5A0",  # bright green
        "#A855F7",  # violet
        "#22C55E",  # green
    ]

    # Overrides duros (si la serie existe, SIEMPRE este color)
    overrides = {
        "Total": "#00F5A0",        # verde brillante
        "CDMX": "#F59E0B",         # naranja fuerte
        "Guadalajara": "#2563EB",  # azul cobalto
        "Monterrey": "#10B981",    # verde
        "Puebla": "#A855F7",       # violeta
        "Querétaro": "#56B4E9",    # sky
        "Queretaro": "#56B4E9",
        "Otros": "#334155",        # slate elegante
    }

    out = {}
    i = 0
    for s in series_list:
        if s in overrides:
            out[s] = overrides[s]
        else:
            out[s] = palette[i % len(palette)]
            i += 1
    return out

def plot_donut_share(df_share, title, series_color_map, value_col="new_users", metric_label="Nuevos usuarios"):
    """
    Donut interactiva (Plotly) con tooltip real.
    df_share: columnas -> series, share, <value_col>

    Nota: Plotly Pie NO soporta cornerRadius real por slice.
    Aquí lo simulamos con stroke + separación leve (pull) + hole.
    """

    if df_share is None or df_share.empty:
        return None

    dfx = df_share.copy()
    dfx["series"] = dfx["series"].astype(str)
    dfx["share"] = pd.to_numeric(dfx["share"], errors="coerce").fillna(0.0)

    if value_col not in dfx.columns:
        dfx[value_col] = 0
    dfx[value_col] = pd.to_numeric(dfx[value_col], errors="coerce").fillna(0)

    # si value_col es GMV puede ser float; si es usuarios puede ser int
    # lo dejamos numérico y formateamos con hovertemplate
    dfx = dfx.sort_values(["share", "series"], ascending=[False, True]).reset_index(drop=True)

    topn = 8
    main = dfx.head(topn).copy()
    rest = dfx.iloc[topn:].copy()

    if not rest.empty:
        main = pd.concat([main, pd.DataFrame([{
            "series": "Otros",
            "share": float(rest["share"].sum()),
            value_col: float(rest[value_col].sum()),
        }])], ignore_index=True)

    labels = main["series"].tolist()
    shares = main["share"].astype(float).tolist()
    values_abs = pd.to_numeric(main[value_col], errors="coerce").fillna(0).tolist()

    colors = ["#334155" if s == "Otros" else series_color_map.get(s, "#2563EB") for s in labels]

    total_base = float(pd.to_numeric(dfx[value_col], errors="coerce").fillna(0).sum())

    # --- knobs para look "rounded"
    HOLE = 0.70            # un pelín más grande que 0.68 => se siente más suave
    STROKE_W = 3           # borde más grueso => look "mark_arc"
    PULL = 0.012           # separación leve entre slices (simula esquinas redondeadas)
    OUTER_RING_W = 2       # anillo exterior sutil para “acabado” (opcional)

    pull_vec = [0.0 if lab == "Otros" else PULL for lab in labels]

    fig = go.Figure()

    # Capa principal (donut)
    fig.add_trace(
        go.Pie(
            labels=labels,
            values=shares,
            hole=HOLE,
            marker=dict(colors=colors, line=dict(color="#0B1B33", width=STROKE_W)),
            pull=pull_vec,
            customdata=values_abs,
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Participación: %{percent:.1%}<br>"
                + metric_label + ": %{customdata:,}<extra></extra>"
            ),
            textinfo="none",
            sort=False,
        )
    )

    # Capa “acabado”: anillo exterior sutil (da sensación de “rounded arc”)
    # (si no lo quieres, borra este bloque)
    fig.add_trace(
        go.Pie(
            labels=labels,
            values=shares,
            hole=0.92,  # casi todo hueco => queda como un borde exterior
            marker=dict(colors=colors, line=dict(color="#0B1B33", width=OUTER_RING_W)),
            pull=pull_vec,
            textinfo="none",
            hoverinfo="skip",
            sort=False,
            showlegend=False,
            opacity=0.85,
        )
    )

    fig.update_layout(
        paper_bgcolor="#000000",
        plot_bgcolor="#000000",
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        annotations=[
            dict(
                text=f"<b>{total_base:,.0f}</b><br><span style='color:#D7ECFF; font-weight:900;'>{metric_label}</span>",
                x=0.5, y=0.5,
                font=dict(color="white", size=18),
                showarrow=False,
            )
        ],
    )

    return fig

# -----------------------------
# CSS (premium, sidebar OK)  — con DOUBLE BRACKET injection [[ ... ]]
# -----------------------------
def inject_css():
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {BRAND["bg"]};
            --panel: {BRAND["panel"]};
            --panel2: {BRAND["panel2"]};
            --card: {BRAND["card"]};
            --grid: {BRAND["grid"]};
            --text: {BRAND["text"]};
            --muted: {BRAND["muted"]};
            --accent: {BRAND["accent"]};
            --accent2: {BRAND["accent2"]};
            --good: {BRAND["good"]};
            --warn: {BRAND["warn"]};
            --bad: {BRAND["bad"]};
            --chartbg: {BRAND["chart_bg"]};
            --charttext: {BRAND["chart_text"]};
            --chipbg: {BRAND["chip_bg"]};
        }}

        html, body, [class*="css"] {{
            background: var(--bg) !important;
            color: var(--text) !important;
        }}
        .stApp {{ background: var(--bg); }}

        header[data-testid="stHeader"] {{
          background: transparent !important;
          box-shadow: none !important;
        }}
        div[data-testid="stDecoration"]{{ display:none !important; }}

        /* SIDEBAR */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--panel) 0%, #070B14 100%) !important;
            border-right: 1px solid rgba(255,255,255,.10);
        }}
        section[data-testid="stSidebar"] * {{
            color: #EAF1FF !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
            font-size: 16px !important;
            font-weight: 900 !important;
            color: #EAF1FF !important;
        }}

        /* selects */
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
            background: #0F1830 !important;
            border: 1px solid rgba(124,58,237,.45) !important;
            border-radius: 16px !important;
        }}
        section[data-testid="stSidebar"] [data-baseweb="tag"] {{
            background: var(--chipbg) !important;
            border: 1px solid rgba(168,85,247,.55) !important;
            border-radius: 10px !important;
            font-weight: 900 !important;
        }}

        /* buttons */
        section[data-testid="stSidebar"] button[kind="primary"],
        section[data-testid="stSidebar"] button[kind="secondary"] {{
            background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
            border: 1px solid rgba(255,255,255,.14) !important;
            border-radius: 16px !important;
            font-weight: 1000 !important;
            color: white !important;
            padding: .70rem 1rem !important;
            box-shadow: 0 14px 28px rgba(0,0,0,.45) !important;
        }}
        section[data-testid="stSidebar"] button[kind="primary"]:hover,
        section[data-testid="stSidebar"] button[kind="secondary"]:hover {{
            filter: brightness(1.05);
            transform: translateY(-1px);
        }}

        /* HERO */
        .mh-hero {{
            background: radial-gradient(1200px 400px at 25% 0%, rgba(124,58,237,.35), transparent 60%),
                        radial-gradient(1000px 420px at 90% 30%, rgba(16,185,129,.22), transparent 55%),
                        linear-gradient(135deg, var(--panel) 0%, #060A12 100%);
            border-radius: 24px;
            padding: 26px 28px;
            box-shadow: 0 22px 44px rgba(0,0,0,.28);
            border: 1px solid rgba(255,255,255,.08);
        }}
        .mh-hero * {{ color: #EAF1FF !important; }}
        .mh-hero h1 {{
            font-size: clamp(22px, 2.6vw, 34px);
            font-weight: 1000;
            margin: 0 0 6px 0;
        }}
        .mh-hero p {{
            opacity: .92;
            margin: 0;
            font-weight: 600;
        }}
        .mh-pill {{
            display:inline-block;
            padding: 8px 12px;
            border-radius: 999px;
            text-align: center;
            background: rgba(255,255,255,.10);
            border: 1px solid rgba(255,255,255,.14);
            font-weight: 900;
            font-size: 13px;
        }}

        /* Section separators */
        .mh-sep {{
            height: 3px;
            border-radius: 8px;
            background: linear-gradient(90deg, rgba(124,58,237,.95), rgba(16,185,129,.85), rgba(245,158,11,.85));
            opacity: .95;
            margin: 8px 0 14px 0;
        }}

        /* KPI cards + tooltip */
        .mh-kpi {{
            background: var(--panel);
            border-radius: 22px;
            padding: 18px 18px;
            min-height: 170px;
            box-shadow: 0 22px 38px rgba(0,0,0,.22);
            border: 1px solid rgba(255,255,255,.08);
            display:flex;
            flex-direction:column;
            justify-content:center;
            gap: 10px;
            position: relative;
            overflow:hidden;
        }}
        .mh-kpi:before {{
            content:"";
            position:absolute;
            inset:-2px;
            background: radial-gradient(650px 120px at 15% 0%, rgba(124,58,237,.30), transparent 55%),
                        radial-gradient(520px 160px at 85% 40%, rgba(16,185,129,.18), transparent 55%);
            pointer-events:none;
        }}
        .mh-kpi > * {{ position: relative; }}
        .mh-kpi-label {{
            font-weight: 1000;
            text-align: center;
            font-size: clamp(14px, 1.3vw, 18px);
            color: #EAF1FF !important;
            opacity:.96;
            letter-spacing: .2px;
        }}
        .mh-kpi-value {{
            font-weight: 1000;
            text-align: center;
            font-size: clamp(22px, 3.5vw, 56px);
            color: #EAF1FF !important;
            letter-spacing: -0.03em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .mh-kpi-sub {{
            text-align:center;
            color: rgba(234,241,255,.82) !important;
            font-weight: 800;
            font-size: 12px;
        }}

        .mh-tip {{
            position:absolute;
            top: 14px;
            right: 14px;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display:flex;
            align-items:center;
            justify-content:center;
            background: rgba(255,255,255,.10);
            border: 1px solid rgba(255,255,255,.14);
            color: #EAF1FF !important;
            font-weight: 1000;
            cursor: default;
        }}
        .mh-tip:hover .mh-tipbox {{
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
        }}
        .mh-tipbox {{
            position:absolute;
            right: 0;
            top: 34px;
            width: 320px;
            background: #0F1830;
            border: 1px solid rgba(168,85,247,.35);
            border-radius: 16px;
            padding: 12px 12px;
            box-shadow: 0 18px 40px rgba(0,0,0,.45);
            opacity: 0;
            transform: translateY(6px);
            transition: all .18s ease;
            pointer-events: none;
            color: #EAF1FF !important;
            font-size: 12.5px;
            line-height: 1.35;
        }}
        .mh-tipbox b {{ color: #EAF1FF !important; }}

        /* Charts container card */
        .mh-card {{
            background: var(--panel);
            border-radius: 20px;
            padding: 16px;
            box-shadow: 0 18px 38px rgba(0,0,0,.20);
            border: 1px solid rgba(255,255,255,.08);
        }}
        .mh-card * {{ color: #EAF1FF !important; }}

        /* =========================
           FIX st.date_input (Rango de fechas)
           Fondo oscuro + letras blancas
           ========================= */

        /* Contenedor general del widget */
        div[data-testid="stDateInput"] {{
          background: transparent !important;
        }}

        /* La cajita (input) donde se ve el rango */
        div[data-testid="stDateInput"] input {{
          background: #0B1B33 !important;          /* azul marino */
          color: #FFFFFF !important;               /* letras blancas */
          border: 1px solid rgba(255,255,255,.22) !important;
          border-radius: 14px !important;
          font-weight: 900 !important;
          padding: 10px 12px !important;
          caret-color: #FFFFFF !important;
        }}

        /* Placeholder (si llegara a aparecer) */
        div[data-testid="stDateInput"] input::placeholder {{
          color: rgba(255,255,255,.65) !important;
        }}

        /* Iconos / adornos del input (calendario, etc.) */
        div[data-testid="stDateInput"] svg {{
          fill: #D7ECFF !important;
          opacity: 1 !important;
        }}

        /* Label del widget */
        div[data-testid="stDateInput"] [data-testid="stWidgetLabel"] p {{
          color: #95B6EC !important;
          font-weight: 900 !important;
        }}

        /* Cuando el texto está seleccionado dentro del input */
        div[data-testid="stDateInput"] input::selection {{
          background: rgba(37,99,235,.55) !important; /* cobalto */
          color: #FFFFFF !important;
        }}

        /* Dark HTML table */
        .mh-dark-table-wrap {{
            width: 100%;
            border-radius: 16px;
            overflow: auto;
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(11,18,32,.95);
            box-shadow: 0 18px 34px rgba(0,0,0,.35);
        }}
        table.mh-dark-table {{
            width: 100% !important;
            border-collapse: separate !important;
            border-spacing: 0 !important;
            color: #EAF1FF !important;
            font-size: 16px !important;
        }}
        table.mh-dark-table thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            background: rgba(15,24,48,.98) !important;
            color: #EAF1FF !important;
            font-weight: 1000 !important;
            text-align: left !important;
            padding: 12px 14px !important;
            border-bottom: 1px solid rgba(255,255,255,.10) !important;
            white-space: nowrap !important;
        }}
        table.mh-dark-table tbody td {{
            padding: 12px 14px !important;
            border-bottom: 1px solid rgba(255,255,255,.06) !important;
            color: #EAF1FF !important;
            white-space: nowrap !important;
        }}
        table.mh-dark-table tbody tr:nth-child(even) {{
            background: rgba(255,255,255,.03) !important;
        }}
        table.mh-dark-table tbody tr:hover {{
            background: rgba(124,58,237,.16) !important;
        }}

        /* =========================
   DOWNLOAD BUTTON COBALTO
   ========================= */

div[data-testid="stDownloadButton"] > button {{
    background: #0047AB !important;   /* Azul cobalto */
    color: #FFFFFF !important;        /* Letras blancas */

    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,.18) !important;

    font-weight: 900 !important;
    padding: 0.65rem 1rem !important;

    box-shadow:
        0 0 0 2px rgba(0, 71, 171, .35),
        0 14px 28px rgba(0,0,0,.35) !important;

    transition: all .2s ease !important;
}}

div[data-testid="stDownloadButton"] > button:hover {{
    background: #003380 !important;   /* Cobalto más oscuro al hover */
    transform: translateY(-1px);
}}

div[data-testid="stDownloadButton"] > button:active {{
    transform: scale(.98);
}}

        /* ===== HERO PILLS AUTO HIGHLIGHT ===== */

        .mh-pills-auto {{
            display:flex;
            flex-wrap:wrap;
            gap:10px;
            margin-top:10px;

            /* 🔒 NO cambies altura aunque cambie el pill */
            min-height: 44px;
            align-items:center;
        }}

        .mh-pills-auto span{{
            /* 👇 fija caja */
            height: 38px;
            display:flex;
            align-items:center;
            justify-content:center;

            padding: 0 14px;
            border-radius:999px;
            font-weight:900;

            /* 🔒 NO cambies tamaño de letra nunca */
            font-size: 15px;
            line-height: 1;

            border:1px solid rgba(255,255,255,.18);
            background: rgba(10, 18, 35, .28);
            color:#EAF1FF;

            transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease, background .25s ease;
            will-change: transform;
            animation: pillHighlight 16s infinite;
        }}

        .mh-pills-auto span:nth-child(1) {{ animation-delay: 0s; }}
        .mh-pills-auto span:nth-child(2) {{ animation-delay: 4s; }}
        .mh-pills-auto span:nth-child(3) {{ animation-delay: 8s; }}
        .mh-pills-auto span:nth-child(4) {{ animation-delay: 12s; }}

        @keyframes pillHighlight {{

          0% {{
            background: rgba(37, 99, 235, .22);
            border-color: rgba(37, 99, 235, .65);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, .18);
            transform: scale(1.06);

            filter: brightness(1.15) saturate(1.2);
            text-shadow:
                0 0 10px rgba(37, 99, 235, .55),
                0 0 2px rgba(147, 197, 253, .9);
          }}

          20% {{
            background: rgba(37, 99, 235, .22);
            border-color: rgba(37, 99, 235, .65);
            box-shadow: 0 0 0 3px rgba(37, 99, 235, .18);
            transform: scale(1.06);

            filter: brightness(1.15) saturate(1.2);
            text-shadow:
                0 0 10px rgba(37, 99, 235, .55),
                0 0 2px rgba(147, 197, 253, .9);
          }}

          25% {{
            background: rgba(10, 18, 35, .28);
            border-color: rgba(255,255,255,.18);
            box-shadow: none;
            transform: scale(1);

            filter: none;
            text-shadow: none;
          }}

          100% {{
            background: rgba(10, 18, 35, .28);
            border-color: rgba(255,255,255,.18);
            box-shadow: none;
            transform: scale(1);

            filter: none;
            text-shadow: none;
          }}

        }}

        /* ===== SIDEBAR: ANALISIS BOX (borde morado cobalto brillante) ===== */
        .mh-analisis-box {{
          border: 2px solid rgba(0, 71, 171, .95);
          border-radius: 18px;
          padding: 14px 14px 10px 14px;
          margin: 10px 0 14px 0;
          background: rgba(0, 71, 171, .10);
          box-shadow:
            0 0 0 3px rgba(168, 85, 247, .14),
            0 18px 34px rgba(0,0,0,.35);
        }}

        .mh-analisis-title {{
          text-align:center;
          font-weight: 1000;
          letter-spacing: .2px;
          margin: 0 0 10px 0;
          color: #D7ECFF !important;
        }}

        /* ===== CONTENEDOR ANALISIS REAL ===== */
        div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stRadio"]) {{
            border: 2px solid #0047AB !important;
            border-radius: 18px !important;
            padding: 18px 16px 14px 16px !important;
            margin-top: 12px !important;
            background: rgba(0, 71, 171, .10) !important;
            box-shadow:
                0 0 0 3px rgba(168, 85, 247, .15),
                0 18px 34px rgba(0,0,0,.35) !important;
        }}

        div[data-testid="stFormSubmitButton"] button {{
            background-color: #0047AB !important;
            color: white !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
        }}

        div[data-testid="stFormSubmitButton"] button:hover {{
            background-color: #000000 !important;
        }}

        .rounded-chart-container {{
            border-radius: 18px;
            overflow: hidden;
        }}


        div[data-testid="stVegaLiteChart"]{{
        border-radius: 18px !important;
        overflow: hidden !important;
        }}

        div[data-testid="stVegaLiteChart"] canvas,
        div[data-testid="stVegaLiteChart"] svg{{
        border-radius: 18px !important;
        }}
        
        </style>
        
        """,
        unsafe_allow_html=True,
    )

inject_css()


def _table_exists(engine, schema: str, table: str) -> bool:
    q = """
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = :schema
      AND table_name = :table
    LIMIT 1
    """
    return pd.read_sql(text(q), engine, params={"schema": schema, "table": table}).shape[0] > 0

# -----------------------------
# PARAMS (bootstrap temprano)
# -----------------------------
# -----------------------------
# SAFE: get_filters_options (define SIEMPRE antes de usar)
# -----------------------------

@st.cache_data(ttl=60)
def query_active_users_by_bins(params, start_day, end_day, period_days: int):
    """
    Activos por bin = usuarios únicos con al menos 1 sesión dentro del bin.
    Usa mp.sessions.session_date (detectado).
    """
    p = {
        "d1": start_day,
        "d2": end_day,
        "period_days": int(period_days),
    }

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    sql = f"""
    WITH bins AS (
      SELECT
        gs::date AS bin_start,
        (gs::date + (%(period_days)s::int - 1) * interval '1 day')::date AS bin_end
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        (%(period_days)s::int) * interval '1 day'
      ) gs
    )
    SELECT
      b.bin_start AS day,
      COUNT(DISTINCT s.user_id)::int AS value
    FROM bins b
    LEFT JOIN mp.sessions s
    ON s.session_date::date BETWEEN b.bin_start AND b.bin_end    LEFT JOIN mp.users u
      ON u.user_id = s.user_id
    WHERE 1=1
      {where_users}
    GROUP BY 1
    ORDER BY 1;
    """
    return pd.read_sql(sql, engine, params=p)


@st.cache_data(ttl=60)
def get_filters_options():
    # Nota: depende de engine y SCHEMA; asegúrate que ya existan ANTES de este bloque.
    q = f"""
    SELECT
      (SELECT ARRAY_AGG(DISTINCT city ORDER BY city) FROM {SCHEMA}.users) AS cities,
      (SELECT ARRAY_AGG(DISTINCT acquisition_channel ORDER BY acquisition_channel) FROM {SCHEMA}.users) AS channels,
      (SELECT ARRAY_AGG(DISTINCT device ORDER BY device) FROM {SCHEMA}.users) AS devices,
      (SELECT ARRAY_AGG(DISTINCT category ORDER BY category) FROM {SCHEMA}.vendors) AS categories
    """
    df = pd.read_sql(q, engine)
    row = df.iloc[0].to_dict()
    return (
        row.get("cities") or [],
        row.get("channels") or [],
        row.get("devices") or [],
        row.get("categories") or [],
    )

# -----------------------------
# BOOTSTRAP (ya puedes llamar sin NameError)
# -----------------------------
cities_all, channels_all, devices_all, categories_all = get_filters_options()

# -----------------------------
# SAFE: defaults (define SIEMPRE antes de usar)
# -----------------------------
def _defaults(cities_all, channels_all, devices_all, categories_all):
    default_to = date.today()
    default_from = default_to - timedelta(days=60)
    return {
        "date_from": default_from,
        "date_to": default_to,
        "cities": cities_all,
        "channels": channels_all,
        "devices": devices_all,
        "categories": categories_all,
        "statuses": ["completed", "cancelled"],        "series_dim": "(ninguno)",
        "show_total_series": True,
        "series_dim": "(ninguno)",
    }

defaults = _defaults(cities_all, channels_all, devices_all, categories_all)

if "filters_nonce" not in st.session_state:
    st.session_state.filters_nonce = 0
if "filters_state" not in st.session_state or st.session_state.filters_state is None:
    st.session_state.filters_state = defaults

fs = st.session_state.filters_state

params = {
    "date_from": fs["date_from"],
    "date_to": fs["date_to"],
    "cities": fs.get("cities", []),
    "channels": fs.get("channels", []),
    "devices": fs.get("devices", []),
    "categories": fs.get("categories", []),
    "statuses": fs.get("statuses", ["completed", "cancelled"]),
    "series_dim": fs.get("series_dim", "(ninguno)"),
    "show_total_series": fs.get("show_total_series", True),
}

# -----------------------------
# CROSS-FILTER GLOBAL (tipo PowerBI/Tableau)
# -----------------------------
DIM_OPTIONS = ["(ninguno)", "Ciudad", "Canal", "Device", "Categoría (vendor)", "Order status"]

if "xf_dim" not in st.session_state:
    st.session_state.xf_dim = "(ninguno)"
if "xf_values" not in st.session_state:
    st.session_state.xf_values = []

def apply_crossfilter_to_params(params: dict) -> dict:
    dim = st.session_state.get("xf_dim", "(ninguno)")
    vals = st.session_state.get("xf_values", []) or []
    if dim == "(ninguno)" or not vals:
        return params

    p = dict(params)

    def _intersect(current_list, new_list):
        if not current_list:
            return new_list
        s = set(current_list)
        return [x for x in new_list if x in s]

    if dim == "Ciudad":
        p["cities"] = _intersect(p.get("cities", []), vals)
    elif dim == "Canal":
        p["channels"] = _intersect(p.get("channels", []), vals)
    elif dim == "Device":
        p["devices"] = _intersect(p.get("devices", []), vals)
    elif dim == "Categoría (vendor)":
        p["categories"] = _intersect(p.get("categories", []), vals)
    elif dim == "Order status":
        p["statuses"] = _intersect(p.get("statuses", []), vals)

    return p

def crossfilter_ui(prefix: str, options_map: dict):
        colA, colB = st.columns([0.55, 0.45])
        with colA:
            dim = st.selectbox(
                "Filtrar por:",
                DIM_OPTIONS,
                index=DIM_OPTIONS.index(st.session_state.xf_dim) if st.session_state.xf_dim in DIM_OPTIONS else 0,
                key=f"{prefix}_xf_dim",
            )
        with colB:
            opts = options_map.get(dim, []) if dim != "(ninguno)" else []
            vals = st.multiselect(
                "Valores:",
                opts,
                default=[v for v in st.session_state.xf_values if v in opts] if dim == st.session_state.xf_dim else [],
                key=f"{prefix}_xf_vals",
            )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Aplicar", use_container_width=True, key=f"{prefix}_apply"):
                st.session_state.xf_dim = dim
                st.session_state.xf_values = vals
                st.rerun()
        with b2:
            if st.button("Limpiar", use_container_width=True, key=f"{prefix}_clear"):
                st.session_state.xf_dim = "(ninguno)"
                st.session_state.xf_values = []
                st.rerun()


@st.cache_data(ttl=60)
def query_ops_share_by_dim(_engine, params, compare_dim: str, schema: str = "mp") -> pd.DataFrame:
    """
    Share de órdenes por dimensión seleccionada.
    Dimensiones soportadas:
      - Ciudad
      - Canal
      - Device
      - Categoría (vendor)
      - Order status
      - (ninguno) -> Total

    Devuelve columnas:
      series, orders_total, orders_completed, orders_cancelled
    """

    o_created = _pick_existing_col(_engine, schema, "orders", ["created_at", "order_created_at", "order_date", "date", "day"])
    if o_created is None:
        return pd.DataFrame(columns=["series", "orders_total", "orders_completed", "orders_cancelled"])

    o_status = _pick_existing_col(_engine, schema, "orders", ["status", "order_status", "state", "order_state"])
    o_user_id = _pick_existing_col(_engine, schema, "orders", ["user_id", "customer_id", "uid"])
    if o_user_id is None:
        return pd.DataFrame(columns=["series", "orders_total", "orders_completed", "orders_cancelled"])

    o_vendor_id = _pick_existing_col(_engine, schema, "orders", ["vendor_id", "store_id", "merchant_id"])
    o_del = "AND o.deleted_at IS NULL" if _has_col(_engine, schema, "orders", "deleted_at") else ""

    u_pk = _pick_existing_col(_engine, schema, "users", ["user_id", "id"])
    if u_pk is None:
        return pd.DataFrame(columns=["series", "orders_total", "orders_completed", "orders_cancelled"])

    u_city = _pick_existing_col(_engine, schema, "users", ["city", "ciudad"])
    u_channel = _pick_existing_col(_engine, schema, "users", ["acquisition_channel", "channel", "canal"])
    u_device = _pick_existing_col(_engine, schema, "users", ["device", "platform"])
    u_del = "AND u.deleted_at IS NULL" if _has_col(_engine, schema, "users", "deleted_at") else ""

    has_vendors = _table_exists(_engine, schema, "vendors") and (o_vendor_id is not None)
    v_pk = _pick_existing_col(_engine, schema, "vendors", ["vendor_id", "id"]) if has_vendors else None
    v_cat = _pick_existing_col(_engine, schema, "vendors", ["category", "categoria"]) if has_vendors else None
    v_del_join = "AND v.deleted_at IS NULL" if (has_vendors and _has_col(_engine, schema, "vendors", "deleted_at")) else ""

    join_v = ""
    cat_filter = ""
    if has_vendors and v_pk and v_cat:
        join_v = f"""
        LEFT JOIN {schema}.vendors v
          ON v.{v_pk} = o.{o_vendor_id}
         {v_del_join}
        """
        cat_filter = "AND (:categories_is_all = 1 OR v.{v_cat} = ANY(:categories))".format(v_cat=v_cat)

    # dimensión elegida
    if compare_dim in ["Ciudad"]:
        dim_expr = f"u.{u_city}" if u_city else "'UNKNOWN'"
    elif compare_dim in ["Canal"]:
        dim_expr = f"u.{u_channel}" if u_channel else "'UNKNOWN'"
    elif compare_dim in ["Device"]:
        dim_expr = f"u.{u_device}" if u_device else "'UNKNOWN'"
    elif compare_dim in ["Categoría (vendor)", "Categoría", "Category"]:
        dim_expr = f"v.{v_cat}" if (has_vendors and v_cat) else "'UNKNOWN'"
    elif compare_dim in ["Order status", "Order Status", "Order status"]:
        dim_expr = f"o.{o_status}" if o_status else "'UNKNOWN'"
    else:
        # (ninguno) => una sola serie Total
        dim_expr = "'Total'"

    city_filter = f"AND (:cities_is_all = 1 OR u.{u_city} = ANY(:cities))" if u_city else ""
    ch_filter = f"AND (:channels_is_all = 1 OR u.{u_channel} = ANY(:channels))" if u_channel else ""
    dev_filter = f"AND (:devices_is_all = 1 OR u.{u_device} = ANY(:devices))" if u_device else ""

    if o_status:
        total_expr = "COUNT(*)::int AS orders_total"
        completed_expr = f"COUNT(*) FILTER (WHERE o.{o_status} = 'completed')::int AS orders_completed"
        cancelled_expr = f"COUNT(*) FILTER (WHERE o.{o_status} = 'cancelled')::int AS orders_cancelled"
    else:
        total_expr = "COUNT(*)::int AS orders_total"
        completed_expr = "0::int AS orders_completed"
        cancelled_expr = "0::int AS orders_cancelled"

    sql = f"""
    SELECT
      COALESCE(({dim_expr})::text, 'UNKNOWN') AS series,
      {total_expr},
      {completed_expr},
      {cancelled_expr}
    FROM {schema}.orders o
    JOIN {schema}.users u
      ON u.{u_pk} = o.{o_user_id}
     {u_del}
    {join_v}
    WHERE 1=1
      {o_del}
      AND o.{o_created}::date BETWEEN :d1 AND :d2
      {city_filter}
      {ch_filter}
      {dev_filter}
      {cat_filter}
    GROUP BY 1
    ORDER BY orders_total DESC, series ASC
    """

    def _is_all(x):
        return 1 if (x is None or (isinstance(x, (list, tuple)) and len(x) == 0)) else 0

    bind = {
        "d1": params["date_from"],
        "d2": params["date_to"],
        "cities_is_all": _is_all(params.get("cities")),
        "channels_is_all": _is_all(params.get("channels")),
        "devices_is_all": _is_all(params.get("devices")),
        "categories_is_all": _is_all(params.get("categories")),
        "cities": params.get("cities") or [],
        "channels": params.get("channels") or [],
        "devices": params.get("devices") or [],
        "categories": params.get("categories") or [],
    }

    return pd.read_sql(text(sql), _engine, params=bind)

# -----------------------------
# TOPS (con color)
# (SOLO cuando se elige Ventas)
# -----------------------------
def _has_col(engine, schema: str, table: str, col: str) -> bool:
    q = """
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = :schema
      AND table_name = :table
      AND column_name = :col
    LIMIT 1
    """
    return pd.read_sql(text(q), engine, params={"schema": schema, "table": table, "col": col}).shape[0] > 0


def active_filter_badge():
    dim = st.session_state.get("xf_dim", "(ninguno)")
    vals = st.session_state.get("xf_values", []) or []
    if dim == "(ninguno)" or not vals:
        return ""
    short = ", ".join([str(v) for v in vals[:3]]) + (f" +{len(vals)-3}" if len(vals) > 3 else "")
    return f"🔎 Filtro activo: {dim} = {short}"

params = apply_crossfilter_to_params(params)

def sep():
    # evita duplicar separador en reruns / flujos donde ya se pintó
    if st.session_state.get("_last_sep", False):
        return
    st.markdown('<div class="mh-sep"></div>', unsafe_allow_html=True)
    st.session_state["_last_sep"] = True

def reset_sep():
    st.session_state["_last_sep"] = False

# -----------------------------
# Helpers
# -----------------------------
def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def fmt_money(x):
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return "-"

def fmt_pct(x):
    try:
        return f"{100*float(x):.1f}%"
    except Exception:
        return "-"

def kpi_card(label, value, sub, tip_title, tip_body):
    st.markdown(
        f"""
        <div class="mh-kpi">
            <div class="mh-tip">i
                <div class="mh-tipbox">
                    <div style="font-weight:1000; margin-bottom:6px;">{tip_title}</div>
                    <div>{tip_body}</div>
                </div>
            </div>
            <div class="mh-kpi-label">{label}</div>
            <div class="mh-kpi-value">{value}</div>
            <div class="mh-kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def get_series_values(params):
    dim = params.get("series_dim", "(ninguno)")
    if dim == "Ciudad":
        return dim, (params.get("cities") or [])
    if dim == "Canal":
        return dim, (params.get("channels") or [])
    if dim == "Device":
        return dim, (params.get("devices") or [])
    if dim == "Categoría (vendor)":
        return dim, (params.get("categories") or [])
    if dim == "Order status":
        return dim, (params.get("statuses") or [])
    return "(ninguno)", []

# ---- Defaults + reset robusto
def _defaults(cities_all, channels_all, devices_all, categories_all):
    default_to = date.today()
    default_from = default_to - timedelta(days=60)
    return {
        "date_from": default_from,
        "date_to": default_to,
        "cities": cities_all,
        "channels": channels_all,
        "devices": devices_all,
        "categories": categories_all,
        "statuses": ["completed", "cancelled"],
        "series_dim": "(ninguno)",
        "show_total_series": True,
    }

if "filters_nonce" not in st.session_state:
    st.session_state.filters_nonce = 0
if "filters_state" not in st.session_state:
    st.session_state.filters_state = None

# ---- paleta y color scale consistente por dimensión
PALETA = [
    "#7C3AED", "#A855F7", "#10B981", "#F59E0B", "#60A5FA",
    "#F472B6", "#34D399", "#F97316", "#22C55E", "#EAB308",
]

def color_scale_for(values):
    dom = list(values)
    rng = (PALETA * 10)[:len(dom)]
    return alt.Scale(domain=dom, range=rng)

# -----------------------------
# NUEVO: CROSS-FILTER GLOBAL tipo PowerBI/Tableau
# -----------------------------
DIM_OPTIONS = ["(ninguno)", "Categoría", "Ciudad", "Canal", "Device", "Order status"]

if "xf_dim" not in st.session_state:
    st.session_state.xf_dim = "(ninguno)"
if "xf_values" not in st.session_state:
    st.session_state.xf_values = []

def apply_crossfilter_to_params(params: dict) -> dict:
    dim = st.session_state.get("xf_dim", "(ninguno)")
    vals = st.session_state.get("xf_values", []) or []
    if dim == "(ninguno)" or not vals:
        return params

    p = dict(params)

    def _intersect(current_list, new_list):
        if not current_list:
            return new_list
        s = set(current_list)
        return [x for x in new_list if x in s]

    if dim == "Ciudad":
        p["cities"] = _intersect(p.get("cities", []), vals)
    elif dim == "Canal":
        p["channels"] = _intersect(p.get("channels", []), vals)
    elif dim == "Device":
        p["devices"] = _intersect(p.get("devices", []), vals)
    elif dim == "Categoría":
        p["categories"] = _intersect(p.get("categories", []), vals)
    elif dim == "Order status":
        p["statuses"] = _intersect(p.get("statuses", []), vals)

    return p

def crossfilter_ui(prefix: str, options_map: dict):
        colA, colB = st.columns([0.55, 0.45])
        with colA:
            dim = st.selectbox(
                "Filtrar por:",
                DIM_OPTIONS,
                index=DIM_OPTIONS.index(st.session_state.xf_dim) if st.session_state.xf_dim in DIM_OPTIONS else 0,
                key=f"{prefix}_xf_dim",
            )
        with colB:
            opts = options_map.get(dim, []) if dim != "(ninguno)" else []
            vals = st.multiselect(
                "Valores:",
                opts,
                default=[v for v in st.session_state.xf_values if v in opts] if dim == st.session_state.xf_dim else [],
                key=f"{prefix}_xf_vals",
            )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Aplicar", use_container_width=True, key=f"{prefix}_apply"):
                st.session_state.xf_dim = dim
                st.session_state.xf_values = vals
                st.rerun()
        with b2:
            if st.button("Limpiar", use_container_width=True, key=f"{prefix}_clear"):
                st.session_state.xf_dim = "(ninguno)"
                st.session_state.xf_values = []
                st.rerun()

def active_filter_badge():
    dim = st.session_state.get("xf_dim", "(ninguno)")
    vals = st.session_state.get("xf_values", []) or []
    if dim == "(ninguno)" or not vals:
        return ""
    short = ", ".join([str(v) for v in vals[:3]]) + (f" +{len(vals)-3}" if len(vals) > 3 else "")
    return f"🔎 Filtro activo: {dim} = {short}"

# -----------------------------
# Queries
# -----------------------------
@st.cache_data(ttl=60)
def query_new_users_series_by_dim(params):
    """
    Nuevos usuarios por día (signups), con serie por dimensión seleccionada.
    Devuelve columnas: day, series, value

    Reglas:
    - Total SIEMPRE es el total real del rango (con filtros globales ciudad/canal/device),
      NO “suma de lo seleccionado”.
    - Si no hay vals seleccionados (o dim no aplica), cae a Total.
    - Para Categoría (vendor) / Order status: serie deriva del 1er pedido en el rango; si no hay, 'Sin compra'.
    """
    d1, d2 = params["date_from"], params["date_to"]
    dim, vals = get_series_values(params)

    # Normaliza vals
    if not vals:
        vals = []

    # --------- filtros USERS (siempre aplican a signups)
    user_filters = []
    p = {"d1": d1, "d2": d2}

    if params.get("cities"):
        user_filters.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        user_filters.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        user_filters.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(user_filters)) if user_filters else ""

    # =========================
    # CASO 1) dims en users (Ciudad/Canal/Device)
    # =========================
    if dim in ["Ciudad", "Canal", "Device"]:
        # Si no hay vals, cae a Total
        if not vals:
            sql = f"""
            WITH daily AS (
              SELECT u.created_at::date AS day, COUNT(*)::int AS value
              FROM {SCHEMA}.users u
              WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
              {where_users}
              GROUP BY 1
            ),
            calendar AS (
              SELECT d::date AS day
              FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
            )
            SELECT c.day, 'Total'::text AS series, COALESCE(d.value,0)::int AS value
            FROM calendar c
            LEFT JOIN daily d USING(day)
            ORDER BY 1;
            """
            df = pd.read_sql(sql, engine, params=p)
            return df

        dim_sql = {
            "Ciudad": "u.city",
            "Canal": "u.acquisition_channel",
            "Device": "u.device",
        }[dim]

        p["vals"] = vals

        # ✅ Total correcto usando daily_total (no suma de lo seleccionado)
        sql = f"""
        WITH calendar AS (
          SELECT d::date AS day
          FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
        ),
        signups AS (
          SELECT u.user_id, u.created_at::date AS day, CAST({dim_sql} AS text) AS series
          FROM {SCHEMA}.users u
          WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
          {where_users}
        ),
        daily_by_dim AS (
          SELECT day, series, COUNT(*)::int AS value
          FROM signups
          WHERE series = ANY(CAST(%(vals)s AS text[]))
          GROUP BY 1,2
        ),
        daily_total AS (
          SELECT day, COUNT(*)::int AS value
          FROM signups
          GROUP BY 1
        ),
        series_list AS (
          SELECT unnest(CAST(%(vals)s AS text[])) AS series
          UNION ALL SELECT 'Total'::text
        )
        SELECT
          c.day,
          s.series,
          CASE
            WHEN s.series='Total' THEN COALESCE(t.value,0)::int
            ELSE COALESCE(d.value,0)::int
          END AS value
        FROM calendar c
        CROSS JOIN series_list s
        LEFT JOIN daily_by_dim d
          ON d.day = c.day AND d.series = s.series
        LEFT JOIN daily_total t
          ON t.day = c.day
        ORDER BY 1,2;
        """

        df = pd.read_sql(sql, engine, params=p)

        if not params.get("show_total_series", True):
            df = df[df["series"] != "Total"].copy()

        return df

    # =========================
    # CASO 2) Categoría (vendor) / Order status (derivan de ORDERS)
    # =========================
    if dim in ["Categoría (vendor)", "Order status"]:
        # Si no hay vals, cae a Total (signups)
        if not vals:
            sql = f"""
            WITH daily AS (
              SELECT u.created_at::date AS day, COUNT(*)::int AS value
              FROM {SCHEMA}.users u
              WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
              {where_users}
              GROUP BY 1
            ),
            calendar AS (
              SELECT d::date AS day
              FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
            )
            SELECT c.day, 'Total'::text AS series, COALESCE(d.value,0)::int AS value
            FROM calendar c
            LEFT JOIN daily d USING(day)
            ORDER BY 1;
            """
            df = pd.read_sql(sql, engine, params=p)
            return df

        p["vals"] = vals
        series_expr = "v.category" if dim == "Categoría (vendor)" else "o.order_status"

        # ✅ Total correcto usando daily_total (no suma de lo seleccionado)
        sql = f"""
        WITH calendar AS (
          SELECT d::date AS day
          FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
        ),
        signups AS (
          SELECT u.user_id, u.created_at::date AS signup_day
          FROM {SCHEMA}.users u
          WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
          {where_users}
        ),
        first_order AS (
          SELECT
            s.user_id,
            s.signup_day,
            COALESCE(CAST({series_expr} AS text), 'Sin compra') AS series
          FROM signups s
          LEFT JOIN LATERAL (
            SELECT o.order_id, o.order_status, o.vendor_id, o.order_date
            FROM {SCHEMA}.orders o
            WHERE o.user_id = s.user_id
              AND o.order_date::date BETWEEN %(d1)s AND %(d2)s
            ORDER BY o.order_date ASC
            LIMIT 1
          ) o ON TRUE
          LEFT JOIN {SCHEMA}.vendors v
            ON v.vendor_id = o.vendor_id
        ),
        daily_by_dim AS (
          SELECT signup_day AS day, series, COUNT(DISTINCT user_id)::int AS value
          FROM first_order
          WHERE series = ANY(CAST(%(vals)s AS text[]))
          GROUP BY 1,2
        ),
        daily_total AS (
          SELECT signup_day AS day, COUNT(DISTINCT user_id)::int AS value
          FROM first_order
          GROUP BY 1
        ),
        series_list AS (
          SELECT unnest(CAST(%(vals)s AS text[])) AS series
          UNION ALL SELECT 'Total'::text
        )
        SELECT
          c.day,
          s.series,
          CASE
            WHEN s.series='Total' THEN COALESCE(t.value,0)::int
            ELSE COALESCE(d.value,0)::int
          END AS value
        FROM calendar c
        CROSS JOIN series_list s
        LEFT JOIN daily_by_dim d
          ON d.day = c.day AND d.series = s.series
        LEFT JOIN daily_total t
          ON t.day = c.day
        ORDER BY 1,2;
        """

        df = pd.read_sql(sql, engine, params=p)

        if not params.get("show_total_series", True):
            df = df[df["series"] != "Total"].copy()

        return df

    # =========================
    # FALLBACK: Total
    # =========================
    sql = f"""
    WITH daily AS (
      SELECT u.created_at::date AS day, COUNT(*)::int AS value
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
    )
    SELECT c.day, 'Total'::text AS series, COALESCE(d.value,0)::int AS value
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1;
    """
    df = pd.read_sql(sql, engine, params=p)
    return df

@st.cache_data(ttl=60)
def query_active_users_compare_by_dim(params, dim_label):
    """
    Comparativo de usuarios activos (DAU) por dimensión.
    - Activo = usuario con >=1 sesión en rango (mp.sessions.session_date).
    - Filtros base: u.city / u.acquisition_channel / u.device (como tus otros queries).
    - Si dim_label es Categoría (vendor) o Order status: se deriva de mp.orders + mp.vendors
      usando el PRIMER pedido del usuario en el rango (LATERAL), igual que tu patrón de signups.
    Retorna: dim, active_users
    """

    d1, d2 = params["date_from"], params["date_to"]

    # filtros base SOLO users (idéntico a tus patterns)
    wh_u = []
    p = {"d1": d1, "d2": d2}

    if params.get("cities"):
        wh_u.append("u.city = ANY(CAST(:cities AS text[]))")
        p["cities"] = params["cities"]

    if params.get("channels"):
        wh_u.append("u.acquisition_channel = ANY(CAST(:channels AS text[]))")
        p["channels"] = params["channels"]

    if params.get("devices"):
        wh_u.append("u.device = ANY(CAST(:devices AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(wh_u)) if wh_u else ""

    # =========================
    # Caso 1: dims que viven en users
    # =========================
    if dim_label in ["Ciudad", "Canal", "Device"]:
        dim_sql = {
            "Ciudad": "u.city",
            "Canal": "u.acquisition_channel",
            "Device": "u.device",
        }[dim_label]

        sql = f"""
        WITH active_users AS (
          SELECT DISTINCT s.user_id
          FROM {SCHEMA}.sessions s
          JOIN {SCHEMA}.users u ON u.user_id = s.user_id
          WHERE s.session_date::date BETWEEN :d1 AND :d2
          {where_users}
        )
        SELECT
          COALESCE(CAST({dim_sql} AS text), 'UNKNOWN') AS dim,
          COUNT(DISTINCT a.user_id)::int AS active_users
        FROM active_users a
        JOIN {SCHEMA}.users u ON u.user_id = a.user_id
        GROUP BY 1
        ORDER BY active_users DESC;
        """
        df = pd.read_sql(text(sql), engine, params=p)
        df["dim"] = df["dim"].astype(str).fillna("UNKNOWN")
        return df

    # =========================
    # Caso 2: dims que derivan de orders/vendors
    # (tu mismo patrón: LATERAL first order en rango)
    # =========================
    if dim_label in ["Categoría (vendor)", "Order status"]:
        # de dónde sale la serie
        series_expr = "v.category" if dim_label == "Categoría (vendor)" else "o.order_status"

        # filtros opcionales (estos SÍ aplican sobre el primer pedido)
        # Nota: aquí NO usamos build_where() porque build_where incluye v/o,
        # pero necesitamos mantener el rango y la relación por user_id.
        wh_o = []
        if params.get("categories"):
            wh_o.append("v.category = ANY(CAST(:categories AS text[]))")
            p["categories"] = params["categories"]

        if params.get("statuses"):
            wh_o.append("o.order_status = ANY(CAST(:statuses AS text[]))")
            p["statuses"] = params["statuses"]

        where_orders = (" AND " + " AND ".join(wh_o)) if wh_o else ""

        sql = f"""
        WITH active_users AS (
          SELECT DISTINCT s.user_id
          FROM {SCHEMA}.sessions s
          JOIN {SCHEMA}.users u ON u.user_id = s.user_id
          WHERE s.session_date::date BETWEEN :d1 AND :d2
          {where_users}
        ),
        first_order AS (
          SELECT
            a.user_id,
            COALESCE(CAST({series_expr} AS text), 'Sin compra') AS dim
          FROM active_users a
          LEFT JOIN LATERAL (
            SELECT o.order_id, o.order_status, o.vendor_id, o.order_date
            FROM {SCHEMA}.orders o
            WHERE o.user_id = a.user_id
              AND o.order_date::date BETWEEN :d1 AND :d2
            ORDER BY o.order_date ASC
            LIMIT 1
          ) o ON TRUE
          LEFT JOIN {SCHEMA}.vendors v
            ON v.vendor_id = o.vendor_id
          WHERE 1=1
          {where_orders}
        )
        SELECT
          dim,
          COUNT(DISTINCT user_id)::int AS active_users
        FROM first_order
        GROUP BY 1
        ORDER BY active_users DESC;
        """

        df = pd.read_sql(text(sql), engine, params=p)
        df["dim"] = df["dim"].astype(str).fillna("UNKNOWN")
        return df

    # fallback seguro
    return pd.DataFrame(columns=["dim", "active_users"])
# -----------------------------
# BOOTSTRAP: opciones + defaults + estado
# -----------------------------
cities_all, channels_all, devices_all, categories_all = get_filters_options()
defaults = _defaults(cities_all, channels_all, devices_all, categories_all)

if "filters_nonce" not in st.session_state:
    st.session_state.filters_nonce = 0
if "filters_state" not in st.session_state or st.session_state.filters_state is None:
    st.session_state.filters_state = defaults

fs = st.session_state.filters_state

def build_where(params):
    wh = []
    p = {}
    p["d1"] = params["date_from"]
    p["d2"] = params["date_to"]

    if params["cities"]:
        wh.append("u.city = ANY(CAST(:cities AS text[]))")
        p["cities"] = params["cities"]
    if params["channels"]:
        wh.append("u.acquisition_channel = ANY(CAST(:channels AS text[]))")
        p["channels"] = params["channels"]
    if params["devices"]:
        wh.append("u.device = ANY(CAST(:devices AS text[]))")
        p["devices"] = params["devices"]
    if params["categories"]:
        wh.append("v.category = ANY(CAST(:categories AS text[]))")
        p["categories"] = params["categories"]
    if params["statuses"]:
        wh.append("o.order_status = ANY(CAST(:statuses AS text[]))")
        p["statuses"] = params["statuses"]

    return (" AND " + " AND ".join(wh)) if wh else "", p

def query_ops_timeseries_by_dim(engine, params, compare_dim: str, schema: str = "mp") -> pd.DataFrame:
    """
    Serie temporal agregada de calidad operativa.
    NO desglosa por ciudad/canal/device/categoría.
    SOLO filtra por lo seleccionado en el sidebar.

    Devuelve:
      day, orders_total, orders_completed, orders_cancelled
    """

    o_created = _pick_existing_col(engine, schema, "orders", ["created_at", "order_created_at", "order_date", "date", "day"])
    if o_created is None:
        return pd.DataFrame(columns=["day", "orders_total", "orders_completed", "orders_cancelled"])

    o_status = _pick_existing_col(engine, schema, "orders", ["status", "order_status", "state", "order_state"])
    o_user_id = _pick_existing_col(engine, schema, "orders", ["user_id", "customer_id", "uid"])
    if o_user_id is None:
        return pd.DataFrame(columns=["day", "orders_total", "orders_completed", "orders_cancelled"])

    o_vendor_id = _pick_existing_col(engine, schema, "orders", ["vendor_id", "store_id", "merchant_id"])
    o_del = "AND o.deleted_at IS NULL" if _has_col(engine, schema, "orders", "deleted_at") else ""

    u_pk = _pick_existing_col(engine, schema, "users", ["user_id", "id"])
    if u_pk is None:
        return pd.DataFrame(columns=["day", "orders_total", "orders_completed", "orders_cancelled"])

    u_city = _pick_existing_col(engine, schema, "users", ["city", "ciudad"])
    u_channel = _pick_existing_col(engine, schema, "users", ["acquisition_channel", "channel", "canal"])
    u_device = _pick_existing_col(engine, schema, "users", ["device", "platform"])
    u_del = "AND u.deleted_at IS NULL" if _has_col(engine, schema, "users", "deleted_at") else ""

    has_vendors = _table_exists(engine, schema, "vendors") and (o_vendor_id is not None)
    v_pk = _pick_existing_col(engine, schema, "vendors", ["vendor_id", "id"]) if has_vendors else None
    v_cat = _pick_existing_col(engine, schema, "vendors", ["category", "categoria"]) if has_vendors else None
    v_del_join = "AND v.deleted_at IS NULL" if (has_vendors and _has_col(engine, schema, "vendors", "deleted_at")) else ""

    join_v = ""
    cat_filter = ""
    if has_vendors and v_pk and v_cat:
        join_v = f"""
        LEFT JOIN {schema}.vendors v
          ON v.{v_pk} = o.{o_vendor_id}
         {v_del_join}
        """
        cat_filter = "AND (:categories_is_all = 1 OR v.{v_cat} = ANY(:categories))".format(v_cat=v_cat)

    city_filter = f"AND (:cities_is_all = 1 OR u.{u_city} = ANY(:cities))" if u_city else ""
    ch_filter   = f"AND (:channels_is_all = 1 OR u.{u_channel} = ANY(:channels))" if u_channel else ""
    dev_filter  = f"AND (:devices_is_all = 1 OR u.{u_device} = ANY(:devices))" if u_device else ""

    if o_status:
        total_expr     = "COUNT(*)::int AS orders_total"
        completed_expr = f"COUNT(*) FILTER (WHERE o.{o_status} = 'completed')::int AS orders_completed"
        cancelled_expr = f"COUNT(*) FILTER (WHERE o.{o_status} = 'cancelled')::int AS orders_cancelled"
    else:
        total_expr     = "COUNT(*)::int AS orders_total"
        completed_expr = "0::int AS orders_completed"
        cancelled_expr = "0::int AS orders_cancelled"

    sql = f"""
    SELECT
      DATE(o.{o_created}) AS day,
      {total_expr},
      {completed_expr},
      {cancelled_expr}
    FROM {schema}.orders o
    JOIN {schema}.users u
      ON u.{u_pk} = o.{o_user_id}
     {u_del}
    {join_v}
    WHERE 1=1
      {o_del}
      AND o.{o_created}::date BETWEEN :d1 AND :d2
      {city_filter}
      {ch_filter}
      {dev_filter}
      {cat_filter}
    GROUP BY 1
    ORDER BY 1
    """

    def _is_all(x):
        return 1 if (x is None or (isinstance(x, (list, tuple)) and len(x) == 0)) else 0

    bind = {
        "d1": params["date_from"],
        "d2": params["date_to"],

        "cities_is_all": _is_all(params.get("cities")),
        "channels_is_all": _is_all(params.get("channels")),
        "devices_is_all": _is_all(params.get("devices")),
        "categories_is_all": _is_all(params.get("categories")),

        "cities": params.get("cities") or [],
        "channels": params.get("channels") or [],
        "devices": params.get("devices") or [],
        "categories": params.get("categories") or [],
    }

    return pd.read_sql(text(sql), engine, params=bind)

def _pick_existing_col(engine, schema: str, table: str, candidates: list[str]) -> str | None:
    for c in candidates:
        if _has_col(engine, schema, table, c):
            return c
    return None


@st.cache_data(ttl=60)
def query_new_users_share_and_samples(params):
    """
    Devuelve:
      - df_share: series, new_users, share
      - df_samples: series, sample_users (string con 5 ids/nombres)
    Solo para dims que existen en mp.users: Ciudad / Canal / Device.
    """
    d1, d2 = params["date_from"], params["date_to"]
    dim = params.get("series_dim", "(ninguno)")

    dim_sql = {
        "Ciudad": "u.city",
        "Canal": "u.acquisition_channel",
        "Device": "u.device",
    }.get(dim, None)

    if not dim_sql:
        return pd.DataFrame(), pd.DataFrame()

    p = {"d1": d1, "d2": d2}

    # Filtros de users (crossfilter ya aplicado en params)
    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    # 1) share por categoría (signups en rango)
    sql_share = f"""
    WITH base AS (
      SELECT
        CAST({dim_sql} AS text) AS series,
        u.user_id,
        u.created_at
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
    ),
    agg AS (
      SELECT series, COUNT(*)::int AS new_users
      FROM base
      GROUP BY 1
    ),
    tot AS (
      SELECT SUM(new_users)::float AS total_new
      FROM agg
    )
    SELECT
      a.series,
      a.new_users,
      CASE WHEN t.total_new > 0 THEN a.new_users / t.total_new ELSE 0 END AS share
    FROM agg a
    CROSS JOIN tot t
    ORDER BY a.new_users DESC;
    """

    df_share = pd.read_sql(sql_share, engine, params=p)

    if df_share.empty:
        return df_share, pd.DataFrame()

    # Tomamos top 5 categorías para muestras (para que sea legible)
    top_series = df_share["series"].astype(str).head(5).tolist()
    p2 = dict(p)
    p2["top_series"] = top_series

    # 2) primeros 5 usuarios por categoría (por created_at asc)
    # OJO: aquí uso user_id. Si tienes "name" o "email", te lo cambio.
    sql_samples = f"""
    WITH base AS (
      SELECT
        CAST({dim_sql} AS text) AS series,
        u.user_id::text AS user_label,
        u.created_at
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
        AND CAST({dim_sql} AS text) = ANY(CAST(%(top_series)s AS text[]))
      {where_users}
    ),
    ranked AS (
      SELECT
        series,
        user_label,
        created_at,
        ROW_NUMBER() OVER (PARTITION BY series ORDER BY created_at ASC) AS rn
      FROM base
    )
    SELECT
      series,
      STRING_AGG(user_label, ', ' ORDER BY created_at ASC) AS sample_users
    FROM ranked
    WHERE rn <= 5
    GROUP BY 1
    ORDER BY 1;
    """

    df_samples = pd.read_sql(sql_samples, engine, params=p2)
    return df_share, df_samples


@st.cache_data(ttl=60)
def query_kpis(params):
    where_extra, p = build_where(params)

    sql = f"""
    WITH base_sessions AS (
      SELECT s.user_id, s.session_date::date AS day
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN :d1 AND :d2
      {(" AND u.city = ANY(CAST(:cities AS text[]))") if params["cities"] else ""}
      {(" AND u.acquisition_channel = ANY(CAST(:channels AS text[]))") if params["channels"] else ""}
      {(" AND u.device = ANY(CAST(:devices AS text[]))") if params["devices"] else ""}
    ),
    base_orders AS (
      SELECT
        o.*,
        u.city,
        u.acquisition_channel,
        u.device,
        v.category
      FROM {SCHEMA}.orders o
      JOIN {SCHEMA}.users u ON u.user_id = o.user_id
      JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
      WHERE o.order_date::date BETWEEN :d1 AND :d2
      {where_extra}
    ),
    dau_by_day AS (
      SELECT day, COUNT(DISTINCT user_id) AS dau
      FROM base_sessions
      GROUP BY 1
    ),
    last7 AS (
      SELECT AVG(dau)::float AS dau_7d_avg
      FROM (
        SELECT * FROM dau_by_day
        ORDER BY day DESC
        LIMIT 7
      ) t
    ),
    mau AS (
      SELECT COUNT(DISTINCT s.user_id) AS mau
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE date_trunc('month', s.session_date) = date_trunc('month', CAST(:d2 AS date))
      {(" AND u.city = ANY(CAST(:cities AS text[]))") if params["cities"] else ""}
      {(" AND u.acquisition_channel = ANY(CAST(:channels AS text[]))") if params["channels"] else ""}
      {(" AND u.device = ANY(CAST(:devices AS text[]))") if params["devices"] else ""}
    ),
    signups AS (
      SELECT COUNT(*) AS new_users
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN :d1 AND :d2
      {(" AND u.city = ANY(CAST(:cities AS text[]))") if params["cities"] else ""}
      {(" AND u.acquisition_channel = ANY(CAST(:channels AS text[]))") if params["channels"] else ""}
      {(" AND u.device = ANY(CAST(:devices AS text[]))") if params["devices"] else ""}
    ),
    first_order AS (
      SELECT
        u.user_id,
        u.created_at::date AS signup_day,
        MIN(o.order_date::date) AS first_order_day
      FROM {SCHEMA}.users u
      LEFT JOIN {SCHEMA}.orders o
        ON o.user_id = u.user_id
      WHERE u.created_at::date BETWEEN :d1 AND :d2
      {(" AND u.city = ANY(CAST(:cities AS text[]))") if params["cities"] else ""}
      {(" AND u.acquisition_channel = ANY(CAST(:channels AS text[]))") if params["channels"] else ""}
      {(" AND u.device = ANY(CAST(:devices AS text[]))") if params["devices"] else ""}
      GROUP BY 1,2
    ),
    activation AS (
      SELECT
        AVG(CASE WHEN first_order_day IS NOT NULL AND first_order_day <= signup_day + 7 THEN 1 ELSE 0 END)::float AS activation_7d
      FROM first_order
    ),
    orders_agg AS (
      SELECT
        COUNT(*) AS orders_total,
        SUM(CASE WHEN order_status='completed' THEN 1 ELSE 0 END) AS orders_completed,
        SUM(CASE WHEN order_status='cancelled' THEN 1 ELSE 0 END) AS orders_cancelled,
        SUM(CASE WHEN order_status='completed' THEN order_total ELSE 0 END)::float AS gmv,
        SUM(CASE WHEN order_status='completed' THEN commission ELSE 0 END)::float AS commission
      FROM base_orders
    )
    SELECT
      (SELECT dau_7d_avg FROM last7) AS dau_7d_avg,
      (SELECT mau FROM mau) AS mau,
      (SELECT new_users FROM signups) AS new_users,
      (SELECT activation_7d FROM activation) AS activation_7d,
      (SELECT orders_total FROM orders_agg) AS orders_total,
      (SELECT orders_completed FROM orders_agg) AS orders_completed,
      (SELECT orders_cancelled FROM orders_agg) AS orders_cancelled,
      (SELECT gmv FROM orders_agg) AS gmv,
      (SELECT commission FROM orders_agg) AS commission
    ;
    """

    df = pd.read_sql(text(sql), engine, params={**p, "d1": params["date_from"], "d2": params["date_to"]})
    r = df.iloc[0].to_dict()

    dau = float(r.get("dau_7d_avg") or 0.0)
    mau = float(r.get("mau") or 0.0)
    stickiness = (dau / mau) if mau > 0 else 0.0

    orders_total = int(r.get("orders_total") or 0)
    orders_completed = int(r.get("orders_completed") or 0)
    orders_cancelled = int(r.get("orders_cancelled") or 0)

    gmv = float(r.get("gmv") or 0.0)
    commission = float(r.get("commission") or 0.0)
    aov = (gmv / orders_completed) if orders_completed > 0 else 0.0
    cancel_rate = (orders_cancelled / orders_total) if orders_total > 0 else 0.0

    return {
        "dau_7d_avg": dau,
        "mau": mau,
        "stickiness": stickiness,
        "new_users": int(r.get("new_users") or 0),
        "activation_7d": float(r.get("activation_7d") or 0.0),
        "orders_total": orders_total,
        "orders_completed": orders_completed,
        "cancel_rate": cancel_rate,
        "gmv": gmv,
        "aov": aov,
        "commission": commission,
        "orders_cancelled": orders_cancelled,
    }

@st.cache_data(ttl=60)
def query_users_base_vs_new(params):
    """
    Regresa:
      - base_before: usuarios creados antes de date_from (con mismos filtros de ciudad/canal/device)
      - new_in_range: usuarios creados entre date_from y date_to
      - total_all: usuarios totales en toda la BD (con filtros ciudad/canal/device)  [sin filtrar por fechas]
    """
    p = {"d1": params["date_from"], "d2": params["date_to"]}

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    wh = (" AND " + " AND ".join(extra)) if extra else ""

    sql = f"""
    WITH base_before AS (
      SELECT COUNT(*)::int AS base_before
      FROM {SCHEMA}.users u
      WHERE u.created_at::date < %(d1)s
      {wh}
    ),
    new_in_range AS (
      SELECT COUNT(*)::int AS new_in_range
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {wh}
    ),
    total_all AS (
      SELECT COUNT(*)::int AS total_all
      FROM {SCHEMA}.users u
      WHERE 1=1
      {wh}
    )
    SELECT
      (SELECT base_before FROM base_before) AS base_before,
      (SELECT new_in_range FROM new_in_range) AS new_in_range,
      (SELECT total_all FROM total_all) AS total_all;
    """

    df = pd.read_sql(sql, engine, params=p)
    r = df.iloc[0].to_dict()

    base_before = int(r.get("base_before") or 0)
    new_in_range = int(r.get("new_in_range") or 0)
    total_all = int(r.get("total_all") or 0)

    return base_before, new_in_range, total_all

# =============================
# ACTIVACIÓN — QUERIES (COPIAR/PEGAR)
# No rompe nada: misma firma, mismo retorno.
# =============================

@st.cache_data(ttl=60)
def query_active_users_kpis_vs_prev(params):
    """
    Regresa:
      - total_users_all: usuarios totales (con filtros ciudad/canal/device) [sin fechas]
      - active_users: usuarios únicos con sesión en rango
      - active_users_prev: usuarios únicos con sesión en periodo anterior (mismo largo)
      - avg_dau: promedio de DAU en rango (promedio diario)
      - prev_d1, prev_d2, delta_abs, delta_pct
    """
    d1 = params["date_from"]
    d2 = params["date_to"]

    days = (d2 - d1).days + 1
    prev_d2 = d1 - timedelta(days=1)
    prev_d1 = prev_d2 - timedelta(days=days - 1)

    p = {"d1": d1, "d2": d2, "pd1": prev_d1, "pd2": prev_d2}

    # filtros SOLO de users (igual que tú)
    wh = []
    if params.get("cities"):
        wh.append("u.city = ANY(CAST(:cities AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        wh.append("u.acquisition_channel = ANY(CAST(:channels AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        wh.append("u.device = ANY(CAST(:devices AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(wh)) if wh else ""

    sql = f"""
    WITH total_users AS (
      SELECT COUNT(*)::int AS total_users_all
      FROM {SCHEMA}.users u
      WHERE 1=1
      {where_users}
    ),
    active_range AS (
      SELECT COUNT(DISTINCT s.user_id)::int AS active_users
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN :d1 AND :d2
      {where_users}
    ),
    active_prev AS (
      SELECT COUNT(DISTINCT s.user_id)::int AS active_users_prev
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN :pd1 AND :pd2
      {where_users}
    ),
    dau_by_day AS (
      SELECT s.session_date::date AS day, COUNT(DISTINCT s.user_id)::int AS dau
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN :d1 AND :d2
      {where_users}
      GROUP BY 1
    ),
    avg_dau AS (
      SELECT COALESCE(AVG(dau),0)::float AS avg_dau
      FROM dau_by_day
    )
    SELECT
      (SELECT total_users_all FROM total_users) AS total_users_all,
      (SELECT active_users FROM active_range) AS active_users,
      (SELECT active_users_prev FROM active_prev) AS active_users_prev,
      (SELECT avg_dau FROM avg_dau) AS avg_dau;
    """

    r = pd.read_sql(text(sql), engine, params=p).iloc[0].to_dict()

    total_users_all = int(r.get("total_users_all") or 0)
    active_users = int(r.get("active_users") or 0)
    active_users_prev = int(r.get("active_users_prev") or 0)
    avg_dau = float(r.get("avg_dau") or 0.0)

    share_active = (active_users / total_users_all) if total_users_all > 0 else 0.0
    delta_abs = active_users - active_users_prev
    delta_pct = (delta_abs / active_users_prev) if active_users_prev > 0 else (1.0 if active_users > 0 else 0.0)

    return {
        "total_users_all": total_users_all,
        "active_users": active_users,
        "active_users_prev": active_users_prev,
        "share_active": share_active,
        "avg_dau": avg_dau,
        "prev_d1": prev_d1,
        "prev_d2": prev_d2,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }


@st.cache_data(ttl=60)
def query_dau_daily_extended(params, start_day, end_day):
    """
    DAU por día para rango extendido (start_day -> end_day)
    respetando filtros ciudad/canal/device (via users)
    """
    p = {"d1": start_day, "d2": end_day}

    # ✅ CAMBIO CLAVE: usa placeholders :param (porque aquí NO envuelves text(sql))
    wh = []
    if params.get("cities"):
        wh.append("u.city = ANY(CAST(:cities AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        wh.append("u.acquisition_channel = ANY(CAST(:channels AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        wh.append("u.device = ANY(CAST(:devices AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(wh)) if wh else ""

    sql = f"""
    WITH daily AS (
      SELECT
        s.session_date::date AS day,
        COUNT(DISTINCT s.user_id)::int AS dau
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN :d1 AND :d2
      {where_users}
      GROUP BY 1
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(CAST(:d1 AS date), CAST(:d2 AS date), interval '1 day') g(d)
    )
    SELECT c.day, COALESCE(d.dau,0)::int AS dau
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1;
    """

    return pd.read_sql(text(sql), engine, params=p)

@st.cache_data(ttl=60)
def query_users_base_new_vs_prev(params):
    # rango actual
    d1 = params["date_from"]
    d2 = params["date_to"]

    # mismo largo de periodo hacia atrás (incluyente)
    days = (d2 - d1).days + 1
    prev_d2 = d1 - timedelta(days=1)
    prev_d1 = prev_d2 - timedelta(days=days - 1)

    # filtros de users (NO uses categories/status aquí)
    wh = []
    p = {
        "d1": d1,
        "d2": d2,
        "pd1": prev_d1,
        "pd2": prev_d2,
    }

    if params.get("cities"):
        wh.append("u.city = ANY(CAST(:cities AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        wh.append("u.acquisition_channel = ANY(CAST(:channels AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        wh.append("u.device = ANY(CAST(:devices AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(wh)) if wh else ""

    sql = f"""
    WITH base_before AS (
      SELECT COUNT(*)::int AS users_before
      FROM {SCHEMA}.users u
      WHERE u.created_at::date < :d1
      {where_users}
    ),
    new_in_range AS (
      SELECT COUNT(*)::int AS new_users
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN :d1 AND :d2
      {where_users}
    ),
    new_prev_range AS (
      SELECT COUNT(*)::int AS new_users_prev
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN :pd1 AND :pd2
      {where_users}
    )
    SELECT
      (SELECT users_before FROM base_before) AS users_before,
      (SELECT new_users FROM new_in_range) AS new_users,
      (SELECT new_users_prev FROM new_prev_range) AS new_users_prev;
    """

    df = pd.read_sql(text(sql), engine, params=p)
    r = df.iloc[0].to_dict()

    users_before = int(r.get("users_before") or 0)
    new_users = int(r.get("new_users") or 0)
    new_users_prev = int(r.get("new_users_prev") or 0)

    total_considered = users_before + new_users
    pct_new = (new_users / total_considered) if total_considered > 0 else 0.0

    delta_abs = new_users - new_users_prev
    delta_pct = (delta_abs / new_users_prev) if new_users_prev > 0 else (1.0 if new_users > 0 else 0.0)

    return {
        "users_before": users_before,
        "new_users": new_users,
        "total_considered": total_considered,
        "pct_new": pct_new,
        "prev_d1": prev_d1,
        "prev_d2": prev_d2,
        "new_users_prev": new_users_prev,
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
    }

def plot_users_one_bar(base_before: int, new_in_range: int):
    total = base_before + new_in_range
    fig, ax = plt.subplots(figsize=(6.2, 2.2), dpi=140)

    # barra base (azul claro)
    ax.barh(["Usuarios"], [base_before], label="Acumulados previos", color="#60A5FA")

    # nuevos (verde si >=0, rojo si <0)
    new_color = "#10B981" if new_in_range >= 0 else "#EF4444"
    ax.barh(["Usuarios"], [new_in_range], left=[base_before], label="Nuevos en el rango", color=new_color)

    # texto
    ax.set_xlim(0, max(total * 1.12, 1))
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.grid(axis="x", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    ax.text(base_before / 2 if base_before else 0.0, 0, f"{base_before:,}", va="center", ha="center", fontsize=10, fontweight="bold", color="white")
    ax.text(base_before + (new_in_range / 2 if new_in_range else 0.0), 0, f"{new_in_range:,}", va="center", ha="center", fontsize=10, fontweight="bold", color="white")

    ax.set_title("Usuarios: base + nuevos (rango seleccionado)", fontsize=11, fontweight="bold")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


@st.cache_data(ttl=3600)
def find_table_by_columns(table_hints, required_cols):
    """
    Encuentra (schema, table) buscando:
    - nombre parecido (hints)
    - y que tenga columnas requeridas (required_cols)
    """
    # 1) primero intenta por nombre exacto / hints
    sql_by_name = """
    SELECT t.table_schema, t.table_name
    FROM information_schema.tables t
    WHERE t.table_type='BASE TABLE'
      AND t.table_name = ANY(CAST(%(names)s AS text[]))
    ORDER BY CASE WHEN t.table_schema='mp' THEN 0
                  WHEN t.table_schema='public' THEN 1
                  ELSE 2 END, t.table_schema
    """
    df = pd.read_sql(sql_by_name, engine, params={"names": list(table_hints)})
    if not df.empty:
        # valida columnas
        for _, r in df.iterrows():
            sch, tbl = r["table_schema"], r["table_name"]
            if table_has_columns(sch, tbl, required_cols):
                return sch, tbl

    # 2) si no, busca cualquier tabla que tenga esas columnas
    sql_any = """
    SELECT c.table_schema, c.table_name
    FROM information_schema.columns c
    WHERE c.column_name = ANY(CAST(%(cols)s AS text[]))
    GROUP BY 1,2
    HAVING COUNT(DISTINCT c.column_name) = %(ncols)s
    ORDER BY CASE WHEN c.table_schema='mp' THEN 0
                  WHEN c.table_schema='public' THEN 1
                  ELSE 2 END, c.table_schema
    LIMIT 1;
    """
    df2 = pd.read_sql(sql_any, engine, params={"cols": list(required_cols), "ncols": len(required_cols)})
    if df2.empty:
        raise ValueError(
            "No encuentro ninguna tabla con columnas "
            + ", ".join(required_cols)
            + ". Revisa que estés conectado a la BD correcta."
        )
    return df2.iloc[0]["table_schema"], df2.iloc[0]["table_name"]


@st.cache_data(ttl=3600)
def table_has_columns(schema: str, table: str, required_cols):
    sql = """
    SELECT COUNT(DISTINCT column_name) AS n
    FROM information_schema.columns
    WHERE table_schema=%(s)s
      AND table_name=%(t)s
      AND column_name = ANY(CAST(%(cols)s AS text[]))
    """
    df = pd.read_sql(sql, engine, params={"s": schema, "t": table, "cols": list(required_cols)})
    return int(df.iloc[0]["n"]) == len(required_cols)

@st.cache_data(ttl=60)
def query_active_users_by_bins(params, start_day, end_day, period_days: int):
    """
    Activos por bin = usuarios únicos con al menos 1 sesión dentro del bin.
    Usa mp.sessions.session_date (ya detectado).
    """
    p = {
        "d1": start_day,
        "d2": end_day,
        "period_days": int(period_days),
    }

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    sql = """
    WITH bins AS (
      SELECT
        gs::date AS bin_start,
        (gs::date + (%(period_days)s::int - 1) * interval '1 day')::date AS bin_end
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        (%(period_days)s::int) * interval '1 day'
      ) gs
    )
    SELECT
      b.bin_start AS day,
      COUNT(DISTINCT s.user_id)::int AS value
    FROM bins b
    LEFT JOIN mp.sessions s
        ON s.session_date::date BETWEEN b.bin_start AND b.bin_end
    LEFT JOIN mp.users u
      ON u.user_id = s.user_id
    WHERE 1=1
      """ + where_users + """
    GROUP BY 1
    ORDER BY 1;
    """

    return pd.read_sql(sql, engine, params=p)


@st.cache_data(ttl=60)
def query_timeseries(params):
    where_extra, p = build_where(params)

    sql_orders = f"""
    SELECT
      o.order_date::date AS day,
      SUM(CASE WHEN o.order_status='completed' THEN o.order_total ELSE 0 END)::float AS gmv,
      COUNT(*)::int AS orders_total,
      SUM(CASE WHEN o.order_status='completed' THEN 1 ELSE 0 END)::int AS orders_completed,
      SUM(CASE WHEN o.order_status='cancelled' THEN 1 ELSE 0 END)::int AS orders_cancelled
    FROM {SCHEMA}.orders o
    JOIN {SCHEMA}.users u ON u.user_id = o.user_id
    JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
    WHERE o.order_date::date BETWEEN :d1 AND :d2
    {where_extra}
    GROUP BY 1
    ORDER BY 1;
    """

    sql_dau = f"""
    SELECT
      s.session_date::date AS day,
      COUNT(DISTINCT s.user_id)::int AS dau
    FROM {SCHEMA}.sessions s
    JOIN {SCHEMA}.users u ON u.user_id = s.user_id
    WHERE s.session_date::date BETWEEN :d1 AND :d2
    {(" AND u.city = ANY(CAST(:cities AS text[]))") if params["cities"] else ""}
    {(" AND u.acquisition_channel = ANY(CAST(:channels AS text[]))") if params["channels"] else ""}
    {(" AND u.device = ANY(CAST(:devices AS text[]))") if params["devices"] else ""}
    GROUP BY 1
    ORDER BY 1;
    """

    df_orders = pd.read_sql(
        text(sql_orders),
        engine,
        params={**p, "d1": params["date_from"], "d2": params["date_to"]},
    )

    df_dau = pd.read_sql(
        text(sql_dau),
        engine,
        params={**p, "d1": params["date_from"], "d2": params["date_to"]},
    )

    return df_orders, df_dau


@st.cache_data(ttl=60)
def query_dau_series_by_dim(params):
    """
    DAU por día y por dimensión (Ciudad/Canal/Device) + Total.
    Respeta filtros de users (cities/channels/devices) que ya vienen en params
    (crossfilter ya aplicado).
    """
    p = {"d1": params["date_from"], "d2": params["date_to"]}

    # dimensión seleccionada
    dim_label = params.get("series_dim", "(ninguno)")
    dim_map = {
        "Ciudad": "u.city",
        "Canal": "u.acquisition_channel",
        "Device": "u.device",
    }
    dim_sql = dim_map.get(dim_label)

    # filtros de users (como ya haces en signup)
    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    # ---- si no hay dimensión, regresamos solo Total
    if dim_sql is None:
        sql = f"""
        WITH daily AS (
          SELECT
            s.created_at::date AS day,
            COUNT(DISTINCT s.user_id)::int AS value
          FROM {SCHEMA}.sessions s
          JOIN {SCHEMA}.users u ON u.user_id = s.user_id
          WHERE s.created_at::date BETWEEN %(d1)s AND %(d2)s
          {where_users}
          GROUP BY 1
        ),
        calendar AS (
          SELECT d::date AS day
          FROM generate_series(
            CAST(%(d1)s AS date),
            CAST(%(d2)s AS date),
            interval '1 day'
          ) g(d)
        )
        SELECT
          c.day,
          'Total'::text AS series,
          COALESCE(d.value, 0)::int AS value
        FROM calendar c
        LEFT JOIN daily d USING(day)
        ORDER BY 1,2;
        """
        return pd.read_sql(sql, engine, params=p)

    # ---- con dimensión: Total + series por dim
    sql = f"""
    WITH by_dim AS (
      SELECT
        s.created_at::date AS day,
        COALESCE(CAST({dim_sql} AS text), 'UNKNOWN') AS series,
        COUNT(DISTINCT s.user_id)::int AS value
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1,2
    ),
    total AS (
      SELECT
        day,
        'Total'::text AS series,
        SUM(value)::int AS value
      FROM by_dim
      GROUP BY 1
    ),
    combined AS (
      SELECT * FROM by_dim
      UNION ALL
      SELECT * FROM total
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    ),
    series_list AS (
      SELECT DISTINCT series FROM combined
    )
    SELECT
      c.day,
      s.series,
      COALESCE(x.value, 0)::int AS value
    FROM calendar c
    CROSS JOIN series_list s
    LEFT JOIN combined x
      ON x.day = c.day AND x.series = s.series
    ORDER BY 1,2;
    """
    return pd.read_sql(sql, engine, params=p)

@st.cache_data(ttl=60)
def query_new_users_series(params):
    # respeta: date_from/date_to + city/channel/device (crossfilter ya aplicado en params)
    p = {"d1": params["date_from"], "d2": params["date_to"]}

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    sql = f"""
    WITH daily AS (
      SELECT
        u.created_at::date AS day,
        COUNT(*)::int AS new_users
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1
    ),
    base_before AS (
      SELECT COUNT(*)::int AS users_before
      FROM {SCHEMA}.users u
      WHERE u.created_at::date < %(d1)s
      {where_users}
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    )
    SELECT
      c.day,
      COALESCE(d.new_users, 0)::int AS new_users,
      (SELECT users_before FROM base_before)
        + SUM(COALESCE(d.new_users,0)) OVER (ORDER BY c.day) AS users_cum
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1;
    """

    # OJO: aquí NO uses text(sql) para que respete %(...)s tal cual
    df = pd.read_sql(sql, engine, params=p)
    return df

@st.cache_data(ttl=60)
def query_new_users_series_by_dim(params):
    d1, d2 = params["date_from"], params["date_to"]
    dim, vals = get_series_values(params)

    # Solo dims que existen en users para signups:
    dim_sql = {
        "Ciudad": "u.city",
        "Canal": "u.acquisition_channel",
        "Device": "u.device",
        "Order status": "NULL",              # no aplica a signups
        "Categoría (vendor)": "NULL",        # no aplica a signups
        "(ninguno)": "NULL",
    }.get(dim, "NULL")

    # si dim no aplica o no hay vals, devolvemos solo Total
    if dim_sql == "NULL" or not vals:
        sql = f"""
        WITH daily AS (
          SELECT u.created_at::date AS day, COUNT(*)::int AS value
          FROM {SCHEMA}.users u
          WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
          {(" AND u.city = ANY(CAST(%(cities)s AS text[]))") if params.get("cities") else ""}
          {(" AND u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))") if params.get("channels") else ""}
          {(" AND u.device = ANY(CAST(%(devices)s AS text[]))") if params.get("devices") else ""}
          GROUP BY 1
        ),
        calendar AS (
          SELECT d::date AS day
          FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
        )
        SELECT c.day, 'Total'::text AS series, COALESCE(d.value,0)::int AS value
        FROM calendar c
        LEFT JOIN daily d USING(day)
        ORDER BY 1;
        """
        p = {"d1": d1, "d2": d2, **{k: params[k] for k in ["cities","channels","devices"] if params.get(k)}}
        return pd.read_sql(sql, engine, params=p)

    # dim activo: series = Total + cada valor seleccionado
    sql = f"""
    WITH calendar AS (
      SELECT d::date AS day
      FROM generate_series(CAST(%(d1)s AS date), CAST(%(d2)s AS date), interval '1 day') g(d)
    ),
    daily_by_dim AS (
      SELECT
        u.created_at::date AS day,
        CAST({dim_sql} AS text) AS series,
        COUNT(*)::int AS value
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
        AND CAST({dim_sql} AS text) = ANY(CAST(%(vals)s AS text[]))
      {(" AND u.city = ANY(CAST(%(cities)s AS text[]))") if params.get("cities") else ""}
      {(" AND u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))") if params.get("channels") else ""}
      {(" AND u.device = ANY(CAST(%(devices)s AS text[]))") if params.get("devices") else ""}
      GROUP BY 1,2
    ),
    daily_total AS (
      SELECT
        u.created_at::date AS day,
        'Total'::text AS series,
        COUNT(*)::int AS value
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {(" AND u.city = ANY(CAST(%(cities)s AS text[]))") if params.get("cities") else ""}
      {(" AND u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))") if params.get("channels") else ""}
      {(" AND u.device = ANY(CAST(%(devices)s AS text[]))") if params.get("devices") else ""}
      GROUP BY 1
    ),
    series_list AS (
      SELECT unnest(CAST(%(vals)s AS text[])) AS series
      UNION ALL SELECT 'Total'::text
    )
    SELECT
      c.day,
      s.series,
      COALESCE(d.value,0)::int AS value
    FROM calendar c
    CROSS JOIN series_list s
    LEFT JOIN daily_by_dim d
      ON d.day = c.day AND d.series = s.series
    LEFT JOIN daily_total t
      ON t.day = c.day AND s.series='Total'
    -- si es Total, usa t.value
    ORDER BY 1,2;
    """

    p = {"d1": d1, "d2": d2, "vals": vals}
    if params.get("cities"): p["cities"] = params["cities"]
    if params.get("channels"): p["channels"] = params["channels"]
    if params.get("devices"): p["devices"] = params["devices"]

    df = pd.read_sql(sql, engine, params=p)

    # Total correcto (sobrescribe value cuando series=Total)
    # (porque arriba devolvimos Total en t.value pero value venía de daily_by_dim)
    # --- Total correcto por día (recalcula desde df mismo)
    if "Total" in df["series"].unique():
        tot = df[df["series"] != "Total"].groupby("day", as_index=False)["value"].sum()
        tot["series"] = "Total"
        df = df[df["series"] != "Total"].copy()
        df = pd.concat([df, tot], ignore_index=True)
        df = df.sort_values(["day", "series"])

    if not params.get("show_total_series", True):
        df = df[df["series"] != "Total"].copy()

    return df

@st.cache_data(ttl=60)
def query_dau_series_by_dim(params):
    """
    DAU por día (usuarios únicos con >=1 sesión), con serie por dimensión elegida.
    Usa mp.sessions.session_date (NO created_at).
    Devuelve columnas: day, series, value
    """
    p = {"d1": params["date_from"], "d2": params["date_to"]}

    # dimensión para series (misma lógica que usas en Nuevos usuarios)
    dim = params.get("series_dim", "(ninguno)")
    dim_map = {
        "Ciudad": "u.city",
        "Canal": "u.acquisition_channel",
        "Device": "u.device",
        "Categoría (vendor)": None,   # no aplica directo a sessions
        "Order status": None,         # no aplica directo a sessions
        "(ninguno)": None,
    }
    dim_sql = dim_map.get(dim)

    # filtros de users (crossfilter global ya aplicado a params)
    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    # --- 1) Total (siempre)
    sql_total = f"""
    WITH daily AS (
      SELECT
        s.session_date::date AS day,
        COUNT(DISTINCT s.user_id)::int AS value
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    )
    SELECT
      c.day,
      'Total'::text AS series,
      COALESCE(d.value, 0)::int AS value
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1,2;
    """

    df_total = pd.read_sql(sql_total, engine, params=p)

    # --- 2) Series por dimensión (si aplica)
    if not dim_sql:
        return df_total

    sql_dim = f"""
    WITH daily AS (
      SELECT
        s.session_date::date AS day,
        COALESCE(CAST({dim_sql} AS text), 'UNKNOWN') AS series,
        COUNT(DISTINCT s.user_id)::int AS value
      FROM {SCHEMA}.sessions s
      JOIN {SCHEMA}.users u ON u.user_id = s.user_id
      WHERE s.session_date::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1,2
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    ),
    series_list AS (
      SELECT DISTINCT series FROM daily
    )
    SELECT
      c.day,
      s.series,
      COALESCE(d.value, 0)::int AS value
    FROM calendar c
    CROSS JOIN series_list s
    LEFT JOIN daily d
      ON d.day = c.day AND d.series = s.series
    ORDER BY 1,2;
    """

    df_dim = pd.read_sql(sql_dim, engine, params=p)

    # Une Total + series
    return pd.concat([df_total, df_dim], ignore_index=True)

@st.cache_data(ttl=60)
def query_new_users_daily(params):
    p = {"d1": params["date_from"], "d2": params["date_to"]}

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    sql = f"""
    WITH daily AS (
      SELECT
        u.created_at::date AS day,
        COUNT(*)::int AS new_users
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    )
    SELECT
      c.day,
      COALESCE(d.new_users, 0)::int AS new_users
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1;
    """
    return pd.read_sql(sql, engine, params=p)


def plot_new_users_accum_stacked(df):
    # df: day, new_users, users_cum
    dfx = df.copy()
    dfx["day"] = pd.to_datetime(dfx["day"])
    dfx["delta_new"] = dfx["new_users"].diff().fillna(dfx["new_users"]).astype(int)

    x = dfx["day"].dt.strftime("%m-%d").tolist()
    cum = dfx["users_cum"].astype(float).tolist()
    delta = dfx["delta_new"].astype(float).tolist()

    fig, ax = plt.subplots(figsize=(8.6, 3.4), dpi=140)

    # fondo oscuro (coherente con tu tema)
    fig.patch.set_facecolor(BRAND["chart_bg"])
    ax.set_facecolor(BRAND["chart_bg"])

    # 1) base acumulado (azul claro)
    ax.bar(
        x, cum,
        color="#93C5FD",  # azul claro
        alpha=0.95,
        label="Usuarios acumulados"
    )

    # 2) “delta” encima (verde/rojo)
    delta_colors = ["#10B981" if v >= 0 else "#EF4444" for v in delta]
    bottoms = [c if v >= 0 else (c + v) for c, v in zip(cum, delta)]  # si baja, pinta hacia abajo

    ax.bar(
        x, [abs(v) for v in delta],
        bottom=bottoms,
        color=delta_colors,
        alpha=0.95,
        label="Δ nuevos usuarios (vs día anterior)"
    )

    # estilo
    ax.tick_params(axis="x", labelrotation=0, labelsize=8, colors=BRAND["chart_text"])
    ax.tick_params(axis="y", labelsize=9, colors=BRAND["chart_text"])
    ax.grid(True, axis="y", alpha=0.18)
    for spine in ax.spines.values():
        spine.set_alpha(0.15)

    ax.set_title("Nuevos usuarios: acumulado + cambio diario", color=BRAND["chart_text"], fontsize=12, fontweight="bold")
    ax.legend(frameon=False, fontsize=8, labelcolor=BRAND["chart_text"])

    fig.tight_layout()
    return fig


def plot_new_users_line(df_daily):
    dfx = df_daily.copy()
    dfx["day"] = pd.to_datetime(dfx["day"])

    fig, ax = plt.subplots(figsize=(10.5, 3.0), dpi=160)
    fig.patch.set_facecolor(BRAND["chart_bg"])
    ax.set_facecolor(BRAND["chart_bg"])

    ax.plot(dfx["day"], dfx["new_users"], linewidth=2.4)

    ax.set_title("Nuevos usuarios por día", color=BRAND["chart_text"], fontsize=12, fontweight="bold", pad=10)
    ax.tick_params(axis="x", colors=BRAND["chart_text"], labelsize=9)
    ax.tick_params(axis="y", colors=BRAND["chart_text"], labelsize=9)
    ax.grid(True, axis="y", alpha=0.18)

    for s in ax.spines.values():
        s.set_alpha(0.15)

    fig.tight_layout()
    return fig

@st.cache_data(ttl=60)
def query_new_users_daily_extended(params, start_day, end_day):
    """
    Devuelve nuevos usuarios por día, para un rango extendido (start_day -> end_day),
    respetando filtros de users: ciudad/canal/device (crossfilter ya aplicado en params).
    """
    p = {"d1": start_day, "d2": end_day}

    extra = []
    if params.get("cities"):
        extra.append("u.city = ANY(CAST(%(cities)s AS text[]))")
        p["cities"] = params["cities"]
    if params.get("channels"):
        extra.append("u.acquisition_channel = ANY(CAST(%(channels)s AS text[]))")
        p["channels"] = params["channels"]
    if params.get("devices"):
        extra.append("u.device = ANY(CAST(%(devices)s AS text[]))")
        p["devices"] = params["devices"]

    where_users = (" AND " + " AND ".join(extra)) if extra else ""

    sql = f"""
    WITH daily AS (
      SELECT
        u.created_at::date AS day,
        COUNT(*)::int AS new_users
      FROM {SCHEMA}.users u
      WHERE u.created_at::date BETWEEN %(d1)s AND %(d2)s
      {where_users}
      GROUP BY 1
    ),
    calendar AS (
      SELECT d::date AS day
      FROM generate_series(
        CAST(%(d1)s AS date),
        CAST(%(d2)s AS date),
        interval '1 day'
      ) g(d)
    )
    SELECT
      c.day,
      COALESCE(d.new_users, 0)::int AS new_users
    FROM calendar c
    LEFT JOIN daily d USING(day)
    ORDER BY 1;
    """
    return pd.read_sql(sql, engine, params=p)


# =========================
# SIGNUPS por series (siempre definido)
# =========================

def plot_period_bars_same_size(
    df_daily,
    period_days: int,
    selected_period_index: int,
    title: str,
):
    """
    df_daily: columnas ['day','value'] o ['day','new_users']
    period_days: tamaño del bin (mismo que rango seleccionado)
    selected_period_index: índice del bin que corresponde al periodo seleccionado
    """
    dfx = df_daily.copy()
    dfx["day"] = pd.to_datetime(dfx["day"]).dt.date

    # detecta col de valor
    val_col = "value" if "value" in dfx.columns else ("new_users" if "new_users" in dfx.columns else None)
    if val_col is None:
        raise ValueError("df_daily debe traer columna 'value' o 'new_users'.")

    # start del bucket = mínimo day del df (debe ser start_all)
    start_all = min(dfx["day"])
    dfx["offset_days"] = dfx["day"].apply(lambda d: (d - start_all).days)
    dfx["period_idx"] = (dfx["offset_days"] // period_days).astype(int)

    agg = dfx.groupby("period_idx", as_index=False)[val_col].sum()
    agg = agg.sort_values("period_idx")

    # labels por rango de cada bin
    def _label_for_idx(i):
        s = start_all + timedelta(days=i * period_days)
        e = s + timedelta(days=period_days - 1)
        return f"{s:%m-%d}→{e:%m-%d}"

    labels = [_label_for_idx(i) for i in agg["period_idx"].tolist()]
    values = agg[val_col].astype(float).tolist()
    idxs = agg["period_idx"].tolist()

    # colores
    COBALT = "#0047AB"
    GREEN_COBALT = "#00F5A0"  # verde brillante con vibe “cobaltico”
    colors = [GREEN_COBALT if i == selected_period_index else COBALT for i in idxs]

    fig, ax = plt.subplots(figsize=(11.5, 3.2), dpi=160)
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    bars = ax.bar(
        labels,
        values,
        color=colors,
        edgecolor=["#7DD3FC" if i == selected_period_index else "#93C5FD" for i in idxs],  # borde azulado
        linewidth=[2.2 if i == selected_period_index else 1.2 for i in idxs],
        alpha=0.95,
    )

    # glow SOLO al seleccionado (doble pintura)
    for b, i in zip(bars, idxs):
        if i == selected_period_index:
            ax.bar(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                width=b.get_width(),
                color=GREEN_COBALT,
                alpha=0.20,
                linewidth=10,
                edgecolor=GREEN_COBALT,
                zorder=0,
            )

    # estilo premium dark
    ax.set_title(title, color="white", fontsize=12.5, fontweight="bold", pad=10)
    ax.tick_params(axis="x", colors="white", labelsize=9, rotation=0)
    ax.tick_params(axis="y", colors="white", labelsize=9)
    ax.grid(True, axis="y", alpha=0.18)
    for s in ax.spines.values():
        s.set_visible(False)

    # etiquetas arriba (compactas)
    ymax = max(values) if values else 1
    ax.set_ylim(0, ymax * 1.18)
    for b, i in zip(bars, idxs):
        h = b.get_height()
        if h <= 0:
            continue
        ax.text(
            b.get_x() + b.get_width() / 2,
            h + ymax * 0.03,
            f"{int(h):,}",
            ha="center",
            va="bottom",
            color="white",
            fontsize=9,
            fontweight="bold" if i == selected_period_index else 700,
        )

    fig.tight_layout()
    return fig

@st.cache_data(ttl=60)
def query_top(params):
    where_extra, p = build_where(params)

    sql_top_cities = f"""
    SELECT
      u.city,
      SUM(CASE WHEN o.order_status='completed' THEN o.order_total ELSE 0 END)::float AS gmv,
      COUNT(*)::int AS orders
    FROM {SCHEMA}.orders o
    JOIN {SCHEMA}.users u ON u.user_id = o.user_id
    JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
    WHERE o.order_date::date BETWEEN :d1 AND :d2
    {where_extra}
    GROUP BY 1
    ORDER BY gmv DESC
    LIMIT 10;
    """

    sql_top_vendors = f"""
    SELECT
      o.vendor_id,
      v.city,
      v.category,
      AVG(v.rating)::float AS rating,
      SUM(CASE WHEN o.order_status='completed' THEN o.order_total ELSE 0 END)::float AS gmv,
      COUNT(*)::int AS orders
    FROM {SCHEMA}.orders o
    JOIN {SCHEMA}.users u ON u.user_id = o.user_id
    JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
    WHERE o.order_date::date BETWEEN :d1 AND :d2
    {where_extra}
    GROUP BY 1,2,3
    ORDER BY gmv DESC
    LIMIT 15;
    """

    df_cities = pd.read_sql(text(sql_top_cities), engine, params={**p, "d1": params["date_from"], "d2": params["date_to"]})
    df_vendors = pd.read_sql(text(sql_top_vendors), engine, params={**p, "d1": params["date_from"], "d2": params["date_to"]})
    return df_cities, df_vendors

@st.cache_data(ttl=60)
def query_compare_orders(params, dim_label):
    where_extra, p = build_where(params)

    dim_map = {
        "Categoría": "v.category",
        "Ciudad": "u.city",
        "Canal": "u.acquisition_channel",
        "Device": "u.device",
        "Order status": "o.order_status",
    }
    dim_sql = dim_map[dim_label]

    sql_dim = f"""
    SELECT
      {dim_sql} AS dim,
      SUM(CASE WHEN o.order_status='completed' THEN o.order_total ELSE 0 END)::float AS gmv,
      COUNT(*)::int AS orders_total,
      SUM(CASE WHEN o.order_status='cancelled' THEN 1 ELSE 0 END)::int AS orders_cancelled,
      SUM(CASE WHEN o.order_status='completed' THEN commission ELSE 0 END)::float AS commission
    FROM {SCHEMA}.orders o
    JOIN {SCHEMA}.users u ON u.user_id = o.user_id
    JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
    WHERE o.order_date::date BETWEEN :d1 AND :d2
    {where_extra}
    GROUP BY 1
    ORDER BY gmv DESC;
    """

    df_dim = pd.read_sql(text(sql_dim), engine, params={**p, "d1": params["date_from"], "d2": params["date_to"]})
    if df_dim.empty:
        return df_dim, df_dim

    top_dims = df_dim["dim"].head(5).astype(str).tolist()

    sql_trend = f"""
    SELECT
      o.order_date::date AS day,
      {dim_sql} AS dim,
      SUM(CASE WHEN o.order_status='completed' THEN o.order_total ELSE 0 END)::float AS gmv,
      COUNT(*)::int AS orders_total,
      SUM(CASE WHEN o.order_status='cancelled' THEN 1 ELSE 0 END)::int AS orders_cancelled,
      SUM(CASE WHEN o.order_status='completed' THEN commission ELSE 0 END)::float AS commission
    FROM {SCHEMA}.orders o
    JOIN {SCHEMA}.users u ON u.user_id = o.user_id
    JOIN {SCHEMA}.vendors v ON v.vendor_id = o.vendor_id
    WHERE o.order_date::date BETWEEN :d1 AND :d2
      AND CAST({dim_sql} AS text) = ANY(CAST(:top_dims AS text[]))
    {where_extra}
    GROUP BY 1,2
    ORDER BY 1,2;
    """

    df_trend = pd.read_sql(
        text(sql_trend),
        engine,
        params={**p, "d1": params["date_from"], "d2": params["date_to"], "top_dims": top_dims},
    )
    return df_dim, df_trend

# -----------------------------
# SIDEBAR
# -----------------------------

defaults = _defaults(cities_all, channels_all, devices_all, categories_all)
if st.session_state.filters_state is None:
    st.session_state.filters_state = defaults

fs = st.session_state.filters_state

with st.sidebar:
    if os.path.exists(SIDEBAR_LOGO):
        st.image(SIDEBAR_LOGO, use_container_width=True)
        st.write("")

    st.markdown(
        '<div style="text-align:center; font-weight:900;">• ¿Qué quieres analizar? •</div>',
        unsafe_allow_html=True,
    )

    st.write("")
    st.write("")

    
    reset_sep()

    sep()

    ANALISIS_OPTS = [
        "Adquisición de clientes",
        "Activación de clientes",
        "Ventas",
        "Calidad operativa",
        "Todos los anteriores",
    ]

    if "focus_analisis" not in st.session_state:
        st.session_state.focus_analisis = "Todos los anteriores"

    focus_analisis = st.radio(
        label="",
        options=ANALISIS_OPTS,
        index=ANALISIS_OPTS.index(st.session_state.focus_analisis),
        key="focus_analisis",
    )

    st.write("")    

    reset_sep()
    sep()

    with st.form(f"filters_{st.session_state.filters_nonce}", clear_on_submit=False):
        date_from, date_to = st.date_input(
            "Rango de fechas:",
            value=(fs["date_from"], fs["date_to"]),
        )

        SERIES_DIM_OPTS = ["(ninguno)", "Ciudad", "Canal", "Device", "Categoría (vendor)", "Order status"]

        series_dim = st.selectbox(
            "Desglosar análisis por:",
            SERIES_DIM_OPTS,
            index=SERIES_DIM_OPTS.index(fs.get("series_dim", "(ninguno)")) if fs.get("series_dim", "(ninguno)") in SERIES_DIM_OPTS else 0,
        )
        
        show_total_series = st.checkbox("Mostrar Total", value=True, key="show_total_series")
        
        st.markdown("### 🎯 Elige los elementos relevantes para el análisis:") 

        city_sel = st.multiselect("Ciudad:", cities_all, default=fs["cities"])
        channel_sel = st.multiselect("Canal:", channels_all, default=fs["channels"])
        device_sel = st.multiselect("Device:", devices_all, default=fs["devices"])
        category_sel = st.multiselect("Categoría (vendor):", categories_all, default=fs["categories"])
        status_sel = st.multiselect("Order status:", ["completed", "cancelled"], default=fs["statuses"])

        apply_btn = st.form_submit_button("Aplicar filtros", use_container_width=True)

    st.write("")


    
    # Reset filtros principales
    if st.button("Desactivar filtros (Reset)", use_container_width=True):
        st.session_state.filters_state = defaults
        st.session_state.filters_nonce += 1
        st.rerun()
    
    with st.expander("📌 Glosario rápido de KPIs", expanded=False):
        st.markdown("""

- **Activación 7d:** % de usuarios que hacen su primera compra dentro de 7 días de signup.
- **AOV:** ticket promedio (GMV / órdenes completadas).
- **Cancelación:** canceladas / total órdenes.
- **Comisión:** suma de comisión (órdenes completadas).
- **DAU (promedio 7 días):** usuarios únicos con sesión en los últimos 7 días del rango.
- **GMV:** ventas brutas (suma de órdenes completadas).
- **MAU:** usuarios únicos con sesión en el mes del `date_to`.
- **Stickiness:** DAU/MAU. Señala hábito de uso.


        """)

    st.markdown(
        """
        <div style="
            margin-top: 48px;
            padding-top: 18px;
            border-top: 1px solid rgba(255,255,255,.16);
            text-align:center;
            font-size:11px;
            font-weight:800;
            opacity:.85;
            line-height:1.35;
        ">
            © 2026 <b>MindHarvestAI</b><br>
            Analítica de Negocios<br>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Normaliza date_input
if isinstance(date_from, (tuple, list)):
    date_from, date_to = date_from[0], date_from[1]

if apply_btn:
    st.session_state.filters_state = {
        "date_from": date_from,
        "date_to": date_to,
        "cities": city_sel,
        "channels": channel_sel,
        "devices": device_sel,
        "categories": category_sel,
        "statuses": status_sel,
        "series_dim": series_dim,
        "show_total_series": show_total_series,
        "compare_dim": series_dim,   
    }
    st.rerun()


# =========================
# PARAMS (siempre definido)
# =========================
# =========================
# PARAMS (siempre definido)
# =========================
fs = st.session_state.filters_state  # dict garantizado

params = {
    "date_from": fs["date_from"],
    "date_to": fs["date_to"],
    "cities": fs.get("cities", []),
    "channels": fs.get("channels", []),
    "devices": fs.get("devices", []),
    "categories": fs.get("categories", []),
    "statuses": fs.get("statuses", ["completed", "cancelled"]),
    "series_dim": fs.get("series_dim", "(ninguno)"),
    "show_total_series": fs.get("show_total_series", True),
}

# alias útiles (para que NO dependas de variables del form)
date_from = params["date_from"]
date_to = params["date_to"]
compare_dim = fs.get("compare_dim", "Ciudad")      # si lo quieres persistir, guárdalo en filters_state
metric_sel = fs.get("metric_sel", "GMV")

    # fallback si aún no hay estado (primer render)
if params["date_from"] is None or params["date_to"] is None:
        # usa defaults que YA estabas usando en el form
        params["date_from"] = fs.get("date_from_default") or st.session_state.get("date_from_default")
        params["date_to"] = fs.get("date_to_default") or st.session_state.get("date_to_default")

# ---- aplica cross-filter global a TODO (KPIs + todas las gráficas)
params = apply_crossfilter_to_params(params)    

# -----------------------------
# FLAGS por categoría (DEFINIR UNA SOLA VEZ)
# -----------------------------
focus_analisis = st.session_state.get("focus_analisis", "Todos los anteriores")
show_ops_panel = focus_analisis in ["Calidad operativa", "Todos los anteriores"]

show_acq = focus_analisis in ["Adquisición de clientes", "Todos los anteriores"]
show_activation = focus_analisis in ["Activación de clientes", "Todos los anteriores"]
show_new_users_share_panel = focus_analisis in ["Adquisición de clientes", "Todos los anteriores"]
show_sales = focus_analisis in ["Ventas", "Todos los anteriores"]
show_ops = focus_analisis in ["Calidad operativa", "Todos los anteriores"]

# ✅ bins específicos
show_new_users_bins = focus_analisis in ["Adquisición de clientes", "Todos los anteriores"]
show_dau_bins = focus_analisis in ["Activación de clientes", "Todos los anteriores"]

show_new_users_line = show_acq
show_dau_panel = (show_activation and focus_analisis != "Activación de clientes")
show_sales_panel = (show_sales)
show_top_tables = focus_analisis in ["Ventas", "Todos los anteriores"]

# -----------------------------
# HEADER / HERO
# -----------------------------
# ========= 2) HERO: reemplaza SOLO el bloque else: st.markdown(...) por este =========
if os.path.exists(TOP_IMAGE):
    st.image(TOP_IMAGE, use_container_width=True)
else:
    hero_html = f"""<div class="mh-hero">
<div style="display:flex; justify-content:space-between; gap:18px; align-items:flex-start;">
<div>
<div  style="text-align:center; width:100%;">
<a href="https://mindharvestai.com/soluciones" target="_blank" style="color:#EAF1FF; text-decoration:none;">
• Módulo de Analítica de Negocios •
</a>
</div>

<h1>📊 Visibilidad del Negocio — Indicadores de crecimiento</h1>

<p style="margin:0; font-weight:800; opacity:.95;">
Diseñado para decisiones rápidas en materia de:
</p>

<div class="mh-pills-auto">
<span>Adquisición de clientes</span>
<span>Activación de clientes</span>
<span>Ventas</span>
<span>Calidad operativa</span>
</div>

<div style="height:15px;"></div>
<div style="opacity:.92; font-weight:800;">
Rango: <span style="color:#fff;">{date_from} → {date_to}</span>
</div>
</div>

<div style="text-align:right; opacity:.92;">
<div style="font-weight:800;">Actualizado</div>
<div style="font-weight:1000; font-size:16px;">{now_stamp()}</div>
</div>
</div>
</div>""".lstrip()


    st.markdown(hero_html, unsafe_allow_html=True)
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)


    

# -----------------------------
# KPIs
# -----------------------------
# -----------------------------
# KPIs
# -----------------------------
k = query_kpis(params)

focus_analisis = st.session_state.get("focus_analisis", "Todos los anteriores")
show_acq = focus_analisis in ["Adquisición de clientes", "Todos los anteriores"]

if show_acq:
    u = query_users_base_new_vs_prev(params)

    # ---- Cards (2 columnas): share + promedio diario
    days_in_range = (params["date_to"] - params["date_from"]).days + 1
    avg_new_per_day = (u["new_users"] / days_in_range) if days_in_range > 0 else 0.0

    cards_row = st.container()
    with cards_row:
        c1, c2 = st.columns(2)

        with c1:
            kpi_card(
                "Nuevos usuarios (share)",
                f"{100*u['pct_new']:.1f}%",
                f"{u['new_users']:,} nuevos de {u['total_considered']:,} usuarios (base+altas)",
                "Comparación vs periodo anterior",
                (
                    f"Periodo actual: {params['date_from']} → {params['date_to']}<br>"
                    f"Periodo anterior: {u['prev_d1']} → {u['prev_d2']}<br><br>"
                    f"Nuevos actual: <b>{u['new_users']:,}</b><br>"
                    f"Nuevos anterior: <b>{u['new_users_prev']:,}</b><br>"
                    f"Δ: <b>{u['delta_abs']:+,}</b> ({u['delta_pct']*100:+.1f}%)"
                ),
            )

        with c2:
            kpi_card(
                "Promedio nuevos / día",
                f"{avg_new_per_day:,.1f}",
                f"En {days_in_range} día{'s' if days_in_range != 1 else ''} del rango",
                "Promedio diario (rango seleccionado)",
                (
                    f"Nuevos en rango: <b>{u['new_users']:,}</b><br>"
                    f"Días: <b>{days_in_range:,}</b><br>"
                    f"Promedio: <b>{avg_new_per_day:,.2f}</b> nuevos/día"
                ),
            )

    # ✅ AQUÍ ya saliste del container de cards_row
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ---- Plot: barra apilada horizontal
    base = u["users_before"]
    new = u["new_users"]

    c_base = "#0047AB"
    c_new  = "#00F5A0"

    fig, ax = plt.subplots(figsize=(10.5, 1.55), dpi=160)
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    y = 0
    ax.barh([y], [base], color=c_base, height=0.42, label="Acumulados previos")
    ax.barh([y], [new], left=[base], color=c_new, height=0.42,
            label=f"Nuevos ({params['date_from']}→{params['date_to']})")

    ax.set_xticks([])
    ax.set_xlabel("")
    ax.grid(False)

    ax.set_yticks([y])
    ax.set_yticklabels(["Usuarios"], color="white", fontsize=12, fontweight="bold")

    for s in ax.spines.values():
        s.set_visible(False)

    delta_txt = f"{u['delta_abs']:+,} ({u['delta_pct']*100:+.1f}%) vs {u['prev_d1']}→{u['prev_d2']}"
    ax.set_title(
        f"Usuarios: base + nuevos (rango seleccionado)  ·  {params['date_from']}→{params['date_to']}  ·  Δ nuevos {delta_txt}",
        color="white",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )

    total = base + new
    xmax = max(total * 1.02, 1)
    ax.set_xlim(0, xmax)

    def label_segment(x0, w, txt):
        if w <= 0:
            return
        if w < 0.12 * xmax:
            ax.text(x0 + w + 0.01 * xmax, y, txt, va="center", ha="left",
                    color="white", fontsize=11, fontweight="bold")
        else:
            ax.text(x0 + w / 2, y, txt, va="center", ha="center",
                    color="white", fontsize=12, fontweight="bold")

    label_segment(0, base, f"{base:,}")
    label_segment(base, new, f"{new:,}")

    leg = ax.legend(loc="center left", bbox_to_anchor=(1.08, 0.5), frameon=False, fontsize=10)
    for t in leg.get_texts():
        t.set_color("white")

    plt.tight_layout(rect=[0, 0, 1, 1])
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    # ---- BARRAS POR PERIODOS (bins del mismo tamaño que el rango seleccionado)
# ---- BINS (mismo tamaño que el rango seleccionado) — NUEVOS USUARIOS
    if show_new_users_bins:
        period_days = (params["date_to"] - params["date_from"]).days + 1
        n_prev_periods = 6

        start_all = params["date_from"] - timedelta(days=period_days * n_prev_periods)
        end_all = params["date_to"]

        # ✅ Nuevos usuarios por día (rango extendido)
        df_nu_ext = query_new_users_daily_extended(params, start_all, end_all)  # day, new_users

        figp = plot_period_bars_same_size(
            df_daily=df_nu_ext,  # usa col new_users
            period_days=period_days,
            selected_period_index=n_prev_periods,
            title=f"Nuevos usuarios por periodo (bins de {period_days} días) — seleccionado en verde",
        )
        st.pyplot(figp, use_container_width=True)
        plt.close(figp)
    st.caption(
        f"Base previa: **{u['users_before']:,}** · "
        f"Nuevos en rango: **{u['new_users']:,}** · "
        f"Total considerado: **{u['total_considered']:,}**"
    )

show_activation = focus_analisis in ["Activación de clientes", "Todos los anteriores"]

if focus_analisis == "Activación de clientes":
    a = query_active_users_kpis_vs_prev(params)

    # ---- Cards (2 columnas): share + promedio diario
    cards_row = st.container()
    with cards_row:
        c1, c2 = st.columns(2)

        with c1:
            kpi_card(
                "Usuarios activos (share)",
                f"{a['share_active']*100:.1f}%",
                f"{a['active_users']:,} activos de {a['total_users_all']:,} usuarios totales",
                "Comparación vs periodo anterior",
                (
                    f"Periodo actual: {params['date_from']} → {params['date_to']}<br>"
                    f"Periodo anterior: {a['prev_d1']} → {a['prev_d2']}<br><br>"
                    f"Activos actual: <b>{a['active_users']:,}</b><br>"
                    f"Activos anterior: <b>{a['active_users_prev']:,}</b><br>"
                    f"Δ: <b>{a['delta_abs']:+,}</b> ({a['delta_pct']*100:+.1f}%)"
                ),
            )

        with c2:
            days_in_range = (params["date_to"] - params["date_from"]).days + 1
            kpi_card(
                "Promedio activos / día",
                f"{a['avg_dau']:,.1f}",
                f"En {days_in_range} día{'s' if days_in_range != 1 else ''} del rango",
                "Promedio diario (DAU)",
                (
                    f"DAU promedio: <b>{a['avg_dau']:,.2f}</b><br>"
                    f"Días: <b>{days_in_range:,}</b>"
                ),
            )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

            # =========================

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)


    

    # ---- Stacked bar: activos (verde) + resto disponible (azul)
    total_all = a["total_users_all"]
    active = a["active_users"]
    rest = max(total_all - active, 0)

    c_rest = "#0047AB"   # azul
    c_active = "#00F5A0" # verde brillante

    fig, ax = plt.subplots(figsize=(10.5, 1.55), dpi=160)
    fig.patch.set_facecolor("#000000")
    ax.set_facecolor("#000000")

    y = 0
    ax.barh([y], [rest], color=c_rest, height=0.42, label="Resto disponible")
    ax.barh([y], [active], left=[rest], color=c_active, height=0.42,
            label=f"Activos ({params['date_from']}→{params['date_to']})")

    ax.set_xticks([])
    ax.grid(False)

    ax.set_yticks([y])
    ax.set_yticklabels(["Usuarios"], color="white", fontsize=12, fontweight="bold")

    for s in ax.spines.values():
        s.set_visible(False)

    delta_txt = f"{a['delta_abs']:+,} ({a['delta_pct']*100:+.1f}%) vs {a['prev_d1']}→{a['prev_d2']}"
    ax.set_title(
        f"Usuarios: resto + activos (rango seleccionado)  ·  {params['date_from']}→{params['date_to']}  ·  Δ activos {delta_txt}",
        color="white",
        fontsize=12,
        fontweight="bold",
        pad=10,
    )

    xmax = max((rest + active) * 1.02, 1)
    ax.set_xlim(0, xmax)

    def label_segment(x0, w, txt):
        if w <= 0:
            return
        if w < 0.12 * xmax:
            ax.text(x0 + w + 0.01 * xmax, y, txt, va="center", ha="left",
                    color="white", fontsize=11, fontweight="bold")
        else:
            ax.text(x0 + w / 2, y, txt, va="center", ha="center",
                    color="white", fontsize=12, fontweight="bold")

    label_segment(0, rest, f"{rest:,}")
    label_segment(rest, active, f"{active:,}")

    leg = ax.legend(loc="center left", bbox_to_anchor=(1.08, 0.5), frameon=False, fontsize=10)
    for t in leg.get_texts():
        t.set_color("white")

    plt.tight_layout(rect=[0, 0, 1, 1])
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

    # ---- Barras por periodos (bins del mismo tamaño que el rango seleccionado)
# ---- Barras por periodos (bins del mismo tamaño que el rango seleccionado) — DAU
    if show_dau_bins:
        period_days = (params["date_to"] - params["date_from"]).days + 1
        n_prev_periods = 6

        start_all = params["date_from"] - timedelta(days=period_days * n_prev_periods)
        end_all = params["date_to"]

        # ✅ DAU bins (tu función existente)
        df_bins = query_active_users_by_bins(params, start_all, end_all, period_days)  # day, value

        figp = plot_period_bars_same_size(
            df_daily=df_bins,  # usa col value
            period_days=period_days,
            selected_period_index=n_prev_periods,
            title=f"Usuarios activos únicos por periodo (bins de {period_days} días) — seleccionado en verde",
        )
        st.pyplot(figp, use_container_width=True)
        plt.close(figp)
    st.caption(
        f"Usuarios totales: **{total_all:,}** · "
        f"Activos en rango: **{active:,}** · "
        f"Resto: **{rest:,}**"
    )


    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)


focus_analisis = st.session_state.get("focus_analisis", "Todos los anteriores")

show_dau_line = (focus_analisis == "Activación de clientes")

KPI_MAP = {


    "Activación de clientes": [
        ("DAU (prom. 7d)", f"{k['dau_7d_avg']:,.0f}", "Usuarios activos diarios (promedio)",
        "DAU (7d promedio)", "Usuarios únicos con al menos 1 sesión. Promedio de los últimos 7 días dentro del rango."),
        ("MAU (mes actual)", f"{k['mau']:,.0f}", "Usuarios activos mensuales",
        "MAU", "Usuarios únicos con sesión en el mes del `date_to`."),
        ("Stickiness", fmt_pct(k["stickiness"]), "Hábito de uso (DAU/MAU)",
        "Stickiness", "DAU/MAU. Valores más altos indican uso frecuente."),
        ("Activación 7d", fmt_pct(k["activation_7d"]), "Primera compra en ≤ 7 días",
        "Activation (7 days)", "Porcentaje de usuarios que hacen su primera compra dentro de 7 días desde signup."),
    ],

    "Ventas": [
        ("GMV", fmt_money(k["gmv"]), "Ventas brutas (completed)",
         "GMV", "Suma de order_total de órdenes completadas en el rango."),
        ("Órdenes completadas", f"{k['orders_completed']:,.0f}", "Órdenes con status completed",
         "Órdenes completadas", "Conteo de órdenes completadas dentro del rango."),
        ("AOV", fmt_money(k["aov"]), "Ticket promedio",
         "AOV", "GMV / órdenes completadas. Indicador de monetización y mix de productos."),
        ("Comisión", fmt_money(k["commission"]), "Ingresos por comisión",
         "Commission", "Suma de la comisión de órdenes completadas. Proxy de ingresos del marketplace."),
    ],

        "Calidad operativa": [
        ("Órdenes totales", f"{k['orders_total']:,.0f}", "Total de órdenes (rango)",
        "Órdenes totales", "Conteo total de órdenes en el rango."),
        ("Órdenes completadas", f"{k['orders_completed']:,.0f}", "Órdenes completadas",
        "Órdenes completadas", "Conteo de órdenes con status completed."),
        ("Órdenes canceladas", f"{k['orders_cancelled']:,.0f}", "Órdenes canceladas",
        "Órdenes canceladas", "Conteo de órdenes con status cancelled."),
        ("Cancelación", fmt_pct(k["cancel_rate"]), "Canceladas / total",
        "Cancel rate", "Proporción de órdenes canceladas sobre el total."),
    ],
    }


if focus_analisis == "Todos los anteriores":
    # mantiene exactamente tu grid 2x4 original
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("DAU (prom. 7d)", f"{k['dau_7d_avg']:,.0f}", "Usuarios activos diarios (promedio)",
                 "DAU (7d promedio)", "Usuarios únicos con al menos 1 sesión. Promedio de los últimos 7 días dentro del rango.")
    with c2:
        kpi_card("MAU (mes actual)", f"{k['mau']:,.0f}", "Usuarios activos mensuales",
                 "MAU", "Usuarios únicos con sesión en el mes del `date_to`. Útil para tamaño de base activa.")
    with c3:
        kpi_card("Stickiness", fmt_pct(k["stickiness"]), "Hábito de uso (DAU/MAU)",
                 "Stickiness", "DAU/MAU. Valores más altos indican uso frecuente. Ideal para medir producto/retención.")
    with c4:
        kpi_card("Activación 7d", fmt_pct(k["activation_7d"]), "Primera compra en ≤ 7 días",
                 "Activation (7 days)", "Porcentaje de usuarios que realizan su primera compra dentro de 7 días desde su signup.")

    st.write("")
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        kpi_card("GMV", fmt_money(k["gmv"]), "Ventas brutas (completed)",
                 "GMV", "Suma de order_total de órdenes completadas en el rango.")
    with c6:
        kpi_card("AOV", fmt_money(k["aov"]), "Ticket promedio",
                 "AOV", "GMV / órdenes completadas. Indicador de monetización y mix de productos.")
    with c7:
        kpi_card("Cancelación", fmt_pct(k["cancel_rate"]), "Canceladas / total órdenes",
                 "Cancel rate", "Proporción de órdenes canceladas. Señal de fricción logística/operativa.")
    with c8:
        kpi_card("Comisión", fmt_money(k["commission"]), "Ingresos por comisión",
                 "Commission", "Suma de la comisión de órdenes completadas. Proxy de ingresos del marketplace.")

elif focus_analisis == "Adquisición de clientes":
    # 👇 NO mostrar cards aquí
    pass

else:
    cards = KPI_MAP.get(focus_analisis, KPI_MAP["Ventas"])
    cols = st.columns(len(cards))
    for col, (label, value, sub, tip_title, tip_body) in zip(cols, cards):
        with col:
            kpi_card(label, value, sub, tip_title, tip_body)

reset_sep()
sep()




def color_scale_for(labels, series_color_map=None):
    """
    Scale explícito (domain/range) para que Altair respete tus colores SIEMPRE.
    labels: lista de categorías en el orden que quieres.
    series_color_map: dict {label: color}. Si None, lo construye.
    """
    domain = [str(x) for x in labels if str(x).strip()]
    if series_color_map is None:
        series_color_map = build_series_color_map(domain)

    return alt.Scale(
        domain=domain,
        range=[series_color_map.get(s, "#2563EB") for s in domain],
    )

# -----------------------------
# CHARTS (todas responden a cross-filter)
# -----------------------------
from html import escape as _html_escape  # <-- asegúrate de tener esto 1 sola vez arriba

def build_series_color_map(series_list):
    """
    Paleta de ALTO contraste (colorblind-friendly) + overrides
    para que CDMX/Guadalajara no se parezcan nunca.
    """
    series_list = [str(x) for x in series_list if str(x).strip()]

    # Base: Okabe-Ito (alto contraste) + extras que combinan con tu branding oscuro
    palette = [
        "#0072B2",  # blue
        "#E69F00",  # orange
        "#009E73",  # green
        "#D55E00",  # vermillion
        "#CC79A7",  # purple/pink
        "#56B4E9",  # sky
        "#F0E442",  # yellow
        "#999999",  # grey
        "#1D4ED8",  # cobalt
        "#00F5A0",  # bright green
        "#A855F7",  # violet
        "#22C55E",  # green
    ]

    # Overrides duros (si la serie existe, SIEMPRE este color)
    overrides = {
        "Total": "#00F5A0",        # verde brillante
        "CDMX": "#F59E0B",         # naranja fuerte
        "Guadalajara": "#2563EB",  # azul cobalto
        "Monterrey": "#10B981",    # verde
        "Puebla": "#A855F7",       # violeta
        "Querétaro": "#56B4E9",    # sky
        "Queretaro": "#56B4E9",
        "Otros": "#334155",        # slate elegante
    }

    out = {}
    i = 0
    for s in series_list:
        if s in overrides:
            out[s] = overrides[s]
        else:
            out[s] = palette[i % len(palette)]
            i += 1
    return out

# Data base (se cargan 1 vez)
df_orders, df_dau = query_timeseries(params)
df_cities, df_vendors = query_top(params)

# ====== A) ADQUISICIÓN: Nuevos usuarios por series (línea) ======
if show_new_users_line:

    st.subheader("Nuevos usuarios — Serie temporal")

    badge = active_filter_badge()
    if badge:
        st.caption(badge)

    df_nu = query_new_users_series_by_dim(params)

    if not df_nu.empty:

        dfx = df_nu.copy()
        dfx["series"] = dfx["series"].astype(str)
        dfx["value"] = pd.to_numeric(dfx["value"], errors="coerce").fillna(0)
        dfx = dfx.sort_values(["day", "series"]).reset_index(drop=True)

        dfx["cum_in_range"] = dfx.groupby("series")["value"].cumsum()

        # ✅ universo completo -> colores estables
        series_universe = sorted(set(dfx["series"].astype(str).tolist()))
        series_color_map = build_series_color_map(series_universe)
        if "Total" in series_universe:
            series_color_map["Total"] = series_color_map.get("Total", "#00F5A0")

        # ✅ domain determinista (Total primero)
        others = sorted([s for s in series_universe if s != "Total"])
        series_domain = (["Total"] + others) if "Total" in series_universe else others

        scale = alt.Scale(
            domain=series_domain,
            range=[series_color_map.get(s, "#2563EB") for s in series_domain],
        )

        base = (
            alt.Chart(dfx)
            .encode(
                x=alt.X(
                    "day:T",
                    axis=alt.Axis(
                        labelColor=BRAND["chart_text"],
                        titleColor=BRAND["chart_text"],
                        gridColor=BRAND["grid"],
                    ),
                    title=None,
                )
            )
            .properties(height=340)
        )

        line_new = base.mark_line().encode(
            y=alt.Y(
                "value:Q",
                axis=alt.Axis(
                    labelColor=BRAND["chart_text"],
                    titleColor=BRAND["chart_text"],
                    gridColor=BRAND["grid"],
                ),
                title="Nuevos",
            ),
            color=alt.Color("series:N", scale=scale, legend=alt.Legend(title=None)),
            strokeWidth=alt.condition(alt.datum.series == "Total", alt.value(4), alt.value(2)),
            tooltip=["day:T", "series:N", alt.Tooltip("value:Q", format=",.0f")],
        )

        line_cum = base.mark_line(strokeDash=[6, 4], opacity=0.9).encode(
            y=alt.Y(
                "cum_in_range:Q",
                axis=alt.Axis(
                    labelColor=BRAND["chart_text"],
                    titleColor=BRAND["chart_text"],
                ),
                title="Acumulado en rango",
            ),
            color=alt.Color("series:N", scale=scale, legend=None),
            strokeWidth=alt.condition(alt.datum.series == "Total", alt.value(4), alt.value(2)),
            tooltip=["day:T", "series:N", alt.Tooltip("cum_in_range:Q", format=",.0f")],
        )

        st.altair_chart(
            alt.layer(line_new, line_cum)
            .resolve_scale(y="independent")
            .configure(background=BRAND["chart_bg"])
            .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
            .configure_axis(domainColor=BRAND["grid"])
            .configure_title(color=BRAND["chart_text"]),
            use_container_width=True,
        )

    else:
        st.info("No hay datos para mostrar con los filtros actuales.")


# =========================
# USUARIOS ACTIVOS — SERIE TEMPORAL (DAU)  (VA AQUÍ)
# =========================
# =========================
# USUARIOS ACTIVOS — SERIE TEMPORAL (DAU)  (SOLO ACTIVACIÓN)
# =========================
if show_dau_line:
    st.subheader("Usuarios activos — Serie temporal (DAU)")

    badge = active_filter_badge()
    if badge:
        st.caption(badge)

    df_dau_series = query_dau_series_by_dim(params)

    if df_dau_series.empty:
        st.info("No hay sesiones para este rango con los filtros actuales.")
    else:
        dfx = df_dau_series.copy()
        dfx["series"] = dfx["series"].astype(str)
        dfx["value"] = pd.to_numeric(dfx["value"], errors="coerce").fillna(0)

        # respeta checkbox global "Mostrar Total"
        show_total_series = st.session_state.get("show_total_series", True)
        if not show_total_series:
            dfx = dfx[dfx["series"] != "Total"].copy()

        if dfx.empty:
            st.info("No hay series para mostrar con los filtros actuales.")
        else:
            series_universe = sorted(set(dfx["series"].tolist()))
            series_color_map = build_series_color_map(series_universe)

            others = sorted([s for s in series_universe if s != "Total"])
            series_domain = (["Total"] + others) if "Total" in series_universe else others

            scale = alt.Scale(
                domain=series_domain,
                range=[series_color_map.get(s, "#2563EB") for s in series_domain],
            )

            base = (
                alt.Chart(dfx)
                .encode(
                    x=alt.X(
                        "day:T",
                        axis=alt.Axis(
                            labelColor=BRAND["chart_text"],
                            titleColor=BRAND["chart_text"],
                            gridColor=BRAND["grid"],
                        ),
                        title=None,
                    )
                )
                .properties(height=320)
            )

            line = base.mark_line().encode(
                y=alt.Y(
                    "value:Q",
                    axis=alt.Axis(
                        labelColor=BRAND["chart_text"],
                        titleColor=BRAND["chart_text"],
                        gridColor=BRAND["grid"],
                    ),
                    title="DAU (usuarios activos únicos)",
                ),
                color=alt.Color("series:N", scale=scale, legend=alt.Legend(title=None)),
                strokeWidth=alt.condition(alt.datum.series == "Total", alt.value(4), alt.value(2)),
                tooltip=["day:T", "series:N", alt.Tooltip("value:Q", format=",.0f")],
            )

            st.altair_chart(
                line
                .configure(background=BRAND["chart_bg"])
                .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
                .configure_axis(domainColor=BRAND["grid"])
                .configure_title(color=BRAND["chart_text"]),
                use_container_width=True,
            )

    # =========================
    # ACTIVACIÓN — COMPARATIVO POR DIM (USUARIOS ACTIVOS)
    # (Solo cuando estás en Activación)
    # =========================
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # usa el mismo selector de tu sidebar: "Desglosar análisis por"
    compare_dim = fs.get("series_dim", "(ninguno)")
    if compare_dim == "(ninguno)":
        compare_dim = "Ciudad"

    st.subheader(f"Comparativo por {compare_dim} · Usuarios activos")

    df_dim = query_active_users_compare_by_dim(params, compare_dim)

    if df_dim.empty:
        st.info("No hay datos para comparar con los filtros actuales.")
    else:
        # respeta "Mostrar Total": aquí significa agregar fila Total (suma)
        show_total_series = st.session_state.get("show_total_series", True)
        dfx = df_dim.copy()

        if show_total_series:
            total_val = int(dfx["active_users"].sum())
            dfx = pd.concat(
                [pd.DataFrame([{"dim": "Total", "active_users": total_val}]), dfx],
                ignore_index=True,
            )

        # top N (como tu UI actual)
        topN = 8
        dfx = dfx.head(topN).copy()

        # shares para tabla/legend
        denom = float(dfx.loc[dfx["dim"] != "Total", "active_users"].sum() or 1)
        dfx["share_pct"] = dfx.apply(
            lambda r: 100.0 * (r["active_users"] / denom) if r["dim"] != "Total" else 100.0,
            axis=1
        )

        # colores consistentes con tu mapa
        series_universe = dfx["dim"].astype(str).tolist()
        series_color_map = build_series_color_map(series_universe)
        if "Total" in series_universe:
            series_color_map["Total"] = "#00F5A0"


        # layout 2 columnas como tu screenshot
        cL, cR = st.columns([1.55, 1.0])

        with cL:
            # barras horizontales
            chart_bar = (
                alt.Chart(dfx[dfx["dim"] != "Total"])
                .mark_bar(cornerRadius=10)
                .encode(
                    y=alt.Y("dim:N", sort="-x", title=None),
                    x=alt.X("active_users:Q", title=None),
                    color=alt.Color(
                        "dim:N",
                        scale=alt.Scale(
                            domain=[d for d in dfx["dim"].tolist() if d != "Total"],
                            range=[series_color_map.get(d, "#2563EB") for d in dfx["dim"].tolist() if d != "Total"],
                        ),
                        legend=None,
                    ),
                    tooltip=["dim:N", alt.Tooltip("active_users:Q", format=",.0f")],
                )
                .properties(height=280)
            )


            st.altair_chart(
                chart_bar
                .configure(background=BRAND["chart_bg"])
                .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
                .configure_axis(domainColor=BRAND["grid"], labelColor=BRAND["chart_text"])
                .configure_title(color=BRAND["chart_text"]),
                use_container_width=True,
            )

            st.markdown("</div>", unsafe_allow_html=True)

            # tabla exportable (igual que tu "Resumen por categoría")
            df_tbl = dfx[dfx["dim"] != "Total"].copy()
            df_tbl.rename(columns={"dim": "series", "active_users": "total_usuarios"}, inplace=True)
            df_tbl["share_pct"] = df_tbl["share_pct"].round(1)

            st.subheader("Resumen por categoría (exportable)")

            view = df_tbl[["series", "share_pct", "total_usuarios"]].copy()

            # punto de color como en Nuevos usuarios
            view.insert(
                0,
                "●",
                view["series"].astype(str).map(
                    lambda s: f"<span style='color:{series_color_map.get(str(s), '#EAF1FF')}; font-weight:1000;'>●</span>"
                ),
            )

            st.markdown(
                "<div class='mh-dark-table-wrap'>"
                + view.to_html(index=False, classes="mh-dark-table", escape=False)
                + "</div>",
                unsafe_allow_html=True,
            )
            st.markdown("")

            csv = df_tbl[["series", "share_pct", "total_usuarios"]].to_csv(index=False).encode("Latin1")
            st.download_button(
                "Descargar resumen (CSV)",
                data=csv,
                file_name="resumen_activacion.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with cR:
    # =========================
    # Leyenda arriba del donut (USUARIOS ACTIVOS)
    # =========================

            legend_df = dfx[dfx["dim"] != "Total"].copy()
            legend_df = legend_df.sort_values(["share_pct", "dim"], ascending=[False, True])

            legend_html = ""
            for _, rr in legend_df.iterrows():
                s = str(rr["dim"])
                p = float(rr["share_pct"])
                c = series_color_map.get(s, "#2563EB")

                legend_html += f"""
                <div style="
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                    padding:4px 0;
                ">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div style="
                            width:17px;
                            height:10px;
                            border-radius:50%;
                            background:{c};
                        "></div>
                        <div style="color:#EAF1FF; font-weight:900; font-size:17px;">
                            {s}
                        </div>
                    </div>
                    <div style="color:#D7ECFF; font-weight:900; font-size:17px;">
                        {p:.1f}%
                    </div>
                </div>
                """

            st.markdown(
                f"""
                <div style="
                    background:#000000;
                    border:1px solid rgba(255,255,255,.06);
                    border-radius:16px;
                    padding:12px;
                    margin-bottom:14px;
                ">
                    <div style="
                        font-weight:1000;
                        color:#D7ECFF;
                        font-size:17px;
                        margin-bottom:6px;
                    ">
                        Share por {compare_dim}
                    </div>
                    {legend_html}
                </div>
                """,
                unsafe_allow_html=True
            )

            total_active = int(dfx[dfx["dim"] != "Total"]["active_users"].sum())
            
            # donut / pie
            # =========================
            # DONUT — USUARIOS ACTIVOS
            # =========================

            # =========================
            # Participación porcentual · Usuarios activos (leyenda arriba del donut)
            # =========================
            # 1) Construimos df_share para Plotly (series, share, active_users)
            df_share_active = dfx[dfx["dim"] != "Total"][["dim", "share_pct", "active_users"]].copy()
            df_share_active.rename(columns={"dim": "series"}, inplace=True)

            # share_pct viene 0-100; lo convertimos a 0-1 para "share"
            df_share_active["share"] = (df_share_active["share_pct"] / 100.0).astype(float)

            # 3) Donut Plotly centrado + total en el centro
            fig_donut_activos = plot_donut_share(
                df_share=df_share_active[["series", "share", "active_users"]],
                title="",
                series_color_map=series_color_map,
                value_col="active_users",
                metric_label="Usuarios activos",
            )
            if fig_donut_activos:
                st.plotly_chart(fig_donut_activos, use_container_width=True)


            st.markdown("</div>", unsafe_allow_html=True)


def _build_series_color_map_stable(all_series):
    # orden estable -> colores estables
    series_sorted = sorted({str(x) for x in all_series if str(x).strip()})
    return build_series_color_map(series_sorted)


if show_sales_panel or show_dau_panel:

    if show_sales_panel:
        st.subheader("Tendencias: GMV, órdenes y cancelación")

        badge = active_filter_badge()
        if badge:
            st.caption(badge)

        if not df_orders.empty:
            dfx = df_orders.copy()
            dfx["cancel_rate"] = dfx.apply(
                lambda r: (r["orders_cancelled"] / r["orders_total"]) if r["orders_total"] else 0.0,
                axis=1,
            )

            # colores
            C_GMV = "#A855F7"
            C_ORD = "#60A5FA"
            C_CAN = "#F59E0B"
            C_RATE = "#10B981"  # dots + eje de tasas

            # ✅ FIX: selector clickeable en leyenda, pero arranca con TODO visible (init)
            sel = alt.selection_multi(
                fields=["metric"],
                bind="legend",
                toggle=True,   # 👈 click = on/off (sin SHIFT)
                init=[
                    {"metric": "GMV"},
                    {"metric": "Órdenes"},
                    {"metric": "Canceladas"},
                    {"metric": "Cancel rate"},
                ],
            )

            base = (
                alt.Chart(dfx)
                .encode(
                    x=alt.X(
                        "day:T",
                        axis=alt.Axis(
                            labelColor=BRAND["chart_text"],
                            titleColor=BRAND["chart_text"],
                            gridColor=BRAND["grid"],
                            labelFontSize=13,
                            titleFontSize=14,
                        ),
                        title=None,
                    )
                )
                .properties(width=340, height=320)
            )

            # ---- GMV (izquierda)
            gmv = (
                base.mark_line(strokeWidth=3)
                .transform_calculate(metric="'GMV'")
                .encode(
                    y=alt.Y(
                        "gmv:Q",
                        axis=alt.Axis(
                            orient="left",
                            labelColor=BRAND["chart_text"],
                            titleColor=BRAND["chart_text"],
                            gridColor=BRAND["grid"],
                            labelOverlap="greedy",
                            tickCount=5,
                            labelFontSize=13,
                            titleFontSize=14,
                        ),
                        title="GMV",
                    ),
                    color=alt.value(C_GMV),
                    tooltip=["day:T", alt.Tooltip("gmv:Q", format=",.0f")],
                    opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                )
            )

            # ---- Órdenes (derecha, offset 0)
            orders = (
                base.mark_line(strokeWidth=2)
                .transform_calculate(metric="'Órdenes'")
                .encode(
                    y=alt.Y(
                        "orders_total:Q",
                        axis=alt.Axis(
                            orient="right",
                            offset=0,
                            labelColor=C_ORD,
                            titleColor=C_ORD,
                            labelOverlap="greedy",
                            tickCount=5,
                            labelFontSize=13,
                            titleFontSize=14,
                            grid=False,
                        ),
                        title="Órdenes",
                    ),
                    color=alt.value(C_ORD),
                    tooltip=["day:T", alt.Tooltip("orders_total:Q", format=",.0f")],
                    opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                )
            )

            # ---- Canceladas (derecha, offset 46)
            cancelled = (
                base.mark_line(strokeWidth=2, strokeDash=[6, 4])
                .transform_calculate(metric="'Canceladas'")
                .encode(
                    y=alt.Y(
                        "orders_cancelled:Q",
                        axis=alt.Axis(
                            orient="right",
                            offset=46,
                            labelColor=C_CAN,
                            titleColor=C_CAN,
                            labelOverlap="greedy",
                            tickCount=5,
                            labelFontSize=13,
                            titleFontSize=14,
                            grid=False,
                        ),
                        title="Canceladas",
                    ),
                    color=alt.value(C_CAN),
                    tooltip=["day:T", alt.Tooltip("orders_cancelled:Q", format=",.0f")],
                    opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                )
            )

            # ---- Cancel rate (derecha, offset 92) — eje del MISMO color que dots
            cr = (
                base.mark_circle(size=55, opacity=0.9)
                .transform_calculate(metric="'Cancel rate'")
                .encode(
                    y=alt.Y(
                        "cancel_rate:Q",
                        axis=alt.Axis(
                            orient="right",
                            offset=92,
                            format="%",
                            labelColor=C_RATE,
                            titleColor=C_RATE,
                            labelOverlap="greedy",
                            tickCount=4,
                            labelFontSize=13,
                            titleFontSize=14,
                            grid=False,
                        ),
                        title="Cancel rate",
                    ),
                    color=alt.value(C_RATE),
                    tooltip=["day:T", alt.Tooltip("cancel_rate:Q", format=".2%")],
                    opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                )
            )

            # ✅ capa “fantasma” SOLO para tener leyenda clickeable con 4 items
            legend_df = pd.concat(
                [
                    dfx.assign(metric="GMV"),
                    dfx.assign(metric="Órdenes"),
                    dfx.assign(metric="Canceladas"),
                    dfx.assign(metric="Cancel rate"),
                ],
                ignore_index=True,
            )

            legend_layer = (
                alt.Chart(legend_df)
                .mark_point(opacity=0)
                .encode(
                    color=alt.Color(
                        "metric:N",
                        scale=alt.Scale(
                            domain=["GMV", "Órdenes", "Canceladas", "Cancel rate"],
                            range=[C_GMV, C_ORD, C_CAN, C_RATE],
                        ),
                        legend=alt.Legend(
                            title=None,
                            labelColor=BRAND["chart_text"],
                            labelFontSize=14,
                            symbolSize=160,
                        ),
                    )
                )
            )

            chart = (
                alt.layer(gmv, orders, cancelled, cr, legend_layer)
                .add_selection(sel)  # ✅ importantísimo: agrega la selección al chart final
                .resolve_scale(y="independent")
                .configure(background=BRAND["chart_bg"])
                .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
                .configure_axis(domainColor=BRAND["grid"])
                .configure_title(color=BRAND["chart_text"])
            )

            # tu leyenda HTML (no controla toggle, pero la puedes dejar)
            st.markdown(
                "<div style='display:flex; gap:14px; flex-wrap:wrap; font-weight:900; font-size:12px; opacity:.95;'>"
                f"<span style='color:{C_GMV}'>● GMV</span>"
                f"<span style='color:{C_ORD}'>● Órdenes</span>"
                f"<span style='color:{C_CAN}'>● Canceladas (dash)</span>"
                f"<span style='color:{C_RATE}'>● Cancel rate (puntos)</span>"
                "</div>",
                unsafe_allow_html=True,
            )

            st.altair_chart(chart, use_container_width=True)

        else:
            st.info("No hay datos de órdenes para este rango.")
    else:
        st.empty()

reset_sep()
sep()

# =========================
# DONUT: Participación por variable (share de nuevos usuarios)
# + Top 5 usuarios por categoría (muestra)
# =========================
# =========================
# COLORES CONSISTENTES + USUARIOS ROBUSTOS
# =========================

# ---------- helpers ----------
def _normalize_sample_users(x, max_items=5):
    """
    Convierte sample_users a HTML seguro:
    - Si viene lista -> toma max_items
    - Si viene string -> intenta separadores comunes
    - Escapa HTML para que no rompa el layout
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""

    # lista / tupla / set
    if isinstance(x, (list, tuple, set)):
        items = [str(i).strip() for i in list(x) if str(i).strip()]
        items = items[:max_items]
        return "<br>".join([_html_escape(i) for i in items])

    # dict (raro pero pasa)
    if isinstance(x, dict):
        items = [f"{k}: {v}" for k, v in x.items()]
        items = [str(i).strip() for i in items if str(i).strip()]
        items = items[:max_items]
        return "<br>".join([_html_escape(i) for i in items])

    # string
    s = str(x).strip()
    if not s:
        return ""

    # si parece venir como "['a','b']" no lo evalúo (seguro), lo dejo como texto
    # mejor split por separadores comunes para mostrar bonito:
    if "\n" in s:
        parts = [p.strip() for p in s.split("\n") if p.strip()]
    elif "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
    elif "•" in s:
        parts = [p.strip() for p in s.split("•") if p.strip()]
    elif "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
    else:
        parts = [s]

    parts = parts[:max_items]
    return "<br>".join([_html_escape(p) for p in parts])



# =========================
# DONUT: Participación por variable (share de nuevos usuarios)
# + Top 5 usuarios por categoría (muestra)
# =========================
if show_new_users_share_panel:

    dim_sel = (
        params.get("series_dim")
        or params.get("nu_series_final_dim")
        or params.get("cmp_dim")
        or params.get("dim")
        or "(ninguno)"
    )

    if dim_sel in ["Ciudad", "Canal", "Device"]:
        df_share, df_samples = query_new_users_share_and_samples(params)

        if df_share is None or df_share.empty:
            st.info("No hay nuevos usuarios en el rango con los filtros actuales.")
        else:
            df_share = df_share.copy()
            df_share["series"] = df_share["series"].astype(str)
            df_share["share"] = pd.to_numeric(df_share["share"], errors="coerce").fillna(0.0)

            # ✅ (1) colores estables para todo el universo
            series_universe = sorted(set(df_share["series"].dropna().astype(str).tolist()))
            series_color_map = build_series_color_map(series_universe)

            # ✅ columnas: donut izquierda, cards derecha
            leftD, rightD = st.columns([0.56, 0.44])

            with leftD:

                st.subheader(f"Comparativo por {compare_dim} · Nuevos usuarios")

                badge = active_filter_badge()
                if badge:
                    st.caption(badge)

                # ✅ la fuente ES df_share (la misma del resumen exportable)
                if df_share is None or df_share.empty:
                    st.info("No hay datos para comparar con los filtros actuales.")
                else:
                    df_bar = df_share.copy()
                    df_bar["series"] = df_bar["series"].astype(str)

                    # ✅ total de usuarios por categoría (preferimos new_users)
                    if "new_users" in df_bar.columns:
                        df_bar["total_usuarios"] = pd.to_numeric(df_bar["new_users"], errors="coerce").fillna(0).astype(int)
                    elif "total_users" in df_bar.columns:
                        df_bar["total_usuarios"] = pd.to_numeric(df_bar["total_users"], errors="coerce").fillna(0).astype(int)
                    else:
                        df_bar["total_usuarios"] = 0

                    # top 10 por nuevos usuarios
                    topn = (
                        df_bar[["series", "total_usuarios"]]
                        .sort_values(["total_usuarios", "series"], ascending=[False, True])
                        .head(10)
                        .rename(columns={"series": "dim"})
                        .reset_index(drop=True)
                    )

                    bar = (
                        alt.Chart(topn)
                        .mark_bar(cornerRadius=10)
                        .encode(
                            y=alt.Y(
                                "dim:N",
                                sort="-x",
                                title=None,
                                axis=alt.Axis(labelColor=BRAND["chart_text"], titleColor=BRAND["chart_text"]),
                            ),
                            x=alt.X(
                                "total_usuarios:Q",
                                title=None,
                                axis=alt.Axis(labelColor=BRAND["chart_text"], titleColor=BRAND["chart_text"], gridColor=BRAND["grid"]),
                            ),
                            color=alt.Color(
                                "dim:N",
                                scale=color_scale_for(topn["dim"].tolist()),
                                legend=None,
                            ),
                            tooltip=["dim:N", alt.Tooltip("total_usuarios:Q", format=",.0f", title="Nuevos usuarios")],
                        )
                        .properties(height=360)
                        .configure(background=BRAND["chart_bg"])
                        .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
                    )

                    st.altair_chart(bar, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                reset_sep()
                # =========================
                # RESUMEN (EXPORTABLE)
                # =========================
                st.subheader("Resumen por categoría (exportable)")

                if df_share is None or df_share.empty:
                    st.info("No hay datos para mostrar con los filtros actuales.")
                else:
                    summary = df_share.copy()
                    summary["series"] = summary["series"].astype(str)
                    summary["share_pct"] = (pd.to_numeric(summary["share"], errors="coerce").fillna(0.0) * 100).round(1)

                    # ✅ total de usuarios por categoría
                    if "new_users" in summary.columns:
                        summary["total_usuarios"] = pd.to_numeric(summary["new_users"], errors="coerce").fillna(0).astype(int)
                    elif "total_users" in summary.columns:
                        summary["total_usuarios"] = pd.to_numeric(summary["total_users"], errors="coerce").fillna(0).astype(int)
                    else:
                        summary["total_usuarios"] = 0

                    # ✅ deja SOLO estas columnas
                    summary = (
                        summary[["series", "share_pct", "total_usuarios"]]
                        .sort_values(["share_pct", "series"], ascending=[False, True])
                        .reset_index(drop=True)
                    )

                    # ✅ tabla negra
                    view = summary.copy()
                    view.insert(
                        0,
                        "●",
                        view["series"].map(
                            lambda s: f"<span style='color:{series_color_map.get(str(s), '#EAF1FF')}; font-weight:1000;'>●</span>"
                        ),
                    )

                    st.markdown(
                        "<div class='mh-dark-table-wrap'>"
                        + view.to_html(index=False, classes="mh-dark-table", escape=False)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    st.markdown("")

                    csv_bytes = summary.to_csv(index=False).encode("Latin1")
                    st.download_button(
                        "Descargar resumen (CSV)",
                        data=csv_bytes,
                        file_name=f"resumen_{dim_sel.lower()}_share_total_usuarios.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

            with rightD:

    # =========================
    # Leyenda arriba del donut
    # =========================
                st.subheader(f"Participación porcentual de {compare_dim} · Nuevos usuarios")

                legend_df = (
                    df_share.sort_values(["share", "series"], ascending=[False, True])
                        .copy()
                )

                legend_df["pct"] = (legend_df["share"] * 100).round(1)

                legend_html = ""

                for _, rr in legend_df.iterrows():
                    s = str(rr["series"])
                    p = float(rr["pct"])
                    c = series_color_map.get(s, "#2563EB")

                    legend_html += f"""
                    <div style="
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                        padding:4px 0;
                    ">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="
                                width:17px;
                                height:10px;
                                border-radius:50%;
                                background:{c};
                            "></div>
                            <div style="color:#EAF1FF; font-weight:900; font-size:17px;">
                                {s}
                            </div>
                        </div>
                        <div style="color:#D7ECFF; font-weight:900; font-size:17px;">
                            {p:.1f}%
                        </div>
                    </div>
                    """

                st.markdown(
                    f"""
                    <div style="
                        background:#000000;
                        border:1px solid rgba(255,255,255,.06);
                        border-radius:16px;
                        padding:12px;
                        margin-bottom:14px;
                    ">
                        <div style="
                            font-weight:1000;
                            color:#D7ECFF;
                            font-size:17px;
                            margin-bottom:6px;
                        ">
                            Share por {dim_sel}
                        </div>
                        {legend_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # st.write("")

                # st.subheader(f"Distribución porcentual por {compare_dim} · Nuevos usuarios")


                fig_donut = plot_donut_share(
                    df_share=df_share,
                    title="",
                    series_color_map=series_color_map,
                )
                if fig_donut:
                    st.markdown(
                        """
                        <div style="
                            background:#000000;
                            border-radius:16px;
                            overflow:hidden;
                            padding:0;
                        ">
                        """,
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(fig_donut, use_container_width=True)

        st.write("")
    reset_sep()
    sep()


if show_ops_panel:
    st.subheader("Tendencias: calidad operativa (órdenes)")

    badge = active_filter_badge()
    if badge:
        st.caption(badge)

    compare_dim = fs.get("series_dim", "(ninguno)")

    # Aunque compare_dim exista, aquí SOLO usamos filtros del sidebar.
    # La gráfica muestra una sola serie agregada de métricas operativas.
    df_ops = query_ops_timeseries_by_dim(engine, params, compare_dim, schema=SCHEMA)

    if df_ops.empty:
        st.info("No hay datos de órdenes para este rango con los filtros actuales.")
    else:
        dfx = df_ops.copy()
        dfx["day"] = pd.to_datetime(dfx["day"])

        dfx["orders_total"] = pd.to_numeric(dfx["orders_total"], errors="coerce").fillna(0).astype(int)
        dfx["orders_completed"] = pd.to_numeric(dfx["orders_completed"], errors="coerce").fillna(0).astype(int)
        dfx["orders_cancelled"] = pd.to_numeric(dfx["orders_cancelled"], errors="coerce").fillna(0).astype(int)

        dfx["cancel_rate"] = dfx.apply(
            lambda r: (r["orders_cancelled"] / r["orders_total"]) if r["orders_total"] else 0.0,
            axis=1,
        )
        dfx["fulfillment_rate"] = dfx.apply(
            lambda r: (r["orders_completed"] / r["orders_total"]) if r["orders_total"] else 0.0,
            axis=1,
        )

        # ✅ Si NO quiere "Mostrar Total", no mostramos esta gráfica agregada
        show_total_series = st.session_state.get("show_total_series", True)

        C_TOT  = "#60A5FA"   # Órdenes
        C_COMP = "#F53D00"   # Atendidas
        C_CANC = "#F59E0B"   # Canceladas
        C_CR   = "#CB6AE9"   # Cancel rate
        C_FR   = "#22C55E"   # Fulfillment

        sel_init = [
            {"metric": "Atendidas"},
            {"metric": "Canceladas"},
            {"metric": "Cancel rate"},
            {"metric": "Fulfillment"},
        ]

        if show_total_series:
            sel_init = [{"metric": "Órdenes"}] + sel_init

        sel = alt.selection_multi(
            fields=["metric"],
            bind="legend",
            toggle=True,
            init=sel_init,
        )

        base = (
            alt.Chart(dfx)
            .encode(
                x=alt.X(
                    "day:T",
                    axis=alt.Axis(
                        labelColor=BRAND["chart_text"],
                        titleColor=BRAND["chart_text"],
                        gridColor=BRAND["grid"],
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title=None,
                )
            )
            .properties(height=330)
        )

        tot = (
            base.mark_line(strokeWidth=2.8, color=C_TOT)
            .transform_calculate(metric="'Órdenes'")
            .encode(
                y=alt.Y(
                    "orders_total:Q",
                    axis=alt.Axis(
                        orient="left",
                        labelColor=C_TOT,
                        titleColor=C_TOT,
                        gridColor=BRAND["grid"],
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title="Órdenes",
                ),
                opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("day:T"), alt.Tooltip("orders_total:Q", format=",.0f", title="Órdenes")],
            )
        )

        comp = (
            base.mark_line(strokeWidth=2.4, color=C_COMP)
            .transform_calculate(metric="'Atendidas'")
            .encode(
                y=alt.Y(
                    "orders_completed:Q",
                    axis=alt.Axis(
                        orient="right",
                        offset=0,
                        labelColor=C_COMP,
                        titleColor=C_COMP,
                        grid=False,
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title="Atendidas",
                ),
                opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("day:T"), alt.Tooltip("orders_completed:Q", format=",.0f", title="Atendidas")],
            )
        )

        canc = (
            base.mark_line(strokeWidth=2.2, strokeDash=[6, 4], color=C_CANC)
            .transform_calculate(metric="'Canceladas'")
            .encode(
                y=alt.Y(
                    "orders_cancelled:Q",
                    axis=alt.Axis(
                        orient="right",
                        offset=56,
                        labelColor=C_CANC,
                        titleColor=C_CANC,
                        grid=False,
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title="Canceladas",
                ),
                opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("day:T"), alt.Tooltip("orders_cancelled:Q", format=",.0f", title="Canceladas")],
            )
        )

        cr = (
            base.mark_circle(size=54, opacity=0.9, color=C_CR)
            .transform_calculate(metric="'Cancel rate'")
            .encode(
                y=alt.Y(
                    "cancel_rate:Q",
                    axis=alt.Axis(
                        orient="right",
                        offset=112,
                        format="%",
                        labelColor=C_CR,
                        titleColor=C_CR,
                        grid=False,
                        tickCount=4,
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title="Cancel rate",
                ),
                opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("day:T"), alt.Tooltip("cancel_rate:Q", format=".2%", title="Cancel rate")],
            )
        )

        fr = (
            base.mark_circle(size=54, opacity=0.9, color=C_FR)
            .transform_calculate(metric="'Fulfillment'")
            .encode(
                y=alt.Y(
                    "fulfillment_rate:Q",
                    axis=alt.Axis(
                        orient="right",
                        offset=168,
                        format="%",
                        labelColor=C_FR,
                        titleColor=C_FR,
                        grid=False,
                        tickCount=4,
                        labelFontSize=13,
                        titleFontSize=14,
                    ),
                    title="Fulfillment",
                ),
                opacity=alt.condition(sel, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("day:T"), alt.Tooltip("fulfillment_rate:Q", format=".2%", title="Fulfillment")],
            )
        )

        legend_parts = []

        if show_total_series:
            legend_parts.append(dfx.assign(metric="Órdenes"))

        legend_parts.extend([
            dfx.assign(metric="Atendidas"),
            dfx.assign(metric="Canceladas"),
            dfx.assign(metric="Cancel rate"),
            dfx.assign(metric="Fulfillment"),
        ])

        legend_df = pd.concat(legend_parts, ignore_index=True)

        legend_domain = ["Atendidas", "Canceladas", "Cancel rate", "Fulfillment"]
        legend_range = [C_COMP, C_CANC, C_CR, C_FR]

        if show_total_series:
            legend_domain = ["Órdenes"] + legend_domain
            legend_range = [C_TOT] + legend_range

        legend_layer = (
            alt.Chart(legend_df)
            .mark_point(opacity=0)
            .encode(
                color=alt.Color(
                    "metric:N",
                    scale=alt.Scale(
                        domain=legend_domain,
                        range=legend_range,
                    ),
                    legend=alt.Legend(
                        title=None,
                        labelColor=BRAND["chart_text"],
                        labelFontSize=14,
                        symbolSize=160,
                    ),
                )
            )
        )

        layers = [comp, canc, cr, fr, legend_layer]

        if show_total_series:
            layers = [tot] + layers

        chart = (
            alt.layer(*layers)
            .add_selection(sel)
            .resolve_scale(y="independent")
            .configure(background=BRAND["chart_bg"])
            .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
            .configure_axis(domainColor=BRAND["grid"])
            .configure_title(color=BRAND["chart_text"])
        )

        st.altair_chart(chart, use_container_width=True)

        # =========================
        # SHARE DE ÓRDENES (debajo de la tendencia operativa)
        # =========================
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        compare_dim_share = fs.get("series_dim", "(ninguno)")

        share_metric_label_map = {
            "Órdenes": ("orders_total", "Órdenes"),
            "Órdenes atendidas": ("orders_completed", "Órdenes atendidas"),
            "Órdenes canceladas": ("orders_cancelled", "Órdenes canceladas"),
        }

        share_metric_sel = st.selectbox(
            "Share por:",
            ["Órdenes", "Órdenes atendidas", "Órdenes canceladas"],
            index=0,
            key="ops_share_metric_sel",
        )

        share_value_col, share_metric_label = share_metric_label_map[share_metric_sel]

        df_ops_share = query_ops_share_by_dim(engine, params, compare_dim_share, schema=SCHEMA)

        if df_ops_share.empty:
            st.info("No hay datos para construir el share de órdenes con los filtros actuales.")
        else:
            dshare = df_ops_share.copy()
            dshare["series"] = dshare["series"].astype(str)

            dshare["orders_total"] = pd.to_numeric(dshare["orders_total"], errors="coerce").fillna(0)
            dshare["orders_completed"] = pd.to_numeric(dshare["orders_completed"], errors="coerce").fillna(0)
            dshare["orders_cancelled"] = pd.to_numeric(dshare["orders_cancelled"], errors="coerce").fillna(0)

            # si no hay desglose, forzamos Total
            if compare_dim_share == "(ninguno)":
                total_value = float(dshare[share_value_col].sum())
                dshare = pd.DataFrame([{
                    "series": "Total",
                    share_value_col: total_value,
                    "share": 1.0 if total_value > 0 else 0.0,
                }])
            else:
                total_value = float(dshare[share_value_col].sum())
                dshare["share"] = dshare[share_value_col] / total_value if total_value > 0 else 0.0

            dshare = dshare.sort_values(["share", "series"], ascending=[False, True]).reset_index(drop=True)

            series_universe = sorted(set(dshare["series"].astype(str).tolist()))
            series_color_map = build_series_color_map(series_universe)
            if "Total" in series_universe:
                series_color_map["Total"] = "#00F5A0"

            left_share, right_share = st.columns([0.56, 0.44])

            with left_share:

                titulo_share = "Share" if compare_dim_share == "(ninguno)" else f"Selecciona el status de la orden que te interesa {compare_dim_share}"

                # =========================
                # Leyenda arriba del donut
                # =========================
                st.markdown("<div style='display:flex; gap:19px; flex-wrap:wrap; font-weight:900; font-size:26px; opacity:.95;'>El valor porcentual representa la participación de cada categoría sobre el total de órdenes en el período seleccionado.</div>", unsafe_allow_html=True)

                legend_df = dshare.copy()
                legend_df["share_pct"] = (legend_df["share"] * 100).round(1)

                legend_html = ""
                for _, rr in legend_df.iterrows():
                    s = str(rr["series"])
                    p = float(rr["share_pct"])
                    c = series_color_map.get(s, "#2563EB")

                    legend_html += f"""
                    <div style="
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                        padding:4px 0;
                    ">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <div style="
                                width:17px;
                                height:10px;
                                border-radius:50%;
                                background:{c};
                            "></div>
                            <div style="color:#EAF1FF; font-weight:900; font-size:17px;">
                                {s}
                            </div>
                        </div>
                        <div style="color:#D7ECFF; font-weight:900; font-size:17px;">
                            {p:.1f}%
                        </div>
                    </div>
                    """

                st.markdown(
                    f"""
                    <div style="
                        background:#000000;
                        border:1px solid rgba(255,255,255,.06);
                        border-radius:16px;
                        padding:12px;
                        margin-bottom:14px;
                    ">
                        <div style="
                            font-weight:1000;
                            color:#D7ECFF;
                            font-size:17px;
                            margin-bottom:6px;
                        ">
                            {("Share total" if compare_dim_share == "(ninguno)" else f"Share por {compare_dim_share}")} · {share_metric_sel}
                        </div>
                        {legend_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                fig_donut_ops = plot_donut_share(
                    df_share=dshare[["series", "share", share_value_col]],
                    title="",
                    series_color_map=series_color_map,
                    value_col=share_value_col,
                    metric_label=share_metric_label,
                )

                if fig_donut_ops:
                    st.plotly_chart(fig_donut_ops, use_container_width=True)


            with right_share:

                titulo_share = "Distribución" if compare_dim_share == "(ninguno)" else f"Distribución por {compare_dim_share}"
                st.subheader(f"{titulo_share} · {share_metric_sel}")

                # tabla resumen
                summary_ops = dshare[["series", share_value_col, "share"]].copy()
                summary_ops["share_pct"] = (summary_ops["share"] * 100).round(1)
                summary_ops.rename(columns={share_value_col: "total"}, inplace=True)

                # =========================
                # BARRAS antes de la tabla
                # =========================
                df_bar_ops = (
                    summary_ops[["series", "total"]]
                    .copy()
                    .sort_values(["total", "series"], ascending=[False, True])
                    .reset_index(drop=True)
                )

                if not df_bar_ops.empty:
                    bar_ops = (
                        alt.Chart(df_bar_ops)
                        .mark_bar(cornerRadius=10)
                        .encode(
                            y=alt.Y(
                                "series:N",
                                sort="-x",
                                title=None,
                                axis=alt.Axis(
                                    labelColor=BRAND["chart_text"],
                                    titleColor=BRAND["chart_text"],
                                ),
                            ),
                            x=alt.X(
                                "total:Q",
                                title=None,
                                axis=alt.Axis(
                                    labelColor=BRAND["chart_text"],
                                    titleColor=BRAND["chart_text"],
                                    gridColor=BRAND["grid"],
                                ),
                            ),
                            color=alt.Color(
                                "series:N",
                                scale=alt.Scale(
                                    domain=df_bar_ops["series"].astype(str).tolist(),
                                    range=[
                                        series_color_map.get(str(s), "#2563EB")
                                        for s in df_bar_ops["series"].astype(str).tolist()
                                    ],
                                ),
                                legend=None,
                            ),
                            tooltip=[
                                alt.Tooltip("series:N", title="Serie"),
                                alt.Tooltip("total:Q", format=",.0f", title=share_metric_sel),
                            ],
                        )
                        .properties(height=320)
                        .configure(background=BRAND["chart_bg"])
                        .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
                    )

                    st.altair_chart(bar_ops, use_container_width=True)

                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

                # =========================
                # TABLA
                # =========================
                view_ops = summary_ops[["series", "share_pct", "total"]].copy()
                view_ops.insert(
                    0,
                    "●",
                    view_ops["series"].astype(str).map(
                        lambda s: f"<span style='color:{series_color_map.get(str(s), '#EAF1FF')}; font-weight:1000;'>●</span>"
                    ),
                )

                st.markdown(
                    "<div class='mh-dark-table-wrap'>"
                    + view_ops.to_html(index=False, classes="mh-dark-table", escape=False)
                    + "</div>",
                    unsafe_allow_html=True,
                )

                st.markdown("")

                csv_ops = summary_ops[["series", "share_pct", "total"]].to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Descargar resumen share (CSV)",
                    data=csv_ops,
                    file_name=f"share_operativo_{share_value_col}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

def query_top10_gmv_by_dim(engine, params, compare_dim: str, schema: str = "mp") -> pd.DataFrame:
    """
    Top 10 por GMV y órdenes por dimensión elegida.

    Soporta: Ciudad, Categoría (vendor), Vendor, Canal, Device, Order status.

    Auto-detecta nombres reales de columnas en mp.orders (status/order_status/state, etc)
    y aplica deleted_at solo si existe.
    """

    # -----------------------------
    # Detecta columnas reales (orders)
    # -----------------------------
    # fecha de orden
    o_created = _pick_existing_col(engine, schema, "orders", ["created_at", "order_created_at", "order_date", "date", "day"])
    if o_created is None:
        # sin fecha -> no podemos filtrar rango, devolvemos vacío (no tronamos)
        return pd.DataFrame(columns=["dim", "gmv", "orders"])

    # GMV / total
    o_total = _pick_existing_col(engine, schema, "orders", ["order_total", "gmv", "total", "amount", "order_amount", "subtotal"])
    if o_total is None:
        return pd.DataFrame(columns=["dim", "gmv", "orders"])

    # status (puede NO existir)
    o_status = _pick_existing_col(engine, schema, "orders", ["status", "order_status", "state", "order_state"])

    # user_id / vendor_id (por si tus llaves no son exactamente iguales)
    o_user_id = _pick_existing_col(engine, schema, "orders", ["user_id", "customer_id", "uid"])
    if o_user_id is None:
        return pd.DataFrame(columns=["dim", "gmv", "orders"])

    o_vendor_id = _pick_existing_col(engine, schema, "orders", ["vendor_id", "store_id", "merchant_id"])

    # soft delete opcional
    o_del = "AND o.deleted_at IS NULL" if _has_col(engine, schema, "orders", "deleted_at") else ""

    # -----------------------------
    # Detecta columnas reales (users)
    # -----------------------------
    u_pk = _pick_existing_col(engine, schema, "users", ["user_id", "id"])
    if u_pk is None:
        return pd.DataFrame(columns=["dim", "gmv", "orders"])

    u_city = _pick_existing_col(engine, schema, "users", ["city", "ciudad"])
    u_channel = _pick_existing_col(engine, schema, "users", ["acquisition_channel", "channel", "canal"])
    u_device = _pick_existing_col(engine, schema, "users", ["device", "platform"])

    u_del = "AND u.deleted_at IS NULL" if _has_col(engine, schema, "users", "deleted_at") else ""

    # -----------------------------
    # Vendors opcional
    # -----------------------------
    has_vendors = _table_exists(engine, schema, "vendors") and (o_vendor_id is not None)
    v_pk = _pick_existing_col(engine, schema, "vendors", ["vendor_id", "id"]) if has_vendors else None
    v_cat = _pick_existing_col(engine, schema, "vendors", ["category", "categoria"]) if has_vendors else None
    v_del_join = "AND v.deleted_at IS NULL" if (has_vendors and _has_col(engine, schema, "vendors", "deleted_at")) else ""

    join_v = ""
    cat_filter = ""
    if has_vendors and v_pk and v_cat:
        join_v = f"""
        LEFT JOIN {schema}.vendors v
          ON v.{v_pk} = o.{o_vendor_id}
         {v_del_join}
        """
        cat_filter = "AND (:categories_is_all = 1 OR v.{v_cat} = ANY(:categories))".format(v_cat=v_cat)

    # -----------------------------
    # Dimensión elegida
    # -----------------------------
    # OJO: Para Order status usamos la columna detectada en orders; si no existe, cae en UNKNOWN.
    if compare_dim in ["Canal"]:
        dim_expr = f"u.{u_channel}" if u_channel else "NULL"
    elif compare_dim in ["Device"]:
        dim_expr = f"u.{u_device}" if u_device else "NULL"
    elif compare_dim in ["Order status", "Order Status", "Order status"]:
        dim_expr = f"o.{o_status}" if o_status else "NULL"
    elif compare_dim in ["Ciudad"]:
        dim_expr = f"u.{u_city}" if u_city else "NULL"
    elif compare_dim in ["Categoría (vendor)", "Categoría", "Category"]:
        dim_expr = f"v.{v_cat}" if (has_vendors and v_cat) else "NULL"
    else:
        # fallback estable
        dim_expr = f"u.{u_city}" if u_city else "NULL"
        compare_dim = "Ciudad"

    # -----------------------------
    # Métricas: si hay status, contamos/sumamos completed; si no, todo.
    # -----------------------------
    if o_status:
        gmv_expr = f"SUM(CASE WHEN o.{o_status} = 'completed' THEN o.{o_total} ELSE 0 END)::float AS gmv"
        orders_expr = f"COUNT(*) FILTER (WHERE o.{o_status} = 'completed')::int AS orders"
    else:
        gmv_expr = f"SUM(o.{o_total})::float AS gmv"
        orders_expr = "COUNT(*)::int AS orders"

    # -----------------------------
    # SQL final
    # -----------------------------
    # filtros de user (si existe la col)
    city_filter = f"AND (:cities_is_all = 1 OR u.{u_city} = ANY(:cities))" if u_city else ""
    ch_filter = f"AND (:channels_is_all = 1 OR u.{u_channel} = ANY(:channels))" if u_channel else ""
    dev_filter = f"AND (:devices_is_all = 1 OR u.{u_device} = ANY(:devices))" if u_device else ""

    sql = f"""
    SELECT
        COALESCE(({dim_expr})::text, 'UNKNOWN') AS dim,
        {gmv_expr},
        {orders_expr}
    FROM {schema}.orders o
    JOIN {schema}.users u
      ON u.{u_pk} = o.{o_user_id}
     {u_del}
    {join_v}
    WHERE 1=1
      {o_del}
      AND o.{o_created}::date BETWEEN :d1 AND :d2
      {city_filter}
      {ch_filter}
      {dev_filter}
      {cat_filter}
    GROUP BY 1
    ORDER BY gmv DESC, dim ASC
    LIMIT 10
    """

    def _is_all(x):
        return 1 if (x is None or (isinstance(x, (list, tuple)) and len(x) == 0)) else 0

    bind = {
        "d1": params["date_from"],
        "d2": params["date_to"],

        "cities_is_all": _is_all(params.get("cities")),
        "channels_is_all": _is_all(params.get("channels")),
        "devices_is_all": _is_all(params.get("devices")),
        "categories_is_all": _is_all(params.get("categories")),

        "cities": params.get("cities") or [],
        "channels": params.get("channels") or [],
        "devices": params.get("devices") or [],
        "categories": params.get("categories") or [],
    }

    return pd.read_sql(text(sql), engine, params=bind)

if show_top_tables:
    st.write("")
    l2, r2 = st.columns([0.55, 0.45])

    # usa el mismo dropdown del sidebar: "Desglosar análisis por"
    compare_dim = fs.get("series_dim", "(ninguno)")
    if compare_dim == "(ninguno)":
        compare_dim = "Ciudad"

    # ---------- helper: normaliza df_top a columnas: dim, gmv, orders ----------
    def _normalize_top_df(df_in: pd.DataFrame, preferred_dim_col: str | None = None) -> pd.DataFrame:
        if df_in is None or df_in.empty:
            return pd.DataFrame(columns=["dim", "gmv", "orders"])

        df = df_in.copy()

        # 1) elige columna dimensión (evita KeyError)
        if preferred_dim_col and preferred_dim_col in df.columns:
            dim_col = preferred_dim_col
        elif "dim" in df.columns:
            dim_col = "dim"
        elif "city" in df.columns:
            dim_col = "city"
        elif "category" in df.columns:
            dim_col = "category"
        elif "vendor" in df.columns:
            dim_col = "vendor"
        elif "vendor_name" in df.columns:
            dim_col = "vendor_name"
        elif "series" in df.columns:
            dim_col = "series"
        else:
            obj_cols = [c for c in df.columns if str(df[c].dtype) == "object"]
            dim_col = obj_cols[0] if obj_cols else df.columns[0]

        # 2) normaliza métricas
        if "gmv" not in df.columns:
            for c in ["GMV", "total_gmv", "order_total", "sales"]:
                if c in df.columns:
                    df["gmv"] = df[c]
                    break
        if "gmv" not in df.columns:
            df["gmv"] = 0

        if "orders" not in df.columns:
            for c in ["orders_total", "order_count", "num_orders", "orders_completed"]:
                if c in df.columns:
                    df["orders"] = df[c]
                    break
        if "orders" not in df.columns:
            df["orders"] = 0

        # 3) renombra dimensión a 'dim'
        if dim_col != "dim":
            df = df.rename(columns={dim_col: "dim"})

        # 4) tipos
        df["dim"] = df["dim"].astype(str)
        df["gmv"] = pd.to_numeric(df["gmv"], errors="coerce").fillna(0.0)
        df["orders"] = pd.to_numeric(df["orders"], errors="coerce").fillna(0).astype(int)

        return df[["dim", "gmv", "orders"]]

    # ---------- construye df_top según dropdown ----------
    df_top_raw = df_cities.copy() if isinstance(df_cities, pd.DataFrame) else pd.DataFrame()

    if compare_dim in ["Ciudad"]:
        df_top_raw = df_cities.copy() if isinstance(df_cities, pd.DataFrame) else pd.DataFrame()
        df_top = _normalize_top_df(df_top_raw, preferred_dim_col="city")

    elif compare_dim in ["Categoría (vendor)", "Categoría", "Category"]:
        if isinstance(df_vendors, pd.DataFrame) and (("category" in df_vendors.columns) or ("Category" in df_vendors.columns)):
            dfxv = df_vendors.copy()
            if "Category" in dfxv.columns and "category" not in dfxv.columns:
                dfxv = dfxv.rename(columns={"Category": "category"})
            if "gmv" not in dfxv.columns and "GMV" in dfxv.columns:
                dfxv = dfxv.rename(columns={"GMV": "gmv"})
            if "orders" not in dfxv.columns and "orders_total" in dfxv.columns:
                dfxv = dfxv.rename(columns={"orders_total": "orders"})

            df_top_raw = (
                dfxv.groupby("category", dropna=False, as_index=False)
                .agg(
                    gmv=("gmv", "sum"),
                    orders=("orders", "sum") if "orders" in dfxv.columns else ("gmv", "size"),
                )
            )
        else:
            df_top_raw = pd.DataFrame()

        df_top = _normalize_top_df(df_top_raw, preferred_dim_col="category")

    elif compare_dim in ["Vendor", "Vendedor", "Proveedor"]:
        df_top_raw = df_vendors.copy() if isinstance(df_vendors, pd.DataFrame) else pd.DataFrame()
        df_top = _normalize_top_df(df_top_raw, preferred_dim_col="vendor_name")

    # ✅ AQUÍ el cambio mínimo que NO rompe: Canal / Device / Order status = query real
    elif compare_dim in ["Canal", "Device", "Order status", "Order Status", "Order status"]:
        # Nota: NO se puede derivar de df_orders si no trae esas columnas.
        df_top_raw = query_top10_gmv_by_dim(engine, params, compare_dim, schema=SCHEMA)
        df_top = _normalize_top_df(df_top_raw, preferred_dim_col="dim")

    else:
        df_top = _normalize_top_df(df_top_raw, preferred_dim_col="city")
        compare_dim = "Ciudad"

    # top 10 por gmv
    df_top = (
        df_top.sort_values(["gmv", "dim"], ascending=[False, True])
        .head(10)
        .reset_index(drop=True)
    )

    with l2:
        st.subheader(f"Top 10 por GMV · {compare_dim}")

        badge = active_filter_badge()
        if badge:
            st.caption(badge)

        if df_top.empty:
            st.info("No hay datos para este desglose con los filtros actuales.")
        else:
            # -----------------------------
            # A) BAR: Top 10
            # -----------------------------
            bar = (
                alt.Chart(df_top)
                .mark_bar(cornerRadius=12)  # ✅ redondeadas
                .encode(
                    y=alt.Y(
                        "dim:N",
                        sort="-x",
                        axis=alt.Axis(labelColor=BRAND["chart_text"], titleColor=BRAND["chart_text"]),
                        title=None,
                    ),
                    x=alt.X(
                        "gmv:Q",
                        axis=alt.Axis(
                            labelColor=BRAND["chart_text"],
                            titleColor=BRAND["chart_text"],
                            gridColor=BRAND["grid"],
                        ),
                        title=None,
                    ),
                    color=alt.Color(
                        "dim:N",
                        scale=color_scale_for(df_top["dim"].astype(str).tolist()),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("dim:N", title=str(compare_dim)),
                        alt.Tooltip("gmv:Q", format=",.0f", title="GMV"),
                        alt.Tooltip("orders:Q", format=",.0f", title="Órdenes"),
                    ],
                )
                .properties(height=350)
                .configure(background=BRAND["chart_bg"])
                .configure_view(strokeOpacity=0, fill=BRAND["chart_bg"])
            )
            st.altair_chart(bar, use_container_width=True)

            # -----------------------------
            # B) DONUT (Plotly): Share de ventas (GMV) con el MISMO look de tus otros shares
            # -----------------------------
            total_gmv = float(pd.to_numeric(df_top["gmv"], errors="coerce").fillna(0).sum())

            if total_gmv <= 0:
                st.caption("Share de ventas: sin GMV en este rango.")
            else:
                # arma df_share con columnas: series, share, gmv
                df_share = df_top[["dim", "gmv"]].copy()
                df_share["gmv"] = pd.to_numeric(df_share["gmv"], errors="coerce").fillna(0.0)
                df_share = df_share.rename(columns={"dim": "series"})

                df_share["series"] = df_share["series"].astype(str)
                df_share["share"] = df_share["gmv"] / total_gmv

                # mapa de colores: usa la misma paleta y respeta "Otros" como gris (ya lo hace tu función)
                # aquí construimos series_color_map para que coincida con el color_scale_for / paleta del dashboard
                labels_now = df_share.sort_values(["share", "series"], ascending=[False, True])["series"].tolist()
                colors_now = (PALETA * 10)[: len(labels_now)]
                series_color_map = dict(zip(labels_now, colors_now))

                st.markdown(
                    f"<div style='margin-top:6px; font-weight:1000; opacity:.95;'>Share de ventas (GMV) · {compare_dim}</div>",
                    unsafe_allow_html=True,
                )

                fig = plot_donut_share(
                    df_share=df_share[["series", "share", "gmv"]],
                    title=None,
                    series_color_map=series_color_map,
                    value_col="gmv",
                    metric_label="GMV",
                )

                # tu función regresa fig o (fig, ...) según cómo la tengas;
                # aquí lo hacemos robusto:
                if isinstance(fig, tuple):
                    fig = fig[0]

                # (Opcional) “look mark_arc cornerRadius=8”: no existe literal en Plotly,
                # pero el borde + separación da el mismo efecto pro.
                # Ajusta el borde si quieres que se vea más “segmentado”.
                fig.update_traces(
                    marker=dict(line=dict(color="#0B1B33", width=2))
                )

                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with r2:
        st.subheader("Top vendors (GMV)")

        badge = active_filter_badge()
        if badge:
            st.caption(badge)

        if not df_vendors.empty:
            show = df_vendors.copy()
            if "gmv" in show.columns:
                show["gmv"] = pd.to_numeric(show["gmv"], errors="coerce").fillna(0).round(2)

            cats = show["category"].astype(str).unique().tolist() if "category" in show.columns else []
            cat_to_color = dict(zip(cats, (PALETA * 10)[: len(cats)]))

            if "category" in show.columns:
                show.insert(
                    0,
                    "●",
                    show["category"].astype(str).map(
                        lambda c: f"<span style='color:{cat_to_color.get(c,'#EAF1FF')}; font-weight:1000;'>●</span>"
                    ),
                )

            st.markdown(
                "<div class='mh-dark-table-wrap'>"
                + show.to_html(index=False, classes="mh-dark-table", escape=False)
                + "</div>",
                unsafe_allow_html=True,
            )

            st.markdown("")

            csv_bytes = df_vendors.to_csv(index=False).encode("Latin1")
            st.download_button(
                "Descargar top vendors (CSV)",
                data=csv_bytes,
                file_name="top_vendors.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No hay vendors en el rango con los filtros actuales.")
        st.markdown("</div>", unsafe_allow_html=True)

    reset_sep()
    sep()

# =========================
# EXPORTAR PÁGINA A PDF (print a PDF)
# =========================
st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

components.html(
    """
    <style>
      /* Que respete colores al imprimir */
      * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }

      /* Botón */
      .mh-pdf-btn{
        width: 100%;
        padding: 14px 16px;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,.10);
        background: #0047AB;
        color: #EAF1FF;
        font-weight: 1000;
        font-size: 16px;
        cursor: pointer;
        box-shadow: 0 10px 22px rgba(0,0,0,.35);
      }
      .mh-pdf-btn:hover{ filter: brightness(1.05); }

      /* Opcional: en impresión, quita UI de Streamlit para que sea “reporte” */
      @media print{
        header, footer { display: none !important; }
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        .stApp { background: #000000 !important; }
        /* margen tipo hoja */
        @page { margin: 10mm; }
      }
    </style>

    <button class="mh-pdf-btn" onclick="window.parent.print()">
      ⬇️ Descargar página como PDF
    </button>
    """,
    height=80,
)