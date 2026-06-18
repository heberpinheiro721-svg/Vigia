import numpy as np
import pandas as pd


# ── Risco e Retorno ──────────────────────────────────────────────────────────

def calcular_risco_retorno(df_cotas: pd.DataFrame, cdi_ano_pct: float = 0.0) -> pd.DataFrame:
    """
    Calcula por fundo: retorno mensal, retorno anual, volatilidade anualizada e Sharpe.
    cdi_ano_pct: CDI acumulado no ano em % (ex: 10.5)
    """
    ultimo = df_cotas['Data'].max()
    df_marco = df_cotas[df_cotas['Data'] >= '2026-03-01'].copy()

    rows = []
    for fundo, grupo in df_marco.groupby('fundo'):
        grupo = grupo.sort_values('Data')

        ret_mes  = grupo.iloc[-1]['Mês_pct'] if not grupo.empty else 0.0
        ret_ano  = grupo.iloc[-1]['Ano_pct']  if not grupo.empty else 0.0
        ret_total = grupo.iloc[-1]['Total_pct'] if not grupo.empty else 0.0

        retornos_diarios = grupo['Dia_pct'].dropna().values
        vol_diaria  = float(np.std(retornos_diarios)) if len(retornos_diarios) > 1 else 0.0
        vol_anual   = vol_diaria * np.sqrt(252)

        ret_anual_calc = ((1 + ret_mes / 100) ** 12 - 1) * 100

        cdi_rf = cdi_ano_pct if cdi_ano_pct > 0 else 10.0
        sharpe = (ret_anual_calc - cdi_rf) / vol_anual if vol_anual > 0 else 0.0

        rows.append({
            'Fundo':          fundo,
            'Retorno Mês (%)': round(ret_mes, 4),
            'Retorno Ano (%)': round(ret_ano, 4),
            'Retorno Total (%)': round(ret_total, 4),
            'Retorno Anualizado (%)': round(ret_anual_calc, 4),
            'Volatilidade Anual (%)': round(vol_anual, 4),
            'Sharpe':         round(sharpe, 3),
        })

    return pd.DataFrame(rows).sort_values('Sharpe', ascending=False)


# ── Concentração por Gestor ──────────────────────────────────────────────────

GESTORES = {
    'BRAM':     'Bradesco Asset',
    'ITAÚ':     'Itaú Asset',
    'ITAU':     'Itaú Asset',
    'WESTERN':  'Western Asset',
    'SOMMA':    'Somma Investimentos',
    'NEO':      'Neo Investimentos',
    'KPTL':     'Kinea / KPTL',
    'CAPTALYS': 'Captalys',
    'OPPORTUNITY': 'Opportunity',
    'BTG':      'BTG Pactual',
    'XP':       'XP Asset',
    'IAJA':     'Próprio (SANGEST)',
    'SANGEST':  'Próprio (SANGEST)',
}


def _extrair_gestor(nome: str) -> str:
    n = nome.upper()
    for kw, label in GESTORES.items():
        if kw in n:
            return label
    partes = nome.split('-')
    if partes:
        return partes[0].strip()[:30]
    return 'Outros'


def concentracao_gestores(df_carteira: pd.DataFrame) -> pd.DataFrame:
    df = df_carteira.copy()
    df['gestor'] = df['descricao'].apply(_extrair_gestor)
    grp = df.groupby('gestor').agg(
        valor=('val_ajustado', 'sum'),
        n_fundos=('descricao', 'count'),
    ).reset_index()
    total = grp['valor'].sum()
    grp['pct'] = grp['valor'] / total * 100
    grp = grp.sort_values('pct', ascending=False)
    grp['alerta'] = grp['pct'].apply(
        lambda x: '🔴 Alta' if x > 30 else ('🟡 Média' if x > 15 else '🟢 Baixa')
    )
    return grp.rename(columns={'gestor': 'Gestor', 'valor': 'Valor (R$)',
                                'n_fundos': 'Nº Fundos', 'pct': '% Carteira',
                                'alerta': 'Concentração'})


# ── Meta Atuarial ────────────────────────────────────────────────────────────

# Metas oficiais — Políticas de Investimentos 2025-2029 aprovadas pelo Conselho Deliberativo
# Alpha (Benefício Definido): INPC + 5,24% a.a.  (aderência da taxa de juros)
# Beta  (Contribuição Variável): INPC + 4,50% a.a.
# Gama  (Contribuição Variável): INPC + 4,50% a.a.
METAS_ATUARIAIS = {
    'PL Alpha':         {'indice': 'INPC', 'spread': 5.24, 'tipo': 'BD',  'descricao': 'INPC + 5,24% a.a.'},
    'PL Beta':          {'indice': 'INPC', 'spread': 4.50, 'tipo': 'CV',  'descricao': 'INPC + 4,50% a.a.'},
    'PL Gama':          {'indice': 'INPC', 'spread': 4.50, 'tipo': 'CV',  'descricao': 'INPC + 4,50% a.a.'},
    'PL Administrativo':{'indice': 'CDI',  'spread': 0.00, 'tipo': 'PGA', 'descricao': 'CDI'},
}


