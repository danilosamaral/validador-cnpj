import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de CNPJ", layout="wide")

st.title("🇧🇷 Validador de Aderência (Fluxo Corrigido)")
st.markdown("---")

# --- FUNÇÕES (MOTOR) ---

@st.cache_data
def carregar_dados(arquivo):
    """Lê Excel ou CSV com tratamento de texto."""
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
    """Remove pontuação, espaços e letras."""
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    if not texto: return ""
    return texto.replace('\n', ' ').strip()

def validar_regra_sim(valor):
    """
    Verifica se o valor na planilha é um 'SIM' válido.
    Aceita: 'Sim', 'SIM', 'sim ', 'S', 's', 'OK', 'Permitido'
    """
    if pd.isna(valor): return False
    v = str(valor).strip().upper()
    return v in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO', 'YES']

def extrair_dados_completos(pdf_file):
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

    # Regex refinados
    match_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto_completo, re.DOTALL)
    if match_nome: dados['nome_empresarial'] = match_nome.group(1).strip()

    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj: dados['cnpj'] = match_cnpj.group(0)

    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_nj:
        txt = limpar_espacos(match_nj.group(1))
        dados['nat_jur_completa'] = txt
        if m := re.search(r'\d{3}-\d', txt): dados['nat_jur_cod'] = m.group(0)

    match_cnae_p = re.search(r"CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÓMICA PRINCIPAL.*?\n(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_cnae_p:
        txt = limpar_espacos(match_cnae_p.group(1))
        dados['cnae_principal_completo'] = txt
        if m := re.search(r'\d{2}\.\d{2}-\d-\d{2}', txt): dados['cnae_principal_cod'] = m.group(0)

    match_bloco = re.search(r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA", texto_completo, re.DOTALL)
    if match_bloco:
        bloco = match_bloco.group(1)
        linhas = re.findall(r'(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)', bloco)
        for l in linhas:
            l_limpa = limpar_espacos(l)
            if m := re.search(r'\d{2}\.\d{2}-\d-\d{2}', l_limpa):
                dados['cnaes_secundarios'].append((m.group(0), l_limpa))

    return dados

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuração")

st.sidebar.markdown("### 1️⃣ Natureza Jurídica")
f_nj = st.sidebar.file_uploader("Arquivo CSV/Excel", type=["csv","xlsx"], key="f_nj")
df_nj, c_nj_cod, c_nj_reg = None, None, None
if f_nj:
    df_nj = carregar_dados(f_nj)
    if df_nj is not None:
        c_nj_cod = st.sidebar.selectbox("Coluna Código", df_nj.columns, key="njc")
        c_nj_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_nj.columns, index=1, key="njr")

st.sidebar.markdown("---")
st.sidebar.markdown("### 2️⃣ CNAEs")
f_cn = st.sidebar.file_uploader("Arquivo CSV/Excel", type=["csv","xlsx"], key="f_cn")
df_cn, c_cn_cod, c_cn_reg = None, None, None
if f_cn:
    df_cn = carregar_dados(f_cn)
    if df_cn is not None:
        c_cn_cod = st.sidebar.selectbox("Coluna Código", df_cn.columns, key="cnc")
        c_cn_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_cn.columns, index=1, key="cnr")

st.sidebar.markdown("---")
st.sidebar.markdown("### 3️⃣ Exceções (CNPJs)")
f_cp = st.sidebar.file_uploader("Arquivo CSV/Excel", type=["csv","xlsx"], key="f_cp")
df_cp, c_cp_val = None, None
if f_cp:
    df_cp = carregar_dados(f_cp)
    if df_cp is not None:
        c_cp_val = st.sidebar.selectbox("Coluna CNPJ", df_cp.columns, key="cpc")

# --- ÁREA PRINCIPAL ---
if not (df_nj is not None and df_cn is not None and df_cp is not None):
    st.warning("👈 Configure as 3 planilhas no menu lateral.")
