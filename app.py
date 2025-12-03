import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de CNPJ - Blindado", layout="wide")

st.title("🛡️ Validador de Aderência (Limpeza Automática)")
st.markdown("""
**Regra de Limpeza:** O sistema agora ignora qualquer pontuação (. - /) e espaços. 
Ele compara apenas os **números** extraídos do PDF com os **números** das planilhas.
""")
st.markdown("---")

# --- FUNÇÕES AUXILIARES ---

@st.cache_data
def carregar_csv(arquivo):
    try:
        # Lê o CSV forçando tudo para texto (dtype=str) para não perder zeros à esquerda
        df = pd.read_csv(arquivo, sep=';', encoding='latin1', dtype=str)
        return df
    except:
        try:
            df = pd.read_csv(arquivo, sep=';', encoding='utf-8', dtype=str)
            return df
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")
            return None

def apenas_numeros(texto):
    """
    Remove TUDO que não for dígito (0-9). 
    Elimina pontos, traços, barras, espaços e letras.
    """
    if not texto: return ""
    # Regex \D significa "Non-Digit" (Não dígito)
    return re.sub(r'\D', '', str(texto))

def extrair_dados_completos(pdf_file):
    texto_completo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
    
    dados = {
        "cnpj": None,
        "nat_jur": None,
        "cnae_principal": None,
        "cnaes_secundarios": []
    }

    # 1. Extrair CNPJ
    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj:
        dados['cnpj'] = match_cnpj.group(0)

    # 2. Extrair Natureza Jurídica
    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?(\d{3}-\d)", texto_completo, re.DOTALL)
    if match_nj:
        dados['nat_jur'] = match_nj.group(1).strip()

    # 3. Extrair CNAE Principal
    match_cnae_p = re.search(r"CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÓMICA PRINCIPAL.*?(\d{2}\.\d{2}-\d-\d{2})", texto_completo, re.DOTALL)
    if match_cnae_p:
        dados['cnae_principal'] = match_cnae_p.group(1).strip()

    # 4. Extrair CNAEs Secundários
    padrao_bloco_sec = r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA"
    match_bloco = re.search(padrao_bloco_sec, texto_completo, re.DOTALL)
    
    if match_bloco:
        bloco_texto = match_bloco.group(1)
        # Busca qualquer padrão que pareça um CNAE (pontuado ou não)
        lista_cnaes = re.findall(r'\d{2}\.\d{2}-\d-\d{2}', bloco_texto)
        dados['cnaes_secundarios'] = list(set(lista_cnaes))

    return dados

# --- BARRA LATERAL: UPLOAD DOS ARQUIVOS ---
st.sidebar.header("📂 Configuração das Regras")

# 1. NATUREZA JURÍDICA
st.sidebar.subheader("1. Natureza Jurídica")
file_nj = st.sidebar.file_uploader("CSV Natureza Jurídica", type=["csv"], key="nj")
df_nj = None
col_nj_cod = col_nj_regra = None

if file_nj:
    df_nj = carregar_csv(file_nj)
    cols = df_nj.columns.tolist()
    col_nj_cod = st.sidebar.selectbox("Coluna Código NJ", cols, index=0, key="c1")
    col_nj_regra = st.sidebar.selectbox("Coluna Regra (Sim/Não)", cols, index=1, key="c2")

st.sidebar.markdown("---")

# 2. CNAES
st.sidebar.subheader("2. CNAEs (Comércio)")
file_cnae = st.sidebar.file_uploader("CSV CNAEs", type=["csv"], key="cnae")
df_cnae = None
col_cnae_cod = col_cnae_regra = None

if file_cnae:
    df_cnae = carregar_csv(file_cnae)
    cols = df_cnae.columns.tolist()
    col_cnae_cod = st.sidebar.selectbox("Coluna Código CNAE", cols, index=0, key="c3")
    col_cnae_regra = st.sidebar.selectbox("Coluna Regra (Sim/Não)", cols, index=1, key="c4")

st.sidebar.markdown("---")

# 3. LISTA CNPJS
st.sidebar.subheader("3. Lista de CNPJs")
file_cnpj = st.sidebar.file_uploader("CSV Lista CNPJs", type=["csv"], key="cnpj_list")
df_cnpj_list = None
col_cnpj_val = None

if file_cnpj:
    df_cnpj_list = carregar_csv(file_cnpj)
    col_cnpj_val = st.sidebar.selectbox("Coluna com CNPJ", df_cnpj_list.columns.tolist(), index=0, key="c5")

# --- ÁREA PRINCIPAL ---
st.header("📄 Análise e Cruzamento")

if not (df_nj is not None and df_cnae is not None and df_cnpj_list is not None):
    st.warning("⚠️ Carregue os 3 arquivos CSV na barra lateral para iniciar.")
