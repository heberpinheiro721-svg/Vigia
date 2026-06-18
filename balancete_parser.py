import re
import pdfplumber
import openpyxl
from pathlib import Path


def _num(s: str) -> float:
    s = s.strip()
    negativo = s.startswith('(') and s.endswith(')')
    s = s.replace('(', '').replace(')', '').replace('.', '').replace(',', '.')
    try:
        return -float(s) if negativo else float(s)
    except ValueError:
        return 0.0


def _extrair_saldo_final(linha: str) -> float | None:
    nums = re.findall(r'\(?\d{1,3}(?:\.\d{3})*,\d{2}\)?', linha)
    if nums:
        return _num(nums[-1])
    return None


CONTAS = {
    '1000000000000': 'ativo_total',
    '1020000000000': 'realizavel',
    '1020300000000': 'investimentos',
    '1020308000000': 'emprestimos_participantes',
    '2030000000000': 'patrimonio_social',
    '2030100000000': 'patrimonio_cobertura',
}

PLANOS_NOME_REGEX = re.compile(r'Plano\s+(ALPHA|BETA|GAMA)', re.IGNORECASE)
FUNCOES_PGA = {'99901', '99701', '99702', '99703'}
FUNCAO_REGEX = re.compile(r'Fun[çc][ãa]o:\s*(\d+)', re.IGNORECASE)
TODOS_PLANOS = ['Alpha', 'Beta', 'Gama', 'PGA']


def _detectar_plano_pdf(texto: str) -> str | None:
    m_func = FUNCAO_REGEX.search(texto)
    if m_func and m_func.group(1) in FUNCOES_PGA:
        return 'PGA'
    m_nome = PLANOS_NOME_REGEX.search(texto)
    if m_nome:
        return {'ALPHA': 'Alpha', 'BETA': 'Beta', 'GAMA': 'Gama'}.get(
            m_nome.group(1).upper()
        )
    return None


def _detectar_plano_xlsx(nome_col9: str, func_code: str) -> str | None:
    """Detecta plano pela col 9 (nome) e col 6 (código de função) do XLSX."""
    nome = str(nome_col9 or '').upper()
    code = str(func_code or '').strip()
    if 'PGA' in nome or code in FUNCOES_PGA:
        return 'PGA'
    if 'ALPHA' in nome:
        return 'Alpha'
    if 'BETA' in nome:
        return 'Beta'
    if 'GAMA' in nome:
        return 'Gama'
    return None


def _consolidar(planos: dict, campos: list) -> dict:
    consolidado = {c: 0.0 for c in campos}
    for dados in planos.values():
        for campo, valor in dados.items():
            if valor is not None:
                consolidado[campo] += valor
    for p in planos:
        for c in campos:
            if planos[p][c] is None:
                planos[p][c] = 0.0
    return consolidado


def _parse_pdf(filepath) -> dict:
    campos = list(CONTAS.values())
    planos = {p: {c: None for c in campos} for p in TODOS_PLANOS}
    plano_atual = None

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ''
            novo = _detectar_plano_pdf(texto)
            if novo:
                plano_atual = novo
            if plano_atual is None:
                continue
            for linha in texto.split('\n'):
                linha = linha.strip()
                for conta, campo in CONTAS.items():
                    if linha.startswith(conta + ' ') or linha.startswith(conta + '\t'):
                        if planos[plano_atual][campo] is None:
                            valor = _extrair_saldo_final(linha)
                            if valor is not None:
                                planos[plano_atual][campo] = abs(valor)

    return {'planos': planos, 'consolidado': _consolidar(planos, list(CONTAS.values()))}


def _parse_xlsx(filepath) -> dict:
    """
    Formato CACEIS/SANGEST XLSX:
      Col 1 (idx 0)  — código da conta
      Col 2 (idx 1)  — 'Função:' nas linhas de identificação do plano
      Col 6 (idx 5)  — código de função (99701/99702/99703 = PGA)
      Col 9 (idx 8)  — nome do plano ('Plano ALPHA', 'Operações PGA - Alpha', …)
      Col 43 (idx 42) — total acumulado do período
    """
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    campos = list(CONTAS.values())
    planos = {p: {c: None for c in campos} for p in TODOS_PLANOS}
    plano_atual = None
    IDX_TOTAL = 42  # coluna 43 em 0-based

    for row in ws.iter_rows(values_only=True):
        if len(row) < 9:
            continue

        # Linha de identificação: col 2 (idx 1) contém 'Função' ou 'Funcao'
        cell_b = str(row[1] or '').lower()
        if 'fun' in cell_b and row[8]:
            novo = _detectar_plano_xlsx(row[8], row[5])
            if novo:
                plano_atual = novo
            continue

        # Linha de conta: col 1 (idx 0) tem o código
        if plano_atual and row[0]:
            conta = str(row[0]).strip()
            if conta in CONTAS:
                campo = CONTAS[conta]
                if len(row) > IDX_TOTAL:
                    valor = row[IDX_TOTAL]
                    if isinstance(valor, (int, float)):
                        abs_valor = abs(float(valor))
                        if plano_atual == 'PGA':
                            # PGA tem 3 sub-seções (Alpha/Beta/Gama) — acumula
                            planos['PGA'][campo] = (planos['PGA'][campo] or 0.0) + abs_valor
                        elif planos[plano_atual][campo] is None:
                            planos[plano_atual][campo] = abs_valor

    return {'planos': planos, 'consolidado': _consolidar(planos, campos)}


def parse_balancete(filepath) -> dict:
    ext = Path(filepath).suffix.lower()
    if ext == '.xlsx':
        return _parse_xlsx(filepath)
    return _parse_pdf(filepath)


def achar_balancete(data_dir: Path):
    bal_dir = data_dir / 'Balancete'
    if bal_dir.exists():
        # Prioriza XLSX (mais recente por mtime), depois PDF
        for padrao in ('*.xlsx', '*.pdf'):
            arquivos = sorted(bal_dir.glob(padrao),
                              key=lambda x: x.stat().st_mtime, reverse=True)
            if arquivos:
                return arquivos[0]
    return None
