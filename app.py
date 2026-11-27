import base64
import gc
import html
import io
import json
import math
import os
import smtplib
import tempfile
import unicodedata
import urllib.parse
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import gspread
import pandas as pd
import pytz
import speech_recognition as sr
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Importação opcional do Matplotlib para gráfico executivo no PDF
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    TEM_MATPLOTLIB = True
except Exception:
    TEM_MATPLOTLIB = False

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditoria Juiz de Fora 2026",
    page_icon="🐾",
    layout="centered",
    initial_sidebar_state="expanded",
)

# --- CONSTANTES, LOGOS E ARQUIVOS ---
ARQUIVO_JSON_HISTORICO = Path("historico_juiz_de_fora_audit.json")
ARQUIVO_JSON_RASCUNHOS = Path("rascunho_auditoria_jf.json")
NOME_PLANILHA_SHEETS = "Juiz_De_Fora_Audit"
LOGO_MINASSAL = "logo_minassal.jpg"
LOGO_ROYAL = "logo_royal.png"

EMAILS_BENEDITO = [
    "benedito.bandola@minassal.com.br",
    "beneditobandola@gmail.com",
]

CODIGOS_JUIZ_DE_FORA_ORDEM = [
    "21294",  # Veterinária Mendes Andrade
    "21873",  # Cristiano Resende
    "21878",  # Luciano tostes
    "21888",  # Rp agrop
    "21209",  # Agrotela
    "21921",  # Cinthia
    "24310",  # Bahpet
    "22341",  # Sítios e quintais
    "21472",  # Rianelli
    "21140",  # Lombello
]

APELIDOS_POR_CODIGO = {
    "21294": "Veterinária Mendes Andrade",
    "21873": "Cristiano Resende",
    "21878": "Luciano tostes",
    "21888": "Rp agrop",
    "21209": "Agrotela",
    "21921": "Cinthia",
    "24310": "Bahpet",
    "22341": "Sítios e quintais",
    "21472": "Rianelli",
    "21140": "Lombello",
}

MARCAS_PADRAO = [
    "Biofresh (BRF)",
    "Equilíbrio (ADM/Total)",
    "Fórmula Natural (Adimax)",
    "Hill's",
    "Pro Plan (Nestlé)",
    "Premier (Premier)",
    "Nattu (Premier)",
    "Vet Life (Farmina)",
    "N&D (Farmina)",
    "Royal Canin",
]

MATERIAIS_PADRAO = [
    "Faixa de Gôndola",
    "Bobina Forração",
    "Display Carona",
    "Cartazete precificador",
    "Base de Sacarias (can base)",
    "Totem Silhueta",
    "Cubo",
    "Clip Strip",
    "Stopper",
    "Outros materiais",
]


# --- PWA (APP INSTALÁVEL COM NOME E ÍCONE) + ESTILO VISUAL DE ALTO CONTRASTE ---
def gerar_icone_pwa_base64() -> str:
    """Gera ícone PNG 512x512 em base64 usando a logo da Royal Canin/Minassal ou emblema padrão."""
    try:
        canvas = PILImage.new("RGB", (512, 512), (226, 0, 26))
        origem_logo = (
            LOGO_ROYAL
            if os.path.exists(LOGO_ROYAL)
            else (LOGO_MINASSAL if os.path.exists(LOGO_MINASSAL) else None)
        )
        if origem_logo:
            with PILImage.open(origem_logo) as logo:
                logo = ImageOps.exif_transpose(logo).convert("RGBA")
                logo.thumbnail((380, 380))
                fundo_branco = PILImage.new("RGB", (440, 440), (255, 255, 255))
                pos_x = (440 - logo.width) // 2
                pos_y = (440 - logo.height) // 2
                fundo_branco.paste(logo, (pos_x, pos_y), logo)
                canvas.paste(fundo_branco, (36, 36))
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""