else:
    pdf_file = st.file_uploader("Arraste o PDF aqui", type=["pdf"])

    if pdf_file:
        with st.spinner("Analisando..."):
            dados = extrair_dados_completos(pdf_file)
            
            # --- MOSTRAR DADOS ---
            st.subheader("🏢 Dados Extraídos")
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown(f"**Empresa:** {dados['nome_empresarial']}")
                st.markdown(f"**Nat. Jurídica:** {dados['nat_jur_completa']}")
            with c2:
                st.markdown(f"**CNPJ:** {dados['cnpj']}")
            st.divider()

            # --- MOTOR DE DECISÃO (CASCATA) ---
            
            # Variáveis de Estado
            status = "REPROVADO" # Padrão inicial
            motivo = ""
            detalhe = ""
            cor_msg = "error" # error = vermelho, success = verde

            # Preparar chaves limpas (apenas números)
            nj_key = apenas_numeros(dados['nat_jur_cod'])
            cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
            cnpj_key = apenas_numeros(dados['cnpj'])

            # --- PASSO 1: NATUREZA JURÍDICA ---
            passou_nj = False
            
            # Cria coluna temporária de busca
            df_nj['TEMP_KEY'] = df_nj[c_nj_cod].apply(apenas_numeros)
            match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

            if not match_nj.empty:
                # Verifica se a regra é SIM
                valor_regra = match_nj.iloc[0][c_nj_reg]
                if validar_regra_sim(valor_regra):
                    passou_nj = True
                    status = "APROVADO"
                    motivo = "Natureza Jurídica Permitida"
                    detalhe = f"A empresa foi aprovada exclusivamente pela Natureza Jurídica: {dados['nat_jur_completa']}"
                    cor_msg = "success"

            # --- PASSO 2: CNAES (Somente se NÃO passou no Passo 1) ---
            if not passou_nj:
                df_cn['TEMP_KEY'] = df_cn[c_cn_cod].apply(apenas_numeros)
                passou_cnae = False
                
                # A) Checar Principal
                match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
                if not match_p.empty:
                    if validar_regra_sim(match_p.iloc[0][c_cn_reg]):
                        passou_cnae = True
                        status = "APROVADO"
                        motivo = "CNAE Principal Aderente"
                        detalhe = f"Atividade Principal compatível: {dados['cnae_principal_completo']}"
                        cor_msg = "success"

                # B) Checar Secundários (Se não passou no Principal)
                if not passou_cnae:
                    for cod, texto in dados['cnaes_secundarios']:
                        sec_key = apenas_numeros(cod)
                        match_s = df_cn[df_cn['TEMP_KEY'] == sec_key]
                        if not match_s.empty:
                            if validar_regra_sim(match_s.iloc[0][c_cn_reg]):
                                passou_cnae = True
                                status = "APROVADO"
                                motivo = "CNAE Secundário Aderente"
                                detalhe = f"Atividade Secundária compatível: {texto}"
                                cor_msg = "success"
                                break # Encontrou um, para.

            # --- PASSO 3: CNPJ (Somente se NÃO passou em 1 e 2) ---
            # Verifica se já foi aprovado antes (NJ ou CNAE)
            ja_aprovado = (status == "APROVADO")
            
            if not ja_aprovado:
                df_cp['TEMP_KEY'] = df_cp[c_cp_val].apply(apenas_numeros)
                if cnpj_key in df_cp['TEMP_KEY'].values:
                    status = "APROVADO"
                    motivo = "CNPJ em Lista de Exceção"
                    detalhe = f"O CNPJ {dados['cnpj']} consta na lista de exceções."
                    cor_msg = "success"

            # --- EXIBIÇÃO FINAL ---
            st.subheader("Resultado da Análise")
            
            if status == "APROVADO":
                st.success(f"✅ {status}")
                st.markdown(f"### Critério: {motivo}")
                st.info(detalhe)
            else:
                st.error(f"❌ {status}")
                st.markdown("**Motivo:** Não houve aderência em nenhum critério.")
                st.markdown("""
                1. Natureza Jurídica não é permitida.
                2. Nenhuma atividade (CNAE) é compatível.
                3. CNPJ não está na lista de exceções.
                """)