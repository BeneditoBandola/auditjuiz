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

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Juiz De Fora audit — Shelf Space Royal Canin",
    page_icon="🐾",
    layout="centered",
    initial_sidebar_state="expanded",
)

# --- ARQUIVOS E ORDEM DA AUDITORIA JUIZ DE FORA ---
ARQUIVO_JSON_HISTORICO = Path("historico_juiz_de_fora_audit.json")
NOME_PLANILHA_SHEETS = "Juiz_De_Fora_Audit"

CODIGOS_JUIZ_DE_FORA_ORDEM = [
    "21294",  # Veterinária Mendes Andrade
    "21873",  # Cristiano Resende
    "21878",  # Luciano tostes
    "21888",  # Rp agrop (RR Agropecuaria)
    "21209",  # Agrotela
    "21921",  # Cinthia
    "24310",  # Bahpet (Supermercado Bahamas)
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


# --- HISTÓRICO LOCAL EM JSON ---
def carregar_historico_json() -> list[dict]:
    if ARQUIVO_JSON_HISTORICO.exists():
        try:
            data = json.loads(ARQUIVO_JSON_HISTORICO.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("auditorias", [])
            if isinstance(data, list):
                return data
        except Exception as e:
            st.warning(f"Erro ao ler {ARQUIVO_JSON_HISTORICO}: {e}")
    return []


def salvar_historico_json(registros: list[dict]) -> bool:
    try:
        payload = {
            "projeto": "Juiz De Fora audit",
            "atualizado_em": datetime.now(pytz.timezone("America/Sao_Paulo")).strftime(
                "%d/%m/%Y %H:%M:%S"
            ),
            "total_registros": len(registros),
            "auditorias": registros,
        }
        ARQUIVO_JSON_HISTORICO.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    except Exception as e:
        st.error(f"Erro ao salvar {ARQUIVO_JSON_HISTORICO}: {e}")
        return False


def registrar_no_json(novo_registro: dict) -> bool:
    historico = carregar_historico_json()
    historico.append(novo_registro)
    return salvar_historico_json(historico)


# --- CARREGAR PLANILHA DE CLIENTES ---
@st.cache_data
def load_clients():
    for nome_arq in [
        "Cópia de clientes com cnpj corretinho novinho.xlsx",
        "Cópia de clientes com cnpj corretinho novinho (1).xlsx",
    ]:
        if os.path.exists(nome_arq):
            try:
                return pd.read_excel(nome_arq)
            except Exception as e:
                st.error(f"Erro ao carregar a planilha de clientes: {e}")
                return pd.DataFrame()
    st.error("A planilha de clientes não foi encontrada.")
    return pd.DataFrame()


df_clientes = load_clients()


# --- PREPARAR FOTO APENAS PARA O PDF (Alta Qualidade) ---
def preparar_foto_pdf(caminho):
    try:
        img = PILImage.open(caminho)
        img = ImageOps.exif_transpose(img)
        img.thumbnail((800, 800))
        caminho_novo = caminho.replace(".jpg", "_pdf.jpg")
        img.save(caminho_novo, "JPEG", quality=85)
        return caminho_novo
    except Exception:
        return caminho


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
                sheet_usr = wb.add_worksheet(
                    title="Usuarios_Senhas", rows="50", cols="3"
                )
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
    destino = "benedito.bandola@minassal.com.br"
    if not senha:
        return False

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destino
    msg["Subject"] = f"💬 Nova Interação da Gestão [{tipo}]: {loja}"

    corpo = f"""
    Olá,
    
    O supervisor {supervisor} registrou uma nova interação na loja {loja} (Auditoria de {data_auditoria}).
    
    Tipo: {tipo}
    Comentário: "{comentario}"
    
    Atenciosamente,
    Sistema de Auditoria Automática.
    """
    msg.attach(MIMEText(corpo, "plain"))
    try:
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(remetente, senha)
        s.sendmail(remetente, destino, msg.as_string())
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


def calcular_frentes_faltantes(frentes_rc, frentes_total, meta_share_pct):
    frentes_concorrentes = frentes_total - frentes_rc
    if frentes_concorrentes <= 0:
        return 0
    meta_dec = meta_share_pct / 100.0
    frentes_necessarias = math.ceil((meta_dec * frentes_concorrentes) / (1.0 - meta_dec))
    faltam = max(0, frentes_necessarias - frentes_rc)
    return faltam


def gerar_pdf_auditoria(
    tipo_auditoria,
    promotora,
    loja,
    cidade,
    endereco,
    dados_completos,
    nota_total,
    frentes_dados,
    caminhos_fotos=None,
):
    loja_limpa = (
        "".join([c for c in loja if c.isalnum() or c in (" ", "_", "-")])
        .strip()
        .replace(" ", "_")
    )
    arq_completo = f"{tipo_auditoria.upper().replace('-', '_')}_{loja_limpa}.pdf"

    estilos = getSampleStyleSheet()
    style_celula = ParagraphStyle(
        "EstiloCelula",
        parent=estilos["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1F2937"),
    )
    style_celula_cab = ParagraphStyle(
        "EstiloCelulaCab",
        parent=estilos["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )

    cor_cabecalho_principal = colors.HexColor("#1E3A8A")
    cor_cabecalho_secundario = colors.HexColor("#059669")

    fuso_sp = pytz.timezone("America/Sao_Paulo")
    agora = datetime.now(fuso_sp).strftime("%d/%m/%Y %H:%M")

    def criar_pagina_1():
        elem = []
        elem.append(
            Paragraph(
                f"<b>RELATÓRIO EXECUTIVO - {tipo_auditoria.upper()} (SHELF SPACE)</b>",
                estilos["Title"],
            )
        )
        elem.append(Spacer(1, 5))
        elem.append(
            Paragraph(
                f"<b>LOJA:</b> {loja} | <b>CIDADE:</b> {cidade}", estilos["Normal"]
            )
        )
        elem.append(Paragraph(f"<b>ENDEREÇO:</b> {endereco}", estilos["Normal"]))
        elem.append(
            Paragraph(
                f"<b>PROMOTORA:</b> {promotora} | <b>DATA/HORA:</b> {agora}",
                estilos["Normal"],
            )
        )
        elem.append(
            Paragraph(
                f"<b>NOTA FINAL DO PDV:</b> <font color='#1E3A8A'><b>{nota_total:.2f} / 10.0 pts</b></font>",
                estilos["Heading2"],
            )
        )
        elem.append(Spacer(1, 10))

        elem.append(
            Paragraph("<b>1. PERFORMANCE DE SHARE POR PILAR</b>", estilos["Heading3"])
        )
        data_share = [[
            Paragraph("<b>Pilar</b>", style_celula_cab),
            Paragraph("<b>Share</b>", style_celula_cab),
            Paragraph("<b>Meta</b>", style_celula_cab),
            Paragraph("<b>Progresso (Visual Base 10)</b>", style_celula_cab),
        ]]

        shares = [
            ("Linha Cão", dados_completos.get("share_cao", 0), 30.0),
            ("Linha Gato", dados_completos.get("share_gato", 0), 35.0),
            ("Linha Veterinária", dados_completos.get("share_vet", 0), 50.0),
        ]

        for nome_pilar, val, meta in shares:
            blocos_cheios = int(round(min(val, 100) / 10))
            blocos_vazios = 10 - blocos_cheios
            barra_visual = "[" + ("█" * blocos_cheios) + ("░" * blocos_vazios) + "]"
            cor_txt = "#059669" if val >= meta else "#DC2626"

            data_share.append([
                Paragraph(nome_pilar, style_celula),
                Paragraph(
                    f"<font color='{cor_txt}'><b>{val:.1f}%</b></font>", style_celula
                ),
                Paragraph(f"{meta:.1f}%", style_celula),
                Paragraph(
                    f"<font name='Courier' size=11 color='{cor_txt}'>{barra_visual}</font>",
                    style_celula,
                ),
            ])

        t_share = Table(data_share, colWidths=[100, 50, 40, 350])
        t_share.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_cabecalho_principal),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elem.append(t_share)
        elem.append(Spacer(1, 10))

        elem.append(Paragraph("<b>2. CHECKLIST DE EXECUÇÃO</b>", estilos["Heading3"]))
        data_exec = [
            [
                Paragraph("<b>Pilar / Categoria</b>", style_celula_cab),
                Paragraph("<b>Planograma?</b>", style_celula_cab),
                Paragraph("<b>Abertura Fluxo?</b>", style_celula_cab),
                Paragraph("<b>Regra Específica</b>", style_celula_cab),
            ],
            [
                Paragraph("Linha Cão", style_celula),
                Paragraph(dados_completos.get("plano_cao", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_cao", ""), style_celula),
                Paragraph("Meta de Frentes >= 30%", style_celula),
            ],
            [
                Paragraph("Linha Gato", style_celula),
                Paragraph(dados_completos.get("plano_gato", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_gato", ""), style_celula),
                Paragraph(
                    f"Super Premium Sep: {dados_completos.get('sep_fhn', '')}",
                    style_celula,
                ),
            ],
            [
                Paragraph("Linha Veterinária", style_celula),
                Paragraph(dados_completos.get("plano_vet", ""), style_celula),
                Paragraph(dados_completos.get("fluxo_vet", ""), style_celula),
                Paragraph("Meta de Frentes >= 50%", style_celula),
            ],
        ]
        t_exec = Table(data_exec, colWidths=[110, 80, 95, 255])
        t_exec.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_cabecalho_secundario),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elem.append(t_exec)
        elem.append(Spacer(1, 10))

        elem.append(
            Paragraph("<b>3. MERCHANDISING E PONTOS EXTRAS</b>", estilos["Heading3"])
        )
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
                Paragraph("Materiais Presentes", style_celula),
                Paragraph(materiais_str, style_celula),
            ],
            [
                Paragraph("Conservação Adequada?", style_celula),
                Paragraph(str(dados_completos.get("conservacao", "")), style_celula),
            ],
            [
                Paragraph("Pontos Extras (Qtd)", style_celula),
                Paragraph(str(dados_completos.get("qtd_extras", 0)), style_celula),
            ],
        ]
        t_merch = Table(data_merch, colWidths=[150, 390])
        t_merch.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_cabecalho_principal),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        elem.append(t_merch)
        elem.append(Spacer(1, 10))

        if dados_completos.get("observacoes"):
            elem.append(
                Paragraph("<b>4. OBSERVAÇÕES DA PROMOTORA</b>", estilos["Heading3"])
            )
            t_obs = Table(
                [[Paragraph(dados_completos["observacoes"], style_celula)]],
                colWidths=[540],
            )
            t_obs.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ])
            )
            elem.append(t_obs)
            elem.append(Spacer(1, 10))

        return elem

    def criar_pagina_2():
        elem = []
        elem.append(PageBreak())
        elem.append(
            Paragraph(
                "<b>ANEXO 1: DETALHAMENTO DE FRENTES POR MARCA</b>", estilos["Title"]
            )
        )
        elem.append(Spacer(1, 10))

        marcas = [
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

        data_frentes = [[
            Paragraph("<b>Marca / Concorrente</b>", style_celula_cab),
            Paragraph("<b>Frentes Cão</b>", style_celula_cab),
            Paragraph("<b>Frentes Gato</b>", style_celula_cab),
            Paragraph("<b>Frentes Vet</b>", style_celula_cab),
        ]]

        for m in marcas:
            data_frentes.append([
                Paragraph(m, style_celula),
                Paragraph(str(frentes_dados["cao"].get(m, 0)), style_celula),
                Paragraph(str(frentes_dados["gato"].get(m, 0)), style_celula),
                Paragraph(str(frentes_dados["vet"].get(m, 0)), style_celula),
            ])

        t_frentes = Table(data_frentes, colWidths=[210, 110, 110, 110])
        t_frentes.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cor_cabecalho_principal),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ])
        )
        elem.append(t_frentes)
        elem.append(Spacer(1, 15))

        if caminhos_fotos:
            elem.append(PageBreak())
            elem.append(
                Paragraph(
                    "<b>ANEXO 2: EVIDÊNCIAS FOTOGRÁFICAS (ALTA QUALIDADE)</b>",
                    estilos["Heading3"],
                )
            )
            elem.append(Spacer(1, 10))
            linhas_tabela = []
            par_atual = []
            for caminho in caminhos_fotos:
                caminho_otimizado = preparar_foto_pdf(caminho)
                img_element = RLImage(
                    caminho_otimizado, width=200, height=200, kind="proportional"
                )
                par_atual.append(img_element)
                if len(par_atual) == 2:
                    linhas_tabela.append(par_atual)
                    par_atual = []
            if par_atual:
                par_atual.append("")
                linhas_tabela.append(par_atual)

            if linhas_tabela:
                t_fotos = Table(linhas_tabela, colWidths=[270, 270])
                t_fotos.setStyle(
                    TableStyle([
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ])
                )
                elem.append(t_fotos)

        return elem

    def adicionar_rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawRightString(A4[0] - 25, 15, "Desenvolvido por Benedito Bandola")
        canvas.restoreState()

    doc_completo = SimpleDocTemplate(
        arq_completo,
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25,
    )
    doc_completo.build(
        criar_pagina_1() + criar_pagina_2(),
        onFirstPage=adicionar_rodape,
        onLaterPages=adicionar_rodape,
    )

    return arq_completo