def calcular_meta_atuarial(
    df_cotas: pd.DataFrame,
    inpc_mes: float,
    inpc_ano: float,
    cdi_mes: float = 0.0,
    cdi_ano: float = 0.0,
) -> dict:
    """
    Compara retorno realizado vs meta atuarial oficial de cada plano.
    Metas definidas nas Políticas de Investimentos 2025-2029 do IAJA.
      Alpha (BD): INPC + 5,24% a.a.
      Beta  (CV): INPC + 4,50% a.a.
      Gama  (CV): INPC + 4,50% a.a.
    """
    df_marco = df_cotas[df_cotas['Data'] >= '2026-03-01']
    ultimo = df_marco[df_marco['Data'] == df_marco['Data'].max()]

    resultados = []
    for plano, cfg in METAS_ATUARIAIS.items():
        row = ultimo[ultimo['fundo'] == plano]
        if row.empty:
            continue

        base_mes = inpc_mes if cfg['indice'] == 'INPC' else cdi_mes
        base_ano = inpc_ano if cfg['indice'] == 'INPC' else cdi_ano
        spread_mes = ((1 + cfg['spread'] / 100) ** (1 / 12) - 1) * 100

        meta_mes = ((1 + base_mes / 100) * (1 + spread_mes / 100) - 1) * 100
        meta_ano = ((1 + base_ano / 100) * (1 + cfg['spread'] / 100) - 1) * 100

        ret_mes = row.iloc[0]['Mês_pct']
        ret_ano = row.iloc[0]['Ano_pct']
        superavit_mes = ret_mes - meta_mes
        superavit_ano = ret_ano - meta_ano

        resultados.append({
            'Plano':           plano,
            'Tipo':            cfg['tipo'],
            'Meta Oficial':    cfg['descricao'],
            'Retorno Mês (%)': round(ret_mes, 4),
            'Meta Mês (%)':    round(meta_mes, 4),
            'Δ Mês (%)':       round(superavit_mes, 4),
            'Status Mês':      '🟢' if superavit_mes >= 0 else '🔴',
            'Retorno Ano (%)': round(ret_ano, 4),
            'Meta Ano (%)':    round(meta_ano, 4),
            'Δ Ano (%)':       round(superavit_ano, 4),
            'Status Ano':      '🟢' if superavit_ano >= 0 else '🔴',
        })

    # Alpha como referência para o dashboard (BD — mais crítico)
    alpha = next((r for r in resultados if 'Alpha' in r['Plano']), resultados[0] if resultados else {})

    return {
        'meta_mes':  round(alpha.get('Meta Mês (%)', 0.0), 4),
        'meta_ano':  round(alpha.get('Meta Ano (%)', 0.0), 4),
        'base_mes':  round(inpc_mes, 4),
        'base_ano':  round(inpc_ano, 4),
        'indice':    'INPC',
        'planos':    pd.DataFrame(resultados),
    }


# ── Atribuição de Performance ────────────────────────────────────────────────

RETORNO_SEGMENTO_REFERENCIA = {
    'Renda Fixa':                 10.5,
    'Renda Variável':             13.0,
    'Investimentos Estruturados': 11.5,
    'Investimentos no Exterior':  12.0,
    'Imóveis':                     9.0,
    'Operações com Participantes': 15.5,
}