def injetar_pwa_e_tema_executivo():
    icone_b64 = gerar_icone_pwa_base64()
    icon_data_url = f"data:image/png;base64,{icone_b64}" if icone_b64 else ""

    manifest_obj = {
        "name": "Auditoria Juiz de Fora 2026",
        "short_name": "Auditoria JF",
        "description": "Auditoria de Execução e Shelf Space • Minassal / Royal Canin",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#F1F5F9",
        "theme_color": "#E2001A",
        "orientation": "portrait",
        "icons": (
            [
                {
                    "src": icon_data_url,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ]
            if icon_data_url
            else []
        ),
    }
    manifest_b64 = base64.b64encode(
        json.dumps(manifest_obj, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    pwa_tags = f"""
    <link rel="manifest" href="data:application/manifest+json;base64,{manifest_b64}">
    <meta name="theme-color" content="#E2001A">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Auditoria JF">
    """
    if icon_data_url:
        pwa_tags += f'<link rel="apple-touch-icon" href="{icon_data_url}">'

    css_executivo = """
    <style>
        /* Força esquema claro de alto contraste mesmo se o celular/navegador estiver em Dark Mode */
        :root {
            color-scheme: light !important;
        }
        [data-testid="stAppViewContainer"], .main, .block-container {
            background-color: #F1F5F9 !important;
            color: #0F172A !important;
        }
        [data-testid="stHeader"] {
            background-color: #F1F5F9 !important;
        }
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #CBD5E1 !important;
        }
        section[data-testid="stSidebar"] * {
            color: #0F172A !important;
        }

        /* Títulos, labels, textos de rádio, checkboxes e parágrafos fora do banner escuro */
        .main h1:not(.banner-executivo h1),
        .main h2, .main h3, .main h4,
        .main p:not(.banner-executivo p),
        .main label,
        .main span:not([data-testid="stMetricDelta"] *):not(.banner-executivo *),
        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stWidgetLabel"] label,
        div[data-testid="stRadio"] label p,
        div[data-testid="stCheckbox"] label p,
        div[data-testid="stMarkdownContainer"] p:not(.banner-executivo p),
        div[data-testid="stMarkdownContainer"] li {
            color: #0F172A !important;
        }
        .main h2, .main h3 {
            font-weight: 800 !important;
        }

        /* Caixas de texto, números (frentes) e selects com fundo branco e borda visível */
        div[data-baseweb="input"],
        div[data-baseweb="base-input"],
        div[data-baseweb="select"] > div,
        textarea,
        input {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
            border-color: #94A3B8 !important;
        }
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
            font-weight: 600 !important;
        }
        /* Botões + e - do number_input no celular */
        div[data-testid="stNumberInput"] button {
            background-color: #E2E8F0 !important;
            color: #0F172A !important;
            border-color: #94A3B8 !important;
        }
        div[data-testid="stNumberInput"] button svg {
            fill: #0F172A !important;
        }

        /* Menu suspenso (dropdown) ao abrir no celular */
        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"],
        li[role="option"] {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
        }
        li[role="option"]:hover {
            background-color: #E2E8F0 !important;
        }

        /* Caixas de aviso / st.info / st.warning em tema claro de alto contraste */
        div[data-testid="stAlert"],
        div[data-testid="stNotification"],
        div.stAlert {
            background-color: #EFF6FF !important;
            color: #0F172A !important;
            border: 1px solid #93C5FD !important;
            border-radius: 10px !important;
        }
        div[data-testid="stAlert"] *,
        div[data-testid="stNotification"] *,
        div.stAlert * {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
        }

        /* File uploader (dropzone e botão Upload) com alto contraste */
        div[data-testid="stFileUploaderDropzone"],
        div[data-testid="stFileUploader"] section {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
            border: 1.5px dashed #64748B !important;
            border-radius: 10px !important;
        }
        div[data-testid="stFileUploaderDropzone"] span,
        div[data-testid="stFileUploaderDropzone"] small,
        div[data-testid="stFileUploaderDropzone"] div,
        div[data-testid="stFileUploader"] section span,
        div[data-testid="stFileUploader"] section small {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
        }
        div[data-testid="stFileUploaderDropzone"] button,
        div[data-testid="stFileUploader"] button {
            background-color: #E2E8F0 !important;
            color: #0F172A !important;
            border: 1px solid #64748B !important;
            font-weight: 700 !important;
        }
        div[data-testid="stFileUploaderDropzone"] button *,
        div[data-testid="stFileUploader"] button * {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
        }

        /* Gravador de áudio (st.audio_input) em fundo claro com alto contraste */
        div[data-testid="stAudioInput"],
        div[data-testid="stAudioInput"] > div,
        div[data-testid="stAudioInput"] section {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
            border: 1.5px solid #94A3B8 !important;
            border-radius: 10px !important;
        }
        div[data-testid="stAudioInput"] *,
        div[data-testid="stAudioInput"] svg {
            color: #0F172A !important;
            fill: #0F172A !important;
        }

        /* Cards, metrics e badges de variação (delta) */
        div[data-testid="stExpander"] {
            background-color: #FFFFFF !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 10px !important;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05) !important;
        }
        div[data-testid="stMetric"] {
            background-color: #FFFFFF !important;
            border: 1px solid #CBD5E1 !important;
            border-top: 4px solid #E2001A !important;
            border-radius: 10px !important;
            padding: 12px 14px !important;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.05) !important;
        }
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] * {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
        }
        div[data-testid="stMetricDelta"] {
            background-color: #F1F5F9 !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 999px !important;
            padding: 2px 8px !important;
        }
        div[data-testid="stMetricDelta"] * {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
            font-weight: 700 !important;
        }

        /* Botões secundários e de link (Google Maps, Zerar Rascunho, etc.) */
        div.stButton > button:not([kind="primary"]),
        div[data-testid="stLinkButton"] > a {
            background-color: #FFFFFF !important;
            color: #0F172A !important;
            border: 1.5px solid #94A3B8 !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
        }
        div.stButton > button:not([kind="primary"]) *,
        div[data-testid="stLinkButton"] > a * {
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
        }

        /* Botões primários em vermelho Royal Canin */
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #E2001A 0%, #B91C1C 100%) !important;
            border: none !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
            padding: 0.65rem 1.2rem !important;
            box-shadow: 0 4px 10px rgba(226, 0, 26, 0.25) !important;
        }
        div.stButton > button[kind="primary"] * {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        /* Banner executivo superior */
        div.banner-executivo {
            background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%) !important;
            border-bottom: 4px solid #E2001A !important;
            padding: 18px 20px !important;
            border-radius: 12px !important;
            margin-bottom: 14px !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12) !important;
        }
        div.banner-executivo h1 {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            font-size: 1.55rem !important;
            margin: 0 0 4px 0 !important;
            font-weight: 800 !important;
        }
        div.banner-executivo p {
            color: #F1F5F9 !important;
            -webkit-text-fill-color: #F1F5F9 !important;
            font-size: 0.9rem !important;
            margin: 0 !important;
            font-weight: 500 !important;
        }

        /* Alerta de trava da loja ativa */
        .trava-loja-alerta {
            background-color: #FEF2F2 !important;
            border: 2px solid #E2001A !important;
            border-left: 8px solid #E2001A !important;
            padding: 14px 16px;
            border-radius: 10px;
            margin: 10px 0 14px 0;
            box-shadow: 0 2px 8px rgba(226, 0, 26, 0.12);
        }
        .trava-loja-alerta .titulo-trava {
            font-size: 13px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #B91C1C !important;
            -webkit-text-fill-color: #B91C1C !important;
            margin-bottom: 4px;
        }
        .trava-loja-alerta .nome-loja-trava {
            font-size: 18px;
            font-weight: 900;
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
            margin-bottom: 4px;
        }
        .badge-autosave {
            display: inline-block;
            background-color: #ECFDF5 !important;
            color: #065F46 !important;
            -webkit-text-fill-color: #065F46 !important;
            border: 1px solid #A7F3D0 !important;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 700;
            margin-top: 4px;
        }
    </style>
    """
    st.markdown(pwa_tags + css_executivo, unsafe_allow_html=True)


injetar_pwa_e_tema_executivo()


# --- AUTO-SAVE CONTÍNUO EM JSON PARA RASCUNHO DE CAMPO (ANTI-PERDA / SEM REDE) ---
def carregar_rascunhos_json() -> dict:
    if ARQUIVO_JSON_RASCUNHOS.exists():
        try:
            raw = ARQUIVO_JSON_RASCUNHOS.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data.setdefault("ultima_loja_ativa", {})
                    data.setdefault("rascunhos", {})
                    return data
        except Exception:
            pass
    return {"ultima_loja_ativa": {}, "rascunhos": {}}


def _gravar_rascunhos_json(payload: dict) -> None:
    try:
        ARQUIVO_JSON_RASCUNHOS.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def salvar_ultima_loja_ativa(
    promotora: str, tipo_auditoria: str, codigo_loja: str, nome_loja: str
) -> None:
    payload = carregar_rascunhos_json()
    payload["ultima_loja_ativa"] = {
        "promotora": promotora,
        "tipo_auditoria": tipo_auditoria,
        "codigo_loja": codigo_loja,
        "nome_loja": nome_loja,
        "atualizado_em": datetime.now(pytz.timezone("America/Sao_Paulo")).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
    }
    _gravar_rascunhos_json(payload)


def salvar_rascunho_loja(chave_rascunho: str, estado_loja: dict) -> str:
    agora_str = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime(
        "%d/%m/%Y %H:%M:%S"
    )
    payload = carregar_rascunhos_json()
    payload["rascunhos"][chave_rascunho] = {
        "salvo_em": agora_str,
        "dados": estado_loja,
    }
    _gravar_rascunhos_json(payload)
    return agora_str


def obter_rascunho_loja(chave_rascunho: str) -> dict | None:
    payload = carregar_rascunhos_json()
    return payload.get("rascunhos", {}).get(chave_rascunho)


def limpar_rascunho_loja(chave_rascunho: str) -> None:
    payload = carregar_rascunhos_json()
    if chave_rascunho in payload.get("rascunhos", {}):
        del payload["rascunhos"][chave_rascunho]
        _gravar_rascunhos_json(payload)


def rascunho_tem_dados_preenchidos(dados: dict) -> bool:
    if not dados:
        return False
    soma_cao = sum(dados.get("frentes_cao", {}).values())
    soma_gato = sum(dados.get("frentes_gato", {}).values())
    soma_vet = sum(dados.get("frentes_vet", {}).values())
    qtd_mat = len(dados.get("materiais_ativos", []))
    extras = int(dados.get("qtd_extras", 0))
    obs = str(dados.get("observacoes", "")).strip()
    return (soma_cao + soma_gato + soma_vet + qtd_mat + extras) > 0 or bool(obs)


def carregar_estado_rascunho_na_sessao(
    chave_rascunho: str, rascunho_entry: dict | None
) -> None:
    dados = (rascunho_entry or {}).get("dados", {})

    for m in MARCAS_PADRAO:
        st.session_state[f"cao_{m}"] = int(dados.get("frentes_cao", {}).get(m, 0))
        st.session_state[f"gato_{m}"] = int(dados.get("frentes_gato", {}).get(m, 0))
        st.session_state[f"vet_{m}"] = int(dados.get("frentes_vet", {}).get(m, 0))

    st.session_state["plano_cao"] = (
        dados.get("plano_cao", "Sim")
        if dados.get("plano_cao") in ("Sim", "Não")
        else "Sim"
    )
    st.session_state["fluxo_cao"] = (
        dados.get("fluxo_cao", "Sim")
        if dados.get("fluxo_cao") in ("Sim", "Não")
        else "Sim"
    )
    st.session_state["plano_gato"] = (
        dados.get("plano_gato", "Sim")
        if dados.get("plano_gato") in ("Sim", "Não")
        else "Sim"
    )
    st.session_state["fluxo_gato"] = (
        dados.get("fluxo_gato", "Sim")
        if dados.get("fluxo_gato") in ("Sim", "Não")
        else "Sim"
    )
    st.session_state["sep_fhn"] = (
        dados.get("sep_fhn", "Sim") if dados.get("sep_fhn") in ("Sim", "Não") else "Sim"
    )
    st.session_state["plano_vet"] = (
        dados.get("plano_vet", "Sim")
        if dados.get("plano_vet") in ("Sim", "Não")
        else "Sim"
    )
    st.session_state["fluxo_vet"] = (
        dados.get("fluxo_vet", "Sim")
        if dados.get("fluxo_vet") in ("Sim", "Não")
        else "Sim"
    )

    mats_salvos = set(dados.get("materiais_ativos", []))
    for mat in MATERIAIS_PADRAO:
        st.session_state[f"mat_{mat}"] = mat in mats_salvos

    cons_salva = dados.get("conservacao", "Sim")
    st.session_state["conservacao"] = (
        cons_salva if cons_salva in ("Sim", "Não") else "Sim"
    )
    st.session_state["qtd_pontos_extras"] = int(dados.get("qtd_extras", 0))
    st.session_state["texto_transcrito_voz"] = str(dados.get("observacoes", ""))
    st.session_state["obs_campo_texto"] = str(dados.get("observacoes", ""))
    st.session_state["chave_rascunho_carregada"] = chave_rascunho
    st.session_state["confirmar_loja_correta"] = False


# --- GESTÃO DO JSON OFICIAL + TESTES SEPARADOS + MESCLAGEM SEM DUPLICAR ---
def estrutura_json_padrao() -> dict:
    return {
        "projeto": "Auditoria Juiz de Fora 2026",
        "modo_teste": False,
        "atualizado_em": datetime.now(pytz.timezone("America/Sao_Paulo")).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
        "lojas_roteiro": [],
        "auditorias": [],
        "testes": [],
    }


def _chave_unica_registro(registro: dict) -> str:
    """Gera uma chave única para evitar duplicar registros mesmo sem ID explícito."""
    reg_id = str(registro.get("id", "")).strip()
    if reg_id:
        return f"ID::{reg_id}"
    return "|".join([
        str(registro.get("codigo_loja", "")).strip(),
        str(registro.get("loja", "")).strip().upper(),
        str(registro.get("data_hora", "")).strip(),
        str(registro.get("tipo_auditoria", "")).strip().upper(),
        str(registro.get("promotora", "")).strip().upper(),
        str(registro.get("nota_total", "")).strip(),
    ])


def _normalizar_payload_json(conteudo_json) -> dict:
    base = estrutura_json_padrao()
    if isinstance(conteudo_json, dict):
        base["projeto"] = conteudo_json.get("projeto", base["projeto"])
        base["modo_teste"] = bool(conteudo_json.get("modo_teste", False))
        base["lojas_roteiro"] = (
            list(conteudo_json.get("lojas_roteiro", []))
            if isinstance(conteudo_json.get("lojas_roteiro"), list)
            else []
        )
        auds_raw = (
            list(conteudo_json.get("auditorias", []))
            if isinstance(conteudo_json.get("auditorias"), list)
            else []
        )
        testes_raw = (
            list(conteudo_json.get("testes", []))
            if isinstance(conteudo_json.get("testes"), list)
            else []
        )

        for r in auds_raw:
            if not isinstance(r, dict):
                continue
            if r.get("registro_teste", False):
                testes_raw.append(r)
            else:
                r["registro_teste"] = False
                base["auditorias"].append(r)

        for r in testes_raw:
            if not isinstance(r, dict):
                continue
            r["registro_teste"] = True
            base["testes"].append(r)

    elif isinstance(conteudo_json, list):
        for r in conteudo_json:
            if not isinstance(r, dict):
                continue
            if r.get("registro_teste", False):
                r["registro_teste"] = True
                base["testes"].append(r)
            else:
                r["registro_teste"] = False
                base["auditorias"].append(r)

    return base


def carregar_dados_json() -> dict:
    if ARQUIVO_JSON_HISTORICO.exists():
        try:
            conteudo = ARQUIVO_JSON_HISTORICO.read_text(encoding="utf-8").strip()
            if not conteudo:
                return estrutura_json_padrao()
            data = json.loads(conteudo)
            return _normalizar_payload_json(data)
        except Exception as e:
            st.warning(f"Erro ao ler {ARQUIVO_JSON_HISTORICO}: {e}")
    return estrutura_json_padrao()


def salvar_dados_json(payload: dict) -> bool:
    try:
        normalizado = _normalizar_payload_json(payload)
        normalizado["atualizado_em"] = datetime.now(
            pytz.timezone("America/Sao_Paulo")
        ).strftime("%d/%m/%Y %H:%M:%S")
        ARQUIVO_JSON_HISTORICO.write_text(
            json.dumps(normalizado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except Exception as e:
        st.error(f"Erro ao salvar {ARQUIVO_JSON_HISTORICO}: {e}")
        return False


def _recalcular_status_roteiro(payload: dict) -> None:
    codigos_com_oficial = {
        str(r.get("codigo_loja", "")).strip()
        for r in payload.get("auditorias", [])
        if not r.get("registro_teste", False)
    }
    for loja_item in payload.get("lojas_roteiro", []):
        cod = str(loja_item.get("codigo_loja", "")).strip()
        if cod in codigos_com_oficial:
            loja_item["status_visita"] = "auditada"
            loja_item["registro_teste"] = False
            loja_item["auditorias"] = [
                {
                    "id": r.get("id"),
                    "data_hora": r.get("data_hora"),
                    "tipo_auditoria": r.get("tipo_auditoria"),
                    "nota_total": r.get("nota_total"),
                }
                for r in payload.get("auditorias", [])
                if str(r.get("codigo_loja", "")).strip() == cod
            ]
        else:
            loja_item["status_visita"] = "pendente"
            loja_item["registro_teste"] = False
            loja_item["auditorias"] = []


def mesclar_backup_json_sem_duplicar(conteudo_backup_raw: bytes) -> dict:
    """Mescla um JSON de backup ao JSON atual sem apagar existentes e sem duplicar registros."""
    texto_backup = conteudo_backup_raw.decode("utf-8").strip()
    if not texto_backup:
        raise ValueError("O arquivo de backup está vazio.")

    dados_backup = _normalizar_payload_json(json.loads(texto_backup))
    atual = carregar_dados_json()

    auditorias_atuais = list(atual.get("auditorias", []))
    testes_atuais = list(atual.get("testes", []))
    roteiro_atual = list(atual.get("lojas_roteiro", []))

    chaves_auds = {_chave_unica_registro(r) for r in auditorias_atuais}
    chaves_testes = {_chave_unica_registro(r) for r in testes_atuais}

    adicionadas_oficiais = 0
    ignoradas_duplicadas_oficiais = 0
    for reg in dados_backup.get("auditorias", []):
        chave = _chave_unica_registro(reg)
        if chave in chaves_auds:
            ignoradas_duplicadas_oficiais += 1
        else:
            reg["registro_teste"] = False
            auditorias_atuais.append(reg)
            chaves_auds.add(chave)
            adicionadas_oficiais += 1

    adicionadas_testes = 0
    ignoradas_duplicadas_testes = 0
    for reg in dados_backup.get("testes", []):
        chave = _chave_unica_registro(reg)
        if chave in chaves_testes:
            ignoradas_duplicadas_testes += 1
        else:
            reg["registro_teste"] = True
            testes_atuais.append(reg)
            chaves_testes.add(chave)
            adicionadas_testes += 1

    # Mescla lojas do roteiro pelo código sem duplicar
    mapa_roteiro = {}
    for item in roteiro_atual:
        if isinstance(item, dict):
            cod = str(item.get("codigo_loja", "")).strip()
            if cod:
                mapa_roteiro[cod] = item
    for item in dados_backup.get("lojas_roteiro", []):
        if isinstance(item, dict):
            cod = str(item.get("codigo_loja", "")).strip()
            if cod and cod not in mapa_roteiro:
                mapa_roteiro[cod] = item

    payload_mesclado = {
        "projeto": atual.get("projeto", "Auditoria Juiz de Fora 2026"),
        "modo_teste": atual.get("modo_teste", False),
        "lojas_roteiro": list(mapa_roteiro.values()),
        "auditorias": auditorias_atuais,
        "testes": testes_atuais,
    }
    _recalcular_status_roteiro(payload_mesclado)
    salvou = salvar_dados_json(payload_mesclado)

    return {
        "salvou": salvou,
        "adicionadas_oficiais": adicionadas_oficiais,
        "ignoradas_duplicadas_oficiais": ignoradas_duplicadas_oficiais,
        "adicionadas_testes": adicionadas_testes,
        "ignoradas_duplicadas_testes": ignoradas_duplicadas_testes,
    }


def registrar_no_json(novo_registro: dict, eh_teste: bool) -> bool:
    payload = carregar_dados_json()
    novo_registro["registro_teste"] = bool(eh_teste)

    if eh_teste:
        payload.setdefault("testes", []).append(novo_registro)
    else:
        payload.setdefault("auditorias", []).append(novo_registro)
        _recalcular_status_roteiro(payload)

    return salvar_dados_json(payload)


def excluir_registro_json(registro_id: str, eh_teste: bool = False) -> bool:
    payload = carregar_dados_json()
    if eh_teste:
        payload["testes"] = [
            r for r in payload.get("testes", []) if r.get("id") != registro_id
        ]
    else:
        payload["auditorias"] = [
            r for r in payload.get("auditorias", []) if r.get("id") != registro_id
        ]
        _recalcular_status_roteiro(payload)
    return salvar_dados_json(payload)


def limpar_testes_json() -> bool:
    payload = carregar_dados_json()
    payload["testes"] = []
    payload["modo_teste"] = False
    for loja_item in payload.get("lojas_roteiro", []):
        loja_item["registro_teste"] = False
    return salvar_dados_json(payload)


# --- CARREGAR PLANILHA DE CLIENTES ---
@st.cache_data
def load_clients():
    candidatos = [
        "Cópia de clientes com cnpj corretinho novinho.xlsx",
        "Cópia de clientes com cnpj corretinho novinho (1).xlsx",
    ]
    for nome_arq in candidatos:
        if os.path.exists(nome_arq):
            try:
                xls = pd.ExcelFile(nome_arq)
                aba = "Book1" if "Book1" in xls.sheet_names else xls.sheet_names[0]
                return pd.read_excel(nome_arq, sheet_name=aba)
            except Exception as e:
                st.error(f"Erro ao carregar a planilha de clientes: {e}")
                return pd.DataFrame()

    xlsx_disponiveis = [
        f
        for f in os.listdir(".")
        if f.lower().endswith(".xlsx") and not f.startswith("~$")
    ]
    for arq in xlsx_disponiveis:
        if "cliente" in arq.lower() or "cnpj" in arq.lower():
            try:
                xls = pd.ExcelFile(arq)
                aba = "Book1" if "Book1" in xls.sheet_names else xls.sheet_names[0]
                return pd.read_excel(arq, sheet_name=aba)
            except Exception as e:
                st.error(f"Erro ao carregar {arq}: {e}")
                return pd.DataFrame()

    if xlsx_disponiveis:
        try:
            xls = pd.ExcelFile(xlsx_disponiveis[0])
            return pd.read_excel(xlsx_disponiveis[0], sheet_name=xls.sheet_names[0])
        except Exception as e:
            st.error(f"Erro ao carregar {xlsx_disponiveis[0]}: {e}")
            return pd.DataFrame()

    st.error("A planilha de clientes não foi encontrada.")
    return pd.DataFrame()


df_clientes = load_clients()


# --- OTIMIZAÇÃO DE FOTOS (ANTI-TRAVAMENTO STREAMLIT CLOUD / CELULAR) ---
def otimizar_imagem_upload(
    arquivo_upload, max_lado: int = 1280, qualidade: int = 82
) -> str | None:
    try:
        raw_bytes = arquivo_upload.getvalue()
        if not raw_bytes:
            return None

        resample = getattr(PILImage, "Resampling", PILImage).LANCZOS
        with PILImage.open(io.BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_lado, max_lado), resample)

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            img.save(tmp.name, format="JPEG", quality=qualidade, optimize=True)
            tmp.close()
            caminho_salvo = tmp.name

        del raw_bytes
        gc.collect()
        return caminho_salvo
    except Exception as e:
        nome_foto = getattr(arquivo_upload, "name", "imagem")
        st.warning(f"Não foi possível processar a foto '{nome_foto}': {e}")
        return None


def processar_fotos_com_cache(arquivos_fotos) -> list[str]:
    if "cache_fotos_processadas" not in st.session_state:
        st.session_state["cache_fotos_processadas"] = {}

    cache = st.session_state["cache_fotos_processadas"]
    chaves_atuais = set()
    caminhos_validos = []

    if arquivos_fotos:
        for foto in arquivos_fotos:
            tamanho = getattr(foto, "size", 0)
            chave = f"{foto.name}_{tamanho}"
            chaves_atuais.add(chave)

            caminho_existente = cache.get(chave)
            if caminho_existente and os.path.exists(caminho_existente):
                caminhos_validos.append(caminho_existente)
            else:
                novo_caminho = otimizar_imagem_upload(foto, max_lado=1280, qualidade=82)
                if novo_caminho:
                    cache[chave] = novo_caminho
                    caminhos_validos.append(novo_caminho)

    chaves_removidas = [k for k in list(cache.keys()) if k not in chaves_atuais]
    for k in chaves_removidas:
        arq_antigo = cache.pop(k, None)
        if arq_antigo and os.path.exists(arq_antigo):
            try:
                os.remove(arq_antigo)
            except Exception:
                pass

    return caminhos_validos


# --- CONEXÃO GOOGLE SHEETS ---
@st.cache_resource
def conectar_google_sheets():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        try:
            return client.open(NOME_PLANILHA_SHEETS)
        except Exception:
            return client.open("Historico_Auditorias_RoyalCanin")
    except Exception as e:
        print(f"Erro de conexão com Google Sheets: {e}")
        return None


# --- GESTÃO DE GRUPOS DE E-MAIL (GOOGLE SHEETS + FALLBACK) ---
def grupos_email_padrao() -> dict:
    return {
        "Somente Benedito": list(EMAILS_BENEDITO),
        "Benedito e Pamela": EMAILS_BENEDITO + ["pamelaalmeida5@icloud.com"],
        "Toda a Equipe Minassal": EMAILS_BENEDITO
        + [
            "pamelaalmeida5@icloud.com",
            "poli@minassal.com.br",
            "caio.poli@minassal.com.br",
            "daniel.santini@minassal.com.br",
            "rubens.porfirio@minassal.com.br",
        ],
    }


def carregar_grupos_email() -> dict:
    padrao = grupos_email_padrao()
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_grp = wb.worksheet("Grupos_Email")
            except Exception:
                sheet_grp = wb.add_worksheet(title="Grupos_Email", rows="50", cols="2")
                sheet_grp.append_row(["Nome_Grupo", "Emails"])
                for nome, lista in padrao.items():
                    sheet_grp.append_row([nome, ", ".join(lista)])
                return padrao

            registros = sheet_grp.get_all_records()
            grupos_sheets = {}
            for row in registros:
                nome = str(row.get("Nome_Grupo", "")).strip()
                emails_raw = str(row.get("Emails", "")).strip()
                if nome and emails_raw:
                    lista_limpa = list(
                        dict.fromkeys(
                            [
                                e.strip()
                                for e in emails_raw.replace(";", ",").split(",")
                                if "@" in e
                            ]
                        )
                    )
                    if lista_limpa:
                        grupos_sheets[nome] = lista_limpa
            if grupos_sheets:
                return grupos_sheets
    except Exception:
        pass
    return padrao


def salvar_grupo_email(nome_grupo: str, lista_emails: list[str]) -> bool:
    try:
        wb = conectar_google_sheets()
        if not wb:
            return False
        try:
            sheet_grp = wb.worksheet("Grupos_Email")
        except Exception:
            sheet_grp = wb.add_worksheet(title="Grupos_Email", rows="50", cols="2")
            sheet_grp.append_row(["Nome_Grupo", "Emails"])

        registros = sheet_grp.get_all_records()
        emails_limpos = list(
            dict.fromkeys([e.strip() for e in lista_emails if "@" in e])
        )
        emails_str = ", ".join(emails_limpos)

        for idx, row in enumerate(registros, start=2):
            if (
                str(row.get("Nome_Grupo", "")).strip().lower()
                == nome_grupo.strip().lower()
            ):
                sheet_grp.update_cell(idx, 1, nome_grupo.strip())
                sheet_grp.update_cell(idx, 2, emails_str)
                return True

        sheet_grp.append_row([nome_grupo.strip(), emails_str])
        return True
    except Exception as e:
        print(f"Erro ao salvar grupo de e-mail: {e}")
        return False


def excluir_grupo_email(nome_grupo: str) -> bool:
    try:
        wb = conectar_google_sheets()
        if not wb:
            return False
        sheet_grp = wb.worksheet("Grupos_Email")
        registros = sheet_grp.get_all_records()
        for idx, row in enumerate(registros, start=2):
            if (
                str(row.get("Nome_Grupo", "")).strip().lower()
                == nome_grupo.strip().lower()
            ):
                sheet_grp.delete_rows(idx)
                return True
    except Exception as e:
        print(f"Erro ao excluir grupo de e-mail: {e}")
    return False


# --- FUNÇÕES DE USUÁRIOS, LOGS E FEEDBACKS ---
def registrar_log_acesso(supervisor):
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_log = wb.worksheet("Logs_Acesso")
            except Exception:
                sheet_log = wb.add_worksheet(title="Logs_Acesso", rows="100", cols="5")
                sheet_log.append_row(["Supervisor", "Data/Hora"])

            fuso_sp = pytz.timezone("America/Sao_Paulo")
            agora = datetime.now(fuso_sp).strftime("%d/%m/%Y %H:%M:%S")
            sheet_log.append_row([supervisor, agora])
    except Exception:
        pass


def listar_usuarios_cadastrados():
    usuarios_padrao = [
        "Benedito",
        "Caio",
        "Poli",
        "Rubens",
        "Daniel",
        "Sarmento",
        "Paulo Maia",
    ]
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_usr = wb.worksheet("Usuarios_Senhas")
                linhas = sheet_usr.get_all_values()
                usuarios_planilha = []
                for idx, linha in enumerate(linhas):
                    if idx == 0:
                        continue
                    if len(linha) >= 1 and linha[0].strip():
                        usuarios_planilha.append(linha[0].strip())
                if usuarios_planilha:
                    return list(dict.fromkeys(usuarios_padrao + usuarios_planilha))
            except Exception:
                pass
    except Exception:
        pass
    return usuarios_padrao


def buscar_senha_usuario(usuario):
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_usr = wb.worksheet("Usuarios_Senhas")
            except Exception:
                return None

            linhas = sheet_usr.get_all_values()
            usuario_limpo = str(usuario).strip().lower()

            for idx, linha in enumerate(linhas):
                if idx == 0:
                    continue
                if len(linha) >= 2:
                    nome_planilha = str(linha[0]).strip().lower()
                    senha_planilha = str(linha[1]).strip()
                    if nome_planilha == usuario_limpo:
                        if (
                            senha_planilha
                            and senha_planilha.lower() != "none"
                            and senha_planilha != ""
                        ):
                            return senha_planilha
    except Exception as e:
        st.error(f"Erro ao ler usuários: {e}")
    return None


def salvar_nova_senha(usuario, senha):
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_usr = wb.worksheet("Usuarios_Senhas")
            except Exception:
                sheet_usr = wb.add_worksheet(title="Usuarios_Senhas", rows="50", cols="3")
                sheet_usr.append_row(["Usuário", "Senha"])

            registros = sheet_usr.get_all_records()
            usuario_limpo = str(usuario).strip().lower()

            encontrado = False
            for idx, linha in enumerate(registros, start=2):
                nome_atual = str(linha.get("Usuário", "")).strip().lower()
                if nome_atual == usuario_limpo:
                    sheet_usr.update_cell(idx, 2, str(senha).strip())
                    encontrado = True
                    break

            if not encontrado:
                sheet_usr.append_row([str(usuario).strip(), str(senha).strip()])

            return True
    except Exception as e:
        print(f"Erro detalhado ao salvar senha: {e}")
        return False
    return False


def enviar_email_interacao(loja, supervisor, tipo, comentario, data_auditoria):
    remetente = st.secrets.get("email_remetente", "beneditobandola@gmail.com")
    senha = st.secrets.get("email_senha", os.getenv("EMAIL_SENHA", ""))
    destinos = list(EMAILS_BENEDITO)
    if not senha:
        return False

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinos)
    msg["Subject"] = f"💬 Nova Interação da Gestão [{tipo}]: {loja}"

    corpo = f"""Olá,

O supervisor {supervisor} registrou uma nova interação na loja {loja} (Auditoria de {data_auditoria}).

Tipo: {tipo}
Comentário: "{comentario}"

Atenciosamente,
Sistema de Auditoria Automática.
"""
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    try:
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(remetente, senha)
        s.sendmail(remetente, destinos, msg.as_string())
        s.quit()
        return True
    except Exception:
        return False


def salvar_comentario_planilha(
    loja, supervisor, comentario, tipo="Feedback", data_auditoria=""
):
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet_com = wb.worksheet("Comentarios_Gestao")
            except Exception:
                sheet_com = wb.add_worksheet(
                    title="Comentarios_Gestao", rows="100", cols="7"
                )
                sheet_com.append_row([
                    "Loja",
                    "Supervisor",
                    "Tipo",
                    "Comentário",
                    "Data_Auditoria",
                    "Data/Hora_Interacao",
                ])

            fuso_sp = pytz.timezone("America/Sao_Paulo")
            agora = datetime.now(fuso_sp).strftime("%d/%m/%Y %H:%M")
            sheet_com.append_row(
                [loja, supervisor, tipo, comentario, data_auditoria, agora]
            )
            enviar_email_interacao(loja, supervisor, tipo, comentario, data_auditoria)
            return True
    except Exception:
        return False
    return False


def salvar_no_google_sheets(dados_auditoria):
    try:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet = wb.worksheet("Historico_Auditorias")
            except Exception:
                try:
                    sheet = wb.add_worksheet(
                        title="Historico_Auditorias", rows="100", cols="25"
                    )
                    sheet.append_row([
                        "Data/Hora",
                        "Promotora",
                        "Cidade",
                        "Loja",
                        "Nota Total",
                        "Share Cão",
                        "Share Gato",
                        "Share Vet",
                        "Frentes Cão JSON",
                        "Frentes Gato JSON",
                        "Frentes Vet JSON",
                        "Plano Cão",
                        "Fluxo Cão",
                        "Plano Gato",
                        "Fluxo Gato",
                        "Sep FHN",
                        "Plano Vet",
                        "Fluxo Vet",
                        "Materiais JSON",
                        "Conservação",
                        "Pontos Extras",
                        "Observações",
                        "Fotos JSON",
                    ])
                except Exception:
                    sheet = wb.sheet1

            dados_str = [str(x) for x in dados_auditoria]
            sheet.append_row(dados_str)
            return True
    except Exception as e:
        print(f"Erro crítico ao salvar no Google Sheets: {e}")
        return False
    return False


# --- CÁLCULO DE NOTA E DIAGNÓSTICO UNIFICADO ---
def calcular_frentes_faltantes(frentes_rc, frentes_total, meta_share_pct):
    frentes_concorrentes = frentes_total - frentes_rc
    if frentes_concorrentes <= 0:
        return 0
    meta_dec = meta_share_pct / 100.0
    frentes_necessarias = math.ceil(
        (meta_dec * frentes_concorrentes) / (1.0 - meta_dec)
    )
    return max(0, frentes_necessarias - frentes_rc)


def calcular_pontuacao_e_diagnostico(
    frentes_cao,
    plano_cao,
    fluxo_cao,
    frentes_gato,
    plano_gato,
    fluxo_gato,
    sep_fhn,
    frentes_vet,
    plano_vet,
    fluxo_vet,
    materiais_ativos_lista,
    conservacao,
    qtd_pontos_extras,
):
    total_cao = sum(frentes_cao.values())
    share_cao = (
        (frentes_cao["Royal Canin"] / total_cao * 100) if total_cao > 0 else 0.0
    )

    total_gato = sum(frentes_gato.values())
    share_gato = (
        (frentes_gato["Royal Canin"] / total_gato * 100) if total_gato > 0 else 0.0
    )

    total_vet = sum(frentes_vet.values())
    share_vet = (
        (frentes_vet["Royal Canin"] / total_vet * 100) if total_vet > 0 else 0.0
    )

    p_cao = (
        (1.0 if plano_cao == "Sim" else 0.0)
        + (1.0 if fluxo_cao == "Sim" else 0.0)
        + (0.5 if share_cao >= 30.0 else 0.0)
    )
    p_gato = (
        (1.0 if plano_gato == "Sim" else 0.0)
        + (1.0 if fluxo_gato == "Sim" else 0.0)
        + (0.5 if share_gato >= 35.0 else 0.0)
        + (0.5 if sep_fhn == "Sim" else 0.0)
    )
    p_vet = (
        (1.0 if plano_vet == "Sim" else 0.0)
        + (1.0 if fluxo_vet == "Sim" else 0.0)
        + (0.5 if share_vet >= 50.0 else 0.0)
    )

    total_materiais = len(materiais_ativos_lista)
    if total_materiais >= 3:
        p_merch = 0.75
    elif total_materiais == 2:
        p_merch = 0.50
    elif total_materiais == 1:
        p_merch = 0.25
    else:
        p_merch = 0.0

    p_cons = 0.25 if conservacao == "Sim" else 0.0

    if qtd_pontos_extras >= 3:
        p_extras = 1.0
    elif qtd_pontos_extras == 2:
        p_extras = 0.5
    elif qtd_pontos_extras == 1:
        p_extras = 0.25
    else:
        p_extras = 0.0

    nota_total = round(p_cao + p_gato + p_vet + p_merch + p_cons + p_extras, 2)

    faltas = []
    if plano_cao != "Sim":
        faltas.append("• [Cão] Aplicar planograma (+1.0 pt)")
    if fluxo_cao != "Sim":
        faltas.append("• [Cão] Ajustar abertura de fluxo (+1.0 pt)")
    if share_cao < 30.0:
        f_falt = calcular_frentes_faltantes(frentes_cao["Royal Canin"], total_cao, 30.0)
        faltas.append(
            f"• [Cão] Aumentar share para 30% (Faltam {f_falt} frentes) (+0.5 pt)"
        )

    if plano_gato != "Sim":
        faltas.append("• [Gato] Aplicar planograma (+1.0 pt)")
    if fluxo_gato != "Sim":
        faltas.append("• [Gato] Ajustar abertura de fluxo (+1.0 pt)")
    if share_gato < 35.0:
        f_falt = calcular_frentes_faltantes(
            frentes_gato["Royal Canin"], total_gato, 35.0
        )
        faltas.append(
            f"• [Gato] Aumentar share para 35% (Faltam {f_falt} frentes) (+0.5 pt)"
        )
    if sep_fhn != "Sim":
        faltas.append("• [Gato] Separar Super Premium da linha FHN (+0.5 pt)")

    if plano_vet != "Sim":
        faltas.append("• [Vet] Aplicar planograma (+1.0 pt)")
    if fluxo_vet != "Sim":
        faltas.append("• [Vet] Ajustar abertura de fluxo (+1.0 pt)")
    if share_vet < 50.0:
        f_falt = calcular_frentes_faltantes(frentes_vet["Royal Canin"], total_vet, 50.0)
        faltas.append(
            f"• [Vet] Aumentar share para 50% (Faltam {f_falt} frentes) (+0.5 pt)"
        )

    if total_materiais < 3:
        faltas.append(
            f"• [Merchandising] Adicionar materiais POP (Atual: {total_materiais}, Meta: 3+) (+{0.75 - p_merch:.2f} pt)"
        )
    if conservacao != "Sim":
        faltas.append("• [Merchandising] Melhorar estado de conservação (+0.25 pt)")

    if qtd_pontos_extras < 3:
        faltas.append(
            f"• [Pontos Extras] Conquistar mais pontos extras (Atual: {qtd_pontos_extras}, Meta: 3+) (+{1.0 - p_extras:.2f} pt)"
        )

    return {
        "nota_total": nota_total,
        "share_cao": share_cao,
        "share_gato": share_gato,
        "share_vet": share_vet,
        "faltas": faltas,
    }


# --- GRÁFICO EXECUTIVO DE SHARE PARA O PDF ---
def gerar_grafico_share_pdf(
    share_cao: float, share_gato: float, share_vet: float
) -> str | None:
    if not TEM_MATPLOTLIB:
        return None
    try:
        pilares = ["Linha Cão", "Linha Gato", "Linha Vet"]
        valores = [share_cao, share_gato, share_vet]
        metas = [30.0, 35.0, 50.0]
        cores_barras = [
            "#059669" if v >= m else "#E2001A" for v, m in zip(valores, metas)
        ]

        fig, ax = plt.subplots(figsize=(6.8, 2.3), dpi=200)
        y_pos = [2, 1, 0]

        ax.barh(
            y_pos, [100, 100, 100], height=0.52, color="#F3F4F6", edgecolor="#E5E7EB"
        )
        ax.barh(
            y_pos, [min(v, 100) for v in valores], height=0.52, color=cores_barras
        )

        for y, meta, val in zip(y_pos, metas, valores):
            ax.plot(
                [meta, meta],
                [y - 0.34, y + 0.34],
                color="#1F2937",
                linewidth=2.2,
                linestyle="--",
            )
            status = "✓ Meta" if val >= meta else f"Meta {meta:.0f}%"
            ax.text(
                min(val, 82) + 2,
                y,
                f"{val:.1f}%  ({status})",
                va="center",
                ha="left",
                fontsize=8.5,
                fontweight="bold",
                color="#111827",
            )

        ax.set_yticks(y_pos)
        ax.set_yticklabels(pilares, fontsize=9, fontweight="bold", color="#1F2937")
        ax.set_xlim(0, 105)
        ax.set_xlabel("Participação em Frentes (%)", fontsize=8, color="#4B5563")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#D1D5DB")
        ax.spines["bottom"].set_color("#D1D5DB")
        ax.tick_params(axis="x", labelsize=8, colors="#4B5563")
        plt.tight_layout()

        tmp_chart = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        fig.savefig(tmp_chart.name, dpi=200, bbox_inches="tight")
        tmp_chart.close()
        plt.close(fig)
        return tmp_chart.name
    except Exception:
        return None


# --- GERAR PDF EXECUTIVO COM LOGOS E CNPJ ---
def gerar_pdf_auditoria(
    tipo_auditoria,
    promotora,
    loja,
    cnpj,
    codigo_loja,
    cidade,
    endereco,
    dados_completos,
    nota_total,
    frentes_dados,
    caminhos_fotos=None,
    eh_teste=False,
    texto_melhorias_pdf=None,
):
    loja_limpa = (
        "".join([c for c in loja if c.isalnum() or c in (" ", "_", "-")])
        .strip()
        .replace(" ", "_")
    )
    prefixo_teste = "TESTE_" if eh_teste else ""
    arq_completo = (
        f"{prefixo_teste}{tipo_auditoria.upper().replace('-', '_')}_{loja_limpa}.pdf"
    )

    estilos = getSampleStyleSheet()
    cor_royal = colors.HexColor("#E2001A")
    cor_chumbo = colors.HexColor("#1F2937")
    cor_fundo_suave = colors.HexColor("#F8FAFC")
    cor_borda = colors.HexColor("#CBD5E1")

    style_celula = ParagraphStyle(
        "EstiloCelula",
        parent=estilos["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=cor_chumbo,
    )
    style_celula_bold = ParagraphStyle(
        "EstiloCelulaBold",
        parent=style_celula,
        fontName="Helvetica-Bold",
    )
    style_celula_cab = ParagraphStyle(
        "EstiloCelulaCab",
        parent=estilos["Normal"],
        fontSize=8.5,
        leading=10.5,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    style_titulo_exec = ParagraphStyle(
        "TituloExec",
        parent=estilos["Title"],
        fontSize=12.5,
        leading=15,
        alignment=1,
        textColor=cor_chumbo,
        spaceAfter=0,
    )
    style_secao = ParagraphStyle(
        "SecaoExec",
        parent=estilos["Heading3"],
        fontSize=10,
        textColor=cor_royal,
        spaceBefore=6,
        spaceAfter=4,
    )
    style_melhorias = ParagraphStyle(
        "EstiloMelhorias",
        parent=estilos["Normal"],
        fontSize=9.5,
        leading=14,
        textColor=cor_chumbo,
    )

    fuso_sp = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(fuso_sp).strftime("%d/%m/%Y %H:%M")

    caminho_grafico_temp = gerar_grafico_share_pdf(
        dados_completos.get("share_cao", 0.0),
        dados_completos.get("share_gato", 0.0),
        dados_completos.get("share_vet", 0.0),
    )

    def carregar_logo_rl(caminho_logo, largura, altura, fallback_texto):
        if os.path.exists(caminho_logo):
            try:
                return RLImage(
                    caminho_logo, width=largura, height=altura, kind="proportional"
                )
            except Exception:
                pass
        return Paragraph(f"<b>{fallback_texto}</b>", style_celula_bold)

    def criar_pagina_1():
        elem = []
        selo_teste = " <font color='#E2001A'>[TESTE]</font>" if eh_teste else ""

        logo_esq = carregar_logo_rl(LOGO_MINASSAL, 85, 42, "MINASSAL")
        logo_dir = carregar_logo_rl(LOGO_ROYAL, 90, 42, "ROYAL CANIN")
        titulo_centro = Paragraph(
            f"<b>RELATÓRIO EXECUTIVO — {tipo_auditoria.upper()}{selo_teste}</b><br/>"
            "<font size=8.5 color='#4B5563'>Auditoria de Execução &amp; Shelf Space • Juiz de Fora 2026</font>",
            style_titulo_exec,
        )

        t_header = Table(
            [[logo_esq, titulo_centro, logo_dir]], colWidths=[95, 350, 95]
        )
        t_header.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 2.0, cor_royal),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ])
        )
        elem.append(t_header)
        elem.append(Spacer(1, 8))

        cor_nota = (
            "#059669"
            if nota_total >= 8.0
            else ("#D97706" if nota_total >= 6.0 else "#E2001A")
        )
        cod_txt = f" (Cód.: {html.escape(str(codigo_loja))})" if codigo_loja else ""
        cnpj_txt = html.escape(str(cnpj)) if cnpj else "Não informado"
        info_pdv = Paragraph(
            f"<b>LOJA:</b> {html.escape(str(loja))}{cod_txt}<br/>"
            f"<b>CNPJ:</b> <font color='#E2001A'><b>{cnpj_txt}</b></font><br/>"
            f"<b>CIDADE:</b> {html.escape(str(cidade))} &nbsp;|&nbsp; <b>ENDEREÇO:</b> {html.escape(str(endereco))}<br/>"
            f"<b>RESPONSÁVEL:</b> {html.escape(str(promotora))} &nbsp;|&nbsp; <b>DATA/HORA:</b> {agora}",
            style_celula,
        )
        box_nota = Paragraph(
            "<font size=8 color='#4B5563'><b>NOTA FINAL PDV</b></font><br/>"
            f"<font size=18 color='{cor_nota}'><b>{nota_total:.2f}</b></font>"
            "<font size=9 color='#6B7280'> / 10.0</font>",
            ParagraphStyle("BoxNota", parent=style_celula, alignment=1, leading=16),
        )

        t_resumo = Table([[info_pdv, box_nota]], colWidths=[415, 125])
        t_resumo.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), cor_fundo_suave),
                ("BOX", (0, 0), (-1, -1), 0.7, cor_borda),
                ("LINEBEFORE", (1, 0), (1, 0), 1.0, cor_borda),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        elem.append(t_resumo)
        elem.append(Spacer(1, 8))

        elem.append(Paragraph("<b>1. PERFORMANCE DE SHARE POR PILAR</b>", style_secao))

        if caminho_grafico_temp and os.path.exists(caminho_grafico_temp):
            elem.append(
                RLImage(caminho_grafico_temp, width=520, height=175, kind="proportional")
            )
            elem.append(Spacer(1, 6))
        else:
            data_share = [[
                Paragraph("<b>Pilar</b>", style_celula_cab),
                Paragraph("<b>Share</b>", style_celula_cab),
                Paragraph("<b>Meta</b>", style_celula_cab),
                Paragraph("<b>Status</b>", style_celula_cab),
            ]]
            for nome_pilar, val, meta in [
                ("Linha Cão", dados_completos.get("share_cao", 0), 30.0),
                ("Linha Gato", dados_completos.get("share_gato", 0), 35.0),
                ("Linha Veterinária", dados_completos.get("share_vet", 0), 50.0),
            ]:
                cor_txt = "#059669" if val >= meta else "#E2001A"
                status_txt = "Meta Atingida" if val >= meta else "Abaixo da Meta"
                data_share.append([
                    Paragraph(nome_pilar, style_celula),
                    Paragraph(
                        f"<font color='{cor_txt}'><b>{val:.1f}%</b></font>", style_celula
                    ),
                    Paragraph(f"{meta:.1f}%", style_celula),
                    Paragraph(
                        f"<font color='{cor_txt}'><b>{status_txt}</b></font>",
                        style_celula,
                    ),
                ])
            t_share = Table(data_share, colWidths=[150, 90, 90, 210])
            t_share.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), cor_royal),
                    ("GRID", (0, 0), (-1, -1), 0.5, cor_borda),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ])
            )
            elem.append(t_share)
            elem.append(Spacer(1, 6))

        elem.append(Paragraph("<b>2. CHECKLIST DE EXECUÇÃO</b>", style_secao))
        data_exec = [
            [
                Paragraph("<b>Pilar / Categoria</b>", style_celula_cab),
                Paragraph("<b>Planograma?</b>", style_celula_cab),
                Paragraph("<b>Abertura Fluxo?</b>", style_celula_cab),
                Paragraph("<b>Regra Específica</b>", style_celula_cab),
            ],
            [
                Paragraph("Linha Cão", style_celula_bold),
                Paragraph(dados_completos.get("plano_cao", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_cao", ""), style_celula),
                Paragraph("Meta de Frentes &ge; 30%", style_celula),
            ],
            [
                Paragraph("Linha Gato", style_celula_bold),
                Paragraph(dados_completos.get("plano_gato", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_gato", ""), style_celula),
                Paragraph(
                    f"Super Premium Sep.: {dados_completos.get('sep_fhn', '')}",
                    style_celula,
                ),
            ],
            [
                Paragraph("Linha Veterinária", style_celula_bold),
                Paragraph(dados_completos.get("plano_vet", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_vet", ""), style_celula),
                Paragraph("Meta de Frentes &ge; 50%", style_celula),
            ],
        ]
        t_exec = Table(data_exec, colWidths=[120, 85, 100, 235])
        t_exec.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_chumbo),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, cor_fundo_suave]),
                ("GRID", (0, 0), (-1, -1), 0.5, cor_borda),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elem.append(t_exec)
        elem.append(Spacer(1, 6))

        elem.append(Paragraph("<b>3. MERCHANDISING E PONTOS EXTRAS</b>", style_secao))
        mat_ativos = dados_completos.get("materiais_ativos", [])
        materiais_str = (
            ", ".join(mat_ativos) if mat_ativos else "Nenhum material assinalado"
        )

        data_merch = [
            [
                Paragraph("<b>Indicador</b>", style_celula_cab),
                Paragraph("<b>Resultado / Detalhe</b>", style_celula_cab),
            ],
            [
                Paragraph("Materiais Presentes", style_celula_bold),
                Paragraph(materiais_str, style_celula),
            ],
            [
                Paragraph("Conservação Adequada?", style_celula_bold),
                Paragraph(str(dados_completos.get("conservacao", "")), style_celula),
            ],
            [
                Paragraph("Pontos Extras (Qtd)", style_celula_bold),
                Paragraph(str(dados_completos.get("qtd_extras", 0)), style_celula),
            ],
        ]
        t_merch = Table(data_merch, colWidths=[150, 390])
        t_merch.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_royal),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, cor_fundo_suave]),
                ("GRID", (0, 0), (-1, -1), 0.5, cor_borda),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elem.append(t_merch)
        elem.append(Spacer(1, 6))

        if dados_completos.get("observacoes"):
            elem.append(Paragraph("<b>4. OBSERVAÇÕES DA VISITA</b>", style_secao))
            t_obs = Table(
                [[Paragraph(html.escape(dados_completos["observacoes"]), style_celula)]],
                colWidths=[540],
            )
            t_obs.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), cor_fundo_suave),
                    ("GRID", (0, 0), (-1, -1), 0.5, cor_borda),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            elem.append(t_obs)

        return elem

    def criar_pagina_2():
        elem = []
        elem.append(PageBreak())
        elem.append(
            Paragraph(
                "<b>ANEXO 1: DETALHAMENTO DE FRENTES POR MARCA</b>", style_titulo_exec
            )
        )
        elem.append(Spacer(1, 10))

        data_frentes = [[
            Paragraph("<b>Marca / Concorrente</b>", style_celula_cab),
            Paragraph("<b>Frentes Cão</b>", style_celula_cab),
            Paragraph("<b>Frentes Gato</b>", style_celula_cab),
            Paragraph("<b>Frentes Vet</b>", style_celula_cab),
        ]]

        for m in MARCAS_PADRAO:
            estilo_linha = style_celula_bold if m == "Royal Canin" else style_celula
            data_frentes.append([
                Paragraph(m, estilo_linha),
                Paragraph(str(frentes_dados["cao"].get(m, 0)), estilo_linha),
                Paragraph(str(frentes_dados["gato"].get(m, 0)), estilo_linha),
                Paragraph(str(frentes_dados["vet"].get(m, 0)), estilo_linha),
            ])

        t_frentes = Table(data_frentes, colWidths=[210, 110, 110, 110])
        estilos_tab = [
            ("BACKGROUND", (0, 0), (-1, 0), cor_chumbo),
            ("GRID", (0, 0), (-1, -1), 0.5, cor_borda),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            (
                "BACKGROUND",
                (0, len(MARCAS_PADRAO)),
                (-1, len(MARCAS_PADRAO)),
                colors.HexColor("#FEF2F2"),
            ),
        ]
        t_frentes.setStyle(TableStyle(estilos_tab))
        elem.append(t_frentes)
        elem.append(Spacer(1, 12))

        if caminhos_fotos:
            elem.append(PageBreak())
            elem.append(
                Paragraph(
                    "<b>ANEXO 2: EVIDÊNCIAS FOTOGRÁFICAS</b>", style_titulo_exec
                )
            )
            elem.append(Spacer(1, 10))
            linhas_tabela = []
            par_atual = []
            for caminho in caminhos_fotos:
                if caminho and os.path.exists(caminho):
                    try:
                        img_element = RLImage(
                            caminho, width=230, height=220, kind="proportional"
                        )
                        par_atual.append(img_element)
                        if len(par_atual) == 2:
                            linhas_tabela.append(par_atual)
                            par_atual = []
                    except Exception:
                        pass
            if par_atual:
                par_atual.append("")
                linhas_tabela.append(par_atual)

            if linhas_tabela:
                t_fotos = Table(linhas_tabela, colWidths=[270, 270])
                t_fotos.setStyle(
                    TableStyle([
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ])
                )
                elem.append(t_fotos)

        return elem

    def criar_pagina_melhorias():
        if not texto_melhorias_pdf:
            return []
        elem = []
        elem.append(PageBreak())
        elem.append(Paragraph("<b>MELHORIAS</b>", style_titulo_exec))
        elem.append(Spacer(1, 10))

        texto_limpo = texto_melhorias_pdf.replace("📊 ", "").replace("🎯 ", "")
        texto_html = html.escape(texto_limpo).replace("\n", "<br/>")

        t_melhorias = Table(
            [[Paragraph(texto_html, style_melhorias)]],
            colWidths=[540],
        )
        t_melhorias.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), cor_fundo_suave),
                ("BOX", (0, 0), (-1, -1), 0.7, cor_borda),
                ("LINEABOVE", (0, 0), (-1, 0), 2.0, cor_royal),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ])
        )
        elem.append(t_melhorias)
        return elem

    def adicionar_rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(
            25, 15, f"Minassal Distribuidora • Royal Canin | {loja} | CNPJ: {cnpj}"
        )
        canvas.drawRightString(
            A4[0] - 25, 15, "Desenvolvido por Benedito Bandola"
        )
        canvas.restoreState()

    try:
        doc_completo = SimpleDocTemplate(
            arq_completo,
            pagesize=A4,
            rightMargin=25,
            leftMargin=25,
            topMargin=22,
            bottomMargin=28,
        )
        doc_completo.build(
            criar_pagina_1() + criar_pagina_2() + criar_pagina_melhorias(),
            onFirstPage=adicionar_rodape,
            onLaterPages=adicionar_rodape,
        )
    finally:
        if caminho_grafico_temp and os.path.exists(caminho_grafico_temp):
            try:
                os.remove(caminho_grafico_temp)
            except Exception:
                pass

    return arq_completo


