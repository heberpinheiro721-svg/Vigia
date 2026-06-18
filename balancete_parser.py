import re
import pdfplumber
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
    '1020300000000': 'investimentos',        # Investimentos (conta principal)
    '1020308000000': 'emprestimos_participantes',
    '2030000000000': 'patrimonio_social',
    '2030100000000': 'patrimonio_cobertura',
}

# Planos pelo nome
PLANOS_NOME_REGEX = re.compile(r'Plano\s+(ALPHA|BETA|GAMA)', re.IGNORECASE)

# PGA identificado pelos códigos de função
FUNCOES_PGA = {'99901', '99701', '99702', '99703'}
FUNCAO_REGEX = re.compile(r'Fun[çc][ãa]o:\s*(\d+)', re.IGNORECASE)

TODOS_PLANOS = ['Alpha', 'Beta', 'Gama', 'PGA']


def _detectar_plano(texto: str) -> str | None:
    # Verifica se é PGA pelos códigos de função
    m_func = FUNCAO_REGEX.search(texto)
    if m_func and m_func.group(1) in FUNCOES_PGA:
        return 'PGA'

    # Verifica plano pelo nome
    m_nome = PLANOS_NOME_REGEX.search(texto)
    if m_nome:
        return {'ALPHA': 'Alpha', 'BETA': 'Beta', 'GAMA': 'Gama'}.get(
            m_nome.group(1).upper()
        )
    return None


def parse_balancete(filepath) -> dict:
    campos = list(CONTAS.values())
    planos = {p: {c: None for c in campos} for p in TODOS_PLANOS}
    plano_atual = None

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ''

            novo_plano = _detectar_plano(texto)
            if novo_plano:
                plano_atual = novo_plano

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

    # Consolida somando todos os planos
    consolidado = {c: 0.0 for c in campos}
    for dados in planos.values():
        for campo, valor in dados.items():
            if valor is not None:
                consolidado[campo] += valor

    # Preenche None com 0
    for p in planos:
        for c in campos:
            if planos[p][c] is None:
                planos[p][c] = 0.0

    return {'planos': planos, 'consolidado': consolidado}


def achar_balancete(data_dir: Path):
    bal_dir = data_dir / 'Balancete'
    if bal_dir.exists():
        pdfs = sorted(bal_dir.glob('*.pdf'), key=lambda x: x.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0]
    return None
