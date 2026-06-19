from __future__ import annotations

import re
import pandas as pd
import pdfplumber
from datetime import datetime
from pathlib import Path
from bcb_api import get_cdi_mes, get_ipca_mes, get_inpc_mes, get_ibov_mes

MESES_PT = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr',
    5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago',
    9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
}

# Mapeamento fundo CSV → nome exibição
PLANOS_CSV = {
    'PL Alpha':       'Alpha',
    'PL Beta':        'Beta',
    'PL Gama':        'Gama',
    'Administrativo': 'PGA',
}

# Ordem de exibição: benchmarks primeiro, planos depois
ORDEM_LINHAS = ['CDI', 'IPCA', 'INPC', 'Ibovespa', 'Alpha', 'Beta', 'Gama', 'PGA']

_PCT_RE  = re.compile(r'\(?\d+,\d+\)?%')
_DATE_RE = re.compile(r'^(\d{2})/(\d{2})/(\d{4})')


def _label(period) -> str:
    return f"{MESES_PT[period.month]}/{str(period.year)[-2:]}"


def _parse_pct(s: str) -> float:
    s = s.strip().replace('%', '')
    neg = s.startswith('(') and s.endswith(')')
    s = s.replace('(', '').replace(')', '').replace(',', '.')
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return 0.0


# ── Leitura de PDFs de Cotas ─────────────────────────────────────────────────

def _plano_from_page(texto: str) -> str | None:
    if re.search(r'PL\s+ALPHA', texto, re.IGNORECASE): return 'Alpha'
    if re.search(r'PL\s+BETA',  texto, re.IGNORECASE): return 'Beta'
    if re.search(r'PL\s+GAMA',  texto, re.IGNORECASE): return 'Gama'
    if re.search(r'ADMINISTR',   texto, re.IGNORECASE): return 'PGA'
    return None


def _periodo_alvo(texto: str):
    """Extrai mês/ano do fim do período: 'Data da Posição: xx/xx/xxxx - dd/mm/aaaa'."""
    m = re.search(
        r'Data da Posi[çc][ãa]o\s*:\s*\S+\s*-\s*(\d{2})/(\d{2})/(\d{4})',
        texto, re.IGNORECASE
    )
    if m:
        return int(m.group(2)), int(m.group(3))  # mes, ano
    return None, None


def _mes_pct_ultimo_dia(texto: str, mes: int, ano: int) -> float | None:
    """Retorna o Mês% da última linha de dados que pertence ao mês/ano alvo."""
    resultado = None
    for linha in texto.split('\n'):
        m = _DATE_RE.match(linha.strip())
        if not m:
            continue
        d_mes, d_ano = int(m.group(2)), int(m.group(3))
        if d_mes != mes or d_ano != ano:
            continue
        pcts = _PCT_RE.findall(linha)
        if len(pcts) >= 3:
            # Colunas finais: Dia%, Mês%, Ano%, Total%  → Mês = pcts[-3]
            resultado = _parse_pct(pcts[-3])
    return resultado


def retornos_de_pdfs(data_dir: Path) -> pd.DataFrame:
    """Extrai retornos mensais de todos os PDFs de cotas em data/cotas/."""
    cotas_dir = data_dir / 'cotas'
    if not cotas_dir.exists():
        return pd.DataFrame()

    rows = []
    for pdf_path in sorted(cotas_dir.glob('*.pdf')):
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    texto = page.extract_text() or ''
                    plano = _plano_from_page(texto)
                    mes, ano = _periodo_alvo(texto)
                    if not plano or not mes:
                        continue
                    mes_pct = _mes_pct_ultimo_dia(texto, mes, ano)
                    if mes_pct is not None:
                        rows.append({
                            'Periodo': pd.Period(f'{ano}-{mes:02d}', freq='M'),
                            'fundo':   plano,
                            'Mês_pct': mes_pct,
                        })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=['Periodo', 'fundo'], keep='last')
    return df


# ── Leitura do CSV de Cotas ───────────────────────────────────────────────────

