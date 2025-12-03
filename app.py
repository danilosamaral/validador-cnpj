import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de CNPJ", layout="wide")

st.title("🇧🇷 Validador de Aderência ao Plano")
st.markdown("---")

# --- FUNÇÕES DE APOIO (O "MOTOR" DO SISTEMA) ---

@st.cache_data
def carregar_dados(arquivo):
    """Lê Excel ou CSV tentando preservar o formato de texto (zeros à esquerda)."""
    try:
        nome = arquivo.name.lower()
        if nome.endswith('.xlsx') or nome.endswith('.xls'):
            return pd.read_excel(arquivo, dtype=str)
        else:
            try:
                return pd.read_csv(arquivo, sep=';', encoding='latin1', dtype=str)
            except:
                return pd.read_csv(arquivo, sep=';', encoding='utf-8', dtype=str)
    except Exception as e:
        st.error(f"Opa, deu erro ao ler o arquivo: {e}")
        return None

def apenas_numeros(texto):
    """Limpa tudo que não é número (tira pontos, traços, barras)."""
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    """Arruma textos que ficaram com quebras de linha estranhas."""
    if not texto: return ""
    return texto.replace('\n', ' ').strip()

def extrair_dados_completos(pdf_file):
    """Lê o PDF e caça as informações necessárias."""
    texto_completo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
    
    dados = {
        "nome_empresarial": "Não identificado",
        "cnpj": "Não identificado",
        "nat_jur_completa": "Não identificada",
        "nat_jur_cod": "",
        "cnae_principal_completo": "Não identificado",
        "cnae_principal_cod": "",
        "cnaes_secundarios": []
    }

    # 1. Nome Empresarial
    match_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto_completo, re.DOTALL)
    if match_nome:
        dados['nome_empresarial'] = match_nome.group(1).strip()

    # 2. CNPJ
    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj:
        dados['cnpj'] = match_cnpj.group(0)

    # 3. Natureza Jurídica
    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_nj:
        texto_capturado = limpar_espacos(match_nj.group(1))
        dados['nat_jur_completa'] = texto_capturado
        match_cod = re.search(r'\d{3}-\d', texto_capturado)
        if match_cod:
            dados['nat_jur_cod'] = match_cod.group(0)

    # 4. CNAE Principal
    match_cnae_p = re.search(r"CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÓMICA PRINCIPAL.*?\n(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_cnae_p:
        texto_capturado = limpar_espacos(match_cnae_p.group(1))
        dados['cnae_principal_completo'] = texto_capturado
        match_cod = re.search(r'\d{2}\.\d{2}-\d-\d{2}', texto_capturado)
        if match_cod:
            dados['cnae_principal_cod'] = match_cod.group(0)

    # 5. CNAEs Secundários
    padrao_bloco_sec = r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA"
    match_bloco = re.search(padrao_bloco_sec, texto_completo, re.DOTALL)
    
    if match_bloco:
        bloco_texto = match_bloco.group(1)
        linhas_cnae = re.findall(r'(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)', bloco_texto)
        for linha in linhas_cnae:
            linha_limpa = limpar_espacos(linha)
            cod_match = re.search(r'\d{2}\.\d{2}-\d-\d{2}', linha_limpa)
            if cod_match:
                cod_limpo = cod_match.group(0)
                dados['cnaes_secundarios'].append((cod_limpo, linha_limpa))

    return dados

# --- MENU LATERAL (CONFIGURAÇÃO PASSO A PASSO) ---
st.sidebar.header("⚙️ Configuração das Regras")
st.sidebar.info("Carregue as planilhas abaixo para configurar o sistema.")

# --- BLOCO 1: NATUREZA JURÍDICA ---
st.sidebar.markdown("### 1️⃣ Natureza Jurídica")
file_nj = st.sidebar.file_uploader("Selecione a planilha (.csv ou .xlsx)", type=["csv", "xlsx"], key="u_nj")

df_nj = None
col_nj_cod = col_nj_regra = None

if file_nj:
    df_nj = carregar_dados(file_nj)
    if df_nj is not None:
        st.sidebar.success("Planilha carregada! Configure as colunas:")
        col_nj_cod = st.sidebar.selectbox("Coluna com o CÓDIGO", df_nj.columns, key="s_nj1")
        col_nj_regra = st.sidebar.selectbox("Coluna da REGRA (Sim/Não)", df_nj.columns, index=1, key="s_nj2")
    st.sidebar.markdown("---")
else:
    st.sidebar.markdown("---")

# --- BLOCO 2: CNAES ---
st.sidebar.markdown("### 2️⃣ CNAEs (Comércio)")
file_cnae = st.sidebar.file_uploader("Selecione a planilha (.csv ou .xlsx)", type=["csv", "xlsx"], key="u_cnae")

df_cnae = None
col_cnae_cod = col_cnae_regra = None

if file_cnae:
    df_cnae = carregar_dados(file_cnae)
    if df_cnae is not None:
        st.sidebar.success("Planilha carregada! Configure as colunas:")
        col_cnae_cod = st.sidebar.selectbox("Coluna com o CÓDIGO", df_cnae.columns, key="s_cn1")
        col_cnae_regra = st.sidebar.selectbox("Coluna da REGRA (Sim/Não)", df_cnae.columns, index=1, key="s_cn2")
    st.sidebar.markdown("---")
else:
    st.sidebar.markdown("---")

# --- BLOCO 3: LISTA DE CNPJs ---
st.sidebar.markdown("### 3️⃣ Exceções (CNPJs)")
file_cnpj = st.sidebar.file_uploader("Selecione a planilha (.csv ou .xlsx)", type=["csv", "xlsx"], key="u_cnpj")

df_cnpj = None
col_cnpj_val = None

if file_cnpj:
    df_cnpj = carregar_dados(file_cnpj)
    if df_cnpj is not None:
        st.sidebar.success("Planilha carregada! Configure a coluna:")
        col_cnpj_val = st.sidebar.selectbox("Coluna com o CNPJ", df_cnpj.columns, key="s_cp1")

# --- ÁREA PRINCIPAL (ANÁLISE) ---

# Verifica se tudo foi carregado antes de liberar a área de drop
if not (df_nj is not None and df_cnae is not None and df_cnpj is not None):
    st.warning("👈 Para começar, carregue e configure as 3 planilhas no menu à esquerda.")
else:
    st.markdown("### 📄 Análise do Documento")
    # Texto abrasileirado no label
    pdf_file = st.file_uploader("Solte o PDF do Cartão CNPJ aqui (ou clique para buscar)", type=["pdf"])

    if pdf_file:
        with st.spinner("Lendo o PDF e cruzando as informações..."):
            dados = extrair_dados_completos(pdf_file)
            
            # --- PAINEL VISUAL DE DADOS ---
            st.subheader("🏢 Dados da Empresa")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("**Nome Empresarial:**")
                st.info(f"{dados['nome_empresarial']}")
                
                st.markdown("**Natureza Jurídica:**")
                st.text(f"{dados['nat_jur_completa']}")

            with col2:
                st.markdown("**CNPJ:**")
                st.warning(f"{dados['cnpj']}")
                st.caption("Documento processado com sucesso")

            st.markdown("---")

            # --- LÓGICA DE VALIDAÇÃO (MOTOR DE REGRAS) ---
            aprovado = False
            nivel_aprovacao = 0
            texto_destaque = "" 
            motivo_logico = ""

            # Preparação (Limpeza)
            nj_limpo = apenas_numeros(dados['nat_jur_cod'])
            cnae_p_limpo = apenas_numeros(dados['cnae_principal_cod'])
            cnpj_limpo = apenas_numeros(dados['cnpj'])

            # 1. Teste Natureza Jurídica
            df_nj['CHAVE'] = df_nj[col_nj_cod].apply(apenas_numeros)
            resultado_nj = df_nj[df_nj['CHAVE'] == nj_limpo]
            
            if not resultado_nj.empty:
                regra = resultado_nj.iloc[0][col_nj_regra]
                if str(regra).upper() in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO']:
                    aprovado = True
                    nivel_aprovacao = 1
                    motivo_logico = "Natureza Jurídica Aderente"

            # 2. Teste CNAEs (Se falhou na NJ)
            if not aprovado:
                df_cnae['CHAVE'] = df_cnae[col_cnae_cod].apply(apenas_numeros)
                
                # A) Principal
                resultado_p = df_cnae[df_cnae['CHAVE'] == cnae_p_limpo]
                if not resultado_p.empty:
                    regra_p = resultado_p.iloc[0][col_cnae_regra]
                    if str(regra_p).upper() in ['SIM', 'S', 'OK']:
                        aprovado = True
                        nivel_aprovacao = 2
                        motivo_logico = "CNAE Principal Aderente"
                        texto_destaque = dados['cnae_principal_completo']

                # B) Secundários (Se falhou no Principal)
                if not aprovado:
                    for cod_sec, texto_sec in dados['cnaes_secundarios']:
                        sec_limpo = apenas_numeros(cod_sec)
                        resultado_s = df_cnae[df_cnae['CHAVE'] == sec_limpo]
                        if not resultado_s.empty:
                            regra_s = resultado_s.iloc[0][col_cnae_regra]
                            if str(regra_s).upper() in ['SIM', 'S', 'OK']:
                                aprovado = True
                                nivel_aprovacao = 2
                                motivo_logico = "CNAE Secundário Aderente"
                                texto_destaque = texto_sec
                                break

            # 3. Teste CNPJ (Se falhou nos CNAEs)
            if not aprovado:
                df_cnpj['CHAVE'] = df_cnpj[col_cnpj_val].apply(apenas_numeros)
                if cnpj_limpo in df_cnpj['CHAVE'].values:
                    aprovado = True
                    nivel_aprovacao = 3
                    motivo_logico = "CNPJ em Lista de Exceção"

            # --- EXIBIÇÃO DO VEREDITO ---
            st.subheader("Resultado da Análise")
            
            if aprovado:
                st.success(f"✅ APROVADO: {motivo_logico}")
                
                # Se foi aprovado por CNAE, mostra qual foi a atividade "salvadora"
                if nivel_aprovacao == 2 and texto_destaque:
                    st.markdown("##### ⭐ Atividade Compatível Encontrada:")
                    st.warning(texto_destaque)
                    
            else:
                st.error("❌ REPROVADO")
                st.markdown("""
                **A empresa não atende aos critérios do Plano de Comércio:**
                1. A Natureza Jurídica não consta como permitida.
                2. Nenhuma atividade econômica (CNAE) é compatível.
                3. O CNPJ não está na lista de exceções.
                """)
            
            # Área "Debug" para conferência (expansível)
            with st.expander("Ver detalhes técnicos dos CNAEs extraídos"):
                st.write(f"**Principal:** {dados['cnae_principal_completo']}")
                if dados['cnaes_secundarios']:
                    st.write("**Secundários encontrados:**")
                    for item in dados['cnaes_secundarios']:
                        st.text(f"- {item[1]}")
                else:
                    st.write("Nenhum secundário encontrado.")