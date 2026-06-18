import feedparser
import re
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

BRT = timezone(timedelta(hours=-3))

# ── Fontes EFPC & Previdência Complementar ────────────────────────────────────
FONTES_EFPC = [
    {
        'nome': 'Google News — EFPC/PREVIC',
        'url': (
            'https://news.google.com/rss/search'
            '?q=EFPC+OR+PREVIC+OR+%22previd%C3%AAncia+complementar%22+OR+%22fundo+de+pens%C3%A3o%22'
            '&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        ),
        'filtro': [],
    },
    {
        'nome': 'Google News — ABRAPP/Gestão',
        'url': (
            'https://news.google.com/rss/search'
            '?q=ABRAPP+OR+ANAPAR+OR+%22pens%C3%A3o+fechada%22+OR+%22regime+pr%C3%B3prio%22'
            '&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        ),
        'filtro': [],
    },
    {
        'nome': 'Agência Brasil',
        'url': 'https://agenciabrasil.ebc.com.br/rss/economia/feed.xml',
        'filtro': ['previdência', 'pensão', 'efpc', 'previc', 'fundo', 'aposentadoria', 'contribuição'],
    },
    {
        'nome': 'PREVIC — gov.br',
        'url': 'https://www.gov.br/previc/pt-br/assuntos/noticias/RSS',
        'filtro': [],
    },
    {
        'nome': 'Ministério da Previdência — gov.br',
        'url': 'https://www.gov.br/previdencia/pt-br/assuntos/noticias/RSS',
        'filtro': [],
    },
]

# ── Fontes Mercado Financeiro ─────────────────────────────────────────────────
FONTES_MERCADO = [
    {
        'nome': 'Infomoney',
        'url': 'https://www.infomoney.com.br/feed/',
        'filtro': [],
    },
    {
        'nome': 'CNN Brasil — Economia',
        'url': 'https://www.cnnbrasil.com.br/economia/feed/',
        'filtro': [],
    },
    {
        'nome': 'Valor Econômico',
        'url': 'https://valor.globo.com/rss/financas/',
        'filtro': [],
    },
    {
        'nome': 'Agência Brasil — Mercado',
        'url': 'https://agenciabrasil.ebc.com.br/rss/economia/feed.xml',
        'filtro': ['cdi', 'selic', 'ipca', 'ibovespa', 'b3', 'taxa', 'inflação', 'juros', 'mercado', 'ações', 'dólar'],
    },
    {
        'nome': 'Google News — Investimentos',
        'url': (
            'https://news.google.com/rss/search'
            '?q=Selic+CDI+IPCA+investimentos+renda+fixa+OR+renda+vari%C3%A1vel+mercado+financeiro'
            '&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        ),
        'filtro': [],
    },
    {
        'nome': 'CVM — gov.br',
        'url': 'https://www.gov.br/cvm/pt-br/assuntos/noticias/RSS',
        'filtro': [],
    },
    {
        'nome': 'Tesouro Nacional — gov.br',
        'url': 'https://www.gov.br/tesouronacional/pt-br/assuntos/noticias/RSS',
        'filtro': [],
    },
    {
        'nome': 'Banco Central — gov.br',
        'url': 'https://www.bcb.gov.br/api/feed/pt-br/noticias',
        'filtro': [],
    },
]


def _limpar_html(texto: str) -> str:
    return re.sub(r'<[^>]+>', '', texto or '').strip()


def _parse_data(entry) -> datetime | None:
    try:
        # published_parsed é sempre UTC — converte para Brasília (UTC-3)
        dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt_utc.astimezone(BRT)
    except Exception:
        return None


def _formatar_data(dt: datetime | None) -> str:
    if not dt:
        return ''
    return dt.strftime('%d/%m/%Y %H:%M')


def _extrair_fonte(entry, feed_nome: str) -> str:
    fonte = entry.get('source', {}).get('title', '') or feed_nome
    # Remove sufixo do Google News do título
    return fonte.split(' - ')[-1].strip() if ' - ' in fonte else fonte


def _buscar_feed(cfg: dict, limite: int) -> list[dict]:
    try:
        feed = feedparser.parse(cfg['url'])
        filtro = [f.lower() for f in cfg.get('filtro', [])]
        resultado = []

        for entry in feed.entries:
            titulo  = _limpar_html(entry.get('title', ''))
            resumo  = _limpar_html(entry.get('summary', ''))
            link    = entry.get('link', '')
            dt      = _parse_data(entry)
            fonte   = _extrair_fonte(entry, cfg['nome'])

            # Remove sufixo "- Fonte" que o Google News adiciona ao título
            if ' - ' in titulo:
                partes = titulo.rsplit(' - ', 1)
                titulo = partes[0].strip()
                if not fonte or fonte == cfg['nome']:
                    fonte = partes[1].strip()

            if not titulo or not link:
                continue

            # Aplica filtro de palavras-chave se configurado
            if filtro:
                texto_busca = (titulo + ' ' + resumo).lower()
                if not any(kw in texto_busca for kw in filtro):
                    continue

            resultado.append({
                'titulo': titulo,
                'resumo': resumo[:200] + ('…' if len(resumo) > 200 else ''),
                'link':   link,
                'fonte':  fonte,
                'data':   _formatar_data(dt),
                'dt':     dt,
            })

            if len(resultado) >= limite:
                break

        return resultado
    except Exception:
        return []


def _deduplicar(noticias: list[dict]) -> list[dict]:
    vistos = set()
    unicas = []
    for n in noticias:
        # Chave: primeiras 6 palavras do título (ignora variações de formatação)
        chave = ' '.join(n['titulo'].lower().split()[:6])
        if chave not in vistos:
            vistos.add(chave)
            unicas.append(n)
    return unicas


def buscar_coluna(fontes: list[dict], limite_total: int = 10) -> list[dict]:
    """Busca notícias de múltiplas fontes em paralelo e retorna as mais recentes."""
    todas = []
    limite_por_fonte = max(4, limite_total // len(fontes) + 2)

    with ThreadPoolExecutor(max_workers=len(fontes)) as ex:
        futuros = {ex.submit(_buscar_feed, cfg, limite_por_fonte): cfg for cfg in fontes}
        for fut in as_completed(futuros):
            todas.extend(fut.result())

    # Ordena por data (mais recentes primeiro), sem data vai pro fim
    _min = datetime.min.replace(tzinfo=BRT)
    todas.sort(key=lambda n: n['dt'] or _min, reverse=True)
    todas = _deduplicar(todas)
    return todas[:limite_total]


# Atalhos para o app.py
def buscar_noticias_efpc(limite: int = 10) -> list[dict]:
    return buscar_coluna(FONTES_EFPC, limite)


def buscar_noticias_mercado(limite: int = 10) -> list[dict]:
    return buscar_coluna(FONTES_MERCADO, limite)
