"""
caceis_data.py — Substitutos das funções CSV de Cotas e Composição.
Fornece os mesmos DataFrames que load_cotas_all() e load_carteira_s3(),
puxando dados direto da API Caceis em tempo real.
"""
from __future__ import annotations

import pickle
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from caceis_api import _base_url, _soap_headers, FUNDOS

# ── Cache em disco ─────────────────────────────────────────────────────────────
_CACHE_DIR = Path(__file__).parent / "data" / ".cache"


def _disk_load(key: str, max_age_s: int) -> object | None:
    p = _CACHE_DIR / f"api_{key}.pkl"
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > max_age_s:
        return None
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _disk_save(key: str, data: object) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_DIR / f"api_{key}.pkl", "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


def _v(row: ET.Element, tag: str) -> str:
    el = row.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _f(row: ET.Element, tag: str) -> float:
    try:
        return float(_v(row, tag))
    except ValueError:
        return 0.0


def _extrair_rowsets(xml_text: str) -> ET.Element | None:
    inicio = xml_text.find("<ROWSET>")
    fim = xml_text.rfind("</ROWSET>") + len("</ROWSET>")
    if inicio == -1:
        return None
    try:
        return ET.fromstring(f"<ROOT>{xml_text[inicio:fim]}</ROOT>")
    except ET.ParseError:
        return None


