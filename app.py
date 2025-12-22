import streamlit as st
import pdfplumber
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Corporativo (Estável)", layout="wide")

# ==============================================================================
# 🔧 ÁREA DE CONFIGURAÇÃO SIMPLIFICADA
# ==============================================================================

# Nomes dos arquivos (Devem estar na mesma pasta)
ARQ_NJ = "regras_nj.csv"
ARQ_CNAE = "regras_cnae.xlsx"
ARQ_CNPJ = "regras_cnpj.parquet"

# Nomes EXATOS das colunas (Verifique seus arquivos!)
# Apenas 2 colunas por arquivo: Identificador e Regra

# 1. Natureza Jurídica
COL_NJ_CODIGO = "CODIGO"       # Ex: 213-5
COL_NJ_REGRA = "ADERENCIA"     # Ex: Sim

# 2. CNAEs
COL_CNAE_CODIGO = "CNAE"       # Ex: 47.11-3-02
COL_CNAE_REGRA = "PERMITIDO"   # Ex: Sim

# 3. CNPJ (Exceções)
COL_CNPJ_NUM = "CNPJ"          # O número do CNPJ
COL_CNPJ_RES = "RESULTADO"     # O texto do resultado (ex: Aderente)

# ==============================================================================

st.title("⚖️ Validador de Aderência (Versão Estável)")
st.markdown("---")

# --- FUNÇÕES ---

@st.cache_data
def carregar_base(caminho):
    """Lê o arquivo e limpa espaços nos nomes das colunas."""
    if not os.path.exists(caminho):
        return None, f"Arquivo não encontrado: {caminho}"
    
    try:
        df = None
        # Seleciona o leitor correto
        if caminho.endswith('.parquet'):
            df = pd.read_parquet(caminho)
        elif caminho.endswith('.xlsx') or caminho.endswith('.xls'):
            df = pd.read_excel(caminho, dtype=str)
        else:
            # Tenta ler CSV (ponto e vírgula ou vírgula)
            try:
                df = pd.read_csv(caminho, sep=';', encoding='latin1', dtype=str)
            except:
                df = pd.read_csv(caminho, sep=',', encoding='utf-8', dtype=str)
        
        # Limpeza básica nos cabeçalhos (remove espaços invisíveis)
        if df is not None:
            df.columns = [str(c).strip().upper() for c in df.columns]
            return df, None
            
    except Exception as e:
        return None, str(e)

def apenas_numeros(texto):
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    if not texto: return ""
    return re.sub(r'\s+', ' ', texto).strip()

def validar_sim(valor):
    """Verifica se é Sim/S/Permitido."""
    if pd.isna(valor): return False
    v = str(valor).strip().upper()
    return v in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO', 'YES', 'ADERENTE']

