import pandas as pd
from datetime import datetime
from bcb_api import get_cdi_mes, get_ipca_mes, get_inpc_mes, get_ibov_mes

MESES_PT = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr',
    5: 'Mai', 6: 'Jun', 7: 'Jul', 8: 'Ago',
    9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez',
}

PLANOS_MAP = {
    'PL Alpha': 'Alpha',
    'PL Beta':  'Beta',
    'PL Gama':  'Gama',
}


def _label(period) -> str:
    return f"{MESES_PT[period.month]}/{str(period.year)[-2:]}"


def retornos_mensais_cotas(df_cotas: pd.DataFrame) -> pd.DataFrame:
    """
    Pega o retorno mensal de cada plano (último dia de cada mês no CSV).
    Exclui o mês base anterior (normalização) e meses futuros.
    """
    periodo_atual = pd.Period(datetime.today(), freq='M')
    df = df_cotas[df_cotas['fundo'].isin(PLANOS_MAP.keys())].copy()
    df['Periodo'] = df['Data'].dt.to_period('M')
    # Filtra: apenas períodos a partir do primeiro mês completo (≥ 2026-03)
    # e não além do mês corrente (sem dados futuros)
    df = df[(df['Periodo'] >= pd.Period('2026-03', freq='M')) &
            (df['Periodo'] <= periodo_atual)]
    idx = df.groupby(['fundo', 'Periodo'])['Data'].idxmax()
    df_ult = df.loc[idx.values]
    pivot = df_ult.pivot_table(index='Periodo', columns='fundo', values='Mês_pct')
    pivot.columns = [PLANOS_MAP.get(c, c) for c in pivot.columns]
    return pivot.sort_index()


def benchmarks_mensais(periodos: list) -> pd.DataFrame:
    """Busca CDI, IPCA, INPC e Ibovespa para cada período via BCB API."""
    rows = []
    for p in periodos:
        ano, mes = p.year, p.month
        rows.append({
            'Periodo': p,
            'CDI':      round(get_cdi_mes(ano, mes), 4),
            'IPCA':     round(get_ipca_mes(ano, mes), 4),
            'INPC':     round(get_inpc_mes(ano, mes), 4),
            'Ibovespa': round(get_ibov_mes(ano, mes), 2),
        })
    return pd.DataFrame(rows).set_index('Periodo')


def montar_tabela_mensal(df_cotas: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna DataFrame com retornos mensais de todos os planos + benchmarks.
    Índice: string 'Mar/26', 'Abr/26', etc.
    """
    ret = retornos_mensais_cotas(df_cotas)
    if ret.empty:
        return pd.DataFrame()
    bm = benchmarks_mensais(ret.index.tolist())
    df = pd.concat([bm, ret], axis=1)
    df.index = [_label(p) for p in df.index]
    df.index.name = 'Período'
    return df


def tabela_para_texto(df: pd.DataFrame) -> str:
    """Formata o DataFrame em texto legível para o prompt da IA."""
    linhas = []
    for periodo, row in df.iterrows():
        partes = [f"{col}={row[col]:+.2f}%" for col in df.columns if not pd.isna(row[col])]
        linhas.append(f"  {periodo}: {', '.join(partes)}")
    return '\n'.join(linhas)
