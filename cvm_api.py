import io
import pickle
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

CVM_INF_BASE  = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS"
CVM_REG_URL   = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"

CACHE_DIR = Path(__file__).parent / "data" / ".cache"

# Mapeamento Tipo_Classe → categoria exibida
TIPO_PARA_CLASSE = {
    'Classes de Cotas de Fundos FIF':       None,   # usa col Classificacao
    'Classes de Cotas de Fundos FIDC':      'FIDC',
    'Classes de Cotas de Fundos FIP':       'FIP',
    'Classes de Cotas de Fundos FII':       'FII',
    'Classes de Cotas de Fundos FIAGRO':    'FIAGRO',
    'Classes de Cotas de Fundos FIIM':      'Multimercado',
    'Classes de Cotas de Fundos FIF (FAPI)':'Renda Fixa',
}

CLASSES_RELEVANTES = ['Renda Fixa', 'Multimercado', 'Ações', 'Cambial', 'FII']


def _cache_path(nome: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"cvm_{nome}.pkl"


def _cache_valido(path: Path, horas: float) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < horas * 3600


def _fmt_cnpj(c: str) -> str:
    """Converte CNPJ numérico (14 dígitos) para formato XX.XXX.XXX/XXXX-XX."""
    c = str(c).strip().zfill(14)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def baixar_cadastro() -> pd.DataFrame:
    """
    Baixa registro_fundo_classe.zip da CVM (novo formato Res. 175/2022).
    Retorna DataFrame com CNPJ_fmt, Denominacao_Social, Classe.
    Cache de 24h.
    """
    cache = _cache_path("cadastro_v2")
    if _cache_valido(cache, horas=24):
        with open(cache, 'rb') as f:
            return pickle.load(f)

    resp = requests.get(CVM_REG_URL, timeout=60)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        with z.open('registro_classe.csv') as f:
            df = pd.read_csv(
                f, sep=';', encoding='latin1',
                dtype={'CNPJ_Classe': str},
                low_memory=False,
                usecols=['CNPJ_Classe', 'Denominacao_Social', 'Tipo_Classe',
                         'Classificacao', 'Situacao', 'Patrimonio_Liquido'],
            )

    # Normaliza CNPJ para o mesmo formato do informe diário
    df['CNPJ_fmt'] = df['CNPJ_Classe'].apply(_fmt_cnpj)

    # Determina a classe final
    def _classe(row):
        tipo = str(row['Tipo_Classe'])
        cl   = TIPO_PARA_CLASSE.get(tipo)
        if cl is not None:
            return cl
        # FIF: usa coluna Classificacao
        c = str(row.get('Classificacao', '')).strip()
        if c and c != 'nan':
            return c.replace('Ações', 'Ações')
        return 'Outros'

    df['Classe'] = df.apply(_classe, axis=1)

    with open(cache, 'wb') as f:
        pickle.dump(df, f)
    return df


def baixar_informe_diario(ano: int, mes: int) -> pd.DataFrame:
    """
    Baixa informe diário de fundos CVM (novo formato com CNPJ_FUNDO_CLASSE).
    Cache de 4h.
    """
    cache = _cache_path(f"inf_{ano}{mes:02d}")
    if _cache_valido(cache, horas=4):
        with open(cache, 'rb') as f:
            return pickle.load(f)

    url = f"{CVM_INF_BASE}/inf_diario_fi_{ano}{mes:02d}.zip"
    resp = requests.get(url, timeout=90)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(
                f, sep=';', encoding='latin1',
                dtype={'CNPJ_FUNDO_CLASSE': str},
                usecols=['CNPJ_FUNDO_CLASSE', 'DT_COMPTC', 'VL_QUOTA', 'VL_PATRIM_LIQ'],
            )

    df['DT_COMPTC']     = pd.to_datetime(df['DT_COMPTC'])
    df['VL_QUOTA']      = pd.to_numeric(df['VL_QUOTA'],      errors='coerce')
    df['VL_PATRIM_LIQ'] = pd.to_numeric(df['VL_PATRIM_LIQ'], errors='coerce')
    df = df.dropna(subset=['VL_QUOTA'])

    with open(cache, 'wb') as f:
        pickle.dump(df, f)
    return df


def _ultima_cota_mes(ano: int, mes: int) -> pd.Series:
    """Retorna a última cota de cada fundo no mês — base para cálculo anual."""
    df = baixar_informe_diario(ano, mes)
    return (
        df.sort_values('DT_COMPTC')
        .groupby('CNPJ_FUNDO_CLASSE')['VL_QUOTA']
        .last()
    )


def calcular_comparativo(
    ano: int,
    mes: int,
    pl_minimo: float = 5_000_000,
) -> pd.DataFrame:
    """
    Retorna DataFrame com retorno mensal e anual de cada fundo + sua classe.
    Filtra por PL médio >= pl_minimo e classes relevantes para EFPC.
    """
    df_inf = baixar_informe_diario(ano, mes)
    df_cad = baixar_cadastro()

    # Só fundos em funcionamento normal
    ativos = df_cad[df_cad['Situacao'] == 'Em Funcionamento Normal'][
        ['CNPJ_fmt', 'Denominacao_Social', 'Classe']
    ].drop_duplicates('CNPJ_fmt')

    # Join pelo CNPJ formatado
    df = df_inf.merge(ativos, left_on='CNPJ_FUNDO_CLASSE', right_on='CNPJ_fmt', how='inner')
    df = df[df['Classe'].isin(CLASSES_RELEVANTES)]

    # Filtra por PL mínimo
    pl_medio = df.groupby('CNPJ_fmt')['VL_PATRIM_LIQ'].mean()
    cnpjs_ok = pl_medio[pl_medio >= pl_minimo].index
    df = df[df['CNPJ_fmt'].isin(cnpjs_ok)]

    # Retorno mês: (última cota / primeira cota - 1) * 100
    grp = df.sort_values('DT_COMPTC').groupby(['CNPJ_fmt', 'Classe', 'Denominacao_Social'])
    ret = pd.DataFrame({
        'quota_fim':  grp['VL_QUOTA'].last(),
        'ultimo_dia': grp['DT_COMPTC'].last(),
        'quota_ini':  grp['VL_QUOTA'].first(),
    }).reset_index()

    ret['retorno_mes'] = (ret['quota_fim'] / ret['quota_ini'] - 1) * 100
    ret = ret[(ret['retorno_mes'] > -30) & (ret['retorno_mes'] < 50)]

    # Retorno anual: compara cota atual com cota do mesmo mês do ano anterior
    mes_ant = mes
    ano_ant = ano - 1
    try:
        cotas_ant = _ultima_cota_mes(ano_ant, mes_ant)
        cotas_ant = cotas_ant.rename('quota_ant')
        ret = ret.merge(cotas_ant, left_on='CNPJ_fmt', right_index=True, how='left')
        ret['retorno_ano'] = (ret['quota_fim'] / ret['quota_ant'] - 1) * 100
        ret.loc[ret['retorno_ano'].abs() > 100, 'retorno_ano'] = float('nan')
    except Exception:
        ret['retorno_ano'] = float('nan')

    return ret


def resumo_por_classe(df_comp: pd.DataFrame) -> pd.DataFrame:
    """Agrega estatísticas de retorno por classe de fundo."""
    def agg(g):
        return pd.Series({
            'qtd_fundos':  len(g),
            'mediana':     round(g['retorno_mes'].median(), 4),
            'media':       round(g['retorno_mes'].mean(),   4),
            'p10':         round(g['retorno_mes'].quantile(0.10), 4),
            'p25':         round(g['retorno_mes'].quantile(0.25), 4),
            'p75':         round(g['retorno_mes'].quantile(0.75), 4),
            'p90':         round(g['retorno_mes'].quantile(0.90), 4),
            'pl_total_bi': round(g['pl_medio'].sum() / 1e9, 1),
        })

    return (
        df_comp.groupby('Classe')
        .apply(agg, include_groups=False)
        .reset_index()
        .sort_values('mediana', ascending=False)
    )