def extrair_pdf(pdf_file):
    """Extrai dados do PDF."""
    texto = ""
    with pdfplumber.open(pdf_file) as pdf:
        for p in pdf.pages: texto += p.extract_text() or ""
    
    dados = {
        "nome": "Não identificado",
        "cnpj": "Não identificado",
        "nj_cod": "", "nj_texto": "",
        "cnae_p_cod": "", "cnae_p_texto": "",
        "cnae_s_lista": []
    }

    # Regex padrão Receita Federal
    m_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto, re.DOTALL)
    if m_nome: dados['nome'] = limpar_espacos(m_nome.group(1))

    m_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    if m_cnpj: dados['cnpj'] = m_cnpj.group(0)

    m_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto, re.DOTALL)
    if m_nj:
        t = limpar_espacos(m_nj.group(1))
        dados['nj_texto'] = t
        if m := re.search(r'\d{3}-\d', t): dados['nj_cod'] = m.group(0)

    m_cp = re.search(r"ATIVIDADE ECON[ÔÓO]MICA PRINCIPAL", texto, re.IGNORECASE)
    if m_cp:
        pos = texto[m_cp.end():]
        m_val = re.search(r"(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n[A-Z]|$)", pos, re.DOTALL)
        if m_val:
            t = limpar_espacos(m_val.group(1))
            dados['cnae_p_texto'] = t
            if m := re.search(r'\d{2}\.\d{2}-\d-\d{2}', t): dados['cnae_p_cod'] = m.group(0)

    m_cs = re.search(r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA", texto, re.DOTALL)
    if m_cs:
        bloc = m_cs.group(1)
        lins = re.findall(r'(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)', bloc)
        for l in lins:
            t = limpar_espacos(l)
            if m := re.search(r'\d{2}\.\d{2}-\d-\d{2}', t):
                dados['cnae_s_lista'].append((m.group(0), t))

    return dados

# --- CARREGAMENTO INICIAL ---
with st.spinner("Carregando bases..."):
    df_nj, err_nj = carregar_base(ARQ_NJ)
    df_cn, err_cn = carregar_base(ARQ_CNAE)
    df_cp, err_cp = carregar_base(ARQ_CNPJ)

erros = []
if err_nj: erros.append(f"Erro NJ: {err_nj}")
if err_cn: erros.append(f"Erro CNAE: {err_cn}")
if err_cp: erros.append(f"Erro CNPJ: {err_cp}")

# Verifica se colunas existem (Maiúsculas)
if not erros:
    if COL_NJ_CODIGO not in df_nj.columns: erros.append(f"Coluna '{COL_NJ_CODIGO}' não existe no arquivo NJ.")
    if COL_CNAE_CODIGO not in df_cn.columns: erros.append(f"Coluna '{COL_CNAE_CODIGO}' não existe no arquivo CNAE.")
    if COL_CNPJ_NUM not in df_cp.columns: erros.append(f"Coluna '{COL_CNPJ_NUM}' não existe no arquivo CNPJ.")

if erros:
    st.error("🚨 ERRO DE LEITURA")
    for e in erros: st.text(e)
    st.stop()
else:
    with st.expander("✅ Status do Sistema", expanded=False):
        st.write("Sistema pronto.")

# --- EXECUÇÃO ---
arquivo = st.file_uploader("Upload do PDF", type=["pdf"])

if arquivo:
    with st.spinner("Analisando..."):
        d = extrair_pdf(arquivo)
        
        # Exibe dados
        st.subheader("Dados Extraídos")
        c1, c2 = st.columns([2,1])
        c1.markdown(f"**Empresa:** {d['nome']}")
        c1.markdown(f"**Nat. Jurídica:** {d['nj_texto']}")
        c2.markdown(f"**CNPJ:** {d['cnpj']}")
        st.divider()

        # --- FASE 1: NATUREZA JURÍDICA ---
        aprovado_nj = False
        msg_nj = ""
        
        key_nj = apenas_numeros(d['nj_cod'])
        df_nj['KEY'] = df_nj[COL_NJ_CODIGO].apply(apenas_numeros)
        
        match = df_nj[df_nj['KEY'] == key_nj]
        if not match.empty:
            regra = match.iloc[0][COL_NJ_REGRA]
            if validar_sim(regra):
                aprovado_nj = True
                msg_nj = "Natureza Jurídica Aderente."
            else:
                msg_nj = "Natureza Jurídica não permitida."
        else:
            msg_nj = f"Código {d['nj_cod']} não encontrado."

        if not aprovado_nj:
            st.error("❌ REPROVADO (Fase 1)")
            st.markdown(f"**Motivo:** {msg_nj}")
            st.stop()
        
        st.success(f"✅ FASE 1 OK: {msg_nj}")

        # --- FASE 2: CNAES ---
        aprovado_cnae = False
        
        # Prepara tabela CNAE
        df_cn['KEY'] = df_cn[COL_CNAE_CODIGO].apply(apenas_numeros)
        
        relatorio = []
        
        # 1. Principal
        k_p = apenas_numeros(d['cnae_p_cod'])
        sts_p = "❌ Não"
        m_p = df_cn[df_cn['KEY'] == k_p]
        if not m_p.empty:
            if validar_sim(m_p.iloc[0][COL_CNAE_REGRA]):
                sts_p = "✅ Aderente"
                aprovado_cnae = True
        
        relatorio.append({"Tipo": "Principal", "Código": d['cnae_p_cod'], "Descrição": d['cnae_p_texto'], "Status": sts_p})

        # 2. Secundários
        for cod, txt in d['cnae_s_lista']:
            k_s = apenas_numeros(cod)
            sts_s = "❌ Não"
            m_s = df_cn[df_cn['KEY'] == k_s]
            if not m_s.empty:
                if validar_sim(m_s.iloc[0][COL_CNAE_REGRA]):
                    sts_s = "✅ Aderente"
                    aprovado_cnae = True
            
            relatorio.append({"Tipo": "Secundário", "Código": cod, "Descrição": txt, "Status": sts_s})

        st.dataframe(pd.DataFrame(relatorio), use_container_width=True, hide_index=True)

        if aprovado_cnae:
            st.success("✅ APROVADO (Fase 2)")
            st.markdown("**Motivo:** Possui CNAE aderente.")
            st.stop()

        # --- FASE 3: CNPJ ---
        st.info("⚠️ CNAEs não aderentes. Buscando Exceções...")
        
        k_cnpj = apenas_numeros(d['cnpj'])
        df_cp['KEY'] = df_cp[COL_CNPJ_NUM].apply(apenas_numeros)
        
        m_cp = df_cp[df_cp['KEY'] == k_cnpj]
        
        if not m_cp.empty:
            res = m_cp.iloc[0][COL_CNPJ_RES]
            st.success("✅ APROVADO (Fase 3)")
            st.markdown(f"**Motivo:** CNPJ na lista de exceções. ({res})")
        else:
            st.error("❌ REPROVADO (Final)")
            st.markdown("Não atende aos requisitos de NJ, CNAE ou Lista de Exceções.")
