import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de CNPJ - 3 Níveis", layout="wide")

st.title("🕵️ Validador de Aderência - Plano de Comércio (3 Níveis)")
st.markdown("""
A validação segue a ordem:
1. **Natureza Jurídica** ➔ 2. **CNAEs (Principal e Secundários)** ➔ 3. **CNPJ (Lista Branca)**
""")
st.markdown("---")

# --- FUNÇÕES AUXILIARES ---

@st.cache_data
def carregar_csv(arquivo):
    try:
        df = pd.read_csv(arquivo, sep=';', encoding='latin1', dtype=str)
        return df
    except:
        try:
            df = pd.read_csv(arquivo, sep=';', encoding='utf-8', dtype=str)
            return df
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")
            return None

def limpar_texto(texto):
    """Remove pontuação para comparação (pontos, traços, barras)."""
    if not texto: return ""
    return re.sub(r'[./-]', '', str(texto)).strip()

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

    # 1. Extrair CNPJ (XX.XXX.XXX/XXXX-XX)
    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj:
        dados['cnpj'] = match_cnpj.group(0)

    # 2. Extrair Natureza Jurídica (Código)
    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?(\d{3}-\d)", texto_completo, re.DOTALL)
    if match_nj:
        dados['nat_jur'] = match_nj.group(1).strip()

    # 3. Extrair CNAE Principal
    match_cnae_p = re.search(r"CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÓMICA PRINCIPAL.*?(\d{2}\.\d{2}-\d-\d{2})", texto_completo, re.DOTALL)
    if match_cnae_p:
        dados['cnae_principal'] = match_cnae_p.group(1).strip()

    # 4. Extrair CNAEs Secundários
    # Captura o bloco de texto entre o título de secundárias e o próximo título grande (Natureza Jurídica ou Logradouro)
    padrao_bloco_sec = r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA"
    match_bloco = re.search(padrao_bloco_sec, texto_completo, re.DOTALL)
    
    if match_bloco:
        bloco_texto = match_bloco.group(1)
        # Encontra todos os padrões de CNAE dentro desse bloco
        lista_cnaes = re.findall(r'\d{2}\.\d{2}-\d-\d{2}', bloco_texto)
        dados['cnaes_secundarios'] = list(set(lista_cnaes)) # Remove duplicados

    return dados, texto_completo

# --- BARRA LATERAL: CONFIGURAÇÃO DAS REGRAS (3 ARQUIVOS) ---
st.sidebar.header("📂 Configuração das Regras")

# ARQUIVO 1: NATUREZA JURÍDICA
st.sidebar.subheader("1. Tabela Natureza Jurídica")
file_nj = st.sidebar.file_uploader("Upload CSV Natureza Jurídica", type=["csv"], key="nj")
df_nj = None
col_nj_cod = col_nj_regra = None
if file_nj:
    df_nj = carregar_csv(file_nj)
    cols = df_nj.columns.tolist()
    col_nj_cod = st.sidebar.selectbox("Coluna Código NJ", cols, index=0, key="c1")
    col_nj_regra = st.sidebar.selectbox("Coluna Regra (Sim/Não)", cols, index=1, key="c2")

st.sidebar.markdown("---")

# ARQUIVO 2: CNAEs (PLANO COMÉRCIO)
st.sidebar.subheader("2. Tabela CNAEs (Comércio)")
file_cnae = st.sidebar.file_uploader("Upload CSV CNAEs", type=["csv"], key="cnae")
df_cnae = None
col_cnae_cod = col_cnae_regra = None
if file_cnae:
    df_cnae = carregar_csv(file_cnae)
    cols = df_cnae.columns.tolist()
    col_cnae_cod = st.sidebar.selectbox("Coluna Código CNAE", cols, index=0, key="c3")
    col_cnae_regra = st.sidebar.selectbox("Coluna Regra (Sim/Não)", cols, index=1, key="c4")

st.sidebar.markdown("---")

# ARQUIVO 3: LISTA DE CNPJs
st.sidebar.subheader("3. Lista de CNPJs (Exceções)")
file_cnpj = st.sidebar.file_uploader("Upload CSV Lista CNPJs", type=["csv"], key="cnpj_list")
df_cnpj_list = None
col_cnpj_val = None
if file_cnpj:
    df_cnpj_list = carregar_csv(file_cnpj)
    col_cnpj_val = st.sidebar.selectbox("Coluna com CNPJ", df_cnpj_list.columns.tolist(), index=0, key="c5")


# --- ÁREA PRINCIPAL ---
st.header("📄 Análise do Documento")

# Verifica se todas as regras foram carregadas (opcional: pode permitir rodar sem todas, mas ideal é ter todas)
if not (df_nj is not None and df_cnae is not None and df_cnpj_list is not None):
    st.warning("⚠️ Por favor, carregue os 3 arquivos CSV na barra lateral para garantir a análise completa.")
