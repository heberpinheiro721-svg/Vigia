import re
import unicodedata
import pandas as pd
import pdfplumber
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


# ── Parser de PDF de Composição da Carteira (S3 Caceis) ──────────────────────

_RE_CNPJ     = re.compile(r'\b(\d{14})\b')
_RE_DATA_POS = re.compile(r'Data da Posi.*?:\s*(\d{2}/\d{2}/\d{4})', re.IGNORECASE)
_RE_CUST     = re.compile(r'(CUST\d+)\s*-\s*(.+)', re.IGNORECASE)
_RE_COMP_HDR = re.compile(r'Composi.*Carteira', re.IGNORECASE)


def _num_pdf(s: str) -> float:
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


def _parse_composicao_pdf(filepath) -> pd.DataFrame:
    """Extrai posições de todos os planos/datas de um PDF de Composição (S3 Caceis)."""
    rows = []
    with pdfplumber.open(filepath) as pdf:
        for pg in pdf.pages:
            txt = pg.extract_text() or ''
            linhas = [l for l in txt.split('\n') if l.strip()]

            # Ignora páginas que não são de composição de carteira
            if not any(_RE_COMP_HDR.search(l) for l in linhas[:3]):
                continue

            data_pos = None
            cliente  = ''

            for l in linhas:
                m = _RE_DATA_POS.search(l)
                if m:
                    data_pos = pd.to_datetime(m.group(1), dayfirst=True)
                    continue
                m2 = _RE_CUST.search(l)
                if m2:
                    cliente = m2.group(2).strip()
                    continue

                stripped = l.strip()
                if not stripped:
                    continue
                if stripped.startswith('Total') or 'Valores Expressos' in stripped:
                    continue
                if 'Descri' in stripped and 'CNPJ' in stripped:
                    continue

                # Linha de dado: precisa ter CNPJ de 14 dígitos
                m3 = _RE_CNPJ.search(l)
                if not m3:
                    continue

                cnpj     = m3.group(1)
                descricao = l[:m3.start()].strip()
                rest     = l[m3.end():].strip().split()

                # Posições após CNPJ: ISIN qtd val_nominal rendimento val_bruto irrf iof val_liquido pct_seg pct_pl
                if len(rest) < 8:
                    continue

                val_liq = _num_pdf(rest[7])
                if val_liq <= 0:
                    continue

                rows.append({
                    'data_pos':    data_pos,
                    'cliente':     cliente,
                    'descricao':   descricao,
                    'cnpj':        cnpj,
                    'val_liquido': val_liq,
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['segmento'] = df.apply(
        lambda r: classificar_segmento(r['cliente'], r['descricao']), axis=1
    )
    return df


def carteira_para_mes(df_hist: pd.DataFrame, patrimonio_liquido: float,
                      ano: int, mes: int) -> pd.DataFrame | None:
    """
    Filtra o DataFrame histórico para o snapshot mais próximo do mês solicitado,
    escala ao PL informado e retorna no mesmo formato de load_carteira_s3.
    Retorna None se não houver dados para o período.
    """
    if df_hist.empty:
        return None

    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    limite     = pd.Timestamp(ano, mes, ultimo_dia)
    inicio     = pd.Timestamp(ano, mes, 1)

    # Snapshots disponíveis no mês escolhido
    datas_mes = df_hist[
        (df_hist['data_pos'] >= inicio) & (df_hist['data_pos'] <= limite)
    ]['data_pos'].unique()

    if len(datas_mes) == 0:
        return None

    # Usa o snapshot mais recente do mês
    data_sel = max(datas_mes)
    df = df_hist[df_hist['data_pos'] == data_sel].copy()

    # Consolida: mesmo fundo aparece em múltiplos planos — soma os valores
    df = (
        df.groupby('cnpj', as_index=False)
        .agg(cliente=('cliente', 'first'), descricao=('descricao', 'first'),
             val_liquido=('val_liquido', 'sum'), segmento=('segmento', 'first'))
    )

    # Escala ao PL do mês
    total_raw = df['val_liquido'].sum()
    escala    = patrimonio_liquido / total_raw if total_raw > 0 else 1.0
    df['val_ajustado'] = (df['val_liquido'] * escala).round(2)
    df['pct_pl_calc']  = df['val_ajustado'] / patrimonio_liquido
    df['_total_raw']   = total_raw

    return df[['cliente', 'descricao', 'cnpj',
               'val_liquido', 'val_ajustado', 'pct_pl_calc', 'segmento', '_total_raw']]


def load_carteira_historica(data_dir: Path) -> pd.DataFrame:
    """
    Carrega composições históricas de todos os PDFs em data/Composição/.
    Retorna DataFrame com coluna data_pos para filtragem por mês.
    """
    comp_dir = Path(data_dir) / 'Composição'
    if not comp_dir.exists():
        return pd.DataFrame()

    dfs = []
    for pdf_path in sorted(comp_dir.glob('*.pdf')):
        try:
            df_pdf = _parse_composicao_pdf(pdf_path)
            if not df_pdf.empty:
                dfs.append(df_pdf)
        except Exception:
            continue

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    df = df.dropna(subset=['data_pos', 'val_liquido'])
    df = df[df['val_liquido'] > 0]
    return df
