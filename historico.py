import json
from datetime import datetime
from pathlib import Path

HISTORICO_DIR = Path(__file__).parent / "historico"


def salvar_snapshot(resumo: list[dict], pl: float, data_ref: str) -> Path:
    HISTORICO_DIR.mkdir(exist_ok=True)
    slug = data_ref.replace('/', '-')
    filepath = HISTORICO_DIR / f"{slug}_compliance.json"

    payload = {
        "data_referencia": data_ref,
        "salvo_em": datetime.now().isoformat(),
        "patrimonio_social": pl,
        "segmentos": [
            {
                "segmento":   r["segmento"],
                "valor":      r["valor"],
                "pct_pl":     r["pct_pl"],
                "limite_pct": r["limite_pct"],
                "pct_limite": r["pct_limite"],
                "status":     r["status"],
            }
            for r in resumo
        ],
    }

    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def carregar_historico() -> list[dict]:
    if not HISTORICO_DIR.exists():
        return []

    snapshots = []
    for f in sorted(HISTORICO_DIR.glob("*_compliance.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            snapshots.append(data)
        except Exception:
            continue

    return snapshots


def historico_para_dataframe(snapshots: list[dict]):
    import pandas as pd

    rows = []
    for snap in snapshots:
        for seg in snap["segmentos"]:
            rows.append({
                "Data":         snap["data_referencia"],
                "PS (R$ Bi)":   snap["patrimonio_social"] / 1e9,
                "Segmento":     seg["segmento"],
                "% do PS":      seg["pct_pl"] * 100,
                "Limite (%)":   seg["limite_pct"] * 100,
                "% do Limite":  seg["pct_limite"] * 100,
                "Status":       seg["status"],
            })

    return pd.DataFrame(rows)