def atribuicao_performance(
    df_carteira: pd.DataFrame,
    pl: float,
    benchmarks: dict,
    df_cotas: pd.DataFrame | None = None,
) -> dict:
    """
    Atribuição de performance simplificada (Brinson-Hood-Beebower).

    Decompõe o retorno estimado do portfólio em:
      - Contribuição por segmento (peso × retorno do segmento)
      - Contribuição por gestor
      - Efeito de alocação vs benchmark (CDI)

    Se df_cotas for fornecido, usa retorno real do mês para os planos;
    caso contrário, usa retorno estimado por segmento.
    """
    cdi_mes = benchmarks.get('cdi_mes', 0.0)
    cdi_ano = benchmarks.get('cdi_ano', 0.0)

    # ── 1. Contribuição por segmento ─────────────────────────────────────────
    grp = df_carteira.groupby('segmento')['val_ajustado'].sum()
    total_carteira = grp.sum()

    seg_rows = []
    retorno_total_est = 0.0
    for seg, valor in grp.items():
        peso = valor / pl
        ret_ref = RETORNO_SEGMENTO_REFERENCIA.get(seg, 10.0)
        ret_mes_est = ((1 + ret_ref / 100) ** (1 / 12) - 1) * 100
        contribuicao = peso * ret_mes_est
        retorno_total_est += contribuicao
        efeito_aloc = peso * (ret_mes_est - cdi_mes)

        seg_rows.append({
            'Segmento': seg,
            'Valor (R$ MM)': round(valor / 1e6, 1),
            'Peso (%)': round(peso * 100, 2),
            'Retorno Est. Mês (%)': round(ret_mes_est, 3),
            'Contribuição (pp)': round(contribuicao, 4),
            'Efeito Alocação (pp)': round(efeito_aloc, 4),
        })

    df_seg = pd.DataFrame(seg_rows).sort_values('Contribuição (pp)', ascending=False)

    # ── 2. Contribuição por gestor ─────────────────────────────────────────
    df_c = df_carteira.copy()
    df_c['gestor'] = df_c['descricao'].apply(_extrair_gestor)
    grp_g = df_c.groupby('gestor')['val_ajustado'].sum()

    gest_rows = []
    for gestor, valor in grp_g.items():
        peso = valor / pl
        gest_rows.append({
            'Gestor': gestor,
            'Valor (R$ MM)': round(valor / 1e6, 1),
            'Peso na Carteira (%)': round(peso * 100, 2),
            'Contribuição Estimada (pp)': round(peso * retorno_total_est, 4),
        })

    df_gest = pd.DataFrame(gest_rows).sort_values('Contribuição Estimada (pp)', ascending=False)

    # ── 3. Retorno real dos planos (se cotas disponíveis) ─────────────────
    df_planos = pd.DataFrame()
    if df_cotas is not None:
        ultimo = df_cotas[df_cotas['Data'] == df_cotas['Data'].max()]
        planos_nomes = ['PL Alpha', 'PL Beta', 'PL Gama']
        rows_p = []
        for nome in planos_nomes:
            r = ultimo[ultimo['fundo'] == nome]
            if r.empty:
                continue
            ret_m = r.iloc[0]['Mês_pct']
            rows_p.append({
                'Plano': nome,
                'Retorno Mês (%)': round(ret_m, 3),
                'vs CDI (pp)': round(ret_m - cdi_mes, 3),
                'vs IPCA (pp)': round(ret_m - benchmarks.get('ipca_mes', 0.0), 3),
                'Retorno No Ano (%)': round(r.iloc[0]['Ano_pct'], 3),
                'vs CDI Ano (pp)': round(r.iloc[0]['Ano_pct'] - cdi_ano, 3),
            })
        df_planos = pd.DataFrame(rows_p)

    return {
        'por_segmento': df_seg,
        'por_gestor': df_gest,
        'planos': df_planos,
        'retorno_estimado_mes': round(retorno_total_est, 4),
        'cdi_mes': cdi_mes,
    }


# ── Simulador de Realocação ──────────────────────────────────────────────────

RETORNOS_ESPERADOS = {
    'Renda Fixa':                 0.105,  # ~10.5% ao ano (CDI)
    'Renda Variável':             0.130,  # ~13% ao ano (estimativa histórica)
    'Investimentos Estruturados': 0.115,  # ~CDI + 1%
    'Investimentos no Exterior':  0.120,  # ~12% ao ano
    'Imóveis e FIIs':             0.090,  # ~9% ao ano
    'Operações com Participantes': 0.155, # CDI + taxa de adm
}


def simular_realocacao(pl: float, novas_alocacoes: dict) -> dict:
    """
    novas_alocacoes: {segmento: pct_pl} (entre 0 e 1)
    Retorna impacto no retorno esperado e compliance.
    """
    from rules_engine import SEGMENT_LIMITS, THRESHOLD_AMARELO

    retorno_esperado = sum(
        pct * RETORNOS_ESPERADOS.get(seg, 0.10)
        for seg, pct in novas_alocacoes.items()
    ) * 100

    compliance = {}
    for seg, pct in novas_alocacoes.items():
        limite = SEGMENT_LIMITS.get(seg, 1.0)
        ratio = pct / limite
        status = 'vermelho' if ratio > 1.0 else ('amarelo' if ratio > THRESHOLD_AMARELO else 'verde')
        compliance[seg] = {
            'pct_pl': pct,
            'pct_limite': ratio,
            'status': status,
            'valor': pct * pl,
        }

    return {
        'retorno_esperado_ano': round(retorno_esperado, 2),
        'compliance': compliance,
    }