else:
    arquivo_pdf = st.file_uploader("Upload do Cartão CNPJ (PDF)", type=["pdf"])

    if arquivo_pdf:
        with st.spinner("Lendo e higienizando dados..."):
            dados = extrair_dados_completos(arquivo_pdf)
            
            # --- HIGIENIZAÇÃO (LIMPEZA TOTAL) ---
            # Aqui transformamos tudo em apenas números para garantir o match
            nj_limpo = apenas_numeros(dados['nat_jur'])
            cnae_p_limpo = apenas_numeros(dados['cnae_principal'])
            # Cria lista de CNAEs secundários limpos, mantendo vínculo com o original
            cnaes_sec_map = {apenas_numeros(c): c for c in dados['cnaes_secundarios']}
            cnpj_limpo = apenas_numeros(dados['cnpj'])

            # MOSTRAR DADOS LIDOS
            col_res, col_det = st.columns([1.5, 1])

            with col_det:
                st.info("🔍 Dados Identificados (Limpos)")
                st.write(f"**Nat. Jurídica:** {dados['nat_jur']} ➡️ `{nj_limpo}`")
                st.write(f"**CNAE Principal:** {dados['cnae_principal']} ➡️ `{cnae_p_limpo}`")
                st.write(f"**Secundários ({len(dados['cnaes_secundarios'])}):**")
                st.text([f"{orig} -> {apenas_numeros(orig)}" for orig in dados['cnaes_secundarios']])

            # --- LÓGICA DE VALIDAÇÃO ---
            aprovado = False
            nivel = 0
            msg_sucesso = ""
            detalhe_tecnico = ""

            # 1. VALIDAR NATUREZA JURÍDICA
            # Cria coluna temporária limpa no DataFrame
            df_nj['TEMP_KEY'] = df_nj[col_nj_cod].apply(apenas_numeros)
            
            match_nj = df_nj[df_nj['TEMP_KEY'] == nj_limpo]
            
            if not match_nj.empty:
                regra = match_nj.iloc[0][col_nj_regra]
                if str(regra).upper() in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO']:
                    aprovado = True
                    nivel = 1
                    msg_sucesso = "Natureza Jurídica Aderente"
                    detalhe_tecnico = f"O código `{nj_limpo}` consta como permitido na tabela 1."

            # 2. VALIDAR CNAES (Se não aprovou no 1)
            if not aprovado:
                df_cnae['TEMP_KEY'] = df_cnae[col_cnae_cod].apply(apenas_numeros)
                
                # A) Checar Principal
                match_p = df_cnae[df_cnae['TEMP_KEY'] == cnae_p_limpo]
                if not match_p.empty:
                    regra_p = match_p.iloc[0][col_cnae_regra]
                    if str(regra_p).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                        aprovado = True
                        nivel = 2
                        msg_sucesso = "CNAE Principal Aderente"
                        detalhe_tecnico = f"Atividade `{cnae_p_limpo}` é permitida na tabela 2."
                
                # B) Checar Secundários
                if not aprovado:
                    for cnae_limpo, cnae_original in cnaes_sec_map.items():
                        match_s = df_cnae[df_cnae['TEMP_KEY'] == cnae_limpo]
                        if not match_s.empty:
                            regra_s = match_s.iloc[0][col_cnae_regra]
                            if str(regra_s).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                                aprovado = True
                                nivel = 2
                                msg_sucesso = "CNAE Secundário Aderente"
                                detalhe_tecnico = f"Atividade Secundária `{cnae_original}` ({cnae_limpo}) é permitida na tabela 2."
                                break

            # 3. VALIDAR CNPJ (Se não aprovou no 2)
            if not aprovado:
                df_cnpj_list['TEMP_KEY'] = df_cnpj_list[col_cnpj_val].apply(apenas_numeros)
                if cnpj_limpo in df_cnpj_list['TEMP_KEY'].values:
                    aprovado = True
                    nivel = 3
                    msg_sucesso = "CNPJ em Lista de Exceção"
                    detalhe_tecnico = f"O CNPJ `{cnpj_limpo}` consta na lista branca (tabela 3)."

            # --- EXIBIÇÃO DO VEREDITO ---
            with col_res:
                st.subheader("Resultado Final")
                if aprovado:
                    st.success(f"✅ APROVADO - Nível {nivel}")
                    st.markdown(f"**Motivo:** {msg_sucesso}")
                    st.caption(f"Detalhe: {detalhe_tecnico}")
                else:
                    st.error("❌ REPROVADO")
                    st.markdown("**Empresa sem aderência ao Plano de Comércio.**")
                    st.markdown("""
                    Foram verificados:
                    1. ❌ Natureza Jurídica
                    2. ❌ CNAE Principal e Secundários
                    3. ❌ Lista de Exceção de CNPJs
                    """)