import streamlit as st
import streamlit.components.v1 as st_components
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import pickle
from pathlib import Path

from parser import load_carteira_s3
from rules_engine import ComplianceEngine, SEGMENT_LIMITS
from ai_analysis import gerar_analise_compliance, chat_vigia, chat_persona, PERSONAS
from email_sender import enviar_relatorio_email
from report_generator import gerar_pdf
from historico import salvar_snapshot, carregar_historico, historico_para_dataframe
from performance import load_cotas, ultima_posicao, achar_cotas_csv
from balancete_parser import parse_balancete, achar_balancete
from bcb_api import get_benchmarks
from analytics import (calcular_risco_retorno, concentracao_gestores,
                       calcular_meta_atuarial, simular_realocacao,
                       atribuicao_performance)
from risco_avancado import (calcular_var, calcular_drawdown,
                             calcular_correlacao, stress_test, CENARIOS_STRESS)
from projecao import monte_carlo_patrimonio, projetar_cenarios, resumo_monte_carlo
from noticias import buscar_noticias_efpc, buscar_noticias_mercado

# ── Configuração da página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="VIGIA — Análise de Investimentos",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

PL_DEFAULT   = 2_107_321_289.97
DATA_DEFAULT = "31/03/2026"
COR  = {'verde': '#27AE60', 'amarelo': '#E67E22', 'vermelho': '#E74C3C'}
AZUL = '#1B3A6B'

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
.main .block-container {
    background: #F0F3F8;
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(175deg, #070F1C 0%, #0D1E35 50%, #122645 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] > div { padding-top: 1.2rem !important; }
section[data-testid="stSidebar"] h2 {
    color: #FFFFFF !important; font-weight: 800 !important;
    font-size: 1.25rem !important; letter-spacing: -0.01em !important;
}
section[data-testid="stSidebar"] h3 {
    color: #7FA8D0 !important; font-weight: 600 !important;
    font-size: 0.70rem !important; text-transform: uppercase !important;
    letter-spacing: 0.10em !important;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] span { color: #8AAECB !important; }
section[data-testid="stSidebar"] label { color: #B8D0E8 !important; }
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.07) !important; margin: 10px 0 !important;
}
section[data-testid="stSidebar"] .stSuccess {
    background: rgba(39,174,96,0.15) !important;
    border-left-color: #27AE60 !important; border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stSuccess p { color: #6DCFA0 !important; }
section[data-testid="stSidebar"] .stInfo {
    background: rgba(46,134,193,0.12) !important;
    border-radius: 8px !important;
}
section[data-testid="stSidebar"] .stWarning {
    background: rgba(230,126,34,0.12) !important;
    border-radius: 8px !important;
}
/* Nav radio */
section[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    display: flex; flex-direction: column; gap: 1px;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    border-radius: 8px !important; padding: 9px 14px !important;
    color: #A8C4DF !important; font-weight: 500 !important;
    font-size: 0.88rem !important; transition: all 0.15s !important;
    cursor: pointer !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,0.06) !important;
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"] {
    background: rgba(46,109,173,0.30) !important;
    color: #FFFFFF !important; font-weight: 600 !important;
    border-left: 3px solid #5BAEE8 !important;
}
/* Inputs sidebar */
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] select,
section[data-testid="stSidebar"] textarea {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #D0E4F5 !important; border-radius: 7px !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(46,109,173,0.25) !important;
    border: 1px solid rgba(91,174,232,0.30) !important;
    color: #C0D8EF !important; border-radius: 8px !important;
    font-weight: 600 !important; transition: all 0.2s !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(46,109,173,0.45) !important;
    color: #FFFFFF !important; border-color: rgba(91,174,232,0.5) !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #FFFFFF !important;
    border-radius: 12px !important; padding: 18px 20px !important;
    border: 1px solid #E2E9F2 !important;
    border-top: 3px solid #1B3A6B !important;
    box-shadow: 0 2px 12px rgba(15,30,60,0.07) !important;
    transition: box-shadow 0.2s, transform 0.2s !important;
}
[data-testid="metric-container"]:hover {
    box-shadow: 0 6px 22px rgba(15,30,60,0.12) !important;
    transform: translateY(-2px) !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.72rem !important; font-weight: 700 !important;
    text-transform: uppercase !important; letter-spacing: 0.07em !important;
    color: #6B7E96 !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.6rem !important; font-weight: 700 !important;
    color: #0F1E33 !important; letter-spacing: -0.02em !important;
}
[data-testid="stMetricDelta"] { font-size: 0.80rem !important; font-weight: 600 !important; }

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: #E2EAF4 !important; border-radius: 10px !important;
    padding: 4px !important; gap: 2px !important; border: none !important;
}
[data-baseweb="tab"] {
    border-radius: 7px !important; font-weight: 500 !important;
    font-size: 0.84rem !important; color: #52697E !important;
    padding: 7px 18px !important; transition: all 0.15s !important;
    border: none !important; background: transparent !important;
}
[data-baseweb="tab"]:hover { background: rgba(255,255,255,0.65) !important; color: #1B3A6B !important; }
[aria-selected="true"][data-baseweb="tab"] {
    background: #FFFFFF !important; color: #1B3A6B !important;
    font-weight: 700 !important; box-shadow: 0 2px 10px rgba(0,0,0,0.10) !important;
}

/* ── Buttons ── */
.stButton > button {
    border-radius: 8px !important; font-weight: 600 !important;
    font-size: 0.87rem !important; transition: all 0.2s !important;
    letter-spacing: 0.01em !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1B3A6B 0%, #2E6DAD 100%) !important;
    border: none !important; color: #FFFFFF !important;
    box-shadow: 0 2px 10px rgba(27,58,107,0.28) !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 18px rgba(27,58,107,0.38) !important;
}
.stButton > button[kind="secondary"] {
    border: 1.5px solid #C5D5E8 !important;
    color: #2E5A8E !important; background: #FFFFFF !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #1B3A6B !important; background: #F0F5FB !important;
}

/* ── Inputs ── */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
    border-radius: 8px !important; border: 1.5px solid #D1DBE8 !important;
    background: #FAFCFF !important; font-size: 0.90rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color: #2E6DAD !important;
    box-shadow: 0 0 0 3px rgba(46,109,173,0.12) !important; outline: none !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #E2E9F2 !important; border-radius: 10px !important;
    background: #FFFFFF !important; box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important; color: #1A2E46 !important; font-size: 0.92rem !important;
}

/* ── Alert boxes ── */
[data-testid="stAlert"] { border-radius: 10px !important; border-left-width: 4px !important; }

