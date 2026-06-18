import unicodedata
import pandas as pd
from pathlib import Path


def _detectar_encoding(path: Path) -> str:
    """Tenta UTF-8 primeiro; cai para cp1252 (superset de latin-1) se falhar."""
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return 'latin-1'


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()


def classificar_segmento(cliente: str, descricao: str) -> str:
    c = _norm(cliente)
    d = _norm(descricao)

    # Investimentos no Exterior: veículo CP IE
    if 'CP IE' in c:
        return 'Investimentos no Exterior'

    # Renda Variável: veículo FIA ou Ações
    if 'FIC FIA' in c or 'ACOES' in c:
        return 'Renda Variável'

    # Veículos de plano específico: classificar pela descrição do fundo
    if any(kw in c for kw in ['PL ALPHA', 'PL BETA', 'PL GAMA', 'ADMINISTR']):
        if 'ACOES' in d or ' FIA' in d:
            return 'Renda Variável'
        if 'FIM' in d and 'CP IE' in d:
            return 'Investimentos no Exterior'
        if 'FIM' in d:
            return 'Investimentos Estruturados'
        return 'Renda Fixa'

    # Investimentos Estruturados: veículo FIM (sem CP IE)
    if 'CI FIM' in c:
        return 'Investimentos Estruturados'

    # Padrão: Renda Fixa (veículos RF, CIRF, ITAU RF, ALM, etc.)
    return 'Renda Fixa'


def load_carteira_s3(filepath: str | Path, patrimonio_liquido: float) -> pd.DataFrame:
    enc = _detectar_encoding(filepath)
    df = pd.read_csv(
        filepath,
        sep=';',
        decimal=',',
        encoding=enc,
        header=None,
        skiprows=1,
        dtype=str,
    )

    if df.shape[1] < 13:
        raise ValueError(f"Formato inesperado: {df.shape[1]} colunas (esperado 13).")

    df.columns = [
        'cliente', 'descricao', 'cnpj', 'isin', 'qtd',
        'val_nominal', 'rendimento', 'val_bruto', 'irrf', 'iof',
        'val_liquido', 'pct_seg', 'pct_pl',
    ]

    # Remove linhas de totais/resumo (CNPJ = '-')
    df = df[df['cnpj'].notna() & (df['cnpj'].str.strip() != '-')].copy()

    df['val_liquido'] = pd.to_numeric(
        df['val_liquido'].str.replace(',', '.', regex=False),
        errors='coerce',
    )
    df = df.dropna(subset=['val_liquido'])
    df = df[df['val_liquido'] > 0]

    # Deduplica: S3 Caceis gera 2 linhas por posição (artefato do sistema)
    df = df.drop_duplicates(subset=['cnpj'], keep='first').reset_index(drop=True)

    # Classifica segmento CMN 4.661
    df['segmento'] = df.apply(
        lambda r: classificar_segmento(r['cliente'], r['descricao']), axis=1
    )

    # Escala os valores ao PL real (corrige dupla contagem fundo-de-fundos)
    total_raw = df['val_liquido'].sum()
    escala = patrimonio_liquido / total_raw if total_raw > 0 else 1.0
    df['val_ajustado'] = (df['val_liquido'] * escala).round(2)
    df['pct_pl_calc'] = df['val_ajustado'] / patrimonio_liquido
    df['_total_raw'] = total_raw  # valor bruto S3 Caceis (antes do escalonamento)

    return df[[
        'cliente', 'descricao', 'cnpj',
        'val_liquido', 'val_ajustado', 'pct_pl_calc', 'segmento', '_total_raw',
    ]]
