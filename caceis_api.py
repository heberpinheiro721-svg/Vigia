from __future__ import annotations

import time
import requests
import streamlit as st

_TOKEN_CACHE: dict = {"token": None, "expires_at": 0}

_AUTH_ENDPOINT = "/APIGateway/security/authenticate"


def _base_url() -> str:
    cfg = st.secrets.get("caceis", {})
    return cfg.get("url_hml", "https://servico-hml.s3caceis.com.br")


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
        )
        if r.status_code == 200 and r.text.startswith("ey"):
            _TOKEN_CACHE["token"] = r.text.strip()
            _TOKEN_CACHE["expires_at"] = now + 900  # 15 min
            return _TOKEN_CACHE["token"]
    except Exception:
        pass
    return None


def _headers(ptf_code: str = "") -> dict:
    token = _get_token()
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if ptf_code:
        h["PortfolioCode"] = ptf_code
    return h


def get_cost_basis(portfolio: str, data_ini: str, data_fim: str) -> dict | None:
    """RequestCostBasis: carteira diária com rentabilidade, RF, RV, FI."""
    payload = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:tem="http://tempuri.org/">
       <soapenv:Header/>
       <soapenv:Body>
          <tem:RequestCostBasis>
             <tem:portfolio>{portfolio}</tem:portfolio>
             <tem:initialDate>{data_ini}</tem:initialDate>
             <tem:finalDate>{data_fim}</tem:finalDate>
          </tem:RequestCostBasis>
       </soapenv:Body>
    </soapenv:Envelope>"""
    try:
        r = requests.post(
            _base_url() + "/APIGateway/services/SOAP/RequestCostBasis",
            headers={**_headers(), "Content-Type": "application/xml"},
            data=payload.encode("utf-8"),
            timeout=30,
        )
        return {"status": r.status_code, "body": r.text}
    except Exception as e:
        return {"status": -1, "body": str(e)}


def get_posicao_cotista(fundo: str, data: str) -> dict | None:
    """ObterRelPosFundoCotista: posição dos cotistas de um fundo por data."""
    payload = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:tem="http://tempuri.org/" xmlns:glob="http://totvs.cot.webservices/global">
        <soapenv:Header/>
        <soapenv:Body>
            <tem:ObterRelPosFundoCotistaResponse>
             <tem:obterRelPosFundoCotistaRequest>
            <tem:filtro>
                <tem:cdFundo>{fundo}</tem:cdFundo>
                <tem:cdDistribuidor></tem:cdDistribuidor>
                <tem:cdGestor></tem:cdGestor>
                <tem:dtPosicao>{data}</tem:dtPosicao>
            </tem:filtro>
        </tem:obterRelPosFundoCotistaRequest>
        </tem:ObterRelPosFundoCotistaResponse>
    </soapenv:Body>
    </soapenv:Envelope>"""
    try:
        r = requests.post(
            _base_url() + "/APIGateway/services/SOAP/ObterRelPosFundoCotista",
            headers={**_headers(), "Content-Type": "application/xml"},
            data=payload.encode("utf-8"),
            timeout=30,
        )
        return {"status": r.status_code, "body": r.text}
    except Exception as e:
        return {"status": -1, "body": str(e)}


def testar_conexao() -> dict:
    """Testa autenticação e retorna status."""
    token = _get_token()
    if token:
        return {"ok": True, "token_preview": token[:40] + "..."}
    return {"ok": False, "erro": "Falha na autenticação"}
