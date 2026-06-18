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

    # Inclui último dia do mês anterior como base (normalização)
    ultimo_anterior = df[df['Data'] < '2026-03-01']['Data'].max()
    df = df[df['Data'] >= ultimo_anterior].copy()
    df = df.sort_values(['fundo', 'Data']).reset_index(drop=True)

    # Retorno acumulado relativo ao primeiro dia (base 100)
    base = df[df['Data'] == ultimo_anterior].set_index('fundo')['Cota']
    df['cota_base100'] = df.apply(
        lambda r: (r['Cota'] / base.get(r['fundo'], r['Cota'])) * 100
        if base.get(r['fundo']) else 100.0,
        axis=1,
    )

    return df

def ultima_posicao(df: pd.DataFrame) -> pd.DataFrame:
    return df[df['Data'] == df['Data'].max()].copy()

def achar_cotas_csv(data_dir: Path) -> Path | None:
    cotas_dir = data_dir / "cotas"
    if cotas_dir.exists():
        csvs = sorted(cotas_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
        if csvs:
            return csvs[0]
    return None