else:
    arquivo_pdf = st.file_uploader("Upload do Cartão CNPJ (PDF)", type=["pdf"])

    if arquivo_pdf:
        with st.spinner("Processando e cruzando dados..."):
            dados, texto_raw = extrair_dados_completos(arquivo_pdf)
            
            # Normalização para comparação (remove pontuação)
            nj_limpo = limpar_texto(dados['nat_jur'])
            cnae_p_limpo = limpar_texto(dados['cnae_principal'])
            cnaes_s_limpos = [limpar_texto(c) for c in dados['cnaes_secundarios']]
            cnpj_limpo = limpar_texto(dados['cnpj'])

            # Coluna de Exibição
            col_res, col_det = st.columns([1, 1])

            with col_det:
                st.subheader("Dados Extraídos")
                st.write(f"**CNPJ:** {dados['cnpj']}")
                st.write(f"**Nat. Jurídica:** {dados['nat_jur']}")
                st.write(f"**CNAE Principal:** {dados['cnae_principal']}")
                st.write(f"**CNAEs Secundários:** {len(dados['cnaes_secundarios'])} encontrados")
                with st.expander("Ver lista de secundários"):
                    st.write(dados['cnaes_secundarios'])

            # --- LÓGICA EM CASCATA ---
            aprovado = False
            motivo = ""
            nivel = 0
            detalhe_aprovacao = ""

            # NÍVEL 1: NATUREZA JURÍDICA
            # Cria coluna temporária limpa no dataframe para comparar
            df_nj['TEMP_COD'] = df_nj[col_nj_cod].apply(limpar_texto)
            linha_nj = df_nj[df_nj['TEMP_COD'] == nj_limpo]

            status_nj = "NÃO"
            if not linha_nj.empty:
                status_nj = linha_nj.iloc[0][col_nj_regra]
            
            if str(status_nj).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                aprovado = True
                nivel = 1
                motivo = "Natureza Jurídica Aderente"
                detalhe_aprovacao = f"Código {dados['nat_jur']} consta como permitido."
            
            # NÍVEL 2: CNAEs (Se não aprovou no 1)
            if not aprovado:
                df_cnae['TEMP_COD'] = df_cnae[col_cnae_cod].apply(limpar_texto)
                
                # Verifica Principal
                linha_cnae_p = df_cnae[df_cnae['TEMP_COD'] == cnae_p_limpo]
                if not linha_cnae_p.empty:
                    status_p = linha_cnae_p.iloc[0][col_cnae_regra]
                    if str(status_p).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                        aprovado = True
                        nivel = 2
                        motivo = "CNAE Principal Aderente"
                        detalhe_aprovacao = f"Atividade Principal {dados['cnae_principal']} é permitida."

                # Verifica Secundários (Se ainda não aprovou pelo principal)
                if not aprovado:
                    for cnae_sec in cnaes_s_limpos:
                        linha_cnae_s = df_cnae[df_cnae['TEMP_COD'] == cnae_sec]
                        if not linha_cnae_s.empty:
                            status_s = linha_cnae_s.iloc[0][col_cnae_regra]
                            if str(status_s).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                                aprovado = True
                                nivel = 2
                                motivo = "CNAE Secundário Aderente"
                                cnae_orig = dados['cnaes_secundarios'][cnaes_s_limpos.index(cnae_sec)]
                                detalhe_aprovacao = f"Atividade Secundária {cnae_orig} é permitida."
                                break # Para de procurar se achou um

            # NÍVEL 3: CNPJ (Se não aprovou no 2)
            if not aprovado:
                df_cnpj_list['TEMP_CNPJ'] = df_cnpj_list[col_cnpj_val].apply(limpar_texto)
                if cnpj_limpo in df_cnpj_list['TEMP_CNPJ'].values:
                    aprovado = True
                    nivel = 3
                    motivo = "CNPJ em Lista de Exceção"
                    detalhe_aprovacao = f"O CNPJ {dados['cnpj']} foi encontrado na base de CNPJs permitidos."

            # --- RESULTADO FINAL ---
            with col_res:
                st.subheader("Veredito")
                if aprovado:
                    st.success(f"✅ APROVADO (Nível {nivel})")
                    st.markdown(f"**Critério:** {motivo}")
                    st.info(detalhe_aprovacao)
                else:
                    st.error("❌ REPROVADO")
                    st.markdown("**Motivo:** Não houve aderência em nenhum dos 3 níveis:")
                    st.markdown("""
                    1. Natureza Jurídica não permitida.
                    2. Nenhum CNAE (Principal ou Secundário) permitido encontrado.
                    3. CNPJ não consta na lista de exceções.
                    """)