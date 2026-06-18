from dataclasses import dataclass
import pandas as pd

# Limites por segmento — Resolução CMN 4.994/2022 (revogou a CMN 4.661/2018)
SEGMENT_LIMITS: dict[str, float] = {
    'Renda Fixa':                  1.00,
    'Renda Variável':              0.70,
    'Investimentos Estruturados':  0.20,
    'Investimentos no Exterior':   0.15,
    'Imóveis e FIIs':              0.08,
    'Operações com Participantes': 0.15,
}

THRESHOLD_AMARELO = 0.80   # >80% do limite → atenção
THRESHOLD_VERMELHO = 1.00  # >100% do limite → crítico


@dataclass
class Alerta:
    segmento: str
    valor: float
    limite_abs: float
    pct_pl: float
    pct_limite: float
    status: str        # 'verde' | 'amarelo' | 'vermelho'


class ComplianceEngine:
    def __init__(self, carteira: pd.DataFrame, patrimonio_liquido: float,
                 extra_segmentos: dict | None = None):
        self.carteira = carteira
        self.pl = patrimonio_liquido
        self.extra = extra_segmentos or {}
        self.alertas: list[Alerta] = []
        self._executar()

    def _status(self, pct_pl: float, limite: float) -> str:
        ratio = pct_pl / limite
        if ratio > THRESHOLD_VERMELHO:
            return 'vermelho'
        # Segmentos com limite de 100% não geram ATENÇÃO — qualquer valor abaixo
        # de 100% é regulatoriamente normal para Renda Fixa
        if limite >= 1.0:
            return 'verde'
        if ratio > THRESHOLD_AMARELO:
            return 'amarelo'
        return 'verde'

    def _executar(self):
        totais = self.carteira.groupby('segmento')['val_ajustado'].sum()

        for seg, limite in SEGMENT_LIMITS.items():
            valor = float(totais.get(seg, 0.0)) + self.extra.get(seg, 0.0)
            pct_pl = valor / self.pl
            self.alertas.append(Alerta(
                segmento=seg,
                valor=valor,
                limite_abs=limite * self.pl,
                pct_pl=pct_pl,
                pct_limite=pct_pl / limite,
                status=self._status(pct_pl, limite),
            ))

    def resumo_segmentos(self) -> list[dict]:
        return [
            {
                'segmento':   a.segmento,
                'valor':      a.valor,
                'limite_abs': a.limite_abs,
                'pct_pl':     a.pct_pl,
                'limite_pct': SEGMENT_LIMITS[a.segmento],
                'pct_limite': a.pct_limite,
                'status':     a.status,
            }
            for a in self.alertas
        ]

    def contagem_status(self) -> dict:
        counts = {'verde': 0, 'amarelo': 0, 'vermelho': 0}
        for a in self.alertas:
            counts[a.status] += 1
        return counts

    def alertas_ativos(self) -> list[Alerta]:
        return [a for a in self.alertas if a.status != 'verde']
