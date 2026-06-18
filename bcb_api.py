import requests
import calendar as _calendar
from datetime import datetime

BCB_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"

SERIES = {
    'cdi_diario': 11,
    'ipca_mensal': 433,
    'inpc_mensal': 188,
    'selic_meta':  432,
}


def _fetch(serie: int, inicio: str, fim: str) -> list[dict]:
    url = f"{BCB_BASE.format(serie=serie)}?formato=json&dataInicial={inicio}&dataFinal={fim}"
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def _num(s) -> float:
    try:
        return float(str(s).replace(',', '.'))
    except Exception:
        return 0.0


def get_cdi_mes(ano: int, mes: int) -> float:
    """Retorna CDI acumulado do mês em % (ex: 0.89 = 0,89%)."""
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"01/{mes:02d}/{ano}"
    fim    = f"{ultimo_dia}/{mes:02d}/{ano}"
    dados  = _fetch(SERIES['cdi_diario'], inicio, fim)
    if not dados:
        return 0.0
    acum = 1.0
    for d in dados:
        taxa = _num(d.get('valor', 0)) / 100
        acum *= (1 + taxa)
    return (acum - 1) * 100


def get_ipca_mes(ano: int, mes: int) -> float:
    """Retorna IPCA do mês em % (ex: 0.56 = 0,56%)."""
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"01/{mes:02d}/{ano}"
    fim    = f"{ultimo_dia}/{mes:02d}/{ano}"
    dados  = _fetch(SERIES['ipca_mensal'], inicio, fim)
    for d in dados:
        try:
            d_mes = int(d['data'].split('/')[1])
            d_ano = int(d['data'].split('/')[2])
            if d_mes == mes and d_ano == ano:
                return _num(d['valor'])
        except Exception:
            continue
    return 0.0


def get_cdi_ano(ano: int) -> float:
    """Retorna CDI acumulado no ano em %."""
    dados = _fetch(SERIES['cdi_diario'], f"01/01/{ano}", f"31/12/{ano}")
    if not dados:
        return 0.0
    acum = 1.0
    for d in dados:
        taxa = _num(d.get('valor', 0)) / 100
        acum *= (1 + taxa)
    return (acum - 1) * 100


def get_ipca_ano(ano: int) -> float:
    """Retorna IPCA acumulado no ano em %."""
    dados = _fetch(SERIES['ipca_mensal'], f"01/01/{ano}", f"31/12/{ano}")
    if not dados:
        return 0.0
    acum = 1.0
    for d in dados:
        acum *= (1 + _num(d.get('valor', 0)) / 100)
    return (acum - 1) * 100


def get_inpc_mes(ano: int, mes: int) -> float:
    """Retorna INPC do mês em % (série BCB 188)."""
    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    inicio = f"01/{mes:02d}/{ano}"
    fim    = f"{ultimo_dia}/{mes:02d}/{ano}"
    dados  = _fetch(SERIES['inpc_mensal'], inicio, fim)
    for d in dados:
        try:
            d_mes = int(d['data'].split('/')[1])
            d_ano = int(d['data'].split('/')[2])
            if d_mes == mes and d_ano == ano:
                return _num(d['valor'])
        except Exception:
            continue
    return 0.0


def get_inpc_ano(ano: int) -> float:
    """Retorna INPC acumulado no ano em %."""
    dados = _fetch(SERIES['inpc_mensal'], f"01/01/{ano}", f"31/12/{ano}")
    if not dados:
        return 0.0
    acum = 1.0
    for d in dados:
        acum *= (1 + _num(d.get('valor', 0)) / 100)
    return (acum - 1) * 100


def get_ibov_mes(ano: int, mes: int) -> float:
    """Retorna variação do Ibovespa no mês em %."""
    try:
        import yfinance as yf
        ultimo_dia = _calendar.monthrange(ano, mes)[1]
        inicio = datetime(ano, mes, 1).strftime('%Y-%m-%d')
        fim    = datetime(ano, mes, ultimo_dia).strftime('%Y-%m-%d')
        # +5 dias para garantir que pegue o último pregão do mês
        from datetime import timedelta
        fim_ext = (datetime(ano, mes, ultimo_dia) + timedelta(days=5)).strftime('%Y-%m-%d')
        ibov = yf.download('^BVSP', start=inicio, end=fim_ext,
                           progress=False, auto_adjust=True)
        # Filtra só o mês solicitado
        ibov = ibov[ibov.index.month == mes]
        if ibov.empty:
            return 0.0
        p0 = float(ibov['Close'].iloc[0].item())
        p1 = float(ibov['Close'].iloc[-1].item())
        return round((p1 / p0 - 1) * 100, 2)
    except Exception:
        return 0.0


def get_ibov_ano(ano: int) -> float:
    """Retorna variação acumulada do Ibovespa no ano em %."""
    try:
        import yfinance as yf
        inicio = datetime(ano, 1, 1).strftime('%Y-%m-%d')
        fim    = datetime.now().strftime('%Y-%m-%d')
        ibov = yf.download('^BVSP', start=inicio, end=fim,
                           progress=False, auto_adjust=True)
        ibov = ibov[ibov.index.year == ano]
        if ibov.empty:
            return 0.0
        p0 = float(ibov['Close'].iloc[0].item())
        p1 = float(ibov['Close'].iloc[-1].item())
        return round((p1 / p0 - 1) * 100, 2)
    except Exception:
        return 0.0


def get_benchmarks(ano: int, mes: int) -> dict:
    """Retorna CDI, IPCA, INPC e Ibovespa do mês e do ano."""
    return {
        'cdi_mes':   get_cdi_mes(ano, mes),
        'ipca_mes':  get_ipca_mes(ano, mes),
        'inpc_mes':  get_inpc_mes(ano, mes),
        'cdi_ano':   get_cdi_ano(ano),
        'ipca_ano':  get_ipca_ano(ano),
        'inpc_ano':  get_inpc_ano(ano),
        'ibov_mes':  get_ibov_mes(ano, mes),
        'ibov_ano':  get_ibov_ano(ano),
    }
