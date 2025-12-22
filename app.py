import streamlit as st
import pdfplumber
import pandas as pd
import re
import os

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Validador Corporativo", layout="wide")

# ==============================================================================
# ARQUIVOS E COLUNAS
# ==============================================================================
ARQ_NJ   = "regras_nj.csv"
ARQ_CNAE = "regras_cnae.xlsx"
ARQ_CNPJ = "regras_cnpj.parquet"

COL_NJ_CODIGO = "CODIGO"
COL_NJ_REGRA  = "ADERENCIA"
COL_NJ_OBS    = "OBS"

COL_CNAE_CODIGO = "CNAE"
COL_CNAE_REGRA  = "PERMITIDO"

COL_CNPJ_NUM = "CNPJ"
COL_CNPJ_RES = "RESULTADO"

# ==============================================================================
# CORREÇÃO DE ENCODING
# ==============================================================================
def corrigir_encoding(texto):
    if texto is None or pd.isna(texto):
        return texto
    texto = str(texto)
    try:
        return texto.encode("latin1").decode("utf-8")
    except:
        return texto

# ==============================================================================
# FUNÇÕES AUXILIARES
# ==============================================================================
@st.cache_data
def carregar_base(caminho):
    if not os.path.exists(caminho):
        return None, f"Arquivo não encontrado: {caminho}"

    try:
        if caminho.endswith(".parquet"):
            df = pd.read_parquet(caminho)
        elif caminho.endswith(".xlsx") or caminho.endswith(".xls"):
            df = pd.read_excel(caminho, dtype=str)
        else:
            try:
                df = pd.read_csv(caminho, sep=";", encoding="utf-8", dtype=str)
            except:
                df = pd.read_csv(caminho, sep=";", encoding="latin1", dtype=str)

        df.columns = [str(c).strip().upper() for c in df.columns]

        for c in df.columns:
            df[c] = df[c].apply(corrigir_encoding)

        return df, None
    except Exception as e:
        return None, str(e)

def apenas_numeros(v):
    if not v:
        return ""
    return re.sub(r"\D", "", str(v))

def limpar_espacos(v):
    if not v:
        return ""
    return re.sub(r"\s+", " ", v).strip()

def validar_sim(v):
    if pd.isna(v):
        return False
    return str(v).strip().upper() in {
        "SIM", "S", "PERMITIDO", "OK", "ADERENTE", "YES", "VERDADEIRO"
    }

# ==============================================================================
# EXTRAÇÃO DO PDF
# ==============================================================================
def extrair_pdf(pdf_file):
    texto = ""
    with pdfplumber.open(pdf_file) as pdf:
        for p in pdf.pages:
            texto += p.extract_text() or ""

    dados = {
        "nome": "Não identificado",
        "cnpj": "",
        "nj_cod": "",
        "nj_texto": "",
        "cnae_p_cod": "",
        "cnae_p_texto": "",
        "cnae_s_lista": []
    }

    if m := re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n", texto, re.DOTALL):
        dados["nome"] = limpar_espacos(m.group(1))

    if m := re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto):
        dados["cnpj"] = m.group(0)

    if m := re.search(r"NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)\n", texto, re.DOTALL):
        t = limpar_espacos(m.group(1))
        dados["nj_texto"] = t
        if c := re.search(r"\d{3}-\d", t):
            dados["nj_cod"] = c.group(0)

    if m := re.search(r"ATIVIDADE ECON[ÔÓO]MICA PRINCIPAL", texto, re.IGNORECASE):
        pos = texto[m.end():]
        if v := re.search(r"(\d{2}\.\d{2}-\d-\d{2}.*?)\n", pos):
            t = limpar_espacos(v.group(1))
            dados["cnae_p_texto"] = t
            if c := re.search(r"\d{2}\.\d{2}-\d-\d{2}", t):
                dados["cnae_p_cod"] = c.group(0)

    if m := re.search(r"ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)NATUREZA", texto, re.DOTALL):
        for l in re.findall(r"(\d{2}\.\d{2}-\d-\d{2}.*?)\n", m.group(1)):
            t = limpar_espacos(l)
            if c := re.search(r"\d{2}\.\d{2}-\d-\d{2}", t):
                dados["cnae_s_lista"].append((c.group(0), t))

    return dados

