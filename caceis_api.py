from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_CACHE: dict = {"token": None, "expires_at": 0}
_AUTH_ENDPOINT = "/APIGateway/security/authenticate"

# Códigos dos planos IAJA no Caceis
FUNDOS = {
    "Alpha": "CUST1811",
    "Beta":  "CUST1812",
    "Gama":  "CUST1813",
    "PGA":   "CUST1814",
}


def _base_url() -> str:
    cfg = st.secrets.get("caceis", {})
    return cfg.get("url_prod", "https://servico.s3caceis.com.br")


def _get_token() -> str | None:
    """Retorna token válido, renovando automaticamente se expirado (TTL 15 min)."""
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"] - 30:
        return _TOKEN_CACHE["token"]

    cfg = st.secrets.get("caceis", {})
    try:
        r = requests.post(
            _base_url() + _AUTH_ENDPOINT,
            headers={
                "API_KEY":           cfg.get("api_key", ""),
                "DIGITAL_SIGNATURE": cfg.get("digital_signature", ""),
                "Content-Type":      "application/x-www-form-urlencoded",
            },
            data={
                "username": cfg.get("username", ""),
                "password": cfg.get("password", ""),
            },
            timeout=15,
            verify=False,
        )
        if r.status_code == 200 and r.text.startswith("ey"):
            _TOKEN_CACHE["token"] = r.text.strip()
            _TOKEN_CACHE["expires_at"] = now + 900
            return _TOKEN_CACHE["token"]
    except Exception:
        pass
    return None


def _soap_headers() -> dict:
    token = _get_token()
    cfg = st.secrets.get("caceis", {})
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/xml"}
    code = cfg.get("ptf_code", "")
    if code:
        h["PortfolioCode"] = code
    return h


# ── Parser XML ────────────────────────────────────────────────────────────────

def _v(row: ET.Element, tag: str) -> str:
    el = row.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _f(row: ET.Element, tag: str) -> float:
    try:
        return float(_v(row, tag))
    except ValueError:
        return 0.0


def parse_cost_basis(xml_text: str) -> dict:
    """Parseia resposta do RequestCostBasis e retorna dict estruturado."""
    result: dict = {
        "patrimonio": 0.0,
        "vlr_cota":   0.0,
        "qtd_cotas":  0.0,
        "rent": {
            "diaria": 0.0, "mensal": 0.0, "anual": 0.0,
            "ult_6m": 0.0, "ult_12m": 0.0,
            "pct_cdi": 0.0, "rent_real_dia": 0.0,
        },
        "fi": [],    # fundos de investimento
        "rf": [],    # renda fixa
        "rv": [],    # renda variável
        "cpr": [],   # provisões
    }

    try:
        # Extrai apenas o conteúdo do Result para evitar namespaces SOAP
        inicio = xml_text.find("<ROWSET>")
        fim = xml_text.rfind("</ROWSET>") + len("</ROWSET>")
        if inicio == -1:
            return result
        inner = f"<ROOT>{xml_text[inicio:fim]}</ROOT>"
        root = ET.fromstring(inner)
    except ET.ParseError:
        return result

    for row in root.iter("ROW"):
        report = _v(row, "REPORT")

        if report == "CD_RENT":
            idx = _v(row, "CD_INDEXADOR")
            if idx == "COTA":
                result["rent"]["diaria"]  = _f(row, "PC_VAR_DIARIA")
                result["rent"]["mensal"]  = _f(row, "PC_VAR_MENSAL")
                result["rent"]["anual"]   = _f(row, "PC_VAR_ANUAL")
                result["rent"]["ult_6m"]  = _f(row, "PC_ULT_6_MESES")
                result["rent"]["ult_12m"] = _f(row, "PC_ULT_12_MESES")
            elif idx == "CDI":
                result["rent"]["pct_cdi"]      = _f(row, "PC_BENCHMARK")
                result["rent"]["rent_real_dia"] = _f(row, "PC_RENT_REAL")
            elif idx == "PATRIMON":
                result["patrimonio"] = _f(row, "VL_PATRIMONIO")
            elif idx == "Vlr Cota":
                result["vlr_cota"] = _f(row, "PC_BENCHMARK")
            elif idx == "Qtd Cota":
                result["qtd_cotas"] = _f(row, "PC_BENCHMARK")

        elif report == "CD_FI":
            result["fi"].append({
                "codigo":      _v(row, "CD_CODIGO"),
                "fundo":       _v(row, "CD_FUNDO"),
                "instituicao": _v(row, "CD_INSTITUICAO"),
                "vl_atual":    _f(row, "VL_ATUAL"),
                "pct_total":   _f(row, "PC_STOTAL"),
            })

        elif report == "CD_RF":
            result["rf"].append({
                "papel":       _v(row, "CD_PAPEL"),
                "emitente":    _v(row, "CD_EMITENTE"),
                "indexador":   _v(row, "CD_INDEX"),
                "vencimento":  _v(row, "DT_VENCIMENTO"),
                "vl_bruto":    _f(row, "VL_BRUTO"),
                "pct_total":   _f(row, "PC_STOTAL"),
            })

        elif report == "CD_RV":
            result["rv"].append({
                "codigo":    _v(row, "CD_CODIGO"),
                "papel":     _v(row, "DS_PAPEL"),
                "vl_mercado": _f(row, "VL_MERC_LIQUIDO"),
                "pct_total": _f(row, "PC_STOTAL"),
            })

        elif report == "CD_CPR":
            result["cpr"].append({
                "descricao": _v(row, "DS_DESCRICAO"),
                "valor":     _f(row, "VL"),
            })

    return result


# ── Busca de dados ─────────────────────────────────────────────────────────────

def _ultima_data_util() -> str:
    """Retorna a última sexta ou dia útil anterior a hoje."""
    d = date.today()
    # Sábado=5, Domingo=6 → volta para sexta
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _fetch_fundo(nome: str, cust: str, data: str) -> tuple[str, dict]:
    payload = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:tem="http://tempuri.org/">
       <soapenv:Header/>
       <soapenv:Body>
          <tem:RequestCostBasis>
             <tem:portfolio>{cust}</tem:portfolio>
             <tem:initialDate>{data}</tem:initialDate>
             <tem:finalDate>{data}</tem:finalDate>
          </tem:RequestCostBasis>
       </soapenv:Body>
    </soapenv:Envelope>"""
    try:
        r = requests.post(
            _base_url() + "/APIGateway/services/SOAP/RequestCostBasis",
            headers=_soap_headers(),
            data=payload.encode("utf-8"),
            timeout=30,
            verify=False,
        )
        if r.status_code == 200:
            return nome, parse_cost_basis(r.text)
    except Exception:
        pass
    return nome, {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_resumo_caceis(data: str | None = None) -> dict:
    """
    Retorna dict {plano: dados_parsed} para todos os fundos IAJA.
    Busca em paralelo. Cache de 1h.
    """
    if not data:
        data = _ultima_data_util()

    resumo: dict = {"data": data, "planos": {}}

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_fetch_fundo, nome, cust, data): nome
                   for nome, cust in FUNDOS.items()}
        for fut in as_completed(futures):
            nome, dados = fut.result()
            resumo["planos"][nome] = dados

    return resumo


def testar_conexao() -> dict:
    token = _get_token()
    if token:
        return {"ok": True, "token_preview": token[:40] + "..."}
    return {"ok": False, "erro": "Falha na autenticação"}