def retornos_de_csv(df_cotas: pd.DataFrame) -> pd.DataFrame:
    """Extrai retornos mensais do CSV de cotas (último dia de cada mês)."""
    periodo_atual = pd.Period(datetime.today(), freq='M')
    df = df_cotas[df_cotas['fundo'].isin(PLANOS_CSV.keys())].copy()
    df['Periodo'] = df['Data'].dt.to_period('M')
    df = df[(df['Periodo'] >= pd.Period('2026-03', freq='M')) &
            (df['Periodo'] <= periodo_atual)]
    idx = df.groupby(['fundo', 'Periodo'])['Data'].idxmax()
    df_ult = df.loc[idx.values]
    pivot = df_ult.pivot_table(index='Periodo', columns='fundo', values='Mês_pct')
    pivot.columns = [PLANOS_CSV.get(c, c) for c in pivot.columns]
    # Converte para formato longo para facilitar a fusão
    df_long = pivot.reset_index().melt(id_vars='Periodo', var_name='fundo', value_name='Mês_pct')
    return df_long.dropna(subset=['Mês_pct'])


# ── Fusão e Tabela ────────────────────────────────────────────────────────────

def montar_tabela_mensal(df_cotas: pd.DataFrame, data_dir: Path,
                         ultimos_n: int = 12) -> pd.DataFrame:
    """
    Monta tabela transposta dos últimos N meses.
    Linhas: CDI, IPCA, INPC, Ibovespa, Alpha, Beta, Gama, PGA
    Colunas: Jun/25, Jul/25, ..., Jun/26
    CSV tem prioridade sobre PDF para o mesmo período/plano.
    """
    hoje = pd.Period(datetime.today(), freq='M')
    inicio = hoje - ultimos_n + 1
    periodos = pd.period_range(inicio, hoje, freq='M')

    # ── Retornos dos planos (PDF + CSV, CSV tem prioridade) ──────────────────
    df_pdf = retornos_de_pdfs(data_dir)
    df_csv = retornos_de_csv(df_cotas) if df_cotas is not None else pd.DataFrame()

    if not df_pdf.empty and not df_csv.empty:
        df_ret = pd.concat([df_pdf, df_csv]).drop_duplicates(
            subset=['Periodo', 'fundo'], keep='last'
        )
    elif not df_csv.empty:
        df_ret = df_csv
    elif not df_pdf.empty:
        df_ret = df_pdf
    else:
        df_ret = pd.DataFrame()

    # Filtra para os últimos N meses
    if not df_ret.empty:
        df_ret = df_ret[df_ret['Periodo'].isin(periodos)]
        pivot_ret = df_ret.pivot_table(
            index='Periodo', columns='fundo', values='Mês_pct', aggfunc='last'
        )
    else:
        pivot_ret = pd.DataFrame(index=periodos)

    # ── Benchmarks da BCB API ────────────────────────────────────────────────
    bm_rows = []
    for p in periodos:
        ano, mes = p.year, p.month
        bm_rows.append({
            'Periodo':  p,
            'CDI':      round(get_cdi_mes(ano, mes), 4),
            'IPCA':     round(get_ipca_mes(ano, mes), 4),
            'INPC':     round(get_inpc_mes(ano, mes), 4),
            'Ibovespa': round(get_ibov_mes(ano, mes), 2),
        })
    df_bm = pd.DataFrame(bm_rows).set_index('Periodo')

    # Junta e transpõe
    df = pd.concat([df_bm, pivot_ret], axis=1)
    df.index = [_label(p) for p in df.index]
    df = df.T
    df.index.name = 'Indicador'
    df.columns.name = None

    ordem = [r for r in ORDEM_LINHAS if r in df.index]
    return df.reindex(ordem)


def tabela_para_texto(df: pd.DataFrame) -> str:
    """Formata o DataFrame transposto em texto para o prompt da IA."""
    linhas = []
    for indicador, row in df.iterrows():
        partes = [f"{col}={row[col]:+.2f}%"
                  for col in df.columns if not pd.isna(row[col]) and row[col] != 0.0]
        linhas.append(f"  {indicador}: {', '.join(partes)}")
    return '\n'.join(linhas)
