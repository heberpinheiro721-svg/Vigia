from __future__ import annotations

import pandas as pd
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
    return float(str(s).replace('%', '').replace(',', '.').strip() or 0)

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

    df['Data']       = pd.to_datetime(df['data'], format='mixed', dayfirst=True)
    df['Cota']       = df['cota'].apply(_num)
    df['Patrimônio'] = df['patrimonio'].apply(_num)
    df['Cliente']    = df['cliente']

    for col, novo in [('dia','Dia'), ('mes','Mês'), ('ano','Ano'), ('total','Total')]:
        df[novo + '_pct'] = df[col].apply(_pct)

    df['fundo'] = df['Cliente'].apply(_curto)
    df['cliente_orig'] = df['Cliente']

    df = df.sort_values(['fundo', 'Data']).reset_index(drop=True)

    # Base dinâmica: primeira data disponível nos dados
    base_date = df['Data'].min()
    base = df[df['Data'] == base_date].set_index('fundo')['Cota']
    df['cota_base100'] = df.apply(
        lambda r: (r['Cota'] / base.get(r['fundo'], r['Cota'])) * 100
        if base.get(r['fundo']) else 100.0,
        axis=1,
    )

    return df


def load_cotas_all(paths: list) -> pd.DataFrame:
    """Carrega e concatena múltiplos CSVs de cotas, recalculando base100 no período completo."""
    dfs = []
    for p in paths:
        try:
            dfs.append(load_cotas(p))
        except Exception:
            continue
    if not dfs:
        raise ValueError("Nenhum CSV de cotas válido encontrado.")
    df = pd.concat(dfs, ignore_index=True)
    df = df.drop_duplicates(subset=['fundo', 'Data']).sort_values(['fundo', 'Data']).reset_index(drop=True)
    # Recalcula base100 para o período completo concatenado
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
    """Retorna todos os CSVs de cotas ordenados por nome (do mais antigo ao mais recente)."""
    cotas_dir = data_dir / "cotas"
    if cotas_dir.exists():
        return sorted(cotas_dir.glob("*.csv"), key=lambda x: x.name)
    return []
