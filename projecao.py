import numpy as np
import pandas as pd


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def monte_carlo_patrimonio(
    pl: float,
    retorno_anual: float,
    volatilidade_anual: float,
    anos: int = 10,
    n_sim: int = 500,
    seed: int = 42,
    data_inicio: str = '2026-03-01',
) -> tuple[pd.DatetimeIndex, dict, np.ndarray]:
    """
    Simula trajetórias do patrimônio líquido com passos mensais.

    Returns:
        datas: DatetimeIndex com os períodos
        percentis: dict com p5, p25, p50, p75, p95 (arrays)
        trajetorias: matriz (n_sim × n_steps+1) — todas as trajetórias
    """
    np.random.seed(seed)
    mu_m = retorno_anual / 12
    sigma_m = volatilidade_anual / np.sqrt(12)
    n_steps = anos * 12

    traj = np.zeros((n_sim, n_steps + 1))
    traj[:, 0] = pl

    for t in range(1, n_steps + 1):
        z = np.random.standard_normal(n_sim)
        traj[:, t] = traj[:, t - 1] * np.exp(
            (mu_m - 0.5 * sigma_m ** 2) + sigma_m * z
        )

    datas = pd.date_range(data_inicio, periods=n_steps + 1, freq='MS')

    percentis = {
        'p5':  np.percentile(traj, 5,  axis=0),
        'p25': np.percentile(traj, 25, axis=0),
        'p50': np.percentile(traj, 50, axis=0),
        'p75': np.percentile(traj, 75, axis=0),
        'p95': np.percentile(traj, 95, axis=0),
    }

    return datas, percentis, traj


# ── Projeção por Cenários ─────────────────────────────────────────────────────

# Cenários alinhados ao Focus BCB (nov/2024) das Políticas de Investimentos 2025-2029
# Meta atuarial Alpha: INPC + 5,24% ≈ 9-10% a.a. | Selic projetada: 11,5% (2025) → 9% (2029)
CENARIOS_PROJECAO = {
    'Abaixo da Meta (~7% a.a.)':        {'retorno': 0.07,  'cor': '#E74C3C'},
    'Na Meta Atuarial (~9,5% a.a.)':    {'retorno': 0.095, 'cor': '#F39C12'},
    'Base — Selic Focus (~11% a.a.)':   {'retorno': 0.11,  'cor': '#2E86C1'},
    'Otimista — CDI+2% (~13% a.a.)':    {'retorno': 0.13,  'cor': '#27AE60'},
}


def projetar_cenarios(
    pl: float,
    anos: int = 10,
    data_inicio: str = '2026-03-01',
    cenarios: dict | None = None,
) -> tuple[pd.DatetimeIndex, dict]:
    """
    Projeção determinística de patrimônio para cada cenário de retorno anual.

    Returns:
        datas: DatetimeIndex
        resultado: {nome_cenario: {'valores': list, 'cor': str, 'retorno': float}}
    """
    if cenarios is None:
        cenarios = CENARIOS_PROJECAO

    datas = pd.date_range(data_inicio, periods=anos * 12 + 1, freq='MS')

    resultado = {}
    for nome, params in cenarios.items():
        mu_m = params['retorno'] / 12
        valores = [pl]
        for _ in range(anos * 12):
            valores.append(valores[-1] * (1 + mu_m))
        resultado[nome] = {
            'valores': valores,
            'cor': params['cor'],
            'retorno': params['retorno'],
        }

    return datas, resultado


# ── Resumo de probabilidades (Monte Carlo) ─────────────────────────────────────

def resumo_monte_carlo(
    pl: float,
    traj: np.ndarray,
    datas: pd.DatetimeIndex,
    meta_pl: float | None = None,
) -> pd.DataFrame:
    """
    Tabela de resumo: PL em t=1, 3, 5, 10 anos com percentis e prob. de atingir meta.
    """
    marcos = {1: 12, 3: 36, 5: 60, 10: 120}
    rows = []
    for anos_label, step in marcos.items():
        if step >= traj.shape[1]:
            continue
        vals = traj[:, step]
        prob_meta = float((vals >= meta_pl).mean() * 100) if meta_pl else None
        rows.append({
            'Horizonte': f'{anos_label} ano{"s" if anos_label > 1 else ""}',
            'Mediana (R$ Bi)': round(float(np.median(vals)) / 1e9, 3),
            'P25 (R$ Bi)': round(float(np.percentile(vals, 25)) / 1e9, 3),
            'P75 (R$ Bi)': round(float(np.percentile(vals, 75)) / 1e9, 3),
            'P5 (pior 5%) (R$ Bi)': round(float(np.percentile(vals, 5)) / 1e9, 3),
            'P95 (melhor 5%) (R$ Bi)': round(float(np.percentile(vals, 95)) / 1e9, 3),
            **({'Prob. ≥ Meta (%)': round(prob_meta, 1)} if prob_meta is not None else {}),
        })
    return pd.DataFrame(rows)