# ==============================================================================
# APP
# ==============================================================================
st.title("⚖️ Validador de Aderência Corporativa")
st.divider()

with st.spinner("Carregando bases..."):
    df_nj, e1 = carregar_base(ARQ_NJ)
    df_cn, e2 = carregar_base(ARQ_CNAE)
    df_cp, e3 = carregar_base(ARQ_CNPJ)

erros = [e for e in (e1, e2, e3) if e]
if erros:
    st.error("Erro ao carregar bases")
    for e in erros:
        st.text(e)
    st.stop()

arquivo = st.file_uploader("Upload do PDF do CNPJ", type=["pdf"])

if arquivo:
    d = extrair_pdf(arquivo)

    st.subheader("Dados Extraídos")
    c1, c2 = st.columns([2, 1])
    c1.markdown(f"**Empresa:** {d['nome']}")
    c1.markdown(f"**Nat. Jurídica:** {d['nj_texto']}")
    c2.markdown(f"**CNPJ:** {d['cnpj']}")
    st.divider()

    # =========================
    # FASE 1 – NATUREZA JURÍDICA
    # =========================
    df_nj["KEY"] = df_nj[COL_NJ_CODIGO].apply(apenas_numeros)
    key_nj = apenas_numeros(d["nj_cod"])
    m_nj = df_nj[df_nj["KEY"] == key_nj]

    obs = ""
    if m_nj.empty or not validar_sim(m_nj.iloc[0][COL_NJ_REGRA]):
        if not m_nj.empty and COL_NJ_OBS in m_nj.columns:
            obs = m_nj.iloc[0][COL_NJ_OBS]
        st.error("❌ REPROVADO (Fase 1)")
        st.markdown("Natureza Jurídica não permitida.")
        if obs:
            st.info(f"📝 **Nota:** {obs}")
        st.stop()

    if COL_NJ_OBS in m_nj.columns:
        obs = m_nj.iloc[0][COL_NJ_OBS]

    st.success("✅ FASE 1 OK: Natureza Jurídica Aderente")
    if obs:
        st.info(f"📝 **Observação:** {obs}")

    # =========================
    # FASE 2 – CNAE
    # =========================
    df_cn["KEY"] = df_cn[COL_CNAE_CODIGO].apply(apenas_numeros)
    aprovado_cnae = False
    relatorio = []

    # Principal
    k = apenas_numeros(d["cnae_p_cod"])
    m = df_cn[df_cn["KEY"] == k]
    status = "❌ Não"
    if not m.empty and validar_sim(m.iloc[0][COL_CNAE_REGRA]):
        status = "✅ Aderente"
        aprovado_cnae = True

    relatorio.append({
        "Tipo": "Principal",
        "Código": d["cnae_p_cod"],
        "Descrição": d["cnae_p_texto"],
        "Status": status
    })

    # Secundários
    for cod, txt in d["cnae_s_lista"]:
        k = apenas_numeros(cod)
        m = df_cn[df_cn["KEY"] == k]
        status = "❌ Não"
        if not m.empty and validar_sim(m.iloc[0][COL_CNAE_REGRA]):
            status = "✅ Aderente"
            aprovado_cnae = True

        relatorio.append({
            "Tipo": "Secundário",
            "Código": cod,
            "Descrição": txt,
            "Status": status
        })

    st.dataframe(pd.DataFrame(relatorio), use_container_width=True, hide_index=True)

    if aprovado_cnae:
        st.success("✅ APROVADO (Fase 2)")
        st.markdown("Possui CNAE aderente.")
        st.stop()

    # =========================
    # FASE 3 – CNPJ (EXCEÇÃO)
    # =========================
    st.warning("⚠️ CNAEs não aderentes. Verificando exceções por CNPJ...")

    df_cp["KEY"] = df_cp[COL_CNPJ_NUM].apply(apenas_numeros)
    k_cnpj = apenas_numeros(d["cnpj"])
    m = df_cp[df_cp["KEY"] == k_cnpj]

    if not m.empty:
        st.success("✅ APROVADO (Fase 3)")
        st.markdown(f"**Motivo:** {m.iloc[0][COL_CNPJ_RES]}")
    else:
        st.error("❌ REPROVADO (Final)")
        st.markdown("Empresa não atende aos critérios.")