/* ── DataFrames ── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important; overflow: hidden !important;
    box-shadow: 0 1px 8px rgba(0,0,0,0.07) !important;
    border: 1px solid #E2E9F2 !important;
}

/* ── Dividers ── */
hr { border: none !important; border-top: 1px solid #E2E9F2 !important; margin: 18px 0 !important; }

/* ── Plotly chart container ── */
[data-testid="stPlotlyChart"] {
    border-radius: 12px; overflow: hidden;
    box-shadow: 0 2px 10px rgba(0,0,0,0.07);
    background: #FFFFFF; padding: 4px;
    border: 1px solid #E8EFF7;
}

/* ── Custom classes ── */
.vigia-header {
    background: linear-gradient(135deg, #070F1C 0%, #1B3A6B 55%, #2472B5 100%);
    padding: 20px 28px; border-radius: 14px; color: white; margin-bottom: 20px;
    box-shadow: 0 6px 28px rgba(7,15,28,0.28);
    border: 1px solid rgba(255,255,255,0.08);
}
.secao-titulo {
    font-size: 1.05rem; font-weight: 700; color: #0F1E33;
    border-left: 4px solid #1B3A6B; padding: 2px 0 2px 12px;
    margin: 4px 0 14px 0; letter-spacing: -0.01em; line-height: 1.4;
}
.kpi-card {
    background: #FFFFFF; border-radius: 12px; padding: 18px 20px;
    border: 1px solid #E2E9F2; border-top: 3px solid #1B3A6B;
    box-shadow: 0 2px 12px rgba(15,30,60,0.07);
}
.badge {
    display: inline-block; border-radius: 20px;
    padding: 3px 11px; font-size: 0.76rem; font-weight: 700; letter-spacing: 0.02em;
}
.badge-verde   { background: #E8F8F1; color: #1A7A40; }
.badge-amarelo { background: #FEF9E7; color: #9A6B00; }
.badge-verm    { background: #FDE8E8; color: #A93226; }

/* ── Hide Streamlit chrome ── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

/* Navegação mobile — radio escondido no desktop */
@media screen and (min-width: 769px) {
    [data-testid="stRadio"][aria-label="📱 Módulo"],
    div:has(> [data-testid="stRadio"] > label[data-baseweb="radio"]:first-child) {
        display: none !important;
    }
}
@media screen and (max-width: 768px) {
    /* Estilo do radio de navegação mobile */
    [data-testid="stRadio"] > div {
        flex-direction: column !important;
        gap: 0 !important;
        border: 1px solid #D0D8E4 !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        background: #FFFFFF !important;
    }
    [data-testid="stRadio"] > div > label {
        padding: 10px 14px !important;
        border-bottom: 1px solid #EEF2F7 !important;
        font-size: 0.88rem !important;
        margin: 0 !important;
    }
    [data-testid="stRadio"] > div > label:last-child {
        border-bottom: none !important;
    }
}

/* ── Mobile ── */
@media screen and (max-width: 768px) {
    /* Padding da página */
    .main .block-container {
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
        padding-top: 0.8rem !important;
    }

    /* Empilha todas as colunas */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.4rem !important;
    }
    [data-testid="stColumn"], [data-testid="column"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
        width: 100% !important;
    }

    /* Métricas: 2 por linha */
    [data-testid="stHorizontalBlock"]:has([data-testid="metric-container"])
    [data-testid="stColumn"] {
        min-width: calc(50% - 0.4rem) !important;
        flex: 1 1 calc(50% - 0.4rem) !important;
    }

    /* Metric cards menores */
    [data-testid="metric-container"] {
        padding: 12px 14px !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: 1.25rem !important;
    }
    [data-testid="stMetricLabel"] > div {
        font-size: 0.65rem !important;
    }

    /* Seção título */
    .secao-titulo {
        font-size: 0.95rem !important;
    }

    /* Header VIGIA */
    .vigia-header {
        padding: 14px 16px !important;
    }
    .vigia-header-previc {
        display: none !important;
    }
    .vigia-header-title {
        font-size: 1.25rem !important;
    }
    .vigia-header-sub {
        font-size: 0.68rem !important;
    }

    /* Tabelas HTML com scroll horizontal */
    .stMarkdown table,
    div[data-testid="stMarkdownContainer"] table {
        display: block !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        white-space: nowrap !important;
    }
    .tabela-scroll {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        width: 100% !important;
    }

    /* DataFrames */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }

    /* Tabs — font menor */
    [data-baseweb="tab"] {
        font-size: 0.75rem !important;
        padding: 6px 10px !important;
    }

    /* Gráficos — altura reduzida */
    [data-testid="stPlotlyChart"] > div {
        max-height: 320px !important;
    }

    /* Texto geral */
    p, .stCaption { font-size: 0.82rem !important; }

    /* Barra de topo do Streamlit — fundo azul VIGIA no mobile */
    header[data-testid="stHeader"] {
        background: #1B3A6B !important;
        min-height: 52px !important;
    }
    /* Todos os botões dentro do header — ícone branco */
    header[data-testid="stHeader"] button,
    header[data-testid="stHeader"] a {
        color: #FFFFFF !important;
    }
    header[data-testid="stHeader"] button svg,
    header[data-testid="stHeader"] svg {
        fill: #FFFFFF !important;
        stroke: #FFFFFF !important;
    }
}

@media screen and (max-width: 480px) {
    /* Métricas: 1 por linha em telas muito pequenas */
    [data-testid="stHorizontalBlock"]:has([data-testid="metric-container"])
    [data-testid="stColumn"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
    .vigia-header-sub { display: none !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if 'analise_ia' not in st.session_state:
    st.session_state.analise_ia = None
if 'chat_historico' not in st.session_state:
    st.session_state.chat_historico = []
if 'chat_persona' not in st.session_state:
    st.session_state.chat_persona = 'vigia'
if 'active_page' not in st.session_state:
    st.session_state.active_page = 'Dashboard'
if 'sidebar_open' not in st.session_state:
    st.session_state.sidebar_open = True

# ── CSS dinâmico da sidebar ───────────────────────────────────────────────────
if st.session_state.sidebar_open:
    st.markdown("""<style>
    section[data-testid="stSidebar"] {
        display: flex !important;
        transform: translateX(0) !important;
        min-width: 244px !important;
    }
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    </style>""", unsafe_allow_html=True)
else:
    st.markdown("""<style>
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    </style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="vigia-header">
  <div style="display:flex;align-items:center;gap:16px;">
    <div style="width:48px;height:48px;background:rgba(255,255,255,0.10);
                border-radius:12px;display:flex;align-items:center;
                justify-content:center;font-size:1.5rem;flex-shrink:0;
                border:1px solid rgba(255,255,255,0.18);">🔍</div>
    <div>
      <div class="vigia-header-title"
           style="font-size:1.55rem;font-weight:800;letter-spacing:-0.03em;
                  line-height:1.1;color:#FFFFFF;">VIGIA</div>
      <div class="vigia-header-sub"
           style="font-size:0.78rem;color:rgba(255,255,255,0.65);margin-top:3px;
                  letter-spacing:0.01em;">
        <strong>V</strong>igilância de <strong>I</strong>nvestimentos e <strong>G</strong>estão do <strong>I</strong>AJ<strong>A</strong> &nbsp;·&nbsp;
        <strong style="color:rgba(255,255,255,0.85);">IAJA</strong>
        — Instituto Adventista de Jubilação e Assistência &nbsp;·&nbsp; PREVIC
      </div>
    </div>
    <div class="vigia-header-previc" style="margin-left:auto;text-align:right;flex-shrink:0;">
      <div style="font-size:0.65rem;color:rgba(255,255,255,0.50);
                  text-transform:uppercase;letter-spacing:0.10em;">Supervisionado por</div>
      <div style="font-size:1.0rem;font-weight:700;color:rgba(255,255,255,0.90);
                  letter-spacing:0.02em;">PREVIC</div>
      <div style="font-size:0.68rem;color:rgba(255,255,255,0.45);margin-top:2px;">
        Res. CMN 4.994/2022
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0 12px 0;">
      <div>
        <div style="font-size:1.35rem;font-weight:800;color:#FFFFFF;letter-spacing:-0.02em;">🔍 VIGIA</div>
        <div style="font-size:0.68rem;color:#5A88B5;margin-top:2px;letter-spacing:0.04em;">ANÁLISE DE INVESTIMENTOS</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("✕ Fechar", key="fechar_sidebar", use_container_width=True):
        st.session_state.sidebar_open = False
        st.rerun()
    st.markdown("---")

    # Navegação principal
    st.markdown("### 📂 Módulos")
    MODULOS = {
        "📊 Dashboard":           "Dashboard",
        "📉 Performance":         "Performance",
        "🏆 Comparativo de Mercado": "Comparativo",
        "📈 Risco Avançado":      "Risco Avançado",
        "🔮 Projeção de Patrimônio": "Projeção",
        "⚖️ Simulador":          "Simulador",
        "🤖 Análise IA":          "Análise IA",
        "💬 Chat Personas":       "Chat",
        "📋 Balancete":           "Balancete",
        "📄 Relatório PDF":       "Relatório PDF",
        "📰 Notícias":            "Notícias",
        "📈 Histórico":           "Histórico",
    }
    _nav_keys = list(MODULOS.keys())
    _nav_vals = list(MODULOS.values())
    _nav_idx  = _nav_vals.index(st.session_state.active_page) if st.session_state.active_page in _nav_vals else 0
    pagina_label = st.radio(
        "Navegação",
        _nav_keys,
        index=_nav_idx,
        label_visibility="collapsed",
    )
    if MODULOS[pagina_label] != st.session_state.active_page:
        st.session_state.active_page = MODULOS[pagina_label]
        st.session_state['_nav_source'] = 'sidebar'
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ Dados")

    uploaded = st.file_uploader("Upload CSV Composição", type=['csv'])
    uploaded_bal = st.file_uploader("Upload PDF Balancete", type=['pdf'])
    uploaded_cotas = st.file_uploader("Upload CSV Cotas", type=['csv'], key="cotas_upload")
    usar_local = st.checkbox("Usar arquivo local (data/Composição/)", value=True)
    data_ref = st.text_input("Data de referência", value=DATA_DEFAULT)

    api_key = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else ""

    st.divider()
    st.caption("IAJA · PREVIC · Res. CMN 4.994/2022")

# ── Carrega dados ─────────────────────────────────────────────────────────────
data_dir = Path(__file__).parent / "data"
_CACHE_DIR = data_dir / ".cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _disk_load(key: str, mtime: float):
    """Carrega dado do cache em disco se o mtime bater."""
    pkl  = _CACHE_DIR / f"{key}.pkl"
    mtf  = _CACHE_DIR / f"{key}.mtime"
    try:
        if pkl.exists() and mtf.exists() and float(mtf.read_text()) == mtime:
            with pkl.open('rb') as f:
                return pickle.load(f)
    except Exception:
        pass
    return None


def _disk_save(key: str, mtime: float, data) -> None:
    """Persiste dado no cache em disco."""
    try:
        with (_CACHE_DIR / f"{key}.pkl").open('wb') as f:
            pickle.dump(data, f)
        (_CACHE_DIR / f"{key}.mtime").write_text(str(mtime))
    except Exception:
        pass


# Wrappers com cache em disco + cache em memória (st.cache_data)
@st.cache_data(show_spinner=False)
def _cached_balancete(path_str: str, mtime: float):
    cached = _disk_load("balancete", mtime)
    if cached is not None:
        return cached
    result = parse_balancete(Path(path_str))
    _disk_save("balancete", mtime, result)
    return result


@st.cache_data(show_spinner=False)
def _cached_carteira(path_str: str, mtime: float, pl: float):
    key = f"carteira_{pl:.0f}"
    cached = _disk_load(key, mtime)
    if cached is not None:
        return cached
    result = load_carteira_s3(Path(path_str), pl)
    _disk_save(key, mtime, result)
    return result


@st.cache_data(show_spinner=False)
def _cached_cotas(path_str: str, mtime: float):
    cached = _disk_load("cotas", mtime)
    if cached is not None:
        return cached
    result = load_cotas(Path(path_str))
    _disk_save("cotas", mtime, result)
    return result


@st.cache_data(show_spinner=False)
def _cached_compliance(path_str: str, mtime: float, pl: float, emprestimos: float):
    key = f"compliance_{pl:.0f}_{emprestimos:.0f}"
    cached = _disk_load(key, mtime)
    if cached is not None:
        return cached
    carteira = load_carteira_s3(Path(path_str), pl)
    extra = {'Operações com Participantes': emprestimos} if emprestimos else {}
    eng = ComplianceEngine(carteira, pl, extra_segmentos=extra)
    result = eng.resumo_segmentos(), eng.contagem_status()
    _disk_save(key, mtime, result)
    return result

# 1. Balancete — extrai o PS real
bal_dados = None
extra_segmentos = {}
pl = PL_DEFAULT
if uploaded_bal:
    dest_bal = data_dir / "Balancete" / uploaded_bal.name
    dest_bal.parent.mkdir(parents=True, exist_ok=True)
    dest_bal.write_bytes(uploaded_bal.read())
    bal_path = dest_bal
else:
    bal_path = achar_balancete(data_dir)
if bal_path:
    try:
        bal_dados = _cached_balancete(str(bal_path), bal_path.stat().st_mtime)
        pl = bal_dados['consolidado']['patrimonio_social']
        extra_segmentos = {
            'Operações com Participantes': bal_dados['consolidado']['emprestimos_participantes']
        }
        st.sidebar.success(f"📋 {bal_path.name}")
        st.sidebar.caption(f"PS: R$ {pl/1e9:.3f} Bi (balancete)")
    except Exception as e:
        st.sidebar.warning(f"Balancete: {e}")
else:
    st.sidebar.info("Adicione o balancete em `data/Balancete/`.")

# 2. Carteira
filepath = None
if uploaded:
    dest = data_dir / "Composição" / uploaded.name
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(uploaded.read())
    filepath = dest
elif usar_local:
    comp_dir = data_dir / "Composição"
    csvs = sorted(comp_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if csvs:
        filepath = csvs[0]

if not filepath or not filepath.exists():
    st.info("👈  Carregue o relatório S3 Caceis no painel lateral para começar.")
    st.stop()

try:
    carteira = _cached_carteira(str(filepath), filepath.stat().st_mtime, pl)
    st.sidebar.success(f"✅ {filepath.name}  ({len(carteira)} posições)")
except Exception as e:
    st.sidebar.error(f"Erro no CSV: {e}")
    st.stop()

emprestimos_val = bal_dados['consolidado']['emprestimos_participantes'] if bal_dados else 0.0
resumo, counts = _cached_compliance(str(filepath), filepath.stat().st_mtime, pl, emprestimos_val)

engine = ComplianceEngine(carteira, pl, extra_segmentos=extra_segmentos)

# 3. Cotas
df_cotas = None
if uploaded_cotas:
    dest_cotas = data_dir / "cotas" / uploaded_cotas.name
    dest_cotas.parent.mkdir(parents=True, exist_ok=True)
    dest_cotas.write_bytes(uploaded_cotas.read())
    cotas_path = dest_cotas
else:
    cotas_path = achar_cotas_csv(data_dir)
if cotas_path:
    try:
        df_cotas = _cached_cotas(str(cotas_path), cotas_path.stat().st_mtime)
    except Exception as e:
        st.sidebar.warning(f"Cotas: {e}")

# 4. Benchmarks BCB
@st.cache_data(ttl=3600, show_spinner=False)
def _buscar_benchmarks(ano: int, mes: int) -> dict:
    return get_benchmarks(ano, mes)

try:
    ano_ref, mes_ref = int(data_ref.split('/')[2]), int(data_ref.split('/')[1])
    benchmarks = _buscar_benchmarks(ano_ref, mes_ref)
except Exception:
    benchmarks = {'cdi_mes': 0.0, 'ipca_mes': 0.0, 'inpc_mes': 0.0,
                  'cdi_ano': 0.0, 'ipca_ano': 0.0, 'inpc_ano': 0.0,
                  'ibov_mes': 0.0, 'ibov_ano': 0.0}


# ── Navegação mobile ──────────────────────────────────────────────────────────
_mob_keys = list(MODULOS.keys())
_mob_vals = list(MODULOS.values())
_mob_label = _mob_keys[_mob_vals.index(st.session_state.active_page)] if st.session_state.active_page in _mob_vals else _mob_keys[0]

# Sincroniza o radio mobile quando a navegação veio da sidebar
if st.session_state.get('_nav_source') == 'sidebar':
    st.session_state['_mob_radio'] = _mob_label
    st.session_state['_nav_source'] = None

# Barra superior: botão menu + módulo atual
_col_menu, _col_mod = st.columns([1, 5])
with _col_menu:
    _menu_label = "☰ Menu" if not st.session_state.sidebar_open else "✕"
    if st.button(_menu_label, key="toggle_sidebar", use_container_width=True):
        st.session_state.sidebar_open = not st.session_state.sidebar_open
        st.rerun()
with _col_mod:
    st.markdown(
        f'<p style="font-size:0.85rem;color:#4A6A8A;margin:6px 0 0 4px;font-weight:500;">'
        f'{_mob_label}</p>',
        unsafe_allow_html=True,
    )

pagina = st.session_state.active_page

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if pagina == 'Dashboard':

    total_investido = bal_dados['consolidado']['investimentos'] if bal_dados else carteira['val_ajustado'].sum()
    b = benchmarks
    v_cnt, a_cnt, r_cnt = counts['verde'], counts['amarelo'], counts['vermelho']
    total_segs  = len(resumo)
    pct_conf    = v_cnt / total_segs * 100 if total_segs else 0

    # ── Banner de status ──────────────────────────────────────────────────────
    if r_cnt == 0 and a_cnt == 0:
        st_cor, st_ico, st_txt = '#1A7A40', '🟢', 'TOTALMENTE CONFORME'
        st_bg = 'linear-gradient(90deg,#E8F8F1,#F0FBF4)'
    elif r_cnt == 0:
        st_cor, st_ico, st_txt = '#9A6B00', '🟡', f'ATENÇÃO — {a_cnt} SEGMENTO(S)'
        st_bg = 'linear-gradient(90deg,#FEF9E7,#FFFBF0)'
    else:
        st_cor, st_ico, st_txt = '#A93226', '🔴', f'CRÍTICO — {r_cnt} VIOLAÇÃO(ÕES)'
        st_bg = 'linear-gradient(90deg,#FDE8E8,#FFF0F0)'

    st.markdown(f"""
    <div style="background:{st_bg};border:1px solid {st_cor}33;border-left:4px solid {st_cor};
                border-radius:10px;padding:10px 18px;margin-bottom:18px;
                display:flex;align-items:center;gap:12px;">
      <span style="font-size:1.4rem;">{st_ico}</span>
      <div>
        <div style="font-size:0.70rem;font-weight:700;letter-spacing:0.09em;
                    text-transform:uppercase;color:{st_cor};opacity:0.75;">Status CMN 4.994/2022</div>
        <div style="font-size:0.95rem;font-weight:700;color:{st_cor};">{st_txt}</div>
      </div>
      <div style="margin-left:auto;font-size:0.78rem;color:#6B7E96;text-align:right;">
        <div><strong style="color:{st_cor};font-size:1.1rem;">{v_cnt}/{total_segs}</strong> segmentos conformes</div>
        <div style="margin-top:2px;">Referência: {data_ref}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Patrimônio Social",  f"R$ {pl/1e9:.3f} Bi")
    k2.metric("Total Investido",    f"R$ {total_investido/1e9:.3f} Bi",
              f"{total_investido/pl:.1%} do PS", delta_color="off")
    k3.metric("Conformidade",       f"{pct_conf:.0f}%",
              f"{v_cnt} de {total_segs} segmentos", delta_color="off")
    k4.metric("🔴 Alertas Críticos", r_cnt,
              "Acima do limite" if r_cnt else "Nenhum",
              delta_color="inverse" if r_cnt else "off")
    k5.metric("🟡 Em Atenção", a_cnt,
              ">80% do limite" if a_cnt else "Nenhum",
              delta_color="inverse" if a_cnt else "off")

    # ══════════════════════════════════════════════════════════════════════════
    # LINHA 2: Alocação | Meta Atuarial | Benchmarks
    # ══════════════════════════════════════════════════════════════════════════
    col_aloc, col_meta, col_bm = st.columns([2, 2, 2], gap="medium")

    # ── Alocação dos Recursos ────────────────────────────────────────────────
    with col_aloc:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <div style="width:4px;height:22px;background:#8E44AD;border-radius:4px;"></div>
          <div>
            <div style="font-size:0.90rem;font-weight:700;color:#0F1E33;">Alocação dos Recursos</div>
            <div style="font-size:0.68rem;color:#8AAECB;">Distribuição por segmento</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        seg_vals = [(s['segmento'], s['valor']) for s in resumo if s['valor'] > 0]
        labels_a = [sv[0] for sv in seg_vals]
        values_a = [sv[1] for sv in seg_vals]
        cores_a  = ['#1B3A6B','#2472B5','#3498DB','#5DADE2','#85C1E9',
                    '#A8D8EA','#2ECC71','#E67E22','#E74C3C','#9B59B6']
        total_a  = sum(values_a)

        fig_pie = go.Figure(go.Pie(
            labels=labels_a, values=values_a, hole=0.55,
            textinfo='percent', textfont=dict(size=10),
            marker=dict(colors=cores_a[:len(labels_a)], line=dict(color='#FFF', width=2)),
            hovertemplate='<b>%{label}</b><br>R$ %{value:,.0f}<br>%{percent}<extra></extra>',
        ))
        fig_pie.update_layout(
            margin=dict(t=5, b=5, l=5, r=5), height=180,
            showlegend=False,
            annotations=[dict(text=f"R$ {total_a/1e9:.2f}Bi",
                              x=0.5, y=0.5, showarrow=False,
                              font=dict(size=12, color='#1B3A6B'))],
        )
        st.plotly_chart(fig_pie, width='stretch', config={'displayModeBar': False})

        # Tabela compacta de alocação com limite CMN 4.994/2022
        lim_dict = {s['segmento']: s for s in resumo}
        html_aloc = """<table style="width:100%;border-collapse:collapse;font-size:0.78rem;margin-top:2px;">
          <tr style="background:#F0F3F8;">
            <th style="padding:5px 8px;text-align:left;color:#52697E;font-weight:600;">Segmento</th>
            <th style="padding:5px 8px;text-align:right;color:#52697E;font-weight:600;">R$ (Bi)</th>
            <th style="padding:5px 8px;text-align:right;color:#52697E;font-weight:600;">% PS</th>
            <th style="padding:5px 8px;text-align:right;color:#52697E;font-weight:600;">Limite</th>
          </tr>"""
        for i, (seg, val) in enumerate(seg_vals):
            cor_seg = cores_a[i % len(cores_a)]
            pct_seg = val / pl * 100
            seg_info = lim_dict.get(seg, {})
            lim_pct = seg_info.get('limite_pct', 1.0) * 100
            status  = seg_info.get('status', 'verde')
            lim_cor = {'verde': '#27AE60', 'amarelo': '#E67E22', 'vermelho': '#E74C3C'}.get(status, '#27AE60')
            html_aloc += f"""
          <tr style="border-bottom:1px solid #F0F3F8;">
            <td style="padding:5px 8px;color:#1A2E46;font-weight:500;">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                           background:{cor_seg};margin-right:5px;"></span>{seg}</td>
            <td style="padding:5px 8px;text-align:right;color:#1A2E46;font-weight:600;">
              {val/1e9:.3f}</td>
            <td style="padding:5px 8px;text-align:right;color:#2472B5;font-weight:600;">
              {pct_seg:.1f}%</td>
            <td style="padding:5px 8px;text-align:right;color:{lim_cor};font-weight:700;">
              {lim_pct:.0f}%</td>
          </tr>"""
        html_aloc += "</table>"
        st.markdown(f'<div class="tabela-scroll">{html_aloc}</div>', unsafe_allow_html=True)

    # ── Meta Atuarial ────────────────────────────────────────────────────────
    with col_meta:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <div style="width:4px;height:22px;background:#E67E22;border-radius:4px;"></div>
          <div>
            <div style="font-size:0.90rem;font-weight:700;color:#0F1E33;">Meta Atuarial</div>
            <div style="font-size:0.68rem;color:#8AAECB;">INPC + spread — Pol. Invest. 2025-2029</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if df_cotas is not None:
            from analytics import calcular_meta_atuarial
            meta = calcular_meta_atuarial(
                df_cotas,
                b.get('inpc_mes', 0.0), b.get('inpc_ano', 0.0),
                b['cdi_mes'], b['cdi_ano'],
            )

            # Card INPC do período
            inpc_m = b.get('inpc_mes', 0.0)
            st.markdown(f"""
            <div style="background:#FFF8F0;border:1px solid #E67E2233;border-radius:10px;
                        padding:10px 14px;margin-bottom:10px;">
              <div style="font-size:0.68rem;color:#9A6B00;font-weight:700;
                          text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">
                Índice Base — INPC</div>
              <div style="display:flex;justify-content:space-between;align-items:flex-end;">
                <div>
                  <div style="font-size:0.62rem;color:#8AAECB;">No Mês</div>
                  <div style="font-size:1.2rem;font-weight:800;color:#E67E22;">{inpc_m:+.2f}%</div>
                </div>
                <div style="text-align:right;">
                  <div style="font-size:0.62rem;color:#8AAECB;">No Ano</div>
                  <div style="font-size:1.0rem;font-weight:700;color:#E67E22;">{b.get('inpc_ano',0.0):+.2f}%</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Status por plano com meta individual
            df_planos = meta['planos']
            if not df_planos.empty:
                for _, row in df_planos.iterrows():
                    dm   = row['Δ Mês (%)']
                    da   = row['Δ Ano (%)']
                    ok_m = dm >= 0
                    ok_a = da >= 0
                    tipo = row.get('Tipo', '')
                    # BD tem destaque urgente; CV é referência
                    if row['Plano'] == 'PL Alpha':
                        borda = '#C0392B' if not ok_m else '#27AE60'
                        bg    = '#FDE8E8' if not ok_m else '#E8F8F1'
                    else:
                        borda = '#E67E22' if not ok_m else '#27AE60'
                        bg    = '#FEF9E7' if not ok_m else '#E8F8F1'
                    ico_m = '🟢' if ok_m else '🔴'
                    ico_a = '🟢' if ok_a else '🔴'
                    meta_m = row['Meta Mês (%)']
                    meta_a = row['Meta Ano (%)']
                    st.markdown(f"""
                    <div style="background:{bg};border-left:3px solid {borda};border-radius:8px;
                                padding:8px 12px;margin-bottom:6px;">
                      <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <div style="font-size:0.80rem;font-weight:700;color:#1A2E46;">
                          {row['Plano']}</div>
                        <div style="font-size:0.62rem;color:#8AAECB;font-weight:600;">
                          {tipo} · {row.get('Meta Oficial','')}</div>
                      </div>
                      <div style="display:flex;gap:10px;font-size:0.74rem;flex-wrap:wrap;">
                        <div style="background:rgba(0,0,0,0.05);border-radius:4px;padding:2px 6px;">
                          <span style="color:#6B7E96;">Meta mês: </span>
                          <strong style="color:#9A6B00;">{meta_m:.2f}%</strong>
                        </div>
                        <div>
                          <span style="color:#6B7E96;">Mês: </span>
                          <strong style="color:#1A2E46;">{row['Retorno Mês (%)']:.2f}%</strong>
                          <span style="margin-left:3px;">{ico_m} {dm:+.2f}%</span>
                        </div>
                        <div>
                          <span style="color:#6B7E96;">Ano: </span>
                          <strong style="color:#1A2E46;">{row['Retorno Ano (%)']:.2f}%</strong>
                          <span style="margin-left:3px;">{ico_a} {da:+.2f}%</span>
                        </div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Dados de cotas insuficientes para calcular a meta.")
        else:
            st.info("Carregue o CSV de cotas para ver a meta atuarial.")

    # ── Benchmarks ───────────────────────────────────────────────────────────
    with col_bm:
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <div style="width:4px;height:22px;background:#2472B5;border-radius:4px;"></div>
          <div>
            <div style="font-size:0.90rem;font-weight:700;color:#0F1E33;">Benchmarks</div>
            <div style="font-size:0.68rem;color:#8AAECB;">Banco Central do Brasil — {data_ref}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        def _bm(label, mes_v, ano_v, cor):
            mc = '#27AE60' if mes_v >= 0 else '#E74C3C'
            ac = '#27AE60' if ano_v >= 0 else '#E74C3C'
            return f"""
            <div style="background:#FFF;border-radius:10px;padding:11px 14px;margin-bottom:9px;
                        border:1px solid #E2E9F2;border-left:3px solid {cor};
                        box-shadow:0 1px 5px rgba(0,0,0,0.04);">
              <div style="font-size:0.67rem;font-weight:700;letter-spacing:0.07em;
                          text-transform:uppercase;color:#6B7E96;margin-bottom:5px;">{label}</div>
              <div style="display:flex;justify-content:space-between;align-items:flex-end;">
                <div>
                  <div style="font-size:0.60rem;color:#8AAECB;">NO MÊS</div>
                  <div style="font-size:1.2rem;font-weight:800;color:{mc};
                              letter-spacing:-0.02em;">{mes_v:+.2f}%</div>
                </div>
                <div style="text-align:right;">
                  <div style="font-size:0.60rem;color:#8AAECB;">NO ANO</div>
                  <div style="font-size:1.2rem;font-weight:800;color:{ac};
                              letter-spacing:-0.02em;">{ano_v:+.2f}%</div>
                </div>
              </div>
            </div>"""

        st.markdown(
            _bm("CDI — Taxa DI",     b['cdi_mes'],            b['cdi_ano'],            '#2472B5') +
            _bm("IPCA — Inflação",   b['ipca_mes'],           b['ipca_ano'],           '#8E44AD') +
            _bm("Ibovespa — B3",     b.get('ibov_mes', 0.0),  b.get('ibov_ano', 0.0), '#E67E22'),
            unsafe_allow_html=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # LINHA 3: Rendimentos dos Planos (largura total)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)

    if df_cotas is not None:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <div style="width:4px;height:22px;background:#27AE60;border-radius:4px;"></div>
          <div>
            <div style="font-size:0.90rem;font-weight:700;color:#0F1E33;">Rendimentos dos Planos</div>
            <div style="font-size:0.68rem;color:#8AAECB;">Retorno realizado vs benchmarks</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        ultimo = ultima_posicao(df_cotas)
        planos_nomes = ['PL Alpha', 'PL Beta', 'PL Gama', 'Administrativo']
        linhas = []
        for nome in planos_nomes:
            rows = ultimo[ultimo['fundo'] == nome]
            if rows.empty:
                continue
            r = rows.iloc[0]
            linhas.append({
                'plano': nome,
                'mes':   r['Mês_pct'],
                'ano':   r['Ano_pct'],
                'dm':    r['Mês_pct'] - b['cdi_mes'],
                'da':    r['Ano_pct'] - b['cdi_ano'],
                'di':    r['Mês_pct'] - b['ipca_mes'],
            })

        def _seta(v): return '▲' if v >= 0 else '▼'
        def _bg(v):   return '#E8F8F1' if v >= 0 else '#FDE8E8'
        def _fc(v):   return '#1A7A40' if v >= 0 else '#A93226'

        html_rend = """
        <style>
        .rt2 { width:100%;border-collapse:collapse;font-size:0.82rem; }
        .rt2 th { background:#1B3A6B;color:#FFF;padding:8px 10px;
                  text-align:center;font-weight:600;font-size:0.74rem; }
        .rt2 th:first-child { text-align:left; }
        .rt2 td { padding:8px 10px;text-align:center;border-bottom:1px solid #EEF1F6; }
        .rt2 td:first-child { text-align:left;font-weight:700;color:#1B3A6B; }
        .rt2 tr:last-child td { border-bottom:none; }
        </style>
        <table class="rt2">
          <tr>
            <th>Plano</th><th>Mês</th><th>vs CDI</th><th>vs IPCA</th>
            <th>No Ano</th><th>vs CDI Ano</th>
          </tr>"""
        for l in linhas:
            html_rend += f"""
          <tr>
            <td>{l['plano']}</td>
            <td style="font-weight:600;color:#1A2E46;">{l['mes']:.2f}%</td>
            <td style="background:{_bg(l['dm'])};color:{_fc(l['dm'])};font-weight:600;">
              {_seta(l['dm'])} {abs(l['dm']):.2f}%</td>
            <td style="background:{_bg(l['di'])};color:{_fc(l['di'])};font-weight:600;">
              {_seta(l['di'])} {abs(l['di']):.2f}%</td>
            <td style="font-weight:600;color:#1A2E46;">{l['ano']:.2f}%</td>
            <td style="background:{_bg(l['da'])};color:{_fc(l['da'])};font-weight:600;">
              {_seta(l['da'])} {abs(l['da']):.2f}%</td>
          </tr>"""

        ibov_mes = b.get('ibov_mes', 0.0)
        ibov_ano = b.get('ibov_ano', 0.0)

        # Renda Variável — FIA Ações
        acoes_row = ultimo[ultimo['fundo'].isin(['FIA Ações', 'FIC FIA'])]
        if not acoes_row.empty and ibov_mes != 0.0:
            ac = acoes_row.iloc[0]
            di2m = ac['Mês_pct'] - ibov_mes
            di2a = ac['Ano_pct'] - ibov_ano
            html_rend += f"""
          <tr style="background:#F5F7FA;">
            <td colspan="6" style="padding:4px 10px;font-size:0.69rem;
                color:#8AAECB;font-weight:600;letter-spacing:0.04em;">RENDA VARIÁVEL</td>
          </tr>
          <tr>
            <td>IAJA Ações (FIA)</td>
            <td style="font-weight:600;color:#1A2E46;">{ac['Mês_pct']:.2f}%</td>
            <td colspan="2" style="background:{_bg(di2m)};color:{_fc(di2m)};font-weight:600;">
              {_seta(di2m)} {abs(di2m):.2f}% vs Ibov ({ibov_mes:.2f}%)</td>
            <td style="font-weight:600;color:#1A2E46;">{ac['Ano_pct']:.2f}%</td>
            <td style="background:{_bg(di2a)};color:{_fc(di2a)};font-weight:600;">
              {_seta(di2a)} {abs(di2a):.2f}% vs Ibov ({ibov_ano:.2f}%)</td>
          </tr>"""

        html_rend += "</table>"
        st.markdown(f'<div class="tabela-scroll">{html_rend}</div>', unsafe_allow_html=True)
    else:
        st.info("Carregue o CSV de cotas para visualizar os rendimentos dos planos.")

    # ── Briefing VIGIA (IA) ───────────────────────────────────────────────────
    if api_key:
        from ai_analysis import gerar_briefing_diario
        briefing_key = f'briefing_{data_ref}'

        if briefing_key not in st.session_state:
            comp_texto = '\n'.join(
                f"  {s['segmento']}: {s['pct_pl']:.1%} / limite {s['limite_pct']:.0%} ({s['status']})"
                for s in resumo
            )
            bm_texto = (
                f"  CDI: {b['cdi_mes']:.2f}% mês / {b['cdi_ano']:.2f}% ano\n"
                f"  IPCA: {b['ipca_mes']:.2f}% mês / {b['ipca_ano']:.2f}% ano\n"
                f"  INPC: {b.get('inpc_mes',0):.2f}% mês / {b.get('inpc_ano',0):.2f}% ano\n"
                f"  Ibovespa: {b.get('ibov_mes',0):.2f}% mês / {b.get('ibov_ano',0):.2f}% ano"
            )
            if df_cotas is not None:
                from analytics import calcular_meta_atuarial
                ult_b = ultima_posicao(df_cotas)
                meta_b = calcular_meta_atuarial(
                    df_cotas,
                    b.get('inpc_mes', 0.0), b.get('inpc_ano', 0.0),
                    b['cdi_mes'], b['cdi_ano'],
                )
                df_meta_b = meta_b['planos']
                linhas_plano = []
                for n in ['PL Alpha', 'PL Beta', 'PL Gama']:
                    row_c = ult_b[ult_b['fundo'] == n]
                    row_m = df_meta_b[df_meta_b['Plano'] == n] if not df_meta_b.empty else None
                    if row_c.empty:
                        continue
                    ret_m = row_c.iloc[0]['Mês_pct']
                    ret_a = row_c.iloc[0]['Ano_pct']
                    ret_d = row_c.iloc[0].get('Dia_pct', 0.0)
                    if row_m is not None and not row_m.empty:
                        meta_m = row_m.iloc[0]['Meta Mês (%)']
                        meta_a = row_m.iloc[0]['Meta Ano (%)']
                        delta_m = ret_m - meta_m
                        delta_a = ret_a - meta_a
                        vs_cdi_m  = ret_m - b['cdi_mes']
                        vs_ipca_m = ret_m - b['ipca_mes']
                        vs_cdi_a  = ret_a - b['cdi_ano']
                        linhas_plano.append(
                            f"  {n}: dia {ret_d:+.2f}% | mês {ret_m:.2f}% (meta {meta_m:.2f}%, Δ {delta_m:+.2f}%;"
                            f" vs CDI {vs_cdi_m:+.2f}%, vs IPCA {vs_ipca_m:+.2f}%) | "
                            f"ano {ret_a:.2f}% (meta {meta_a:.2f}%, Δ {delta_a:+.2f}%; vs CDI {vs_cdi_a:+.2f}%)"
                        )
                    else:
                        linhas_plano.append(f"  {n}: dia {ret_d:+.2f}% | mês {ret_m:.2f}% | ano {ret_a:.2f}%")
                planos_txt = '\n'.join(linhas_plano) if linhas_plano else 'Dados de cotas não disponíveis'
            else:
                planos_txt = 'Dados de cotas não disponíveis'
            ctx = {
                'data_ref':         data_ref,
                'pl':               pl,
                'compliance_texto': comp_texto,
                'benchmarks_texto': bm_texto,
                'planos_texto':     planos_txt,
                'meta_texto': (
                    f"Alpha (BD): INPC+5,24%a.a. | Beta/Gama (CV): INPC+4,50%a.a. | "
                    f"INPC mês: {b.get('inpc_mes',0):.2f}% | INPC ano: {b.get('inpc_ano',0):.2f}%"
                ),
            }
            with st.spinner('VIGIA preparando o briefing do dia...'):
                try:
                    st.session_state[briefing_key] = gerar_briefing_diario(ctx, api_key)
                except Exception as e:
                    st.session_state[briefing_key] = f'Não foi possível gerar o briefing: {e}'

        briefing_txt = st.session_state.get(briefing_key, '')
        if briefing_txt:
            def _briefing_linha(ln: str) -> str:
                raw = ln.rstrip()
                if not raw:
                    return ''
                indent = len(raw) - len(raw.lstrip())
                if raw.strip().startswith('**') and raw.strip().endswith('**'):
                    return (f'<div style="font-size:0.80rem;font-weight:700;color:#1B3A6B;'
                            f'margin-top:10px;margin-bottom:4px;">{raw.strip().strip("*")}</div>')
                if indent >= 2:
                    return (f'<div style="margin-left:18px;margin-bottom:3px;font-size:0.80rem;'
                            f'color:#3A5070;">{raw.strip()}</div>')
                return f'<div style="margin-bottom:5px;">{raw.strip()}</div>'

            linhas_html = ''.join(_briefing_linha(ln) for ln in briefing_txt.split('\n'))
            col_b, col_btn = st.columns([11, 1])
            with col_b:
                st.markdown(f"""
                <div style="background:linear-gradient(90deg,#1B3A6B08,#2472B505);
                            border:1px solid #2472B52A;border-left:4px solid #2472B5;
                            border-radius:10px;padding:13px 18px;margin:18px 0 8px 0;">
                  <div style="font-size:0.66rem;font-weight:700;letter-spacing:0.09em;
                              text-transform:uppercase;color:#2472B5;margin-bottom:9px;">
                    🤖 Briefing VIGIA · {data_ref}</div>
                  <div style="font-size:0.83rem;color:#1A2E46;line-height:1.75;">
                    {linhas_html}</div>
                </div>
                """, unsafe_allow_html=True)
            with col_btn:
                st.markdown("<div style='margin-top:26px;'></div>", unsafe_allow_html=True)
                if st.button('↻', help='Atualizar briefing', key='btn_refresh_briefing'):
                    if briefing_key in st.session_state:
                        del st.session_state[briefing_key]
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Performance':
    st.markdown('<div class="secao-titulo">📉 Performance dos Fundos</div>', unsafe_allow_html=True)

    if df_cotas is None:
        st.info("Adicione o CSV 'Mapa de Evolução da Cotas' na pasta `data/cotas/`.")
        st.stop()

    ultimo = ultima_posicao(df_cotas)
    df_periodo = df_cotas[df_cotas['Data'] >= f'{ano_ref}-{mes_ref:02d}-01']
    b = benchmarks

    planos_kpi = ['PL Alpha', 'PL Beta', 'PL Gama']
    kpi_cols = st.columns(3)
    for i, plano in enumerate(planos_kpi):
        row = ultimo[ultimo['fundo'] == plano]
        if not row.empty:
            r = row.iloc[0]
            delta = r['Mês_pct'] - b['cdi_mes']
            kpi_cols[i].metric(plano,
                               f"{r['Mês_pct']:.2f}% no mês",
                               f"{delta:+.2f}% vs CDI")

    st.markdown("---")
    tab_ev, tab_rank, tab_heat, tab_risco, tab_attr, tab_conc = st.tabs([
        "📈 Evolução", "🏆 Ranking", "🌡️ Heatmap Diário",
        "⚡ Risco/Sharpe", "🔬 Atribuição", "🏢 Gestores",
    ])

    with tab_ev:
        st.markdown(f"**Rentabilidade Acumulada (base 100)**")
        fig_l = px.line(df_periodo.sort_values('Data'), x='Data', y='cota_base100',
                        color='fundo', markers=False,
                        color_discrete_sequence=px.colors.qualitative.Set2)
        fig_l.add_hline(y=100, line_dash='dash', line_color='gray', opacity=0.4)
        fig_l.update_layout(yaxis_title='Índice (Base 100)', xaxis_title='',
                            hovermode='x unified', margin=dict(t=20, b=10),
                            legend=dict(orientation='h', y=1.05))
        st.plotly_chart(fig_l, width='stretch')

    with tab_rank:
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("**Ranking — Mês**")
            rank = ultimo[['fundo', 'Mês_pct']].sort_values('Mês_pct', ascending=True)
            cores = ['#E74C3C' if v < b['cdi_mes'] else '#27AE60' for v in rank['Mês_pct']]
            fig_r = go.Figure(go.Bar(
                x=rank['Mês_pct'], y=rank['fundo'], orientation='h',
                marker_color=cores,
                text=[f"{v:.2f}%" for v in rank['Mês_pct']], textposition='outside',
            ))
            fig_r.add_vline(x=b['cdi_mes'], line_dash='dash', line_color='#2E86C1',
                            annotation_text=f"CDI {b['cdi_mes']:.2f}%")
            fig_r.update_layout(margin=dict(t=10, b=10, r=60), height=420, showlegend=False)
            st.plotly_chart(fig_r, width='stretch')

        with col_r2:
            st.markdown("**Retorno por Horizonte**")
            horiz = ultimo[['fundo', 'Mês_pct', 'Ano_pct', 'Total_pct']].sort_values('Mês_pct', ascending=False)
            fig_h = go.Figure()
            fig_h.add_bar(name='Mês',    x=horiz['fundo'], y=horiz['Mês_pct'],   marker_color='#2E86C1')
            fig_h.add_bar(name='No Ano', x=horiz['fundo'], y=horiz['Ano_pct'],   marker_color='#1ABC9C')
            fig_h.add_bar(name='Total',  x=horiz['fundo'], y=horiz['Total_pct'], marker_color='#8E44AD')
            fig_h.update_layout(barmode='group', xaxis_tickangle=-30, height=420,
                                margin=dict(t=10, b=10), legend=dict(orientation='h', y=1.05))
            st.plotly_chart(fig_h, width='stretch')

    with tab_heat:
        st.markdown("**Retornos Diários (%)**")
        piv = df_periodo.pivot_table(index='fundo', columns='Data',
                                     values='Dia_pct', aggfunc='first')
        piv.columns = [d.strftime('%d/%m') for d in piv.columns]
        fig_ht = go.Figure(go.Heatmap(
            z=piv.values, x=list(piv.columns), y=list(piv.index),
            colorscale=[[0, '#C0392B'], [0.45, '#FADBD8'],
                        [0.5, '#FFFFFF'], [0.55, '#D5F5E3'], [1, '#1E8449']],
            zmid=0,
            text=[[f"{v:.2f}%" for v in row] for row in piv.values],
            texttemplate="%{text}", textfont={"size": 8},
        ))
        fig_ht.update_layout(height=440, margin=dict(t=10, b=10),
                             xaxis=dict(tickangle=-45))
        st.plotly_chart(fig_ht, width='stretch')

    with tab_risco:
        st.markdown("**Risco Ajustado ao Retorno**")
        df_rr = calcular_risco_retorno(df_cotas, benchmarks['cdi_ano'])
        st.caption("Sharpe > 1: excelente | Sharpe > 0.5: bom | Sharpe < 0: abaixo do CDI")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fig_sh = go.Figure(go.Bar(
                x=df_rr['Sharpe'], y=df_rr['Fundo'], orientation='h',
                marker_color=['#27AE60' if v > 1 else ('#F39C12' if v > 0 else '#E74C3C')
                              for v in df_rr['Sharpe']],
                text=[f"{v:.2f}" for v in df_rr['Sharpe']], textposition='outside',
            ))
            fig_sh.update_layout(title='Índice Sharpe', height=420,
                                 margin=dict(t=40, b=10, r=60), showlegend=False)
            st.plotly_chart(fig_sh, width='stretch')

        with col_s2:
            fig_vv = go.Figure()
            fig_vv.add_scatter(
                x=df_rr['Volatilidade Anual (%)'], y=df_rr['Retorno Anualizado (%)'],
                mode='markers+text', text=df_rr['Fundo'], textposition='top center',
                marker=dict(size=12, color=AZUL), name='Fundos',
            )
            fig_vv.add_hline(y=benchmarks['cdi_ano'], line_dash='dash', line_color='#2E86C1',
                             annotation_text=f"CDI ano {benchmarks['cdi_ano']:.2f}%")
            fig_vv.update_layout(title='Risco × Retorno',
                                 xaxis_title='Volatilidade Anualizada (%)',
                                 yaxis_title='Retorno Anualizado (%)',
                                 height=420, margin=dict(t=40, b=10))
            st.plotly_chart(fig_vv, width='stretch')

        st.dataframe(df_rr, width='stretch', hide_index=True)

    with tab_attr:
        st.markdown("**Atribuição de Performance**")
        attr = atribuicao_performance(carteira, pl, benchmarks, df_cotas)

        st.markdown(f"Retorno estimado da carteira no mês: **{attr['retorno_estimado_mes']:.3f}%** "
                    f"| CDI mês: **{attr['cdi_mes']:.2f}%**")

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.markdown("**Por Segmento**")
            df_s = attr['por_segmento']
            fig_as = go.Figure(go.Bar(
                x=df_s['Contribuição (pp)'], y=df_s['Segmento'], orientation='h',
                marker_color=['#27AE60' if v > 0 else '#E74C3C' for v in df_s['Contribuição (pp)']],
                text=[f"{v:.4f} pp" for v in df_s['Contribuição (pp)']],
                textposition='outside',
            ))
            fig_as.update_layout(height=320, margin=dict(t=10, b=10, r=80), showlegend=False,
                                 xaxis_title='Contribuição (p.p.)')
            st.plotly_chart(fig_as, width='stretch')
            st.dataframe(df_s, width='stretch', hide_index=True)

        with col_a2:
            st.markdown("**Por Gestor**")
            df_g = attr['por_gestor']
            fig_ag = px.pie(df_g, values='Peso na Carteira (%)', names='Gestor',
                            hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_ag.update_traces(textposition='inside', textinfo='percent+label')
            fig_ag.update_layout(showlegend=False, margin=dict(t=10, b=10), height=320)
            st.plotly_chart(fig_ag, width='stretch')
            st.dataframe(df_g, width='stretch', hide_index=True)

        if not attr['planos'].empty:
            st.markdown("**Desempenho dos Planos vs Benchmarks**")
            st.dataframe(attr['planos'], width='stretch', hide_index=True)

    with tab_conc:
        st.markdown("**Concentração por Gestor**")
        df_conc = concentracao_gestores(carteira)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            fig_c = px.pie(df_conc, values='% Carteira', names='Gestor',
                           hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
            fig_c.update_traces(textposition='inside', textinfo='percent+label')
            fig_c.update_layout(showlegend=False, margin=dict(t=10, b=10), height=360)
            st.plotly_chart(fig_c, width='stretch')
        with col_c2:
            df_disp = df_conc.copy()
            df_disp['Valor (R$)'] = df_disp['Valor (R$)'].apply(lambda x: f"R$ {x/1e6:.1f} MM")
            df_disp['% Carteira'] = df_disp['% Carteira'].apply(lambda x: f"{x:.2f}%")
            st.dataframe(df_disp[['Gestor', 'Nº Fundos', '% Carteira', 'Valor (R$)', 'Concentração']],
                         width='stretch', hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: COMPARATIVO DE MERCADO — CVM Dados Abertos
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Comparativo':
    st.markdown('<div class="secao-titulo">🏆 Comparativo de Mercado — CVM Dados Abertos</div>', unsafe_allow_html=True)

    from cvm_api import calcular_comparativo, resumo_por_classe

    col_ano, col_mes, col_btn = st.columns([1, 1, 2])
    ano_cvm  = col_ano.number_input("Ano", value=ano_ref, min_value=2020, max_value=ano_ref, step=1)
    mes_cvm  = col_mes.number_input("Mês", value=mes_ref, min_value=1, max_value=12, step=1)
    carregar = col_btn.button("🔄 Carregar dados CVM", type="primary", use_container_width=True)

    if 'cvm_comp' not in st.session_state:
        st.session_state.cvm_comp   = None
        st.session_state.cvm_params = None

    if carregar or st.session_state.cvm_comp is None:
        with st.spinner(f"Baixando dados CVM {mes_cvm:02d}/{ano_cvm}... (pode levar ~20s na primeira vez)"):
            try:
                df_comp = calcular_comparativo(int(ano_cvm), int(mes_cvm), pl_minimo=5_000_000)
                st.session_state.cvm_comp   = df_comp
                st.session_state.cvm_params = (int(ano_cvm), int(mes_cvm))
            except Exception as e:
                st.error(f"Erro ao baixar dados CVM: {e}")
                st.stop()

    df_comp = st.session_state.cvm_comp
    if df_comp is None or df_comp.empty:
        st.info("Clique em 'Carregar dados CVM' para iniciar.")
        st.stop()

    df_resumo = resumo_por_classe(df_comp)

    # Mapa: fundo IAJA → categoria CVM
    MAPA_IAJA = {
        'PL Alpha':      ('Renda Fixa', 'PL Alpha (BD)'),
        'PL Beta':       ('Renda Fixa', 'PL Beta (CV)'),
        'PL Gama':       ('Renda Fixa', 'PL Gama (CV)'),
        'FIA Ações':     ('Ações',      'IAJA Ações (FIA)'),
    }

    # ── Cards de comparação por fundo ─────────────────────────────────────────
    if df_cotas is not None:
        ult = ultima_posicao(df_cotas)
        cards = []
        for fundo, (classe, label) in MAPA_IAJA.items():
            row_f = ult[ult['fundo'] == fundo]
            row_r = df_resumo[df_resumo['Classe'] == classe]
            if row_f.empty or row_r.empty:
                continue
            ret     = row_f.iloc[0]['Mês_pct']
            mediana = float(row_r.iloc[0]['mediana'])
            p25     = float(row_r.iloc[0]['p25'])
            p75     = float(row_r.iloc[0]['p75'])
            qtd     = int(row_r.iloc[0]['qtd_fundos'])
            d_cls   = df_comp[df_comp['Classe'] == classe]['retorno_mes']
            percentil = float((d_cls < ret).mean() * 100)
            cards.append(dict(label=label, classe=classe, ret=ret,
                              mediana=mediana, p25=p25, p75=p75,
                              delta=ret - mediana, percentil=percentil, qtd=qtd))

        cols_card = st.columns(len(cards))
        for i, c in enumerate(cards):
            cor   = '#27AE60' if c['delta'] >= 0 else '#E74C3C'
            seta  = '▲' if c['delta'] >= 0 else '▼'
            emoji = '🟢' if c['delta'] >= 0 else '🔴'
            with cols_card[i]:
                st.markdown(f"""
                <div style="background:#fff;border:1px solid #E0E6EF;border-top:4px solid {cor};
                            border-radius:10px;padding:14px 16px;margin-bottom:8px;">
                  <div style="font-size:0.70rem;font-weight:700;color:#8AAECB;
                              text-transform:uppercase;letter-spacing:0.07em;margin-bottom:4px;">
                    {c['label']}</div>
                  <div style="font-size:0.65rem;color:#B0BEC5;margin-bottom:10px;">
                    vs {c['classe']} · {c['qtd']:,} fundos</div>
                  <div style="font-size:1.70rem;font-weight:800;color:#0F1E33;line-height:1;">
                    {c['ret']:+.2f}%</div>
                  <div style="font-size:0.72rem;color:#5A6A7A;margin-top:6px;">
                    Mediana mercado: <strong>{c['mediana']:+.2f}%</strong></div>
                  <div style="font-size:0.80rem;font-weight:700;color:{cor};margin-top:4px;">
                    {emoji} {seta} {abs(c['delta']):.2f} pp &nbsp;·&nbsp; P{c['percentil']:.0f}</div>
                </div>
                """, unsafe_allow_html=True)

        # ── Gráfico: IAJA vs distribuição de mercado ──────────────────────────
        st.markdown("#### IAJA vs Mercado — Retorno Mês")
        st.caption(f"Referência: {mes_cvm:02d}/{ano_cvm} · Zona cinza = P25 a P75 (50% central dos fundos de mercado)")

        fig = go.Figure()
        labels  = [c['label']   for c in cards]
        ret_v   = [c['ret']     for c in cards]
        med_v   = [c['mediana'] for c in cards]
        p25_v   = [c['p25']     for c in cards]
        p75_v   = [c['p75']     for c in cards]

        # Zona P25–P75 do mercado (banda cinza): barra invisível até P25 + barra cinza até P75
        fig.add_trace(go.Bar(
            name='P25', y=labels, x=p25_v, orientation='h',
            marker_color='rgba(0,0,0,0)', showlegend=False,
            hoverinfo='skip',
        ))
        fig.add_trace(go.Bar(
            name='Intervalo mercado (P25–P75)', y=labels,
            x=[p75 - p25 for p75, p25 in zip(p75_v, p25_v)],
            base=p25_v, orientation='h',
            marker_color='rgba(180,195,215,0.45)',
            hovertemplate='P25: %{base:.2f}%<br>P75: %{x:.2f}%<extra>Zona central mercado</extra>',
        ))

        # Mediana do mercado
        fig.add_trace(go.Scatter(
            name='Mediana mercado', y=labels, x=med_v, mode='markers',
            marker=dict(symbol='line-ns', size=18, color='#5A6A7A',
                        line=dict(width=2, color='#5A6A7A')),
            hovertemplate='Mediana: %{x:.2f}%<extra></extra>',
        ))

        # Retorno IAJA
        cores_iaja = ['#1B3A6B', '#2472B5', '#3498DB', '#E67E22']
        for i, c in enumerate(cards):
            fig.add_trace(go.Scatter(
                name=c['label'], y=[c['label']], x=[c['ret']],
                mode='markers+text',
                text=[f"  {c['ret']:+.2f}%"],
                textposition='middle right',
                textfont=dict(size=11, color='#0F1E33', family='Inter'),
                marker=dict(symbol='diamond', size=16,
                            color=cores_iaja[i % len(cores_iaja)],
                            line=dict(width=2, color='white')),
                hovertemplate=f"{c['label']}: %{{x:.2f}}%<extra></extra>",
            ))

        # Linha vertical em 0%
        fig.add_vline(x=0, line_width=1, line_dash='dot', line_color='#BDC3C7')

        fig.update_layout(
            barmode='overlay',
            xaxis_title='Retorno no Mês (%)',
            height=max(200, len(cards) * 90),
            margin=dict(t=10, b=30, l=10, r=80),
            legend=dict(orientation='h', y=-0.18, x=0),
            plot_bgcolor='#F8FAFD',
            paper_bgcolor='#F8FAFD',
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("Carregue o CSV de cotas para ver o comparativo com os fundos IAJA.")

    # ── Top fundos por categoria ──────────────────────────────────────────────
    st.markdown("---")
    classes_disp = sorted(df_resumo['Classe'].tolist())
    cls_top = st.selectbox("Ver top 10 fundos da categoria", classes_disp)
    row_r   = df_resumo[df_resumo['Classe'] == cls_top].iloc[0]
    st.caption(
        f"{cls_top} · {int(row_r['qtd_fundos']):,} fundos · "
        f"Mediana: {row_r['mediana']:+.2f}% · P25: {row_r['p25']:+.2f}% · P75: {row_r['p75']:+.2f}%"
    )
    df_top = (
        df_comp[df_comp['Classe'] == cls_top]
        .nlargest(10, 'retorno_mes')[['Denominacao_Social', 'retorno_mes', 'retorno_ano']]
        .rename(columns={
            'Denominacao_Social': 'Fundo',
            'retorno_mes':        'Retorno Mês (%)',
            'retorno_ano':        'Retorno Ano (%)',
        })
    )
    df_top['Retorno Mês (%)'] = df_top['Retorno Mês (%)'].apply(lambda x: f"{x:+.2f}%")
    df_top['Retorno Ano (%)'] = df_top['Retorno Ano (%)'].apply(
        lambda x: f"{x:+.2f}%" if pd.notna(x) else "—"
    )
    st.dataframe(df_top, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: RISCO AVANÇADO
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Risco Avançado':
    st.markdown('<div class="secao-titulo">📈 Risco Avançado</div>', unsafe_allow_html=True)

    if df_cotas is None:
        st.info("Adicione o CSV de Cotas para calcular métricas de risco.")
        st.stop()

    tab_var, tab_dd, tab_corr, tab_stress = st.tabs([
        "📉 VaR & CVaR", "📊 Drawdown", "🔗 Correlação", "⚡ Stress Test",
    ])

    with tab_var:
        st.markdown("**Value at Risk (VaR) e Expected Shortfall por Fundo**")

        col_niv, _ = st.columns([1, 3])
        nivel_conf = col_niv.selectbox("Nível de confiança", [0.90, 0.95, 0.99],
                                       index=1, format_func=lambda x: f"{x:.0%}")

        df_var = calcular_var(df_cotas, nivel=nivel_conf)
        st.caption(
            f"VaR {nivel_conf:.0%}: perda máxima esperada em 1 dia com {nivel_conf:.0%} de confiança. "
            f"CVaR (Expected Shortfall): média das perdas além do VaR."
        )

        # Gráfico de barras VaR
        fig_var = go.Figure()
        fig_var.add_bar(name='VaR Histórico', x=df_var['Fundo'],
                        y=df_var['VaR Histórico (%)'].abs(),
                        marker_color='#E74C3C')
        fig_var.add_bar(name='CVaR / ES', x=df_var['Fundo'],
                        y=df_var['CVaR / ES (%)'].abs(),
                        marker_color='#C0392B')
        fig_var.update_layout(barmode='group', yaxis_title='Perda (%) — maior = pior',
                              xaxis_tickangle=-30,
                              legend=dict(orientation='h', y=1.05),
                              margin=dict(t=20, b=10), height=380)
        st.plotly_chart(fig_var, width='stretch')
        st.dataframe(df_var, width='stretch', hide_index=True)

    with tab_dd:
        st.markdown("**Drawdown — Queda a partir do pico histórico**")
        df_dd = calcular_drawdown(df_cotas)

        # Gráfico de drawdown por fundo ao longo do tempo
        fig_dd_line = go.Figure()
        for fundo in df_cotas['fundo'].unique():
            df_f = df_cotas[df_cotas['fundo'] == fundo].sort_values('Data')
            cotas = df_f['cota_base100'].values
            peak = np.maximum.accumulate(cotas)
            dd_series = (cotas - peak) / peak * 100
            fig_dd_line.add_scatter(x=df_f['Data'], y=dd_series,
                                    mode='lines', name=fundo)

        fig_dd_line.add_hline(y=0, line_color='gray', line_dash='dash', opacity=0.4)
        fig_dd_line.update_layout(
            yaxis_title='Drawdown (%)', xaxis_title='',
            hovermode='x unified', height=380,
            legend=dict(orientation='h', y=1.05),
            margin=dict(t=20, b=10),
        )
        st.plotly_chart(fig_dd_line, width='stretch')
        st.dataframe(df_dd, width='stretch', hide_index=True)

    with tab_corr:
        st.markdown("**Matriz de Correlação dos Retornos Diários**")
        corr = calcular_correlacao(df_cotas)

        fig_corr = go.Figure(go.Heatmap(
            z=corr.values,
            x=list(corr.columns),
            y=list(corr.index),
            colorscale=[[0, '#E74C3C'], [0.5, '#FFFFFF'], [1, '#27AE60']],
            zmin=-1, zmax=1, zmid=0,
            text=[[f"{v:.2f}" for v in row] for row in corr.values],
            texttemplate="%{text}", textfont={"size": 9},
        ))
        fig_corr.update_layout(height=480, margin=dict(t=20, b=10),
                               xaxis=dict(tickangle=-30))
        st.plotly_chart(fig_corr, width='stretch')

        st.caption(
            "Correlação próxima de 1 = movimentos juntos (baixa diversificação). "
            "Próxima de 0 ou negativa = boa diversificação."
        )

    with tab_stress:
        st.markdown("**Stress Test — Impacto de Cenários no Patrimônio**")
        df_st = stress_test(carteira, pl)

        fig_st = go.Figure(go.Bar(
            x=df_st['Cenário'],
            y=df_st['Impacto (R$ MM)'],
            marker_color=['#27AE60' if v > 0 else ('#F39C12' if v > -pl * 0.05 / 1e6 else '#E74C3C')
                          for v in df_st['Impacto (R$ MM)']],
            text=[f"R$ {v:.0f} MM ({r:.1f}%)"
                  for v, r in zip(df_st['Impacto (R$ MM)'], df_st['Variação (%)'])],
            textposition='outside',
        ))
        fig_st.add_hline(y=0, line_color='gray', line_dash='dash', opacity=0.5)
        fig_st.update_layout(yaxis_title='Impacto (R$ MM)', xaxis_tickangle=-15,
                             margin=dict(t=20, b=60), height=420, showlegend=False)
        st.plotly_chart(fig_st, width='stretch')

        st.dataframe(df_st, width='stretch', hide_index=True)
        st.caption(
            "Os choques aplicam retornos anuais por segmento. "
            "Cenários negativos podem indicar perdas permanentes se o portfólio não se recuperar."
        )


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: PROJEÇÃO DE PATRIMÔNIO
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Projeção':
    st.markdown('<div class="secao-titulo">🔮 Projeção de Patrimônio</div>', unsafe_allow_html=True)

    tab_mc, tab_cen = st.tabs(["🎲 Monte Carlo", "📊 Cenários Determinísticos"])

    with tab_mc:
        st.markdown("**Simulação Monte Carlo — Trajetórias Possíveis do Patrimônio**")

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        anos_mc = col_p1.slider("Horizonte (anos)", 1, 20, 10)
        ret_mc  = col_p2.number_input("Retorno anual médio (%)", value=13.0,
                                      min_value=1.0, max_value=30.0, step=0.5) / 100
        vol_mc  = col_p3.number_input("Volatilidade anual (%)", value=4.0,
                                      min_value=0.5, max_value=20.0, step=0.5) / 100
        n_sim   = col_p4.selectbox("Nº de simulações", [200, 500, 1000], index=1)
        meta_pl = st.number_input("Meta de patrimônio (R$ Bi, 0 = ignorar)",
                                  value=3.0, min_value=0.0, step=0.5) * 1e9

        if st.button("▶️ Executar Monte Carlo", type="primary"):
            with st.spinner("Simulando..."):
                datas_mc, perc, traj = monte_carlo_patrimonio(
                    pl, ret_mc, vol_mc, anos_mc, n_sim, seed=42,
                )

                fig_mc = go.Figure()

                # Faixa de confiança
                x_dates = [str(d.date()) for d in datas_mc]
                fig_mc.add_scatter(
                    x=x_dates + x_dates[::-1],
                    y=list(perc['p95'] / 1e9) + list(perc['p5'][::-1] / 1e9),
                    fill='toself', fillcolor='rgba(43,130,229,0.10)',
                    line=dict(color='rgba(255,255,255,0)'),
                    name='Intervalo 90%', showlegend=True,
                )
                fig_mc.add_scatter(
                    x=x_dates + x_dates[::-1],
                    y=list(perc['p75'] / 1e9) + list(perc['p25'][::-1] / 1e9),
                    fill='toself', fillcolor='rgba(43,130,229,0.18)',
                    line=dict(color='rgba(255,255,255,0)'),
                    name='Intervalo 50%', showlegend=True,
                )
                fig_mc.add_scatter(x=x_dates, y=perc['p50'] / 1e9,
                                   line=dict(color=AZUL, width=2.5),
                                   name='Mediana (P50)')
                fig_mc.add_scatter(x=x_dates, y=perc['p95'] / 1e9,
                                   line=dict(color='#27AE60', width=1, dash='dot'),
                                   name='P95 (otimista)')
                fig_mc.add_scatter(x=x_dates, y=perc['p5'] / 1e9,
                                   line=dict(color='#E74C3C', width=1, dash='dot'),
                                   name='P5 (pessimista)')

                if meta_pl > 0:
                    fig_mc.add_hline(y=meta_pl / 1e9, line_color='orange',
                                     line_dash='dash', line_width=1.5,
                                     annotation_text=f"Meta R$ {meta_pl/1e9:.1f} Bi")

                fig_mc.update_layout(
                    yaxis_title='Patrimônio (R$ Bi)',
                    xaxis_title='', hovermode='x unified',
                    legend=dict(orientation='h', y=1.05),
                    margin=dict(t=20, b=10), height=480,
                )
                st.plotly_chart(fig_mc, width='stretch')

                # Tabela resumo
                meta_arg = meta_pl if meta_pl > 0 else None
                df_resumo = resumo_monte_carlo(pl, traj, datas_mc, meta_arg)
                st.markdown("**Resumo por Horizonte**")
                st.dataframe(df_resumo, width='stretch', hide_index=True)

    with tab_cen:
        st.markdown("**Projeção Determinística por Cenário de Retorno**")

        col_c1, col_c2 = st.columns([1, 3])
        anos_cen = col_c1.slider("Horizonte (anos)", 1, 20, 10, key='anos_cen')

        datas_cen, cenarios_res = projetar_cenarios(pl, anos_cen)
        x_dates_cen = [str(d.date()) for d in datas_cen]

        fig_cen = go.Figure()
        for nome, dados in cenarios_res.items():
            pl_final = dados['valores'][-1]
            fig_cen.add_scatter(
                x=x_dates_cen, y=[v / 1e9 for v in dados['valores']],
                mode='lines', name=nome, line=dict(color=dados['cor'], width=2),
            )

        fig_cen.add_scatter(x=[x_dates_cen[0]], y=[pl / 1e9],
                            mode='markers', marker=dict(size=10, color=AZUL),
                            name='Posição Atual', showlegend=True)
        fig_cen.update_layout(
            yaxis_title='Patrimônio (R$ Bi)', xaxis_title='',
            hovermode='x unified', legend=dict(orientation='h', y=1.05),
            margin=dict(t=20, b=10), height=460,
        )
        st.plotly_chart(fig_cen, width='stretch')

        # Tabela final
        tabela_cen = []
        for nome, dados in cenarios_res.items():
            crescimento = (dados['valores'][-1] / pl - 1) * 100
            tabela_cen.append({
                'Cenário': nome,
                'PL Inicial (R$ Bi)': round(pl / 1e9, 3),
                f'PL em {anos_cen} anos (R$ Bi)': round(dados['valores'][-1] / 1e9, 3),
                'Crescimento Total (%)': round(crescimento, 1),
                'Retorno Anual': f"{dados['retorno']:.0%}",
            })
        st.dataframe(pd.DataFrame(tabela_cen), width='stretch', hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: SIMULADOR
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Simulador':
    st.markdown('<div class="secao-titulo">⚖️ Simulador de Realocação</div>', unsafe_allow_html=True)
    st.caption("Ajuste as alocações por segmento e veja o impacto no compliance e no retorno esperado.")

    atuais = {s['segmento']: s['pct_pl'] for s in resumo}
    limites = {s['segmento']: s['limite_pct'] for s in resumo}

    st.markdown("### Alocação Proposta")
    col_slid = st.columns(2)
    novas = {}

    for i, (seg, pct_atual) in enumerate(atuais.items()):
        col = col_slid[i % 2]
        lim = limites[seg]
        nova = col.slider(
            f"**{seg}** (limite: {lim:.0%})",
            min_value=0.0, max_value=float(lim),
            value=float(round(pct_atual, 4)), step=0.005, format="%.1f%%",
            key=f"slider_{seg}",
        )
        novas[seg] = nova

    total_alocado = sum(novas.values())
    st.markdown(f"**Total alocado: {total_alocado:.1%}** {'⚠️ Excede 100%!' if total_alocado > 1 else '✅'}")

    st.markdown("---")
    resultado = simular_realocacao(pl, novas)

    TAXAS = {
        'Renda Fixa': 0.105,
        'Renda Variável': 0.130,
        'Investimentos Estruturados': 0.115,
        'Investimentos no Exterior': 0.120,
        'Imóveis': 0.090,
        'Operações com Participantes': 0.155,
    }

    retorno_atual = sum(atuais[s] * TAXAS.get(s, 0.10) for s in atuais) * 100
    retorno_prop  = resultado['retorno_esperado_ano']
    delta_ret     = retorno_prop - retorno_atual

    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Retorno Atual (est.)",    f"{retorno_atual:.2f}% a.a.")
    col_r2.metric("Retorno Proposto (est.)", f"{retorno_prop:.2f}% a.a.",
                  delta=f"{delta_ret:+.2f}%")
    col_r3.metric("Impacto no PS",
                  f"R$ {pl * (retorno_prop - retorno_atual) / 100:+,.0f}",
                  delta=f"{delta_ret:+.2f}% a.a.")

    st.markdown("---")
    st.markdown("### Relatório de Rendimento por Segmento")

    rows = []
    for seg in atuais:
        taxa = TAXAS.get(seg, 0.10)
        al_at = atuais[seg]
        al_pr = novas.get(seg, 0.0)
        rows.append({
            'Segmento':           seg,
            'Alocação Atual':     f"{al_at:.1%}",
            'Alocação Proposta':  f"{al_pr:.1%}",
            'Δ Alocação':         f"{al_pr - al_at:+.1%}",
            'Taxa Est. a.a.':     f"{taxa:.1%}",
            'Contribuição Atual': f"{al_at * taxa * 100:.3f}%",
            'Contribuição Nova':  f"{al_pr * taxa * 100:.3f}%",
            'Δ Contribuição':     f"{(al_pr - al_at) * taxa * 100:+.3f}%",
        })
    df_rel = pd.DataFrame(rows).set_index('Segmento')

    def _colorir(val):
        if isinstance(val, str) and val.startswith('+'):
            return 'color: #1A7A45; font-weight:600'
        if isinstance(val, str) and val.startswith('-'):
            return 'color: #C0392B; font-weight:600'
        return ''

    st.dataframe(
        df_rel.style.map(_colorir, subset=['Δ Alocação', 'Δ Contribuição']),
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown("### Projeção de Crescimento do Patrimônio")

    anos = [1, 2, 3, 5, 10]
    proj_rows = []
    for a in anos:
        ps_at  = pl * (1 + retorno_atual / 100) ** a
        ps_pr  = pl * (1 + retorno_prop  / 100) ** a
        proj_rows.append({
            'Horizonte': f"{a} ano{'s' if a > 1 else ''}",
            'Com Alocação Atual':    f"R$ {ps_at:,.0f}",
            'Com Alocação Proposta': f"R$ {ps_pr:,.0f}",
            'Ganho Adicional':       f"R$ {ps_pr - ps_at:+,.0f}",
        })
    st.dataframe(pd.DataFrame(proj_rows).set_index('Horizonte'), use_container_width=True)

    st.markdown("---")
    st.markdown("### Atual vs Proposto")
    segs = list(atuais.keys())
    fig_sim = go.Figure()
    fig_sim.add_bar(name='Atual',    x=segs, y=[atuais[s]*100 for s in segs], marker_color='#2E86C1')
    fig_sim.add_bar(name='Proposto', x=segs, y=[novas[s]*100  for s in segs], marker_color='#27AE60')
    fig_sim.add_bar(name='Limite CMN 4.994',
                    x=segs, y=[limites[s]*100 for s in segs],
                    marker_color='rgba(231,76,60,0.3)')
    fig_sim.update_layout(barmode='group', yaxis_title='% do PS',
                          xaxis_tickangle=-20, margin=dict(t=10, b=10),
                          legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig_sim, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: COMPLIANCE CMN 4.994
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: ANÁLISE IA
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Análise IA':
    st.markdown('<div class="secao-titulo">🤖 Diagnóstico Executivo por Inteligência Artificial</div>', unsafe_allow_html=True)
    st.caption("Powered by Groq (Llama 3.3 70B)")

    if st.button("🚀 Gerar Diagnóstico Completo", type="primary", width='stretch'):
            with st.spinner("Analisando carteira com IA..."):
                try:
                    st.session_state.analise_ia = gerar_analise_compliance(resumo, pl, data_ref, api_key)
                    st.success("Análise concluída!")
                except Exception as e:
                    st.error(f"Erro na API Groq: {e}")

    if st.session_state.analise_ia:
        st.divider()
        st.markdown(st.session_state.analise_ia)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: CHAT VIGIA
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Chat':
    _p_ativo = PERSONAS[st.session_state.chat_persona]
    st.markdown(
        f'<div class="secao-titulo">💬 Chat Personas — {_p_ativo["emoji"]} {_p_ativo["nome"]}</div>',
        unsafe_allow_html=True,
    )

    # ── Seleção de persona ──────────────────────────────────────────────────
    st.markdown("##### Escolha com quem você quer conversar")
    persona_cols = st.columns(len(PERSONAS))
    for idx, (pkey, pdata) in enumerate(PERSONAS.items()):
        is_sel = st.session_state.chat_persona == pkey
        borda = f"3px solid {pdata['cor']}" if is_sel else "1px solid #E2E9F2"
        bg    = f"{pdata['cor']}12" if is_sel else "#FFFFFF"
        with persona_cols[idx]:
            st.markdown(f"""
            <div style="background:{bg};border:{borda};border-radius:14px;
                        padding:16px 12px;text-align:center;min-height:148px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:6px;">
              <div style="font-size:2.0rem;line-height:1;">{pdata['emoji']}</div>
              <div style="font-weight:700;color:#0F1E33;font-size:0.88rem;
                          margin-top:8px;line-height:1.2;">{pdata['nome']}</div>
              <div style="font-size:0.67rem;color:{pdata['cor']};font-weight:600;
                          margin-top:3px;letter-spacing:0.02em;">{pdata['subtitulo']}</div>
              <div style="font-size:0.74rem;color:#5A6E84;margin-top:8px;
                          line-height:1.45;">{pdata['descricao']}</div>
            </div>
            """, unsafe_allow_html=True)
            if is_sel:
                st.markdown(
                    f"<div style='text-align:center;font-size:0.73rem;"
                    f"color:{pdata['cor']};font-weight:700;margin-top:2px;'>✓ Ativo</div>",
                    unsafe_allow_html=True,
                )
            else:
                if st.button("Selecionar", key=f"btn_p_{pkey}", width='stretch'):
                    st.session_state.chat_persona = pkey
                    st.session_state.chat_historico = []
                    st.rerun()

    st.markdown("---")

    # ── Exemplos de perguntas contextualizados ──────────────────────────────
    _exemplos_por_persona = {
        'vigia':   ["Estamos em compliance com a CMN 4.994?",
                    "Qual o retorno dos planos no mês?",
                    "Quais segmentos precisam de atenção?",
                    "Qual é o patrimônio social atual?"],
        'buffett': ["O portfólio do IAJA tem empresas com moat real?",
                    "Qual segmento você compraria e manteria por 10 anos?",
                    "A alocação atual tem margem de segurança suficiente?",
                    "O que Charlie Munger diria sobre nossa renda variável?"],
        'barsi':   ["Qual segmento gera mais renda passiva para o participante?",
                    "Os fundos estão distribuindo rendimentos de forma consistente?",
                    "Como a carteira se compara ao ideal de um portfólio de dividendos?",
                    "O Buy and Hold faz sentido para um fundo de pensão como o IAJA?"],
        'soros':   ["Quais riscos macro você vê na carteira atual do IAJA?",
                    "Existe alguma assimetria de risco/retorno nos segmentos?",
                    "Como a teoria da reflexividade se aplica ao mercado brasileiro?",
                    "Quais eventos de cauda poderiam impactar o portfólio?"],
    }
    with st.expander("💡 Sugestões de perguntas", expanded=False):
        for ex in _exemplos_por_persona.get(st.session_state.chat_persona, []):
            st.markdown(f"- _{ex}_")

    # ── Histórico de mensagens ──────────────────────────────────────────────
    for msg in st.session_state.chat_historico:
        avatar = _p_ativo['emoji'] if msg['role'] == 'assistant' else None
        with st.chat_message(msg['role'], avatar=avatar):
            st.markdown(msg['content'])

    # ── Input ───────────────────────────────────────────────────────────────
    pergunta = st.chat_input(f"Pergunte para {_p_ativo['nome']}...")

    if pergunta:
        st.session_state.chat_historico.append({'role': 'user', 'content': pergunta})
        with st.chat_message('user'):
            st.markdown(pergunta)

        # Monta contexto com dados atuais
        compliance_texto = "\n".join([
            f"  • {s['segmento']}: {s['pct_pl']:.2%} do PS "
            f"({s['pct_limite']:.1%} do limite) — {s['status'].upper()}"
            for s in resumo
        ])
        bm = benchmarks
        benchmarks_texto = (
            f"  CDI Mês: {bm['cdi_mes']:.2f}% | CDI Ano: {bm['cdi_ano']:.2f}%\n"
            f"  IPCA Mês: {bm['ipca_mes']:.2f}% | IPCA Ano: {bm['ipca_ano']:.2f}%\n"
            f"  Ibovespa Mês: {bm.get('ibov_mes', 0):.2f}% | Ibovespa Ano: {bm.get('ibov_ano', 0):.2f}%"
        )
        performance_texto = "Dados de cotas não carregados."
        if df_cotas is not None:
            ultimo_chat = ultima_posicao(df_cotas)
            linhas_perf = []
            for plano in ['PL Alpha', 'PL Beta', 'PL Gama', 'Administrativo']:
                row = ultimo_chat[ultimo_chat['fundo'] == plano]
                if not row.empty:
                    r = row.iloc[0]
                    linhas_perf.append(
                        f"  {plano}: Mês {r['Mês_pct']:.2f}% | Ano {r['Ano_pct']:.2f}%"
                        f" | vs CDI {r['Mês_pct'] - bm['cdi_mes']:+.2f}%"
                    )
            performance_texto = "\n".join(linhas_perf) if linhas_perf else performance_texto

        contexto_chat = {
            'data_ref': data_ref,
            'pl': pl,
            'total_investido': carteira['val_ajustado'].sum(),
            'compliance_texto': compliance_texto,
            'benchmarks_texto': benchmarks_texto,
            'performance_texto': performance_texto,
        }

        with st.chat_message('assistant', avatar=_p_ativo['emoji']):
            with st.spinner(f"{_p_ativo['nome']} está pensando..."):
                try:
                    resposta = chat_persona(
                        list(st.session_state.chat_historico),
                        contexto_chat,
                        api_key,
                        persona_key=st.session_state.chat_persona,
                    )
                    st.markdown(resposta)
                    st.session_state.chat_historico.append({'role': 'assistant', 'content': resposta})
                except Exception as e:
                    st.error(f"Erro na API Groq: {e}")

    if st.session_state.chat_historico:
        if st.button("🗑️ Limpar conversa", width='content'):
            st.session_state.chat_historico = []
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: ENVIO POR E-MAIL
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: BALANCETE
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Balancete':
    st.markdown('<div class="secao-titulo">📋 Balancete Contábil</div>', unsafe_allow_html=True)

    if not bal_dados:
        st.info("Adicione o PDF do balancete na pasta `data/Balancete/`.")
        st.stop()

    con = bal_dados['consolidado']
    planos = bal_dados['planos']

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PL Alpha", f"R$ {planos['Alpha']['patrimonio_social']/1e6:.1f} MM",
              f"{planos['Alpha']['patrimonio_social']/con['patrimonio_social']:.1%}")
    c2.metric("PL Beta",  f"R$ {planos['Beta']['patrimonio_social']/1e6:.1f} MM",
              f"{planos['Beta']['patrimonio_social']/con['patrimonio_social']:.1%}")
    c3.metric("PL Gama",  f"R$ {planos['Gama']['patrimonio_social']/1e6:.1f} MM",
              f"{planos['Gama']['patrimonio_social']/con['patrimonio_social']:.1%}")
    c4.metric("Total PS", f"R$ {con['patrimonio_social']/1e9:.3f} Bi")

    st.markdown("---")
    col_pie, col_emp = st.columns(2)

    with col_pie:
        st.markdown("**Distribuição do Patrimônio Social**")
        fig_ps = go.Figure(go.Pie(
            labels=['PL Alpha', 'PL Beta', 'PL Gama'],
            values=[planos[p]['patrimonio_social'] for p in ['Alpha', 'Beta', 'Gama']],
            hole=0.45, marker_colors=[AZUL, '#2E86C1', '#85C1E9'],
            textinfo='label+percent', textfont_size=13,
        ))
        fig_ps.update_layout(showlegend=False, margin=dict(t=10, b=10), height=300)
        st.plotly_chart(fig_ps, width='stretch')

    with col_emp:
        st.markdown("**Empréstimos a Participantes**")
        total_emp = con['emprestimos_participantes']
        pct_emp = total_emp / pl
        ea, eb, ec = st.columns(3)
        ea.metric("Saldo Total", f"R$ {total_emp/1e6:.2f} MM")
        eb.metric("Limite 15% PS", f"R$ {pl*0.15/1e6:.1f} MM")
        ec.metric("% do PS", f"{pct_emp:.2%}",
                  "🟢 Conforme" if pct_emp <= 0.12 else "🟡 Atenção")

        fig_emp = go.Figure(go.Bar(
            x=['PL Alpha', 'PL Beta', 'PL Gama'],
            y=[planos[p]['emprestimos_participantes']/1e6 for p in ['Alpha', 'Beta', 'Gama']],
            marker_color=[AZUL, '#2E86C1', '#85C1E9'],
            text=[f"R$ {planos[p]['emprestimos_participantes']/1e6:.2f} MM"
                  for p in ['Alpha', 'Beta', 'Gama']],
            textposition='outside',
        ))
        fig_emp.update_layout(yaxis_title='R$ MM', height=240,
                              margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig_emp, width='stretch')

    st.markdown("---")
    st.markdown("**Resumo por Plano**")
    tabela = pd.DataFrame([{
        'Plano': nome,
        'Patrimônio Social': f"R$ {d['patrimonio_social']/1e6:.1f} MM",
        '% do Total': f"{d['patrimonio_social']/con['patrimonio_social']:.1%}",
        'Empréstimos': f"R$ {d['emprestimos_participantes']/1e6:.2f} MM",
        '% PS do Plano': f"{d['emprestimos_participantes']/d['patrimonio_social']:.2%}",
        'Folga (15%)': f"R$ {(d['patrimonio_social']*0.15 - d['emprestimos_participantes'])/1e6:.1f} MM",
    } for nome, d in planos.items()])
    st.dataframe(tabela, width='stretch', hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: RELATÓRIO PDF
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Relatório PDF':
    st.markdown('<div class="secao-titulo">📄 Relatório Executivo — Conselho Deliberativo</div>', unsafe_allow_html=True)
    st.caption("Relatório completo com benchmarks, desempenho dos planos, compliance e análise por IA.")

    if api_key:
        st.success("✅ Análise detalhada por IA será incluída no relatório.")

    if st.button("📥 Gerar Relatório PDF", type="primary", width='stretch'):
        with st.spinner("Preparando dados e gerando PDF..."):
            from ai_analysis import gerar_analise_completa_pdf

            # Monta contexto para análise IA do PDF
            analise_pdf = None
            if api_key:
                total_inv_pdf = bal_dados['consolidado']['investimentos'] if bal_dados else carteira['val_ajustado'].sum()
                comp_txt = '\n'.join(
                    f"  {s['segmento']}: {s['pct_pl']:.2%} do PS / limite {s['limite_pct']:.0%} "
                    f"({s['pct_limite']:.1%} utilizado) — {s['status'].upper()}"
                    for s in resumo
                )
                bm_txt = (
                    f"  CDI: {benchmarks['cdi_mes']:.2f}% mês / {benchmarks['cdi_ano']:.2f}% ano\n"
                    f"  IPCA: {benchmarks['ipca_mes']:.2f}% mês / {benchmarks['ipca_ano']:.2f}% ano\n"
                    f"  INPC: {benchmarks.get('inpc_mes',0):.2f}% mês / {benchmarks.get('inpc_ano',0):.2f}% ano\n"
                    f"  Ibovespa: {benchmarks.get('ibov_mes',0):.2f}% mês / {benchmarks.get('ibov_ano',0):.2f}% ano"
                )
                if df_cotas is not None:
                    from analytics import calcular_meta_atuarial
                    ult_pdf = ultima_posicao(df_cotas)
                    meta_pdf = calcular_meta_atuarial(
                        df_cotas, benchmarks.get('inpc_mes',0), benchmarks.get('inpc_ano',0),
                        benchmarks['cdi_mes'], benchmarks['cdi_ano'],
                    )
                    planos_txt_pdf = '\n'.join(
                        f"  {row['Plano']} ({row['Tipo']}): "
                        f"mês {row['Retorno Mês (%)']:.2f}% (meta {row['Meta Mês (%)']:.2f}%, Δ {row['Δ Mês (%)']:+.2f}%) | "
                        f"ano {row['Retorno Ano (%)']:.2f}% (meta {row['Meta Ano (%)']:.2f}%, Δ {row['Δ Ano (%)']:+.2f}%) | "
                        f"status mês: {row['Status Mês']} | status ano: {row['Status Ano']}"
                        for _, row in meta_pdf['planos'].iterrows()
                    )
                else:
                    ult_pdf = None
                    meta_pdf = None
                    planos_txt_pdf = 'Dados de cotas não disponíveis'

                ctx_pdf = {
                    'data_ref':         data_ref,
                    'pl':               pl,
                    'total_investido':  total_inv_pdf,
                    'pct_investido':    total_inv_pdf / pl * 100 if pl else 0,
                    'compliance_texto': comp_txt,
                    'benchmarks_texto': bm_txt,
                    'planos_texto':     planos_txt_pdf,
                    'meta_texto': (
                        "Alpha (BD): INPC + 5,24% a.a. (Benefício Definido — obrigação contratual) | "
                        "Beta (CV): INPC + 4,50% a.a. | Gama (CV): INPC + 4,50% a.a. | "
                        f"INPC mês: {benchmarks.get('inpc_mes',0):.2f}% | INPC ano: {benchmarks.get('inpc_ano',0):.2f}%"
                    ),
                }
                try:
                    with st.spinner("Gerando análise detalhada por IA..."):
                        analise_pdf = gerar_analise_completa_pdf(ctx_pdf, api_key)
                except Exception as e:
                    st.warning(f"Análise IA não pôde ser gerada: {e}. O PDF será gerado sem ela.")
                    analise_pdf = None
            else:
                ult_pdf = ultima_posicao(df_cotas) if df_cotas is not None else None
                if df_cotas is not None:
                    from analytics import calcular_meta_atuarial
                    meta_pdf = calcular_meta_atuarial(
                        df_cotas, benchmarks.get('inpc_mes',0), benchmarks.get('inpc_ano',0),
                        benchmarks['cdi_mes'], benchmarks['cdi_ano'],
                    )
                else:
                    meta_pdf = None

            total_inv_pdf2 = bal_dados['consolidado']['investimentos'] if bal_dados else carteira['val_ajustado'].sum()
            pdf_buf = gerar_pdf(
                resumo_segmentos=resumo,
                pl=pl,
                data_ref=data_ref,
                analise_ia=analise_pdf,
                benchmarks=benchmarks,
                meta_planos=meta_pdf['planos'] if meta_pdf and not meta_pdf['planos'].empty else None,
                ultima_pos=ult_pdf,
                total_investido=total_inv_pdf2,
            )
            st.download_button(
                label="⬇️ Baixar Relatório PDF",
                data=pdf_buf,
                file_name=f"VIGIA_IAJA_{data_ref.replace('/', '-')}.pdf",
                mime="application/pdf",
                width='stretch',
            )


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: NOTÍCIAS
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Notícias':
    st.markdown('<div class="secao-titulo">📰 Notícias — EFPC & Mercado Financeiro</div>', unsafe_allow_html=True)

    # Fontes listadas
    with st.expander("📡 Fontes utilizadas", expanded=False):
        c1, c2 = st.columns(2)
        c1.markdown(
            "**EFPC & Previdência**\n"
            "- PREVIC — gov.br\n"
            "- Ministério da Previdência — gov.br\n"
            "- Google News (EFPC, PREVIC, fundo de pensão)\n"
            "- Google News (ABRAPP, ANAPAR, regime próprio)\n"
            "- Agência Brasil — Economia"
        )
        c2.markdown(
            "**Mercado Financeiro**\n"
            "- CVM — gov.br\n"
            "- Tesouro Nacional — gov.br\n"
            "- Banco Central — gov.br\n"
            "- Infomoney\n"
            "- CNN Brasil Economia\n"
            "- Valor Econômico\n"
            "- Agência Brasil — Mercado\n"
            "- Google News (Selic, CDI, IPCA, Ibovespa)"
        )

    col_lim, col_ref = st.columns([4, 1])
    limite = col_lim.slider("Notícias por coluna", min_value=6, max_value=20, value=10, step=2)
    if col_ref.button("🔄 Atualizar", width='stretch'):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

    @st.cache_data(ttl=1800, show_spinner=False)
    def _efpc(n): return buscar_noticias_efpc(n)

    @st.cache_data(ttl=1800, show_spinner=False)
    def _mercado(n): return buscar_noticias_mercado(n)

    def _card(n: dict) -> str:
        return f"""
        <div style="background:#FFFFFF;border-radius:12px;padding:16px 18px;
                    border:1px solid #E2E9F2;border-left:4px solid #1B3A6B;
                    box-shadow:0 2px 8px rgba(15,30,60,0.06);margin-bottom:14px;">
          <div style="font-size:0.67rem;color:#7FA8D0;font-weight:700;
                      text-transform:uppercase;letter-spacing:0.07em;margin-bottom:6px;">
            {n['fonte']} &nbsp;·&nbsp; {n['data']}
          </div>
          <a href="{n['link']}" target="_blank"
             style="font-size:0.92rem;font-weight:700;color:#0F1E33;
                    text-decoration:none;line-height:1.45;display:block;margin-bottom:8px;">
            {n['titulo']}
          </a>
          <div style="font-size:0.80rem;color:#5A6E84;line-height:1.55;">
            {n['resumo']}
          </div>
          <a href="{n['link']}" target="_blank"
             style="font-size:0.75rem;color:#2472B5;font-weight:600;
                    text-decoration:none;margin-top:10px;display:inline-block;">
            Ler matéria completa →
          </a>
        </div>"""

    col_efpc, col_merc = st.columns(2)

    with col_efpc:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
          <div style="width:4px;height:28px;background:#1B3A6B;border-radius:4px;"></div>
          <div>
            <div style="font-size:1.0rem;font-weight:700;color:#0F1E33;">EFPC & Previdência</div>
            <div style="font-size:0.72rem;color:#8AAECB;">PREVIC · ABRAPP · Fundos de Pensão</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Carregando..."):
            noticias_efpc = _efpc(limite)

        if not noticias_efpc:
            st.warning("Sem notícias no momento. Verifique a conexão.")
        else:
            for n in noticias_efpc:
                st.markdown(_card(n), unsafe_allow_html=True)

    with col_merc:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
          <div style="width:4px;height:28px;background:#2472B5;border-radius:4px;"></div>
          <div>
            <div style="font-size:1.0rem;font-weight:700;color:#0F1E33;">Mercado Financeiro</div>
            <div style="font-size:0.72rem;color:#8AAECB;">Infomoney · CNN Brasil · Valor · B3</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Carregando..."):
            noticias_mercado = _mercado(limite)

        if not noticias_mercado:
            st.warning("Sem notícias no momento. Verifique a conexão.")
        else:
            for n in noticias_mercado:
                st.markdown(_card(n), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO: HISTÓRICO
# ══════════════════════════════════════════════════════════════════════════════
elif pagina == 'Histórico':
    st.markdown('<div class="secao-titulo">📈 Histórico de Compliance — Evolução Mensal</div>', unsafe_allow_html=True)

    col_sv, col_info = st.columns([1, 3])
    with col_sv:
        if st.button("💾 Salvar snapshot atual", type="primary", width='stretch'):
            caminho = salvar_snapshot(resumo, pl, data_ref)
            st.success(f"Salvo: {caminho.name}")
    with col_info:
        st.info("Salve um snapshot após cada fechamento mensal para acompanhar a evolução do compliance.")

    snapshots = carregar_historico()
    if not snapshots:
        st.warning("Nenhum snapshot salvo ainda.")
    else:
        df_hist = historico_para_dataframe(snapshots)
        st.markdown(f"**{len(snapshots)} períodos registrados**")

        fig_line = px.line(df_hist, x="Data", y="% do PS", color="Segmento",
                           markers=True,
                           color_discrete_sequence=px.colors.qualitative.Set2)
        for seg in df_hist["Segmento"].unique():
            lim = df_hist[df_hist["Segmento"] == seg]["Limite (%)"].iloc[0]
            fig_line.add_hline(y=lim, line_dash="dot", line_color="red",
                               opacity=0.3, annotation_text=f"Lim.{seg[:8]}")
        fig_line.update_layout(yaxis_title="% do PS", xaxis_title="",
                               legend=dict(orientation='h', y=1.05),
                               margin=dict(t=30, b=10))
        st.plotly_chart(fig_line, width='stretch')

        st.divider()
        pivot = df_hist.pivot_table(index="Segmento", columns="Data",
                                    values="Status", aggfunc="first")
        pivot_display = pivot.map(
            lambda v: {'vermelho': '🔴', 'amarelo': '🟡', 'verde': '🟢'}.get(v, v)
        )
        st.dataframe(pivot_display, width='stretch')


if __name__ == '__main__':
    pass