def enviar_email_auditoria(assunto, anexos_paths, destinatarios, corpo_email=""):
    remetente = st.secrets.get("email_remetente", "beneditobandola@gmail.com")
    senha = st.secrets.get("email_senha", os.getenv("EMAIL_SENHA", ""))
    destinatarios_limpos = list(
        dict.fromkeys([d.strip() for d in destinatarios if "@" in d])
    )
    if not senha or not destinatarios_limpos:
        return False

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios_limpos)
    msg["Subject"] = assunto

    if not corpo_email:
        corpo_email = (
            "Olá,\n\nSegue em anexo o relatório executivo e as comprovações da"
            " auditoria.\n\nAtenciosamente,\nSistema de Auditoria Shelf Space."
        )

    msg.attach(MIMEText(corpo_email, "plain", "utf-8"))

    try:
        for caminho_arquivo in anexos_paths:
            if caminho_arquivo and os.path.exists(caminho_arquivo):
                nome_arquivo_anexo = os.path.basename(caminho_arquivo)
                with open(caminho_arquivo, "rb") as f:
                    part = MIMEApplication(f.read(), Name=nome_arquivo_anexo)
                part.add_header(
                    "Content-Disposition", "attachment", filename=nome_arquivo_anexo
                )
                msg.attach(part)

        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(remetente, senha)
        s.sendmail(remetente, destinatarios_limpos, msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False


# --- MENU LATERAL DE NAVEGAÇÃO (COM LOGOS) ---
dados_json_nav = carregar_dados_json()
rascunhos_nav = carregar_rascunhos_json().get("rascunhos", {})
qtd_oficiais = len(dados_json_nav.get("auditorias", []))
qtd_testes = len(dados_json_nav.get("testes", []))
qtd_rascunhos = sum(
    1
    for item in rascunhos_nav.values()
    if rascunho_tem_dados_preenchidos(item.get("dados", {}))
)

col_l1, col_l2 = st.sidebar.columns(2)
with col_l1:
    if os.path.exists(LOGO_MINASSAL):
        st.image(LOGO_MINASSAL, use_container_width=True)
with col_l2:
    if os.path.exists(LOGO_ROYAL):
        st.image(LOGO_ROYAL, use_container_width=True)

st.sidebar.title("🐾 Auditoria Juiz de Fora 2026")
st.sidebar.caption(
    f"💾 Oficiais: **{qtd_oficiais}** | 📝 Rascunhos: **{qtd_rascunhos}** | 🧪 Testes: **{qtd_testes}**"
)

if "menu_principal" not in st.session_state:
    st.session_state["menu_principal"] = "📝 Área da Promotora"


def voltar_menu_principal():
    st.session_state["menu_principal"] = "📝 Área da Promotora"


menu = st.sidebar.selectbox(
    "Escolha o Módulo:",
    [
        "📝 Área da Promotora",
        "📋 Histórico & Feedbacks",
        "🔒 Painel Admin (Supervisores)",
    ],
    key="menu_principal",
)

if menu != "📝 Área da Promotora":
    st.sidebar.button(
        "🏠 Voltar ao Menu Principal",
        on_click=voltar_menu_principal,
        use_container_width=True,
    )

# ==============================================================
# FLUXO 1: ÁREA DA PROMOTORA
# ==============================================================
if menu == "📝 Área da Promotora":
    st.markdown(
        """
        <div class="banner-executivo">
            <h1>🐾 Auditoria Juiz de Fora 2026</h1>
            <p>Execução de Ponto de Venda &amp; Shelf Space • Minassal Distribuidora &amp; Royal Canin</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df_clientes.empty:
        st.warning("A planilha de clientes não foi encontrada ou está vazia.")
    else:

        def normalize(text):
            if pd.isna(text):
                return ""
            nfkd = unicodedata.normalize("NFKD", str(text))
            return (
                "".join([c for c in nfkd if not unicodedata.combining(c)])
                .upper()
                .strip()
            )

        df_clientes["CIDADE_NORM"] = df_clientes["CIDADE"].apply(normalize)
        df_clientes["NOME_NORM"] = df_clientes["NOME"].apply(normalize)

        coluna_codigo = None
        for col_posivel in ["CODIGO", "CÓDIGO", "ID", "COD", "CLIENTE", "CNPJ"]:
            if col_posivel in df_clientes.columns:
                coluna_codigo = col_posivel
                break

        if coluna_codigo:
            df_clientes["COD_NORM"] = (
                df_clientes[coluna_codigo]
                .astype(str)
                .str.replace(".0", "", regex=False)
                .str.strip()
            )
        else:
            df_clientes["COD_NORM"] = ""

        # Recupera última loja ativa caso a página tenha recarregado no celular
        ultima_loja_info = carregar_rascunhos_json().get("ultima_loja_ativa", {})
        tipos_opts = ["Pré-Auditoria", "Auditoria"]
        proms_opts = [
            "Auditoria Juiz de Fora",
            "Pamela",
            "Fernanda",
            "Madalla",
            "Sarmento",
            "Paulo Maia",
        ]

        idx_tipo_default = 0
        if ultima_loja_info.get("tipo_auditoria") in tipos_opts:
            idx_tipo_default = tipos_opts.index(ultima_loja_info["tipo_auditoria"])

        idx_prom_default = 0
        if ultima_loja_info.get("promotora") in proms_opts:
            idx_prom_default = proms_opts.index(ultima_loja_info["promotora"])

        st.subheader("1. Identificação e Tipo de Registro")

        col_tipo, col_prom = st.columns(2)
        with col_tipo:
            tipo_auditoria = st.radio(
                "Selecione o Tipo de Registro:",
                tipos_opts,
                index=idx_tipo_default,
                horizontal=True,
                key="radio_tipo_auditoria",
            )
        with col_prom:
            promotora = st.selectbox(
                "Selecione a Promotora / Supervisor:",
                proms_opts,
                index=idx_prom_default,
                key="sel_promotora_ativa",
            )

        if promotora == "Auditoria Juiz de Fora":
            df_jf_base = df_clientes[
                df_clientes["COD_NORM"].isin(CODIGOS_JUIZ_DE_FORA_ORDEM)
            ].copy()
            if df_jf_base.empty:
                df_jf_base = df_clientes[
                    df_clientes["CIDADE_NORM"] == "JUIZ DE FORA"
                ].copy()

            codigos_oficiais_auditados = {
                str(r.get("codigo_loja", "")).strip()
                for r in dados_json_nav.get("auditorias", [])
                if not r.get("registro_teste", False)
            }

            lojas_ordenadas = []
            for idx_ord, cod_alvo in enumerate(CODIGOS_JUIZ_DE_FORA_ORDEM, start=1):
                match = df_jf_base[df_jf_base["COD_NORM"] == cod_alvo]
                if not match.empty:
                    nome_cli = str(match.iloc[0]["NOME"]).strip()
                    apelido = APELIDOS_POR_CODIGO.get(cod_alvo, nome_cli)
                    lojas_ordenadas.append((idx_ord, cod_alvo, apelido, nome_cli))

            st.subheader("2. Seleção da Loja (Ordem Juiz de Fora)")
            if lojas_ordenadas:
                rotulos = []
                mapa_rotulo_nome = {}
                idx_loja_default = 0
                cod_salvo_ultimo = str(ultima_loja_info.get("codigo_loja", "")).strip()

                for i_rot, (idx_ord, cod_alvo, apelido, nome_cli) in enumerate(
                    lojas_ordenadas
                ):
                    chave_teste_rasc = f"{tipo_auditoria}__{cod_alvo}__{nome_cli}"
                    tem_rasc = rascunho_tem_dados_preenchidos(
                        (obter_rascunho_loja(chave_teste_rasc) or {}).get("dados", {})
                    )
                    if cod_alvo in codigos_oficiais_auditados:
                        marca_json = "✅"
                    elif tem_rasc:
                        marca_json = "📝"
                    else:
                        marca_json = "⏳"

                    rot = f"{marca_json} #{idx_ord:02d} • [{cod_alvo}] {nome_cli} ({apelido})"
                    rotulos.append(rot)
                    mapa_rotulo_nome[rot] = nome_cli
                    if cod_salvo_ultimo and cod_alvo == cod_salvo_ultimo:
                        idx_loja_default = i_rot

                rotulo_escolhido = st.selectbox(
                    "Selecione o Cliente / Loja (✅ Auditada | 📝 Rascunho salvo | ⏳ Pendente):",
                    rotulos,
                    index=idx_loja_default,
                    key="sel_loja_jf_ativa",
                )
                loja_selecionada = mapa_rotulo_nome[rotulo_escolhido]
                df_filtrado = df_jf_base
            else:
                loja_selecionada = None
                df_filtrado = df_jf_base
        else:
            cidades_map = {
                "Pamela": [
                    "POCOS DE CALDAS",
                    "ANDRADAS",
                    "VARGINHA",
                    "ALFENAS",
                    "SAO LOURENCO",
                    "ITAJUBA",
                    "TRES PONTAS",
                    "TRES CORACOES",
                    "POUSO ALEGRE",
                ],
                "Fernanda": ["JUIZ DE FORA"],
                "Madalla": [
                    "MURIAE",
                    "VICOSA",
                    "UBA",
                    "VISCONDE DO RIO BRANCO",
                    "PIRAUBA",
                    "RIO POMBA",
                    "GUARANI",
                    "GUIDOVAL",
                    "TOCANTINS",
                    "SAO JOAO NEPOMUCENO",
                    "RIO NOVO",
                    "RODEIRO",
                ],
                "Sarmento": [
                    "SAO JOSE DO RIO PRETO",
                    "MIRASSOL",
                    "OLIMPIA",
                    "IBIRA",
                    "POTIRENDABA",
                    "JOSE BONIFACIO",
                    "NEVES PAULISTA",
                    "TABAPUA",
                    "POLONI",
                    "CEDRAL",
                    "TANABI",
                    "JACI",
                    "BADY BASSITT",
                    "IPIGUA",
                    "NOVA GRANADA",
                    "GUAPIACU",
                    "MONTE APRAZIVEL",
                    "URUPES",
                    "MENDONCA",
                    "BALSAMO",
                    "UCHOA",
                    "CATIGUA",
                    "MIRASSOLANDIA",
                ],
                "Paulo Maia": [
                    "RIBEIRAO PRETO",
                    "BATATAIS",
                    "SERRANA",
                    "JARDINOPOLIS",
                    "SERTAOZINHO",
                    "CRAVINHOS",
                    "PONTAL",
                    "SAO SIMAO",
                    "PITANGUEIRAS",
                    "BRODOWSKI",
                    "LUIS ANTONIO",
                    "DUMONT",
                    "SALES OLIVEIRA",
                    "BARRINHA",
                    "SERRA AZUL",
                    "SAO CARLOS",
                    "MATAO",
                    "ARARAQUARA",
                    "IBATE",
                    "BOA ESPERANCA DO SUL",
                    "AMERICO BRASILIENSE",
                    "RINCAO",
                    "DOURADO",
                    "NOVA EUROPA",
                    "RIBEIRAO BONITO",
                    "SANTA LUCIA",
                    "TABATINGA",
                    "SAO JOSE DO RIO PARDO",
                    "VARGEM GRANDE DO SUL",
                    "MOCOCA",
                    "DIVINOLANDIA",
                    "CASA BRANCA",
                    "SAO SEBASTIAO DA GRAMA",
                    "SAO JOAO DA BOA VISTA",
                    "TAPIRATIBA",
                    "ITOBI",
                    "AGUAS PRATA",
                    "ALTINOPOLIS",
                ],
            }
            cidades_alvo = cidades_map.get(promotora, [])
            df_filtrado = df_clientes[df_clientes["CIDADE_NORM"].isin(cidades_alvo)]
            lojas_lista = sorted(df_filtrado["NOME"].dropna().unique().tolist())

            idx_outra_default = 0
            nome_salvo_ultimo = str(ultima_loja_info.get("nome_loja", "")).strip()
            if nome_salvo_ultimo in lojas_lista:
                idx_outra_default = lojas_lista.index(nome_salvo_ultimo)

            st.subheader("2. Seleção da Loja")
            loja_selecionada = (
                st.selectbox(
                    "Selecione o Cliente / Loja:",
                    lojas_lista,
                    index=idx_outra_default,
                    key="sel_loja_outra_ativa",
                )
                if lojas_lista
                else None
            )

        if loja_selecionada:
            dados_loja = df_filtrado[df_filtrado["NOME"] == loja_selecionada].iloc[0]
            codigo_loja_atual = str(dados_loja.get("COD_NORM", "")).strip()
            cidade_loja = str(dados_loja.get("CIDADE", "")).strip()
            bairro_loja = str(dados_loja.get("BAIRRO", "")).strip()
            uf_loja = str(dados_loja.get("UF", "MG")).strip()
            endereco_loja = str(
                dados_loja.get("ENDEREÇO", "Endereço não informado")
            ).strip()
            endereco_exibicao = (
                f"{endereco_loja} - {bairro_loja}"
                if bairro_loja and bairro_loja.lower() != "nan"
                else endereco_loja
            )

            doc_bruto = str(dados_loja.get("DOCUMENTO", "")).strip()
            if doc_bruto.endswith(".0"):
                doc_bruto = doc_bruto[:-2]

            nums_doc = "".join([c for c in doc_bruto if c.isdigit()])
            if len(nums_doc) == 14:
                cnpj_formatado = f"{nums_doc[:2]}.{nums_doc[2:5]}.{nums_doc[5:8]}/{nums_doc[8:12]}-{nums_doc[12:]}"
            elif 0 < len(nums_doc) < 14:
                nums_doc = nums_doc.zfill(14)
                cnpj_formatado = f"{nums_doc[:2]}.{nums_doc[2:5]}.{nums_doc[5:8]}/{nums_doc[8:12]}-{nums_doc[12:]}"
            else:
                cnpj_formatado = "Não informado"

            # Chave única do rascunho para esta loja + tipo de auditoria
            chave_rascunho_atual = (
                f"{tipo_auditoria}__{codigo_loja_atual}__{loja_selecionada}"
            )

            # Sempre que abrir ou trocar de loja, carrega o rascunho exclusivo dela
            if (
                st.session_state.get("chave_rascunho_carregada")
                != chave_rascunho_atual
            ):
                rascunho_existente = obter_rascunho_loja(chave_rascunho_atual)
                carregar_estado_rascunho_na_sessao(
                    chave_rascunho_atual, rascunho_existente
                )
                salvar_ultima_loja_ativa(
                    promotora, tipo_auditoria, codigo_loja_atual, loja_selecionada
                )

            # --- TRAVA VISUAL: AVISO EXPLÍCITO DA LOJA ATIVA ---
            apelido_atual = APELIDOS_POR_CODIGO.get(codigo_loja_atual, "")
            apelido_badge = (
                f" ({apelido_atual})"
                if apelido_atual
                and apelido_atual.lower() != loja_selecionada.lower()
                else ""
            )
            st.markdown(
                f"""
                <div class="trava-loja-alerta">
                    <div class="titulo-trava">⚠️ ATENÇÃO: A LOJA QUE VOCÊ ESTÁ AGORA É:</div>
                    <div class="nome-loja-trava">{html.escape(loja_selecionada)}{html.escape(apelido_badge)}</div>
                    <div style="font-size: 14px; color: #1E293B;">
                        🏢 <b>Cód.:</b> {html.escape(codigo_loja_atual)} &nbsp;|&nbsp;
                        <b>CNPJ:</b> <span style="color: #E2001A; font-weight: 900; font-family: monospace;">{html.escape(cnpj_formatado)}</span>
                    </div>
                    <div style="font-size: 13px; color: #475569; margin-top: 2px;">
                        📍 <b>Cidade:</b> {html.escape(cidade_loja)}/{html.escape(uf_loja)} &nbsp;|&nbsp;
                        <b>Endereço:</b> {html.escape(endereco_exibicao)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_maps, col_limpar_rasc = st.columns([3, 1.4])
            with col_maps:
                query_maps = urllib.parse.quote(
                    f"{endereco_loja}, {bairro_loja}, {cidade_loja} - {uf_loja}"
                )
                url_maps = (
                    f"https://www.google.com/maps/search/?api=1&query={query_maps}"
                )
                st.link_button(
                    "🗺️ Abrir endereço no Google Maps",
                    url_maps,
                    use_container_width=True,
                )
            with col_limpar_rasc:
                if st.button(
                    "🧹 Zerar Rascunho desta Loja",
                    use_container_width=True,
                    key="btn_zerar_rascunho",
                ):
                    limpar_rascunho_loja(chave_rascunho_atual)
                    carregar_estado_rascunho_na_sessao(chave_rascunho_atual, None)
                    st.rerun()

            ja_auditada_oficial = any(
                str(r.get("codigo_loja", "")).strip() == codigo_loja_atual
                for r in dados_json_nav.get("auditorias", [])
                if not r.get("registro_teste", False)
            )
            if ja_auditada_oficial and tipo_auditoria == "Auditoria":
                st.warning(
                    f"🔒 **Trava de Segurança:** A loja **{loja_selecionada}** já possui uma auditoria oficial registrada. "
                    "Confira se você não está sobrescrevendo por engano antes de salvar."
                )

            st.markdown("---")
            st.subheader("3. Contagem de Frentes & Share por Pilar")

            st.markdown("### 🐶 Linha Cão (Meta: 30%)")
            frentes_cao = {
                m: st.number_input(
                    f"[Cão] Frentes - {m}",
                    min_value=0,
                    max_value=100,
                    key=f"cao_{m}",
                )
                for m in MARCAS_PADRAO
            }
            total_cao = sum(frentes_cao.values())
            share_cao = (
                (frentes_cao["Royal Canin"] / total_cao * 100)
                if total_cao > 0
                else 0.0
            )
            st.write(f"📊 **Share Cão Atual:** {share_cao:.1f}% (Meta: 30%)")

            plano_cao = st.radio(
                "Linha Cão está no Planograma?", ["Sim", "Não"], key="plano_cao"
            )
            fluxo_cao = st.radio(
                "Royal Canin está abrindo o Fluxo (Cão)?",
                ["Sim", "Não"],
                key="fluxo_cao",
            )

            st.markdown("---")
            st.markdown("### 🐱 Linha Gato (Meta: 35%)")
            frentes_gato = {
                m: st.number_input(
                    f"[Gato] Frentes - {m}",
                    min_value=0,
                    max_value=100,
                    key=f"gato_{m}",
                )
                for m in MARCAS_PADRAO
            }
            total_gato = sum(frentes_gato.values())
            share_gato = (
                (frentes_gato["Royal Canin"] / total_gato * 100)
                if total_gato > 0
                else 0.0
            )
            st.write(f"📊 **Share Gato Atual:** {share_gato:.1f}% (Meta: 35%)")

            plano_gato = st.radio(
                "Linha Gato está no Planograma?", ["Sim", "Não"], key="plano_gato"
            )
            fluxo_gato = st.radio(
                "Royal Canin está abrindo o Fluxo (Gato)?",
                ["Sim", "Não"],
                key="fluxo_gato",
            )
            sep_fhn = st.radio(
                "Super Premium Cat está separada da linha FHN?",
                ["Sim", "Não"],
                key="sep_fhn",
            )

            st.markdown("---")
            st.markdown("### 🩺 Linha Veterinária / Tratamento (Meta: 50%)")
            frentes_vet = {
                m: st.number_input(
                    f"[Vet] Frentes - {m}",
                    min_value=0,
                    max_value=100,
                    key=f"vet_{m}",
                )
                for m in MARCAS_PADRAO
            }
            total_vet = sum(frentes_vet.values())
            share_vet = (
                (frentes_vet["Royal Canin"] / total_vet * 100)
                if total_vet > 0
                else 0.0
            )
            st.write(f"📊 **Share Vet Atual:** {share_vet:.1f}% (Meta: 50%)")

            plano_vet = st.radio(
                "Linha Vet está no Planograma?", ["Sim", "Não"], key="plano_vet"
            )
            fluxo_vet = st.radio(
                "Royal Canin está abrindo o Fluxo (Vet)?",
                ["Sim", "Não"],
                key="fluxo_vet",
            )

            st.markdown("---")
            st.subheader("4. Merchandising e Presença de Materiais")
            mat_presenca = {
                mat: st.checkbox(mat, key=f"mat_{mat}") for mat in MATERIAIS_PADRAO
            }
            materiais_ativos_lista = [m for m in MATERIAIS_PADRAO if mat_presenca[m]]
            conservacao = st.radio(
                "Os materiais estão bem executados e em bom estado de conservação?",
                ["Sim", "Não"],
                key="conservacao",
            )

            st.markdown("---")
            st.subheader("5. Pontos Extras Presentes")
            qtd_pontos_extras = st.number_input(
                "Quantidade de Pontos Extras encontrados:",
                min_value=0,
                max_value=10,
                key="qtd_pontos_extras",
            )

            # --- PAINEL EXECUTIVO AO VIVO ---
            res_diag = calcular_pontuacao_e_diagnostico(
                frentes_cao,
                plano_cao,
                fluxo_cao,
                frentes_gato,
                plano_gato,
                fluxo_gato,
                sep_fhn,
                frentes_vet,
                plano_vet,
                fluxo_vet,
                materiais_ativos_lista,
                conservacao,
                qtd_pontos_extras,
            )
            nota_live = res_diag["nota_total"]
            faltas_live = res_diag["faltas"]

            st.markdown("---")
            st.subheader("🎯 Diagnóstico Executivo em Tempo Real")
            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            c_m1.metric("Nota Atual", f"{nota_live:.2f} / 10")
            c_m2.metric("Share Cão", f"{share_cao:.1f}%", f"{share_cao - 30.0:+.1f}% meta")
            c_m3.metric(
                "Share Gato", f"{share_gato:.1f}%", f"{share_gato - 35.0:+.1f}% meta"
            )
            c_m4.metric("Share Vet", f"{share_vet:.1f}%", f"{share_vet - 50.0:+.1f}% meta")

            with st.expander(
                "📋 Ver Plano de Ação Imediato (O que falta para Nota 10)", expanded=False
            ):
                if faltas_live:
                    st.markdown("\n".join(faltas_live))
                else:
                    st.success("🏆 PDV com nota máxima e 100% de conformidade!")

            # --- 6. REGISTRO FOTOGRÁFICO OTIMIZADO ---
            st.markdown("---")
            st.subheader("6. Registro Fotográfico")
            st.info(
                "💡 As fotos são comprimidas automaticamente em alta nitidez para o PDF sem travar o celular."
            )
            arquivos_fotos = st.file_uploader(
                "Envie as fotos da auditoria:",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="uploader_fotos_auditoria",
            )

            caminhos_temporarios = processar_fotos_com_cache(arquivos_fotos)

            if arquivos_fotos:
                tamanho_total_mb = sum(
                    getattr(arq, "size", 0) for arq in arquivos_fotos
                ) / (1024 * 1024)
                st.caption(
                    f"📸 {len(caminhos_temporarios)} foto(s) pronta(s) para o PDF "
                    f"(originais: {tamanho_total_mb:.1f} MB — otimizadas automaticamente)"
                )
                if len(arquivos_fotos) > 15:
                    st.warning(
                        "⚠️ Mais de 15 fotos selecionadas. No celular, prefira até 10–12 fotos por auditoria para maior velocidade."
                    )

                cols = st.columns(3)
                for idx, caminho_otimizado in enumerate(caminhos_temporarios):
                    with cols[idx % 3]:
                        st.image(
                            caminho_otimizado,
                            caption=f"Foto {idx + 1}",
                            use_container_width=True,
                        )

            # --- 7. OBSERVAÇÕES POR VOZ ---
            st.markdown("---")
            st.subheader("7. Observações por Voz (Transcrição Automática)")

            if "texto_transcrito_voz" not in st.session_state:
                st.session_state["texto_transcrito_voz"] = ""
            if "audio_key_id" not in st.session_state:
                st.session_state["audio_key_id"] = 0

            audio_gravado = st.audio_input(
                "🎙️ Grave o áudio falando as observações da loja:",
                key=f"audio_input_{st.session_state['audio_key_id']}",
            )

            if audio_gravado is not None:
                col_transc, col_apagar = st.columns([3, 1])
                with col_transc:
                    if st.button("✨ Transcrever Áudio em Texto"):
                        with st.spinner("Interpretando e transcrevendo áudio..."):
                            caminho_audio_temp = None
                            try:
                                with tempfile.NamedTemporaryFile(
                                    delete=False, suffix=".wav"
                                ) as f_audio:
                                    f_audio.write(audio_gravado.getvalue())
                                    caminho_audio_temp = f_audio.name

                                r = sr.Recognizer()
                                with sr.AudioFile(caminho_audio_temp) as source:
                                    audio_data = r.record(source)
                                    texto_falado = r.recognize_google(
                                        audio_data, language="pt-BR"
                                    )
                                    st.session_state["texto_transcrito_voz"] = (
                                        texto_falado
                                    )
                                    st.session_state["obs_campo_texto"] = texto_falado
                                    st.success("✅ Áudio transcrito com sucesso!")
                            except sr.UnknownValueError:
                                st.warning(
                                    "⚠️ Não foi possível entender o áudio. Tente falar mais perto."
                                )
                            except Exception as e:
                                st.error(f"Erro ao transcrever: {e}")
                            finally:
                                if caminho_audio_temp and os.path.exists(
                                    caminho_audio_temp
                                ):
                                    try:
                                        os.remove(caminho_audio_temp)
                                    except Exception:
                                        pass
                with col_apagar:
                    if st.button("🗑️ Apagar Tudo"):
                        st.session_state["texto_transcrito_voz"] = ""
                        st.session_state["obs_campo_texto"] = ""
                        st.session_state["audio_key_id"] += 1
                        st.rerun()

            observacoes_promotora = st.text_area(
                "Revise ou complemente o texto transcrito da observação:",
                key="obs_campo_texto",
            )

            # --- EXECUÇÃO DO AUTO-SAVE EM JSON A CADA ALTERAÇÃO ---
            snapshot_atual = {
                "codigo_loja": codigo_loja_atual,
                "loja": loja_selecionada,
                "cnpj": cnpj_formatado,
                "tipo_auditoria": tipo_auditoria,
                "promotora": promotora,
                "frentes_cao": frentes_cao,
                "plano_cao": plano_cao,
                "fluxo_cao": fluxo_cao,
                "frentes_gato": frentes_gato,
                "plano_gato": plano_gato,
                "fluxo_gato": fluxo_gato,
                "sep_fhn": sep_fhn,
                "frentes_vet": frentes_vet,
                "plano_vet": plano_vet,
                "fluxo_vet": fluxo_vet,
                "materiais_ativos": materiais_ativos_lista,
                "conservacao": conservacao,
                "qtd_extras": qtd_pontos_extras,
                "observacoes": observacoes_promotora.strip(),
            }
            hora_autosave = salvar_rascunho_loja(chave_rascunho_atual, snapshot_atual)
            st.markdown(
                f'<div class="badge-autosave">💾 Auto-save ativo ({ARQUIVO_JSON_RASCUNHOS}) • Último salvamento desta loja: {hora_autosave}</div>',
                unsafe_allow_html=True,
            )

            # --- 8. GRUPOS DE E-MAIL E ENVIO ---
            st.markdown("---")
            st.subheader("8. Opções de Envio e Grupos de E-mail")

            grupos_disponiveis = carregar_grupos_email()
            nomes_grupos = list(grupos_disponiveis.keys())
            opcao_envio = st.selectbox(
                "Selecione o Grupo de Destinatários:",
                nomes_grupos,
            )
            emails_do_grupo = list(grupos_disponiveis.get(opcao_envio, EMAILS_BENEDITO))
            st.caption(f"📧 Destinatários do grupo: {', '.join(emails_do_grupo)}")

            emails_avulsos_raw = st.text_input(
                "➕ Adicionar e-mail(s) avulso(s) neste envio (separados por vírgula):",
                placeholder="gerente@royalcanin.com, diretor@minassal.com.br",
            )

            with st.expander(
                "⚙️ Gerenciar Grupos de E-mail (Criar, Editar ou Excluir)"
            ):
                tab_novo_grp, tab_del_grp = st.tabs([
                    "💾 Criar / Editar Grupo",
                    "🗑️ Excluir Grupo",
                ])
                with tab_novo_grp:
                    grupo_base_edit = st.selectbox(
                        "Preencher a partir de um grupo existente (opcional):",
                        ["(Novo Grupo)"] + nomes_grupos,
                        key="sel_edit_grupo",
                    )
                    nome_default = (
                        "" if grupo_base_edit == "(Novo Grupo)" else grupo_base_edit
                    )
                    emails_default = (
                        ""
                        if grupo_base_edit == "(Novo Grupo)"
                        else ", ".join(grupos_disponiveis.get(grupo_base_edit, []))
                    )

                    novo_nome_grupo = st.text_input(
                        "Nome do Grupo:",
                        value=nome_default,
                        placeholder="Ex: Gerência Royal Canin MG",
                        key="inp_nome_grupo",
                    )
                    novos_emails_texto = st.text_area(
                        "E-mails separados por vírgula:",
                        value=emails_default,
                        placeholder="benedito.bandola@minassal.com.br, beneditobandola@gmail.com, gerente@royalcanin.com",
                        key="inp_emails_grupo",
                    )
                    if st.button(
                        "💾 Salvar Grupo na Planilha", key="btn_salvar_grupo"
                    ):
                        lista_valida = [
                            e.strip()
                            for e in novos_emails_texto.replace(";", ",").split(",")
                            if "@" in e
                        ]
                        if novo_nome_grupo.strip() and lista_valida:
                            if salvar_grupo_email(novo_nome_grupo, lista_valida):
                                st.success(
                                    f"✅ Grupo '{novo_nome_grupo}' salvo no Google Sheets!"
                                )
                                st.rerun()
                            else:
                                st.error(
                                    "Erro ao salvar grupo. Verifique a conexão com o Google Sheets."
                                )
                        else:
                            st.warning(
                                "Informe um nome para o grupo e pelo menos um e-mail válido."
                            )

                with tab_del_grp:
                    if len(nomes_grupos) > 1:
                        grupo_excluir = st.selectbox(
                            "Selecione o grupo para excluir:",
                            nomes_grupos,
                            key="sel_del_grupo",
                        )
                        conf_del_grp = st.checkbox(
                            f"Confirmar exclusão do grupo '{grupo_excluir}'",
                            key="conf_del_grupo",
                        )
                        if st.button(
                            "🗑️ Excluir Grupo",
                            disabled=not conf_del_grp,
                            key="btn_del_grupo",
                        ):
                            if excluir_grupo_email(grupo_excluir):
                                st.success(f"Grupo '{grupo_excluir}' excluído!")
                                st.rerun()
                            else:
                                st.error("Não foi possível excluir o grupo.")
                    else:
                        st.info("Mantenha pelo menos um grupo cadastrado.")

            mostrar_o_que_falta = st.checkbox(
                "🔍 MOSTRAR O QUE FALTA (Incluir no e-mail o diagnóstico detalhado para atingir Nota 10)",
                value=True,
            )

            incluir_melhorias_pdf = st.checkbox(
                "📄 INCLUIR PÁGINA 'MELHORIAS' NO PDF (Adicionar o mesmo conteúdo do corpo do e-mail em uma página do PDF)",
                value=True,
            )

            registrar_como_teste = st.checkbox(
                "🧪 Registrar como teste (não entra nas auditorias oficiais nem dá baixa na loja)",
                value=False,
            )
            if registrar_como_teste:
                st.warning(
                    "Modo TESTE ativado: este registro será marcado com "
                    "`registro_teste: true`, enviado somente para o Benedito e "
                    "não será gravado no Google Sheets oficial."
                )

            # --- TRAVA FINAL ANTES DE SALVAR E ENVIAR ---
            st.markdown("---")
            confirmacao_loja_envio = st.checkbox(
                f"🔒 Confirmo que estou na loja **{loja_selecionada}** (Cód.: {codigo_loja_atual} • CNPJ: {cnpj_formatado}) e desejo finalizar.",
                key="confirmar_loja_correta",
            )

            if st.button(
                "Finalizar, Salvar e Enviar Auditoria",
                type="primary",
                disabled=not confirmacao_loja_envio,
            ):
                if registrar_como_teste:
                    destinatarios = list(EMAILS_BENEDITO)
                else:
                    destinatarios = list(emails_do_grupo)
                    if emails_avulsos_raw.strip():
                        extras = [
                            e.strip()
                            for e in emails_avulsos_raw.replace(";", ",").split(",")
                            if "@" in e
                        ]
                        destinatarios.extend(extras)
                    if "benedito.bandola@minassal.com.br" in destinatarios:
                        destinatarios.append("beneditobandola@gmail.com")
                    destinatarios = list(dict.fromkeys(destinatarios))

                nota_total = res_diag["nota_total"]
                faltas = res_diag["faltas"]

                dados_completos = {
                    "share_cao": share_cao,
                    "plano_cao": plano_cao,
                    "fluxo_cao": fluxo_cao,
                    "share_gato": share_gato,
                    "plano_gato": plano_gato,
                    "fluxo_gato": fluxo_gato,
                    "sep_fhn": sep_fhn,
                    "share_vet": share_vet,
                    "plano_vet": plano_vet,
                    "fluxo_vet": fluxo_vet,
                    "materiais_ativos": materiais_ativos_lista,
                    "conservacao": conservacao,
                    "qtd_extras": qtd_pontos_extras,
                    "observacoes": observacoes_promotora.strip(),
                }

                frentes_dados = {
                    "cao": frentes_cao,
                    "gato": frentes_gato,
                    "vet": frentes_vet,
                }

                fuso_sp = pytz.timezone("America/Sao_Paulo")
                data_atual = datetime.now(fuso_sp).strftime("%d/%m/%Y %H:%M:%S")

                corpo_email = (
                    f"Olá,\n\nSegue o relatório executivo e as comprovações da auditoria referente a "
                    f"{tipo_auditoria.upper()} da loja {loja_selecionada} (CNPJ: {cnpj_formatado} - {cidade_loja}).\n\n"
                )
                corpo_email += f"📊 NOTA FINAL ATUAL: {nota_total:.2f} / 10.0 pts\n"
                corpo_email += f"• Share Cão: {share_cao:.1f}% (Meta: 30%)\n"
                corpo_email += f"• Share Gato: {share_gato:.1f}% (Meta: 35%)\n"
                corpo_email += f"• Share Veterinária: {share_vet:.1f}% (Meta: 50%)\n\n"

                if mostrar_o_que_falta:
                    corpo_email += (
                        "==================================================\n"
                    )
                    corpo_email += (
                        "🎯 PLANO DE AÇÃO: O QUE FALTA PARA ATINGIR NOTA 10.0?\n"
                    )
                    corpo_email += (
                        "==================================================\n\n"
                    )
                    if faltas:
                        corpo_email += "\n".join(faltas) + "\n\n"
                    else:
                        corpo_email += "Parabéns! PDV com nota máxima e 100% de conformidade!\n\n"

                corpo_email += f"Observações: {observacoes_promotora.strip() if observacoes_promotora.strip() else 'Nenhuma.'}\n\n"
                corpo_email += "Atenciosamente,\nSistema de Auditoria Shelf Space • Minassal / Royal Canin."

                with st.spinner(
                    "Gerando PDF executivo, gravando histórico e enviando..."
                ):
                    pdf_path = gerar_pdf_auditoria(
                        tipo_auditoria,
                        promotora,
                        loja_selecionada,
                        cnpj_formatado,
                        codigo_loja_atual,
                        cidade_loja,
                        endereco_exibicao,
                        dados_completos,
                        nota_total,
                        frentes_dados,
                        caminhos_temporarios,
                        eh_teste=registrar_como_teste,
                        texto_melhorias_pdf=(
                            corpo_email if incluir_melhorias_pdf else None
                        ),
                    )

                    lista_anexos = [pdf_path]
                    audio_novo_path = None

                    if audio_gravado is not None:
                        loja_limpa = (
                            "".join([
                                c
                                for c in loja_selecionada
                                if c.isalnum() or c in (" ", "_", "-")
                            ])
                            .strip()
                            .replace(" ", "_")
                        )
                        data_hora_arq = datetime.now(fuso_sp).strftime("%d-%m-%Y_%H-%M")
                        tipo_arq = tipo_auditoria.upper().replace("-", "_")

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".wav"
                        ) as f_audio_envio:
                            f_audio_envio.write(audio_gravado.getvalue())
                            audio_temp_path = f_audio_envio.name

                        audio_novo_path = os.path.join(
                            tempfile.gettempdir(),
                            f"Audio_{tipo_arq}_{loja_limpa}_{data_hora_arq}.wav",
                        )
                        os.replace(audio_temp_path, audio_novo_path)
                        lista_anexos.append(audio_novo_path)

                    if not registrar_como_teste:
                        dados_planilha = [
                            data_atual,
                            promotora,
                            cidade_loja,
                            loja_selecionada,
                            f"{nota_total:.2f}",
                            f"{share_cao:.1f}",
                            f"{share_gato:.1f}",
                            f"{share_vet:.1f}",
                            json.dumps(frentes_cao, ensure_ascii=False),
                            json.dumps(frentes_gato, ensure_ascii=False),
                            json.dumps(frentes_vet, ensure_ascii=False),
                            plano_cao,
                            fluxo_cao,
                            plano_gato,
                            fluxo_gato,
                            sep_fhn,
                            plano_vet,
                            fluxo_vet,
                            json.dumps(materiais_ativos_lista, ensure_ascii=False),
                            conservacao,
                            qtd_pontos_extras,
                            observacoes_promotora.strip(),
                            json.dumps([]),
                        ]
                        salvou_sheets = salvar_no_google_sheets(dados_planilha)
                    else:
                        salvou_sheets = False

                    prefixo_assunto = "[TESTE] " if registrar_como_teste else ""
                    assunto = f"{prefixo_assunto}📋 Relatório {tipo_auditoria}: {loja_selecionada} ({cidade_loja}) - Nota {nota_total:.2f}"
                    enviado = enviar_email_auditoria(
                        assunto, lista_anexos, destinatarios, corpo_email
                    )

                    registro_json = {
                        "id": f"JF_{codigo_loja_atual}_{datetime.now(fuso_sp).strftime('%Y%m%d%H%M%S')}",
                        "registro_teste": registrar_como_teste,
                        "data_hora": data_atual,
                        "tipo_auditoria": tipo_auditoria,
                        "promotora": promotora,
                        "codigo_loja": codigo_loja_atual,
                        "loja": loja_selecionada,
                        "cnpj": cnpj_formatado,
                        "cidade": cidade_loja,
                        "endereco": endereco_exibicao,
                        "nota_total": round(nota_total, 2),
                        "shares": {
                            "cao": round(share_cao, 1),
                            "gato": round(share_gato, 1),
                            "vet": round(share_vet, 1),
                        },
                        "frentes": frentes_dados,
                        "checklist": {
                            "plano_cao": plano_cao,
                            "fluxo_cao": fluxo_cao,
                            "plano_gato": plano_gato,
                            "fluxo_gato": fluxo_gato,
                            "sep_fhn": sep_fhn,
                            "plano_vet": plano_vet,
                            "fluxo_vet": fluxo_vet,
                        },
                        "merchandising": {
                            "materiais": materiais_ativos_lista,
                            "conservacao": conservacao,
                            "qtd_pontos_extras": qtd_pontos_extras,
                        },
                        "observacoes": observacoes_promotora.strip(),
                        "incluir_melhorias_pdf": incluir_melhorias_pdf,
                        "melhorias_plano_acao": faltas,
                        "texto_melhorias_email": corpo_email,
                        "destinatarios_envio": destinatarios,
                        "sincronizado_sheets": salvou_sheets,
                        "email_enviado": enviado,
                    }
                    salvou_json = registrar_no_json(
                        registro_json, eh_teste=registrar_como_teste
                    )

                    if salvou_json:
                        limpar_rascunho_loja(chave_rascunho_atual)

                    if audio_novo_path and os.path.exists(audio_novo_path):
                        try:
                            os.remove(audio_novo_path)
                        except Exception:
                            pass

                    if registrar_como_teste:
                        st.info(
                            "🧪 Registro salvo apenas na área de **testes** do JSON "
                            "(`registro_teste: true`). Não foi incluído nas auditorias oficiais."
                        )
                    elif salvou_json:
                        st.info(
                            f"💾 Auditoria oficial salva no JSON (`{ARQUIVO_JSON_HISTORICO}`) e loja marcada como auditada!"
                        )

                    if enviado:
                        st.success(
                            f"✅ Relatório PDF gerado e enviado para: {', '.join(destinatarios)}"
                        )
                    else:
                        st.warning(
                            "⚠️ Salvo no JSON local (verifique a senha de e-mail nos secrets caso queira disparo automático)."
                        )

                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "📥 Baixar PDF Gerado",
                            data=f,
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf",
                        )

# ==============================================================
# FLUXO 2: HISTÓRICO & FEEDBACKS
# ==============================================================
elif menu == "📋 Histórico & Feedbacks":
    st.button(
        "🏠 Voltar ao Menu Principal",
        on_click=voltar_menu_principal,
        key="btn_voltar_hist",
    )
    st.title("📋 Histórico de Auditorias & Feedbacks")
    st.markdown("---")

    dados_json = carregar_dados_json()
    auditorias_oficiais = dados_json.get("auditorias", [])
    registros_testes = dados_json.get("testes", [])
    roteiro_status = dados_json.get("lojas_roteiro", [])

    tab_oficial, tab_roteiro, tab_testes, tab_sheets = st.tabs([
        f"✅ Auditorias Oficiais ({len(auditorias_oficiais)})",
        f"📍 Status Roteiro JF ({len(roteiro_status)})",
        f"🧪 Testes ({len(registros_testes)})",
        "☁️ Google Sheets",
    ])

    with tab_oficial:
        if auditorias_oficiais:
            linhas_of = []
            for r in reversed(auditorias_oficiais):
                sh = r.get("shares", {})
                linhas_of.append({
                    "ID": r.get("id", ""),
                    "Data/Hora": r.get("data_hora", ""),
                    "Tipo": r.get("tipo_auditoria", ""),
                    "Cód.": r.get("codigo_loja", ""),
                    "Loja": r.get("loja", ""),
                    "CNPJ": r.get("cnpj", ""),
                    "Nota": r.get("nota_total", 0),
                    "Share Cão": f"{sh.get('cao', 0)}%",
                    "Share Gato": f"{sh.get('gato', 0)}%",
                    "Share Vet": f"{sh.get('vet', 0)}%",
                    "Observações": r.get("observacoes", ""),
                })
            st.dataframe(
                pd.DataFrame(linhas_of), use_container_width=True, hide_index=True
            )

            st.markdown("#### 🗑️ Apagar auditoria para refazer")
            opcoes_apagar = {
                f"[{r.get('codigo_loja')}] {r.get('loja')} — {r.get('data_hora')} (Nota {r.get('nota_total')})": r.get(
                    "id"
                )
                for r in reversed(auditorias_oficiais)
                if r.get("id")
            }
            if opcoes_apagar:
                escolha_apagar = st.selectbox(
                    "Selecione a auditoria que deseja apagar:",
                    list(opcoes_apagar.keys()),
                    key="sel_apagar_oficial",
                )
                confirmar_apagar_of = st.checkbox(
                    "Confirmar que desejo apagar permanentemente esta auditoria para refazer",
                    key="conf_apagar_oficial",
                )
                if st.button(
                    "🗑️ Confirmar e apagar auditoria",
                    key="btn_apagar_oficial",
                    disabled=not confirmar_apagar_of,
                ):
                    if excluir_registro_json(
                        opcoes_apagar[escolha_apagar], eh_teste=False
                    ):
                        st.success(
                            "Auditoria apagada do JSON e loja devolvida a pendente! Agora você pode refazer na Área da Promotora."
                        )
                        st.rerun()
        else:
            st.info(
                "Nenhuma auditoria oficial registrada ainda (registros de teste não aparecem aqui)."
            )

        st.download_button(
            "⬇️ Baixar JSON Oficial (Backup)",
            data=json.dumps(dados_json, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="historico_juiz_de_fora_audit.json",
            mime="application/json",
            use_container_width=True,
        )

        st.markdown("#### 📤 Upar Backup JSON (Sem Duplicar)")
        st.caption(
            "Envie um arquivo `.json` de backup. Os registros que já existem são ignorados automaticamente para não duplicar, e os novos são adicionados."
        )
        arquivo_backup_up = st.file_uploader(
            "Selecione o arquivo de backup (.json):",
            type=["json"],
            key="uploader_backup_json",
        )
        if arquivo_backup_up is not None:
            if st.button(
                "📥 Mesclar Backup ao JSON Atual",
                key="btn_mesclar_backup",
                use_container_width=True,
            ):
                try:
                    res_merge = mesclar_backup_json_sem_duplicar(
                        arquivo_backup_up.getvalue()
                    )
                    if res_merge["salvou"]:
                        st.success(
                            f"✅ Backup mesclado! Novas oficiais: **{res_merge['adicionadas_oficiais']}** "
                            f"(duplicadas ignoradas: {res_merge['ignoradas_duplicadas_oficiais']}) | "
                            f"Novos testes: **{res_merge['adicionadas_testes']}** "
                            f"(duplicados ignorados: {res_merge['ignoradas_duplicadas_testes']})."
                        )
                        st.rerun()
                    else:
                        st.error("Não foi possível salvar o JSON mesclado.")
                except Exception as e:
                    st.error(f"Erro ao ler ou mesclar o backup JSON: {e}")

    with tab_roteiro:
        if roteiro_status:
            linhas_rot = [
                {
                    "Ordem": l.get("ordem"),
                    "Status": (
                        "✅ Auditada"
                        if l.get("status_visita") == "auditada"
                        else "⏳ Pendente"
                    ),
                    "Código": l.get("codigo_loja"),
                    "Referência": l.get("apelido"),
                    "Loja": l.get("loja"),
                    "Endereço": l.get("endereco"),
                }
                for l in roteiro_status
            ]
            st.dataframe(
                pd.DataFrame(linhas_rot), use_container_width=True, hide_index=True
            )
        else:
            st.info(
                "Coloque o arquivo `historico_juiz_de_fora_audit.json` na pasta do projeto para visualizar o painel de status das 10 lojas."
            )

    with tab_testes:
        if registros_testes:
            linhas_t = [
                {
                    "ID": r.get("id", ""),
                    "Data/Hora": r.get("data_hora", ""),
                    "Cód.": r.get("codigo_loja", ""),
                    "Loja": r.get("loja", ""),
                    "CNPJ": r.get("cnpj", ""),
                    "Nota": r.get("nota_total", 0),
                    "registro_teste": r.get("registro_teste", True),
                    "Observações": r.get("observacoes", ""),
                }
                for r in reversed(registros_testes)
            ]
            st.dataframe(
                pd.DataFrame(linhas_t), use_container_width=True, hide_index=True
            )

            st.markdown("#### 🗑️ Apagar registro de teste")
            opcoes_apagar_teste = {
                f"[{r.get('codigo_loja')}] {r.get('loja')} — {r.get('data_hora')} (Nota {r.get('nota_total')})": r.get(
                    "id"
                )
                for r in reversed(registros_testes)
                if r.get("id")
            }
            if opcoes_apagar_teste:
                escolha_teste = st.selectbox(
                    "Selecione o teste que deseja apagar:",
                    list(opcoes_apagar_teste.keys()),
                    key="sel_apagar_teste",
                )
                confirmar_apagar_teste = st.checkbox(
                    "Confirmar que desejo apagar este registro de teste",
                    key="conf_apagar_teste",
                )
                if st.button(
                    "🗑️ Confirmar e apagar teste",
                    key="btn_apagar_teste",
                    disabled=not confirmar_apagar_teste,
                ):
                    if excluir_registro_json(
                        opcoes_apagar_teste[escolha_teste], eh_teste=True
                    ):
                        st.success("Registro de teste apagado com sucesso!")
                        st.rerun()

            st.markdown("---")
            confirmar_limpar_todos_testes = st.checkbox(
                "Confirmar que desejo limpar TODOS os registros de teste de uma vez",
                key="conf_limpar_todos_testes",
            )
            if st.button(
                "🧹 Confirmar e limpar todos os testes do JSON",
                disabled=not confirmar_limpar_todos_testes,
            ):
                limpar_testes_json()
                st.success("Registros de teste removidos com sucesso!")
                st.rerun()
        else:
            st.info("Nenhum registro de teste salvo no momento.")

    with tab_sheets:
        wb = conectar_google_sheets()
        if wb:
            try:
                sheet = wb.worksheet("Historico_Auditorias")
                dados = sheet.get_all_records()
                if dados:
                    df_hist = pd.DataFrame(dados)
                    st.dataframe(df_hist.tail(20), use_container_width=True)
                else:
                    st.info("Nenhuma auditoria registrada até o momento.")
            except Exception as e:
                st.error(f"Erro ao ler histórico: {e}")
        else:
            st.error("Não foi possível conectar ao Google Sheets.")

# ==============================================================
# FLUXO 3: PAINEL ADMIN
# ==============================================================
elif menu == "🔒 Painel Admin (Supervisores)":
    st.button(
        "🏠 Voltar ao Menu Principal",
        on_click=voltar_menu_principal,
        key="btn_voltar_admin",
    )
    st.title("🔒 Painel Administrativo de Supervisores")
    st.markdown("---")

    usuarios_disp = listar_usuarios_cadastrados()
    usuario_sel = st.selectbox(
        "Selecione seu Usuário:", ["Selecione..."] + usuarios_disp
    )

    if usuario_sel != "Selecione...":
        senha_correta = buscar_senha_usuario(usuario_sel)

        if not senha_correta:
            st.warning("Primeiro acesso deste usuário! Cadastre sua senha abaixo:")
            with st.form("form_cad_admin"):
                nova_senha = st.text_input("Defina sua nova senha:", type="password")
                confirma_senha = st.text_input(
                    "Confirme sua nova senha:", type="password"
                )
                btn_salvar = st.form_submit_button("Salvar Nova Senha")

                if btn_salvar:
                    if nova_senha and nova_senha == confirma_senha:
                        if salvar_nova_senha(usuario_sel, nova_senha):
                            st.success(
                                "Senha cadastrada com sucesso! Recarregue a página."
                            )
                            st.rerun()
                        else:
                            st.error("Erro ao salvar a senha na planilha.")
                    else:
                        st.error("As senhas digitadas não coincidem ou estão vazias.")
        else:
            with st.form("form_login_admin"):
                senha_digitada = st.text_input("Digite sua senha:", type="password")
                btn_entrar = st.form_submit_button("Entrar")

                if btn_entrar:
                    if senha_digitada == senha_correta:
                        st.session_state[f"auth_{usuario_sel}"] = True
                        registrar_log_acesso(usuario_sel)
                        st.success(f"Bem-vindo(a), {usuario_sel}!")
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")

        if st.session_state.get(f"auth_{usuario_sel}", False):
            st.markdown("---")
            st.subheader("💬 Registrar Feedback / Ação para Loja")

            wb = conectar_google_sheets()
            if wb:
                try:
                    sheet = wb.worksheet("Historico_Auditorias")
                    registros = sheet.get_all_records()
                    if registros:
                        df_aud = pd.DataFrame(registros)
                        lojas_aud = df_aud["Loja"].dropna().unique().tolist()

                        loja_comentar = st.selectbox(
                            "Selecione a Loja Auditada:", lojas_aud
                        )
                        tipo_interacao = st.selectbox(
                            "Tipo de Registro:",
                            [
                                "Feedback da Visita",
                                "Plano de Ação Corretiva",
                                "Observação Geral",
                            ],
                        )
                        comentario_texto = st.text_area(
                            "Descreva a orientação ou retorno para a promotora/gestão:"
                        )

                        if st.button("Salvar e Notificar por E-mail"):
                            if comentario_texto.strip():
                                sucesso = salvar_comentario_planilha(
                                    loja_comentar,
                                    usuario_sel,
                                    comentario_texto,
                                    tipo_interacao,
                                )
                                if sucesso:
                                    st.success(
                                        "✅ Feedback registrado e notificação por e-mail enviada com sucesso!"
                                    )
                                else:
                                    st.error("Erro ao registrar feedback.")
                            else:
                                st.warning("Digite um comentário antes de enviar.")
                    else:
                        st.info(
                            "Nenhuma auditoria cadastrada para receber feedbacks."
                        )
                except Exception as e:
                    st.error(f"Erro ao buscar histórico: {e}")

# --- ASSINATURA DE AUTORIA ---
st.markdown(
    "<br><hr><p style='text-align: center; color: #555555; font-size: 11px;'>Desenvolvido por Benedito Bandola</p>",
    unsafe_allow_html=True,
)
