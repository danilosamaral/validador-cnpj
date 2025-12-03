import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Completo", layout="wide")

st.title("📊 Painel de Análise de Aderência")
st.markdown("---")

# --- FUNÇÕES AUXILIARES ---

@st.cache_data
def carregar_dados(arquivo):
    """Lê Excel ou CSV forçando texto para preservar zeros."""
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
        st.error(f"Erro ao ler arquivo: {e}")
        return None

def apenas_numeros(texto):
    """Remove tudo que não é dígito."""
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    """Remove quebras de linha e espaços extras do texto capturado."""
    if not texto: return ""
    return texto.replace('\n', ' ').strip()

def extrair_dados_completos(pdf_file):
    texto_completo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
    
    dados = {
        "nome_empresarial": "Não identificado",
        "cnpj": "Não identificado",
        "nat_jur_completa": "Não identificada", # Código + Texto
        "nat_jur_cod": "",
        "cnae_principal_completo": "Não identificado",
        "cnae_principal_cod": "",
        "cnaes_secundarios": [] # Lista de tuplas (codigo, texto_completo)
    }

    # 1. Extrair Nome Empresarial
    # Procura entre "NOME EMPRESARIAL" e o próximo campo "TÍTULO DO ESTABELECIMENTO" ou "PORTE"
    match_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto_completo, re.DOTALL)
    if match_nome:
        dados['nome_empresarial'] = match_nome.group(1).strip()

    # 2. Extrair CNPJ
    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj:
        dados['cnpj'] = match_cnpj.group(0)

    # 3. Extrair Natureza Jurídica (Código + Descrição)
    # Captura o padrão NNN-N e o texto que segue até o fim da linha
    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_nj:
        texto_capturado = limpar_espacos(match_nj.group(1))
        dados['nat_jur_completa'] = texto_capturado
        # Separa só o código para validação
        match_cod = re.search(r'\d{3}-\d', texto_capturado)
        if match_cod:
            dados['nat_jur_cod'] = match_cod.group(0)

    # 4. Extrair CNAE Principal (Código + Descrição)
    match_cnae_p = re.search(r"CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÓMICA PRINCIPAL.*?\n(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_cnae_p:
        texto_capturado = limpar_espacos(match_cnae_p.group(1))
        dados['cnae_principal_completo'] = texto_capturado
        # Separa só o código
        match_cod = re.search(r'\d{2}\.\d{2}-\d-\d{2}', texto_capturado)
        if match_cod:
            dados['cnae_principal_cod'] = match_cod.group(0)

    # 5. Extrair CNAEs Secundários
    padrao_bloco_sec = r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA"
    match_bloco = re.search(padrao_bloco_sec, texto_completo, re.DOTALL)
    
    if match_bloco:
        bloco_texto = match_bloco.group(1)
        # Encontra todas as linhas que começam com o padrão de CNAE
        linhas_cnae = re.findall(r'(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)', bloco_texto)
        for linha in linhas_cnae:
            linha_limpa = limpar_espacos(linha)
            # Extrai o código numérico dessa linha para usar na chave
            cod_match = re.search(r'\d{2}\.\d{2}-\d-\d{2}', linha_limpa)
            if cod_match:
                cod_limpo = cod_match.group(0)
                dados['cnaes_secundarios'].append((cod_limpo, linha_limpa))

    return dados

# --- SIDEBAR (Uploads) ---
st.sidebar.header("📂 Configuração")
file_nj = st.sidebar.file_uploader("1. Natureza Jurídica", type=["csv", "xlsx"])
file_cnae = st.sidebar.file_uploader("2. CNAEs", type=["csv", "xlsx"])
file_cnpj = st.sidebar.file_uploader("3. Lista CNPJs", type=["csv", "xlsx"])

# Carregamento dos dataframes
df_nj = carregar_dados(file_nj) if file_nj else None
df_cnae = carregar_dados(file_cnae) if file_cnae else None
df_cnpj = carregar_dados(file_cnpj) if file_cnpj else None

# Seleção de colunas (simplificada para agilidade)
if df_nj is not None:
    st.sidebar.markdown("**Colunas Nat. Jurídica:**")
    col_nj_cod = st.sidebar.selectbox("Cód NJ", df_nj.columns, key="nj1")
    col_nj_regra = st.sidebar.selectbox("Regra NJ", df_nj.columns, index=1, key="nj2")

if df_cnae is not None:
    st.sidebar.markdown("**Colunas CNAE:**")
    col_cnae_cod = st.sidebar.selectbox("Cód CNAE", df_cnae.columns, key="cn1")
    col_cnae_regra = st.sidebar.selectbox("Regra CNAE", df_cnae.columns, index=1, key="cn2")

if df_cnpj is not None:
    st.sidebar.markdown("**Colunas CNPJ:**")
    col_cnpj_val = st.sidebar.selectbox("Cód CNPJ", df_cnpj.columns, key="cp1")

# --- ÁREA PRINCIPAL ---

if not (df_nj is not None and df_cnae is not None and df_cnpj is not None):
    st.warning("⚠️ Aguardando upload das 3 planilhas na barra lateral.")
else:
    pdf_file = st.file_uploader("Arrastar PDF do Cartão CNPJ", type=["pdf"])

    if pdf_file:
        with st.spinner("Analisando PDF..."):
            dados = extrair_dados_completos(pdf_file)
            
            # --- PAINEL DE DADOS EXTRAÍDOS ---
            st.subheader("🏢 Dados da Empresa")
            
            # Layout em colunas para ficar elegante
            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.markdown(f"**Nome Empresarial:** \n### {dados['nome_empresarial']}")
                st.markdown(f"**Natureza Jurídica:** \n{dados['nat_jur_completa']}")
            
            with c2:
                st.markdown(f"**CNPJ:** \n### {dados['cnpj']}")
                st.info("Documento Processado")

            st.markdown("---")

            # --- PROCESSAMENTO LÓGICO ---
            aprovado = False
            nivel = 0
            cnae_aderente_texto = "" # Para guardar o nome do CNAE que salvou a empresa
            motivo_display = ""
            
            # Limpeza para validação
            nj_limpo = apenas_numeros(dados['nat_jur_cod'])
            cnae_p_limpo = apenas_numeros(dados['cnae_principal_cod'])
            cnpj_limpo = apenas_numeros(dados['cnpj'])

            # 1. Validação Natureza Jurídica
            df_nj['KEY'] = df_nj[col_nj_cod].apply(apenas_numeros)
            match_nj = df_nj[df_nj['KEY'] == nj_limpo]
            
            if not match_nj.empty:
                regra = match_nj.iloc[0][col_nj_regra]
                if str(regra).upper() in ['SIM', 'S', 'PERMITIDO', 'OK']:
                    aprovado = True
                    nivel = 1
                    motivo_display = "Natureza Jurídica Aderente"

            # 2. Validação CNAEs (Se não passou na NJ)
            if not aprovado:
                df_cnae['KEY'] = df_cnae[col_cnae_cod].apply(apenas_numeros)
                
                # A) Principal
                match_p = df_cnae[df_cnae['KEY'] == cnae_p_limpo]
                if not match_p.empty:
                    regra_p = match_p.iloc[0][col_cnae_regra]
                    if str(regra_p).upper() in ['SIM', 'S', 'OK']:
                        aprovado = True
                        nivel = 2
                        motivo_display = "CNAE Principal Aderente"
                        cnae_aderente_texto = dados['cnae_principal_completo']

                # B) Secundários
                if not aprovado:
                    # Itera sobre a lista de tuplas (codigo, texto_completo)
                    for cod_sec, texto_sec in dados['cnaes_secundarios']:
                        sec_limpo = apenas_numeros(cod_sec)
                        match_s = df_cnae[df_cnae['KEY'] == sec_limpo]
                        if not match_s.empty:
                            regra_s = match_s.iloc[0][col_cnae_regra]
                            if str(regra_s).upper() in ['SIM', 'S', 'OK']:
                                aprovado = True
                                nivel = 2
                                motivo_display = "CNAE Secundário Aderente"
                                cnae_aderente_texto = texto_sec
                                break

            # 3. Validação CNPJ (Se não passou nos CNAEs)
            if not aprovado:
                df_cnpj['KEY'] = df_cnpj[col_cnpj_val].apply(apenas_numeros)
                if cnpj_limpo in df_cnpj['KEY'].values:
                    aprovado = True
                    nivel = 3
                    motivo_display = "CNPJ em Lista de Exceção"

            # --- EXIBIÇÃO DO VEREDITO ---
            st.subheader("Resultado da Análise")
            
            if aprovado:
                st.success(f"✅ APROVADO - {motivo_display}")
                
                # SE O MOTIVO FOI CNAE, MOSTRAR QUAL FOI
                if nivel == 2 and cnae_aderente_texto:
                    st.markdown("#### ⭐ CNAE Identificado como Aderente:")
                    st.warning(cnae_aderente_texto) # Usa warning (amarelo) ou success (verde) para destacar
                
            else:
                st.error("❌ REPROVADO")
                st.markdown("**Motivos:**")
                st.write(f"1. Natureza Jurídica não aceita ({dados['nat_jur_completa']})")
                st.write(f"2. Nenhum CNAE compatível encontrado.")
                st.write(f"3. CNPJ não está na lista de exceção.")
            
            # Expandir detalhes dos CNAEs lidos para conferência
            with st.expander("Ver lista completa de CNAEs encontrados no PDF"):
                st.write(f"**Principal:** {dados['cnae_principal_completo']}")
                st.write("**Secundários:**")
                for item in dados['cnaes_secundarios']:
                    st.text(item[1]) # Mostra o texto completo