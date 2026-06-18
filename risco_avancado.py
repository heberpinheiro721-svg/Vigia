import numpy as np
import pandas as pd


# ── VaR & CVaR ───────────────────────────────────────────────────────────────

_Z = {0.90: 1.282, 0.95: 1.645, 0.975: 1.960, 0.99: 2.326}


def calcular_var(df_cotas: pd.DataFrame, nivel: float = 0.95) -> pd.DataFrame:
    """VaR histórico, paramétrico e CVaR (Expected Shortfall) por fundo."""
    pivot = df_cotas.pivot_table(index='Data', columns='fundo', values='Dia_pct')

    rows = []
    for fundo in pivot.columns:
        r = pivot[fundo].dropna().values / 100
        if len(r) < 3:
            continue

        mu = float(r.mean())
        sigma = float(r.std(ddof=1)) if len(r) > 1 else 0.0

        var_h = float(np.percentile(r, (1 - nivel) * 100))

        z = _Z.get(nivel, 1.645)
        var_p = mu - z * sigma

        tail = r[r <= var_h]
        cvar = float(tail.mean()) if len(tail) > 0 else var_h

        rows.append({
            'Fundo': fundo,
            'VaR Histórico (%)': round(var_h * 100, 3),
            'VaR Paramétrico (%)': round(var_p * 100, 3),
            'CVaR / ES (%)': round(cvar * 100, 3),
            'Vol. Diária (%)': round(sigma * 100, 3),
            'Vol. Anual (%)': round(sigma * np.sqrt(252) * 100, 2),
            'Retorno Médio/Dia (%)': round(mu * 100, 4),
            'N Dias': len(r),
        })

    return pd.DataFrame(rows).sort_values('VaR Histórico (%)')


# ── Drawdown ─────────────────────────────────────────────────────────────────

def calcular_drawdown(df_cotas: pd.DataFrame) -> pd.DataFrame:
    """Drawdown máximo e atual por fundo, calculado sobre cota_base100."""
    rows = []
    for fundo in df_cotas['fundo'].unique():
        df_f = df_cotas[df_cotas['fundo'] == fundo].sort_values('Data').reset_index(drop=True)
        if df_f.empty:
            continue

        cotas = df_f['cota_base100'].values
        peak = np.maximum.accumulate(cotas)
        dd = (cotas - peak) / peak * 100

        max_dd = float(dd.min())
        max_dd_idx = int(dd.argmin())
        atual_dd = float(dd[-1])
        peak_val = float(peak[max_dd_idx])
        peak_idx = max(0, max_dd_idx - np.argmax(cotas[:max_dd_idx + 1][::-1] >= peak_val))

        rows.append({
            'Fundo': fundo,
            'Drawdown Máximo (%)': round(max_dd, 3),
            'Drawdown Atual (%)': round(atual_dd, 3),
            'Data do Vale': df_f.iloc[max_dd_idx]['Data'].strftime('%d/%m/%Y'),
            'Retorno Mês (%)': round(float(df_f['Mês_pct'].iloc[-1]), 2),
        })

    return pd.DataFrame(rows).sort_values('Drawdown Máximo (%)')


# ── Correlação ───────────────────────────────────────────────────────────────

def calcular_correlacao(df_cotas: pd.DataFrame) -> pd.DataFrame:
    """Matriz de correlação dos retornos diários entre todos os fundos."""
    pivot = df_cotas.pivot_table(index='Data', columns='fundo', values='Dia_pct')
    return pivot.corr().round(3)


# ── Stress Test ───────────────────────────────────────────────────────────────

CENARIOS_STRESS = {
    'Crise Severa (2008-like)': {
        'Renda Fixa': -0.03,
        'Renda Variável': -0.45,
        'Investimentos Estruturados': -0.20,
        'Investimentos no Exterior': -0.30,
        'Imóveis': -0.08,
        'Operações com Participantes': 0.00,
    },
    'Alta de Juros (+5pp Selic)': {
        'Renda Fixa': 0.02,
        'Renda Variável': -0.20,
        'Investimentos Estruturados': -0.08,
        'Investimentos no Exterior': -0.12,
        'Imóveis': -0.05,
        'Operações com Participantes': 0.00,
    },
    'Cenário Base (CDI + 4%)': {
        'Renda Fixa': 0.125,
        'Renda Variável': 0.15,
        'Investimentos Estruturados': 0.13,
        'Investimentos no Exterior': 0.14,
        'Imóveis': 0.09,
        'Operações com Participantes': 0.155,
    },
    'Cenário Otimista (Bull Market)': {
        'Renda Fixa': 0.14,
        'Renda Variável': 0.35,
        'Investimentos Estruturados': 0.20,
        'Investimentos no Exterior': 0.25,
        'Imóveis': 0.12,
        'Operações com Participantes': 0.155,
    },
    'Recessão Moderada': {
        'Renda Fixa': 0.08,
        'Renda Variável': -0.25,
        'Investimentos Estruturados': -0.10,
        'Investimentos no Exterior': -0.15,
        'Imóveis': -0.03,
        'Operações com Participantes': 0.00,
    },
}


def stress_test(df_carteira: pd.DataFrame, pl: float,
                cenarios: dict | None = None) -> pd.DataFrame:
    """
    Calcula o impacto de cada cenário de stress no PL consolidado.
    cenarios: dict {nome: {segmento: retorno_anual}} — usa CENARIOS_STRESS se None.
    """
    if cenarios is None:
        cenarios = CENARIOS_STRESS

    seg_valores = df_carteira.groupby('segmento')['val_ajustado'].sum().to_dict()

    rows = []
    for nome, choques in cenarios.items():
        impacto = sum(seg_valores.get(seg, 0) * chq for seg, chq in choques.items())
        pl_novo = pl + impacto
        var_pct = impacto / pl * 100

        if impacto > 0:
            status = '🟢 Positivo'
        elif impacto > -pl * 0.05:
            status = '🟡 Moderado'
        else:
            status = '🔴 Severo'

        rows.append({
            'Cenário': nome,
            'Impacto (R$ MM)': round(impacto / 1e6, 1),
            'Variação (%)': round(var_pct, 2),
            'PL Resultante (R$ Bi)': round(pl_novo / 1e9, 3),
            'Avaliação': status,
        })

    return pd.DataFrame(rows)
