from __future__ import annotations

import re
import pandas as pd
import pdfplumber
from pathlib import Path
from parser import _detectar_encoding

NOMES_CURTOS = {
    'ADMINISTR': 'Administrativo',
    'PL ALPHA':  'PL Alpha',
    'PL BETA':   'PL Beta',
    'PL GAMA':   'PL Gama',
    'AÇÕES':     'FIA Ações',
    'ACOES':     'FIA Ações',
    'FIC FIA':   'FIA Ações',
    'CP IE':     'FIM Exterior',
    'BRAM':      'BRAM RF',
    'ITAÚ':      'Itaú RF',
    'ITAU':      'Itaú RF',
    'WESTERN':   'Western RF',
    'CIRF':      'CIRF Cred Priv',
    'IAJA 3':    'IAJA 3 RF',
    'CI COTAS':  'CI FIM CP',
}

def _curto(nome: str) -> str:
    n = nome.upper()
    for kw, label in NOMES_CURTOS.items():
        if kw in n:
            return label
    return nome[:22]

def _num(s) -> float:
    if pd.isna(s): return 0.0
    return float(str(s).strip().replace('.', '').replace(',', '.') or 0)

def _pct(s) -> float:
    if pd.isna(s): return 0.0
    s = str(s).replace('%', '').replace(',', '.').strip()
    if s.startswith('(') and s.endswith(')'):
        try: return -float(s[1:-1])
        except: return 0.0
    try: return float(s or 0)
    except: return 0.0

def _aplicar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica colunas derivadas comuns a CSV e PDF."""
    df['Data']       = pd.to_datetime(df['data'], format='mixed', dayfirst=True)
    df['Cota']       = df['cota'].apply(_num)
    df['Patrimônio'] = df['patrimonio'].apply(_num)
    df['Cliente']    = df['cliente']
    for col, novo in [('dia','Dia'), ('mes','Mês'), ('ano','Ano'), ('total','Total')]:
        df[novo + '_pct'] = df[col].apply(_pct)
    df['fundo'] = df['Cliente'].apply(_curto)
    df['cliente_orig'] = df['Cliente']
    df = df.sort_values(['fundo', 'Data']).reset_index(drop=True)
    base_date = df['Data'].min()
    base = df[df['Data'] == base_date].set_index('fundo')['Cota']
    df['cota_base100'] = df.apply(
        lambda r: (r['Cota'] / base.get(r['fundo'], r['Cota'])) * 100
        if base.get(r['fundo']) else 100.0,
        axis=1,
    )
    return df

def load_cotas(filepath) -> pd.DataFrame:
    enc = _detectar_encoding(filepath)
    df = pd.read_csv(filepath, sep=';', encoding=enc, dtype=str,
                     header=None, skiprows=1)

    # Colunas por posição: Código;Cliente;Data;Entradas;Saída;Patrimônio;
    #                      Qtde.Cotas;Cota;AporteTít;RetirTít;Dia;Mês;Ano;Total
    df.columns = [
        'codigo', 'cliente', 'data', 'entradas', 'saida', 'patrimonio',
        'qtde_cotas', 'cota', 'aporte_tit', 'retir_tit',
        'dia', 'mes', 'ano', 'total',
    ]
    return _aplicar_colunas(df)


_RE_DATA   = re.compile(r'^\d{2}/\d{2}/\d{4} ')
_RE_CUST   = re.compile(r'(CUST\d+)\s*-\s*(.+)', re.IGNORECASE)
_RE_NUM    = re.compile(r'^[\d.,()-]+%?$')
_RE_MAPA   = re.compile(r'Mapa de Evolu', re.IGNORECASE)

def _parse_cotas_pdf(filepath) -> pd.DataFrame:
    """Extrai dados do Mapa de Evolução de Cotas em formato PDF (S3 Caceis)."""
    rows = []
    with pdfplumber.open(filepath) as pdf:
        for pg in pdf.pages:
            txt = pg.extract_text() or ''
            linhas = [l for l in txt.split('\n') if l.strip()]

            # Ignora páginas que não são do Mapa de Evolução de Cotas
            if not any(_RE_MAPA.search(l) for l in linhas[:3]):
                continue

            codigo, cliente = '', ''
            for l in linhas[:6]:
                m = _RE_CUST.search(l)
                if m:
                    codigo  = m.group(1).strip()
                    cliente = m.group(2).strip()
                    break

            for l in linhas:
                if not _RE_DATA.match(l):
                    continue
                partes = l.split()
                # Valida que os primeiros campos numéricos são realmente números
                # (filtra linhas de movimentação que também começam com data)
                if len(partes) < 12 or not _RE_NUM.match(partes[1]):
                    continue
                rows.append({
                    'codigo':     codigo,
                    'cliente':    cliente,
                    'data':       partes[0],
                    'entradas':   partes[1],
                    'saida':      partes[2],
                    'patrimonio': partes[3],
                    'qtde_cotas': partes[4],
                    'cota':       partes[5],
                    'aporte_tit': partes[6],
                    'retir_tit':  partes[7],
                    'dia':        partes[8],
                    'mes':        partes[9],
                    'ano':        partes[10],
                    'total':      partes[11],
                })

    if not rows:
        return pd.DataFrame()
    return _aplicar_colunas(pd.DataFrame(rows))


def load_cotas_all(paths: list) -> pd.DataFrame:
    """Carrega e concatena múltiplos arquivos de cotas (CSV ou PDF), recalculando base100."""
    dfs = []
    for p in paths:
        try:
            p = Path(p)
            if p.suffix.lower() == '.pdf':
                df_i = _parse_cotas_pdf(p)
            else:
                df_i = load_cotas(p)
            if not df_i.empty:
                dfs.append(df_i)
        except Exception:
            continue
    if not dfs:
        raise ValueError("Nenhum arquivo de cotas válido encontrado.")
    df = pd.concat(dfs, ignore_index=True)
    df = df.drop_duplicates(subset=['fundo', 'Data']).sort_values(['fundo', 'Data']).reset_index(drop=True)
    base_date = df['Data'].min()
    base = df[df['Data'] == base_date].set_index('fundo')['Cota']
    df['cota_base100'] = df.apply(
        lambda r: (r['Cota'] / base.get(r['fundo'], r['Cota'])) * 100
        if base.get(r['fundo']) else 100.0,
        axis=1,
    )
    return df


def ultima_posicao(df: pd.DataFrame) -> pd.DataFrame:
    return df[df['Data'] == df['Data'].max()].copy()

def achar_cotas_csv(data_dir: Path) -> list:
    """Retorna todos os arquivos de cotas (CSV e PDF) ordenados por nome."""
    cotas_dir = data_dir / "cotas"
    if cotas_dir.exists():
        files = list(cotas_dir.glob("*.csv")) + list(cotas_dir.glob("*.pdf"))
        return sorted(files, key=lambda x: x.name)
    return []