def enviar_email_auditoria(assunto, anexos_paths, destinatarios, corpo_email=""):
    remetente = st.secrets.get("email_remetente", "beneditobandola@gmail.com")
    senha = st.secrets.get("email_senha", os.getenv("EMAIL_SENHA", ""))
    if not senha:
        return False

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(destinatarios)
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
        s.sendmail(remetente, destinatarios, msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False


# --- MENU LATERAL DE NAVEGAÇÃO ---
st.sidebar.title("🐾 Juiz De Fora audit")
st.sidebar.caption(f"💾 JSON: `{ARQUIVO_JSON_HISTORICO}`")
menu = st.sidebar.selectbox(
    "Escolha o Módulo:",
    [
        "📝 Área da Promotora",
        "📋 Histórico & Feedbacks",
        "🔒 Painel Admin (Supervisores)",
    ],
)

# ==============================================================
# FLUXO 1: ÁREA DA PROMOTORA
# ==============================================================
if menu == "📝 Área da Promotora":
    st.title("🐾 Juiz De Fora audit — Shelf Space Royal Canin")
    st.markdown("---")

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

        st.subheader("1. Identificação e Tipo de Registro")

        col_tipo, col_prom = st.columns(2)
        with col_tipo:
            tipo_auditoria = st.radio(
                "Selecione o Tipo de Registro:",
                ["Pré-Auditoria", "Auditoria"],
                horizontal=True,
            )
        with col_prom:
            promotora = st.selectbox(
                "Selecione a Promotora / Supervisor:",
                [
                    "Auditoria Juiz de Fora",
                    "Pamela",
                    "Fernanda",
                    "Madalla",
                    "Sarmento",
                    "Paulo Maia",
                ],
            )

        if promotora == "Auditoria Juiz de Fora":
            df_jf_base = df_clientes[
                df_clientes["COD_NORM"].isin(CODIGOS_JUIZ_DE_FORA_ORDEM)
            ].copy()
            if df_jf_base.empty:
                df_jf_base = df_clientes[
                    df_clientes["CIDADE_NORM"] == "JUIZ DE FORA"
                ].copy()

            # Mantém exatamente a ordem das 10 lojas de Juiz de Fora
            lojas_ordenadas = []
            for idx_ord, cod_alvo in enumerate(CODIGOS_JUIZ_DE_FORA_ORDEM, start=1):
                match = df_jf_base[df_jf_base["COD_NORM"] == cod_alvo]
                if not match.empty:
                    nome_cli = str(match.iloc[0]["NOME"]).strip()
                    apelido = APELIDOS_POR_CODIGO.get(cod_alvo, nome_cli)
                    lojas_ordenadas.append((idx_ord, cod_alvo, apelido, nome_cli))

            hist_json_atual = carregar_historico_json()
            codigos_salvos_json = {
                str(r.get("codigo_loja", "")).strip() for r in hist_json_atual
            }

            st.subheader("2. Seleção da Loja (Ordem Juiz de Fora)")
            if lojas_ordenadas:
                rotulos = []
                mapa_rotulo_nome = {}
                for idx_ord, cod_alvo, apelido, nome_cli in lojas_ordenadas:
                    marca_json = "✅" if cod_alvo in codigos_salvos_json else "⏳"
                    rot = f"{marca_json} #{idx_ord:02d} • [{cod_alvo}] {nome_cli} ({apelido})"
                    rotulos.append(rot)
                    mapa_rotulo_nome[rot] = nome_cli

                rotulo_escolhido = st.selectbox(
                    "Selecione o Cliente / Loja:", rotulos
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

            st.subheader("2. Seleção da Loja")
            loja_selecionada = (
                st.selectbox("Selecione o Cliente / Loja:", lojas_lista)
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
            elif len(nums_doc) > 0 and len(nums_doc) < 14:
                nums_doc = nums_doc.zfill(14)
                cnpj_formatado = f"{nums_doc[:2]}.{nums_doc[2:5]}.{nums_doc[5:8]}/{nums_doc[8:12]}-{nums_doc[12:]}"
            else:
                cnpj_formatado = "Não informado"

            st.markdown(
                f"""
                <div style="background-color: #F8FAFC; border-left: 5px solid #E2001A; padding: 12px; border-radius: 6px; margin-bottom: 10px; color: #0F172A;">
                    <div style="font-size: 15px; margin-bottom: 4px;">
                        🏢 <b>Cód.:</b> {codigo_loja_atual} | <b>CNPJ:</b> <span style="color: #E2001A; font-weight: 900; font-size: 17px; font-family: monospace;">{cnpj_formatado}</span>
                    </div>
                    <div style="font-size: 13.5px; color: #475569;">
                        📍 <b>Cidade:</b> {cidade_loja}/{uf_loja} | <b>Endereço:</b> {endereco_exibicao}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

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

            st.markdown("---")
            st.subheader("3. Contagem de Frentes & Share por Pilar")

            marcas = [
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

            st.markdown("### 🐶 Linha Cão (Meta: 30%)")
            frentes_cao = {
                m: st.number_input(
                    f"[Cão] Frentes - {m}",
                    min_value=0,
                    max_value=100,
                    value=0,
                    key=f"cao_{m}",
                )
                for m in marcas
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
                    value=0,
                    key=f"gato_{m}",
                )
                for m in marcas
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
                    value=0,
                    key=f"vet_{m}",
                )
                for m in marcas
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
            materiais = [
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
            mat_presenca = {
                mat: st.checkbox(mat, key=f"mat_{mat}") for mat in materiais
            }
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
                value=0,
            )

            st.markdown("---")
            st.subheader("6. Registro Fotográfico")
            st.info(
                "💡 As fotos serão anexadas diretamente no Relatório PDF com alta qualidade e não pesarão o aplicativo."
            )
            arquivos_fotos = st.file_uploader(
                "Envie as fotos da auditoria:",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
            )

            caminhos_temporarios = []
            if arquivos_fotos:
                st.write("📷 **Pré-visualização das fotos:**")
                cols = st.columns(3)
                for idx, foto in enumerate(arquivos_fotos):
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".jpg"
                    ) as f:
                        f.write(foto.read())
                        caminho_temp = f.name
                        caminhos_temporarios.append(caminho_temp)

                    caminho_tela = preparar_foto_pdf(caminho_temp)
                    with cols[idx % 3]:
                        st.image(
                            caminho_tela,
                            caption=f"Foto {idx+1}",
                            use_container_width=True,
                        )

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
                            try:
                                with tempfile.NamedTemporaryFile(
                                    delete=False, suffix=".wav"
                                ) as f_audio:
                                    f_audio.write(audio_gravado.read())
                                    caminho_audio_temp = f_audio.name

                                r = sr.Recognizer()
                                with sr.AudioFile(caminho_audio_temp) as source:
                                    audio_data = r.record(source)
                                    texto_falado = r.recognize_google(
                                        audio_data, language="pt-BR"
                                    )
                                    st.session_state[
                                        "texto_transcrito_voz"
                                    ] = texto_falado
                                    st.success("✅ Áudio transcrito com sucesso!")
                            except sr.UnknownValueError:
                                st.warning(
                                    "⚠️ Não foi possível entender o áudio. Tente falar mais perto."
                                )
                            except Exception as e:
                                st.error(f"Erro ao transcrever: {e}")
                with col_apagar:
                    if st.button("🗑️ Apagar Tudo"):
                        st.session_state["texto_transcrito_voz"] = ""
                        st.session_state["audio_key_id"] += 1
                        st.rerun()

            observacoes_promotora = st.text_area(
                "Revise ou complemente o texto transcrito da observação:",
                value=st.session_state["texto_transcrito_voz"],
            )

            st.markdown("---")
            st.subheader("8. Opções de Envio e Diagnóstico")
            opcao_envio = st.radio(
                "Selecione quem deve receber o relatório completo (PDF):",
                [
                    "Somente Benedito",
                    "Toda a Equipe (Benedito, Poli, Caio, Daniel, Rubens)",
                ],
            )

            mostrar_o_que_falta = st.checkbox(
                "🔍 MOSTRAR O QUE FALTA (Incluir no e-mail o diagnóstico detalhado para atingir Nota 10)",
                value=False,
            )

            st.markdown("---")
            if st.button("Finalizar, Salvar e Enviar Auditoria", type="primary"):
                if opcao_envio == "Somente Benedito":
                    destinatarios = ["benedito.bandola@minassal.com.br"]
                else:
                    destinatarios = [
                        "benedito.bandola@minassal.com.br",
                        "poli@minassal.com.br",
                        "caio.poli@minassal.com.br",
                        "daniel.santini@minassal.com.br",
                        "rubens.porfirio@minassal.com.br",
                    ]

                email_pamela = "pamelaalmeida5@icloud.com"
                if email_pamela not in destinatarios:
                    destinatarios.append(email_pamela)

                nota_total = 0.0

                p_cao = 0.0
                if plano_cao == "Sim":
                    p_cao += 1.0
                if fluxo_cao == "Sim":
                    p_cao += 1.0
                if share_cao >= 30.0:
                    p_cao += 0.5
                nota_total += p_cao

                p_gato = 0.0
                if plano_gato == "Sim":
                    p_gato += 1.0
                if fluxo_gato == "Sim":
                    p_gato += 1.0
                if share_gato >= 35.0:
                    p_gato += 0.5
                if sep_fhn == "Sim":
                    p_gato += 0.5
                nota_total += p_gato

                p_vet = 0.0
                if plano_vet == "Sim":
                    p_vet += 1.0
                if fluxo_vet == "Sim":
                    p_vet += 1.0
                if share_vet >= 50.0:
                    p_vet += 0.5
                nota_total += p_vet

                materiais_ativos_lista = [m for m in materiais if mat_presenca[m]]
                total_materiais = len(materiais_ativos_lista)
                p_merch = 0.0
                if total_materiais >= 3:
                    p_merch = 0.75
                elif total_materiais == 2:
                    p_merch = 0.50
                elif total_materiais == 1:
                    p_merch = 0.25
                nota_total += p_merch

                p_cons = 0.25 if conservacao == "Sim" else 0.0
                nota_total += p_cons

                p_extras = 0.0
                if qtd_pontos_extras >= 3:
                    p_extras = 1.0
                elif qtd_pontos_extras == 2:
                    p_extras = 0.5
                elif qtd_pontos_extras == 1:
                    p_extras = 0.25
                nota_total += p_extras

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
                    f"Olá,\n\nSegue o relatório executivo e as comprovações da auditoria referente a {tipo_auditoria.upper()} da loja {loja_selecionada} ({cidade_loja}).\n\n"
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

                    faltas = []
                    if plano_cao != "Sim":
                        faltas.append("• [Cão] Aplicar planograma (+1.0 pt)")
                    if fluxo_cao != "Sim":
                        faltas.append("• [Cão] Ajustar abertura de fluxo (+1.0 pt)")
                    if share_cao < 30.0:
                        f_faltantes = calcular_frentes_faltantes(
                            frentes_cao["Royal Canin"], total_cao, 30.0
                        )
                        faltas.append(
                            f"• [Cão] Aumentar share para 30% (Faltam {f_faltantes} frentes) (+0.5 pt)"
                        )

                    if plano_gato != "Sim":
                        faltas.append("• [Gato] Aplicar planograma (+1.0 pt)")
                    if fluxo_gato != "Sim":
                        faltas.append("• [Gato] Ajustar abertura de fluxo (+1.0 pt)")
                    if share_gato < 35.0:
                        f_faltantes = calcular_frentes_faltantes(
                            frentes_gato["Royal Canin"], total_gato, 35.0
                        )
                        faltas.append(
                            f"• [Gato] Aumentar share para 35% (Faltam {f_faltantes} frentes) (+0.5 pt)"
                        )
                    if sep_fhn != "Sim":
                        faltas.append(
                            "• [Gato] Separar Super Premium da linha FHN (+0.5 pt)"
                        )

                    if plano_vet != "Sim":
                        faltas.append("• [Vet] Aplicar planograma (+1.0 pt)")
                    if fluxo_vet != "Sim":
                        faltas.append("• [Vet] Ajustar abertura de fluxo (+1.0 pt)")
                    if share_vet < 50.0:
                        f_faltantes = calcular_frentes_faltantes(
                            frentes_vet["Royal Canin"], total_vet, 50.0
                        )
                        faltas.append(
                            f"• [Vet] Aumentar share para 50% (Faltam {f_faltantes} frentes) (+0.5 pt)"
                        )

                    if total_materiais < 3:
                        faltas.append(
                            f"• [Merchandising] Adicionar materiais POP (Atual: {total_materiais}, Meta: 3+) (+{0.75 - p_merch:.2f} pt)"
                        )
                    if conservacao != "Sim":
                        faltas.append(
                            "• [Merchandising] Melhorar estado de conservação (+0.25 pt)"
                        )

                    if qtd_pontos_extras < 3:
                        faltas.append(
                            f"• [Pontos Extras] Conquistar mais pontos extras (Atual: {qtd_pontos_extras}, Meta: 3+) (+{1.0 - p_extras:.2f} pt)"
                        )

                    if faltas:
                        corpo_email += "\n".join(faltas) + "\n\n"
                    else:
                        corpo_email += (
                            "Parabéns! PDV com nota máxima e 100% de conformidade!\n\n"
                        )

                corpo_email += f"Observações: {observacoes_promotora.strip() if observacoes_promotora.strip() else 'Nenhuma.'}\n\n"
                corpo_email += (
                    "Atenciosamente,\nSistema de Auditoria Shelf Space Royal Canin."
                )

                with st.spinner(
                    "Gerando PDF, salvando no JSON e enviando e-mail..."
                ):
                    pdf_path = gerar_pdf_auditoria(
                        tipo_auditoria,
                        promotora,
                        loja_selecionada,
                        cidade_loja,
                        endereco_exibicao,
                        dados_completos,
                        nota_total,
                        frentes_dados,
                        caminhos_temporarios,
                    )

                    lista_anexos = [pdf_path]

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
                        data_hora_arq = datetime.now(fuso_sp).strftime(
                            "%d-%m-%Y_%H-%M"
                        )
                        tipo_arq = tipo_auditoria.upper().replace("-", "_")

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=".wav"
                        ) as f_audio_envio:
                            f_audio_envio.write(audio_gravado.getbuffer())
                            audio_temp_path = f_audio_envio.name

                        audio_novo_path = os.path.join(
                            tempfile.gettempdir(),
                            f"Audio_{tipo_arq}_{loja_limpa}_{data_hora_arq}.wav",
                        )
                        os.rename(audio_temp_path, audio_novo_path)
                        lista_anexos.append(audio_novo_path)

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

                    assunto = f"📋 Relatório {tipo_auditoria}: {loja_selecionada} ({cidade_loja}) - Nota {nota_total:.2f}"
                    enviado = enviar_email_auditoria(
                        assunto, lista_anexos, destinatarios, corpo_email
                    )

                    registro_json = {
                        "id": f"JF_{codigo_loja_atual}_{datetime.now(fuso_sp).strftime('%Y%m%d%H%M%S')}",
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
                        "sincronizado_sheets": salvou_sheets,
                        "email_enviado": enviado,
                    }
                    salvou_json = registrar_no_json(registro_json)

                    if "audio_novo_path" in locals() and os.path.exists(
                        audio_novo_path
                    ):
                        os.remove(audio_novo_path)

                    if salvou_json:
                        st.info(
                            f"💾 Resultado salvo no histórico JSON (`{ARQUIVO_JSON_HISTORICO}`)."
                        )

                    if enviado:
                        st.success(
                            "✅ Auditoria enviada com sucesso! Observações transcritas e e-mail disparado."
                        )
                    else:
                        st.warning(
                            "⚠️ Auditoria salva no histórico JSON, mas houve falha no envio do e-mail."
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
    st.title("📋 Histórico de Auditorias & Feedbacks — Juiz De Fora audit")
    st.markdown("---")

    hist_json = carregar_historico_json()
    st.subheader(f"💾 Histórico JSON ({len(hist_json)} registro(s))")
    if hist_json:
        linhas_json = []
        for r in reversed(hist_json):
            sh = r.get("shares", {})
            linhas_json.append({
                "Data/Hora": r.get("data_hora", ""),
                "Tipo": r.get("tipo_auditoria", ""),
                "Cód.": r.get("codigo_loja", ""),
                "Loja": r.get("loja", ""),
                "Nota": r.get("nota_total", 0),
                "Share Cão": f"{sh.get('cao', 0)}%",
                "Share Gato": f"{sh.get('gato', 0)}%",
                "Share Vet": f"{sh.get('vet', 0)}%",
                "Sheets": "✅" if r.get("sincronizado_sheets") else "⏳",
                "E-mail": "✅" if r.get("email_enviado") else "⚠️",
                "Observações": r.get("observacoes", ""),
            })
        st.dataframe(pd.DataFrame(linhas_json), use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ Baixar JSON Completo (Backup)",
            data=json.dumps(
                {"projeto": "Juiz De Fora audit", "auditorias": hist_json},
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
            file_name="historico_juiz_de_fora_audit.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.info("Nenhum registro salvo no JSON ainda.")

    st.markdown("---")
    st.subheader("☁️ Histórico no Google Sheets")
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
    st.title("🔒 Painel Administrativo de Supervisores")
    st.markdown("---")

    usuarios_disp = listar_usuarios_cadastrados()
    usuario_sel = st.selectbox("Selecione seu Usuário:", ["Selecione..."] + usuarios_disp)

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
                            st.success("Senha cadastrada com sucesso! Recarregue a página.")
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
