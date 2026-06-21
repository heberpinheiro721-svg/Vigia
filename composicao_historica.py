from __future__ import annotations

import re
import calendar
import pandas as pd
import pdfplumber
from pathlib import Path

from parser import classificar_segmento

_RE_CNPJ     = re.compile(r'\b(\d{14})\b')
_RE_DATA_POS = re.compile(r'Data da Posi.*?:\s*(\d{2}/\d{2}/\d{4})', re.IGNORECASE)
_RE_CUST     = re.compile(r'(CUST\d+)\s*-\s*(.+)', re.IGNORECASE)
_RE_COMP_HDR = re.compile(r'Composi.*Carteira', re.IGNORECASE)


def _num_pdf(s: str) -> float:
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


def _parse_composicao_pdf(filepath) -> pd.DataFrame:
    """Extrai posicoes de todos os planos/datas de um PDF de Composicao (S3 Caceis)."""
    rows = []
    with pdfplumber.open(filepath) as pdf:
        for pg in pdf.pages:
            txt = pg.extract_text() or ''
            linhas = [l for l in txt.split('\n') if l.strip()]

            if not any(_RE_COMP_HDR.search(l) for l in linhas[:3]):
                continue

            data_pos = None
            cliente  = ''

            for l in linhas:
                m = _RE_DATA_POS.search(l)
                if m:
                    data_pos = pd.to_datetime(m.group(1), dayfirst=True)
                    continue
                m2 = _RE_CUST.search(l)
                if m2:
                    cliente = m2.group(2).strip()
                    continue

                stripped = l.strip()
                if not stripped:
                    continue
                if stripped.startswith('Total') or 'Valores Expressos' in stripped:
                    continue
                if 'Descri' in stripped and 'CNPJ' in stripped:
                    continue

                m3 = _RE_CNPJ.search(l)
                if not m3:
                    continue

                cnpj      = m3.group(1)
                descricao = l[:m3.start()].strip()
                rest      = l[m3.end():].strip().split()

                # Apos CNPJ: ISIN qtd val_nominal rendimento val_bruto irrf iof val_liquido pct_seg pct_pl
                if len(rest) < 8:
                    continue

                val_liq = _num_pdf(rest[7])
                if val_liq <= 0:
                    continue

                rows.append({
                    'data_pos':    data_pos,
                    'cliente':     cliente,
                    'descricao':   descricao,
                    'cnpj':        cnpj,
                    'val_liquido': val_liq,
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['segmento'] = df.apply(
        lambda r: classificar_segmento(r['cliente'], r['descricao']), axis=1
    )
    return df


def load_carteira_historica(data_dir: Path) -> pd.DataFrame:
    """Carrega composicoes historicas de todos os PDFs em data/Composicao/."""
    comp_dir = Path(data_dir) / 'Composição'
    if not comp_dir.exists():
        return pd.DataFrame()

    dfs = []
    for pdf_path in sorted(comp_dir.glob('*.pdf')):
        try:
            df_pdf = _parse_composicao_pdf(pdf_path)
            if not df_pdf.empty:
                dfs.append(df_pdf)
        except Exception:
            continue

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    df = df.dropna(subset=['data_pos', 'val_liquido'])
    df = df[df['val_liquido'] > 0]
    return df


def carteira_para_mes(df_hist: pd.DataFrame, patrimonio_liquido: float,
                      ano: int, mes: int) -> pd.DataFrame | None:
    """
    Filtra o historico para o snapshot mais recente do mes solicitado,
    escala ao PL e retorna no mesmo formato de load_carteira_s3.
    """
    if df_hist is None or df_hist.empty:
        return None

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    limite     = pd.Timestamp(ano, mes, ultimo_dia)
    inicio     = pd.Timestamp(ano, mes, 1)

    datas_mes = df_hist[
        (df_hist['data_pos'] >= inicio) & (df_hist['data_pos'] <= limite)
    ]['data_pos'].unique()

    if len(datas_mes) == 0:
        return None

    data_sel = max(datas_mes)
    df = df_hist[df_hist['data_pos'] == data_sel].copy()

    # Consolida: mesmo fundo aparece em multiplos planos — soma os valores
    df = (
        df.groupby('cnpj', as_index=False)
        .agg(cliente=('cliente', 'first'), descricao=('descricao', 'first'),
             val_liquido=('val_liquido', 'sum'), segmento=('segmento', 'first'))
    )

    total_raw = df['val_liquido'].sum()
    escala    = patrimonio_liquido / total_raw if total_raw > 0 else 1.0
    df['val_ajustado'] = (df['val_liquido'] * escala).round(2)
    df['pct_pl_calc']  = df['val_ajustado'] / patrimonio_liquido
    df['_total_raw']   = total_raw

    return df[['cliente', 'descricao', 'cnpj',
               'val_liquido', 'val_ajustado', 'pct_pl_calc', 'segmento', '_total_raw']]