def _soap_request(cust: str, data_ini: str, data_fim: str) -> str:
    payload = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:tem="http://tempuri.org/">
       <soapenv:Header/>
       <soapenv:Body>
          <tem:RequestCostBasis>
             <tem:portfolio>{cust}</tem:portfolio>
             <tem:initialDate>{data_ini}</tem:initialDate>
             <tem:finalDate>{data_fim}</tem:finalDate>
          </tem:RequestCostBasis>
       </soapenv:Body>
    </soapenv:Envelope>"""
    r = requests.post(
        _base_url() + "/APIGateway/services/SOAP/RequestCostBasis",
        headers=_soap_headers(),
        data=payload.encode("utf-8"),
        timeout=60,
        verify=False,
    )
    return r.text if r.status_code == 200 else ""


# ── Cotas ─────────────────────────────────────────────────────────────────────

_NOME_CURTO = {
    "Alpha": "PL Alpha",
    "Beta":  "PL Beta",
    "Gama":  "PL Gama",
    "PGA":   "Administrativo",
}


def _parse_cotas_range(xml_text: str, fundo_curto: str) -> list[dict]:
    root = _extrair_rowsets(xml_text)
    if root is None:
        return []
    by_date: dict = {}
    for row in root.iter("ROW"):
        if _v(row, "REPORT") != "CD_RENT":
            continue
        dt = _v(row, "DT")
        if not dt:
            continue
        if dt not in by_date:
            by_date[dt] = {
                "data": dt,
                "cliente": _v(row, "NOME") or fundo_curto,
                "fundo_curto": fundo_curto,
                "dia": 0.0, "mes": 0.0, "ano": 0.0, "ult_12m": 0.0,
                "cota": 0.0, "patrimonio": 0.0,
            }
        idx = _v(row, "CD_INDEXADOR")
        if idx == "COTA":
            by_date[dt].update({
                "dia":    _f(row, "PC_VAR_DIARIA"),
                "mes":    _f(row, "PC_VAR_MENSAL"),
                "ano":    _f(row, "PC_VAR_ANUAL"),
                "ult_12m": _f(row, "PC_ULT_12_MESES"),
            })
        elif idx == "Vlr Cota":
            by_date[dt]["cota"] = _f(row, "PC_BENCHMARK")
        elif idx == "PATRIMON":
            by_date[dt]["patrimonio"] = _f(row, "VL_PATRIMONIO")
    return list(by_date.values())


def _fetch_cotas(nome: str, cust: str, data_ini: str, data_fim: str) -> list[dict]:
    try:
        xml = _soap_request(cust, data_ini, data_fim)
        return _parse_cotas_range(xml, _NOME_CURTO[nome])
    except Exception:
        return []


@st.cache_data(ttl=86400, show_spinner=False)
def load_cotas_api(meses: int = 12) -> pd.DataFrame:
    """
    Substitui load_cotas_all() do CSV Mapa de Evolução de Cotas.
    Retorna DataFrame com: Data, Cota, Patrimônio, Cliente, fundo,
    Dia_pct, Mês_pct, Ano_pct, Total_pct, cota_base100.
    Cache em disco por 24h para evitar lentidão no primeiro carregamento.
    """
    cached = _disk_load("cotas", 86400)
    if cached is not None:
        return cached

    hoje = date.today()
    data_ini = (hoje.replace(day=1) - timedelta(days=meses * 30)).strftime("%Y-%m-%d")
    data_fim = hoje.strftime("%Y-%m-%d")

    registros: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_fetch_cotas, nome, cust, data_ini, data_fim): nome
            for nome, cust in FUNDOS.items()
        }
        for fut in as_completed(futures):
            registros.extend(fut.result())

    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    df["Data"]       = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["Cota"]       = df["cota"]
    df["Patrimônio"] = df["patrimonio"]
    df["Cliente"]    = df["cliente"]
    df["fundo"]      = df["fundo_curto"]
    df["Dia_pct"]    = df["dia"]
    df["Mês_pct"]    = df["mes"]
    df["Ano_pct"]    = df["ano"]
    df["Total_pct"]  = df["ult_12m"]
    df["cliente_orig"] = df["cliente"]

    df = df.sort_values(["fundo", "Data"]).reset_index(drop=True)
    base_date = df["Data"].min()
    base = df[df["Data"] == base_date].set_index("fundo")["Cota"]
    df["cota_base100"] = df.apply(
        lambda r: (r["Cota"] / base.get(r["fundo"], r["Cota"])) * 100
        if base.get(r["fundo"]) else 100.0,
        axis=1,
    )

    result = df[[
        "Data", "Cota", "Patrimônio", "Cliente", "fundo", "cliente_orig",
        "Dia_pct", "Mês_pct", "Ano_pct", "Total_pct", "cota_base100",
    ]]
    # Só salva em disco se todos os 4 fundos retornaram dados
    if set(result["fundo"].unique()) >= set(_NOME_CURTO.values()):
        _disk_save("cotas", result)
    return result


# ── Composição da Carteira (compliance) ───────────────────────────────────────

def _norm(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper()


def _classificar_segmento(cd_fundo: str) -> str:
    nome = _norm(cd_fundo)
    if "CP IE" in nome:
        return "Investimentos no Exterior"
    if "FIC FIA" in nome or "ACOES" in nome:
        return "Renda Variável"
    if "FIM" in nome:
        return "Investimentos Estruturados"
    return "Renda Fixa"


def _parse_fi(xml_text: str) -> list[dict]:
    root = _extrair_rowsets(xml_text)
    if root is None:
        return []
    rows = []
    for row in root.iter("ROW"):
        if _v(row, "REPORT") != "CD_FI":
            continue
        rows.append({
            "codigo":     _v(row, "CD_CODIGO"),
            "fundo_nome": _v(row, "CD_FUNDO"),
            "vl_atual":   _f(row, "VL_ATUAL"),
        })
    return rows


def _fetch_fi(cust: str, data: str) -> tuple[list[dict], str | None]:
    """Retorna (registros, erro_str). erro_str é None se ok."""
    try:
        xml = _soap_request(cust, data, data)
        if not xml:
            return [], f"{cust}: resposta vazia"
        return _parse_fi(xml), None
    except Exception as exc:
        return [], f"{cust}: {exc}"


def _dia_util_anterior(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _ultima_data_util() -> str:
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@st.cache_data(ttl=3600, show_spinner=False)
def load_carteira_api(data: str | None = None, pl: float | None = None) -> tuple[pd.DataFrame, str]:
    """
    Substitui load_carteira_s3(filepath, patrimonio_liquido).
    Retorna (DataFrame, data_usada). Tenta hoje → até 5 dias úteis anteriores.
    DataFrame vazio + data_usada="" indica falha total.
    Cache em disco por 1h para evitar espera a cada reinício.
    """
    cached = _disk_load("carteira", 3600)
    if cached is not None:
        return cached

    d = date.fromisoformat(data) if data else date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)

    for _ in range(5):
        data_str = d.strftime("%Y-%m-%d")
        todas: list[dict] = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_fetch_fi, cust, data_str): cust for cust in FUNDOS.values()}
            for fut in as_completed(futures):
                registros, _ = fut.result()
                todas.extend(registros)
        if todas:
            break
        d = _dia_util_anterior(d)
    else:
        return pd.DataFrame(), ""

    if not todas:
        return pd.DataFrame(), ""

    # Consolida: soma o mesmo fundo em todos os planos
    por_fundo: dict = {}
    for item in todas:
        key = item["codigo"]
        if key not in por_fundo:
            por_fundo[key] = {**item, "vl_atual": 0.0}
        por_fundo[key]["vl_atual"] += item["vl_atual"]

    df = pd.DataFrame(list(por_fundo.values()))
    total_raw = df["vl_atual"].sum()
    pl_ref = pl if pl else total_raw
    escala = pl_ref / total_raw if total_raw > 0 else 1.0

    df["val_liquido"]  = df["vl_atual"]
    df["val_ajustado"] = (df["vl_atual"] * escala).round(2)
    df["pct_pl_calc"]  = df["val_ajustado"] / pl_ref
    df["segmento"]     = df["fundo_nome"].apply(_classificar_segmento)
    df["cliente"]      = df["codigo"]
    df["descricao"]    = df["fundo_nome"]
    df["cnpj"]         = df["codigo"]
    df["_total_raw"]   = total_raw

    result = (df[[
        "cliente", "descricao", "cnpj",
        "val_liquido", "val_ajustado", "pct_pl_calc", "segmento", "_total_raw",
    ]], data_str)
    _disk_save("carteira", result)
    return result
