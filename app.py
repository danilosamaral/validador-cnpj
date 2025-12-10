import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de Aderência ao Comércio - Lógica Sequencial", layout="wide")

st.title("⚖️ Validador de Aderência (Lógica Sequencial)")
st.markdown("""
**Fluxo de Análise:**
1. **Natureza Jurídica:** Pré-requisito obrigatório. Se falhar, encerra.
2. **CNAEs:** Analisa todos. Se houver algum permitido, aprova.
3. **CNPJ:** Se nenhum CNAE for permitido, verifica se o CNPJ é exceção.
""")
st.markdown("---")

# --- FUNÇÕES (MOTOR) ---

@st.cache_data
def carregar_dados(arquivo):
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
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    if not texto: return ""
    return re.sub(r'\s+', ' ', texto).strip()

def validar_regra_sim(valor):
    if pd.isna(valor): return False
    v = str(valor).strip().upper()
    return v in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO', 'YES', 'ADERENTE']

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

    # 1. Nome Empresarial
    match_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto_completo, re.DOTALL)
    if match_nome: dados['nome_empresarial'] = limpar_espacos(match_nome.group(1))

    # 2. CNPJ
    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj: dados['cnpj'] = match_cnpj.group(0)

    # 3. Natureza Jurídica
    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_nj:
        txt = limpar_espacos(match_nj.group(1))
        dados['nat_jur_completa'] = txt
        if m := re.search(r'\d{3}-\d', txt): dados['nat_jur_cod'] = m.group(0)

    # 4. CNAE Principal
    match_header_cnae = re.search(r"ATIVIDADE ECON[ÔÓO]MICA PRINCIPAL", texto_completo, re.IGNORECASE)
    if match_header_cnae:
        inicio_busca = match_header_cnae.end()
        texto_pos_header = texto_completo[inicio_busca:]
        match_cnae_valor = re.search(r"(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n[A-Z]|$)", texto_pos_header, re.DOTALL)
        if match_cnae_valor:
            txt_full = limpar_espacos(match_cnae_valor.group(1))
            dados['cnae_principal_completo'] = txt_full
            match_cod_only = re.search(r'\d{2}\.\d{2}-\d-\d{2}', txt_full)
            if match_cod_only:
                dados['cnae_principal_cod'] = match_cod_only.group(0)

    # 5. CNAEs Secundários
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

# NJ
st.sidebar.markdown("### 1️⃣ Natureza Jurídica")
f_nj = st.sidebar.file_uploader("Arquivo NJ", type=["csv","xlsx"], key="f_nj")
df_nj, c_nj_cod, c_nj_reg = None, None, None
if f_nj:
    df_nj = carregar_dados(f_nj)
    if df_nj is not None:
        c_nj_cod = st.sidebar.selectbox("Coluna Código NJ", df_nj.columns, key="njc")
        c_nj_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_nj.columns, index=1, key="njr")

# CNAEs
st.sidebar.markdown("---")
st.sidebar.markdown("### 2️⃣ CNAEs")
f_cn = st.sidebar.file_uploader("Arquivo CNAE", type=["csv","xlsx"], key="f_cn")
df_cn, c_cn_cod, c_cn_reg = None, None, None
if f_cn:
    df_cn = carregar_dados(f_cn)
    if df_cn is not None:
        c_cn_cod = st.sidebar.selectbox("Coluna Código CNAE", df_cn.columns, key="cnc")
        c_cn_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_cn.columns, index=1, key="cnr")

# CNPJs
st.sidebar.markdown("---")
st.sidebar.markdown("### 3️⃣ Exceções (CNPJs)")
f_cp = st.sidebar.file_uploader("Arquivo CNPJ", type=["csv","xlsx"], key="f_cp")
df_cp, c_cp_val, c_cp_res = None, None, None
if f_cp:
    df_cp = carregar_dados(f_cp)
    if df_cp is not None:
        c_cp_val = st.sidebar.selectbox("Coluna CNPJ", df_cp.columns, key="cpc")
        # Campo novo para ler o resultado esperado na planilha 3
        c_cp_res = st.sidebar.selectbox("Coluna 'Aderência/Resultado'", df_cp.columns, index=min(1, len(df_cp.columns)-1), key="cp_res")

# --- ÁREA PRINCIPAL ---
if not (df_nj is not None and df_cn is not None and df_cp is not None):
    st.warning("👈 Por favor, configure as 3 planilhas no menu lateral.")
else:
    pdf_file = st.file_uploader("Arraste o PDF do Cartão CNPJ aqui", type=["pdf"])

    if pdf_file:
        with st.spinner("Processando..."):
            dados = extrair_dados_completos(pdf_file)
            
            # --- CABEÇALHO ---
            st.subheader("🏢 Dados Extraídos")
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown(f"**Empresa:** {dados['nome_empresarial']}")
                st.markdown(f"**Natureza Jurídica:** {dados['nat_jur_completa']}")
            with c2:
                st.markdown(f"**CNPJ:** {dados['cnpj']}")
            st.divider()

            # Variáveis principais
            nj_key = apenas_numeros(dados['nat_jur_cod'])
            
            # ==========================================================
            # PASSO 1: NATUREZA JURÍDICA (ELIMINATÓRIO)
            # ==========================================================
            nj_aprovada = False
            justificativa_nj = ""
            
            df_nj['TEMP_KEY'] = df_nj[c_nj_cod].apply(apenas_numeros)
            match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

            if not match_nj.empty:
                regra = match_nj.iloc[0][c_nj_reg]
                if validar_regra_sim(regra):
                    nj_aprovada = True
                    justificativa_nj = "Natureza Jurídica Aderente."
                else:
                    justificativa_nj = f"Natureza Jurídica não permitida (Regra='{regra}')."
            else:
                justificativa_nj = f"Código {dados['nat_jur_cod']} não encontrado na planilha de regras."

            # SE FALHOU NA NJ, PARA TUDO.
            if not nj_aprovada:
                st.error("❌ REPROVADO (Fase 1)")
                st.markdown("**Motivo:** A Natureza Jurídica da empresa não é aderente ao Plano.")
                st.warning(f"**Justificativa:** {justificativa_nj}")
                st.markdown(f"**Descrição:** {dados['nat_jur_completa']}")
                st.stop() # Encerra o programa aqui
            
            # SE PASSOU, CONTINUA...
            st.success("✅ FASE 1 OK: Natureza Jurídica Aderente. Analisando CNAEs...")
            
            # ==========================================================
            # PASSO 2: ANÁLISE DE CNAES (CLASSIFICATÓRIO)
            # ==========================================================
            cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
            df_cn['TEMP_KEY'] = df_cn[c_cn_cod].apply(apenas_numeros)
            
            relatorio_cnaes = []
            algum_cnae_ok = False

            # A) Principal
            status_p = "❌ Não Aderente"
            match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
            if not match_p.empty:
                if validar_regra_sim(match_p.iloc[0][c_cn_reg]):
                    status_p = "✅ Aderente"
                    algum_cnae_ok = True
            
            relatorio_cnaes.append({
                "Tipo": "Principal", 
                "Código": dados['cnae_principal_cod'], 
                "Descrição": dados['cnae_principal_completo'], 
                "Status": status_p
            })

            # B) Secundários
            for cod, desc in dados['cnaes_secundarios']:
                s_key = apenas_numeros(cod)
                status_s = "❌ Não Aderente"
                match_s = df_cn[df_cn['TEMP_KEY'] == s_key]
                if not match_s.empty:
                    if validar_regra_sim(match_s.iloc[0][c_cn_reg]):
                        status_s = "✅ Aderente"
                        algum_cnae_ok = True
                
                relatorio_cnaes.append({
                    "Tipo": "Secundário", 
                    "Código": cod, 
                    "Descrição": desc, 
                    "Status": status_s
                })

            # Exibe tabela de CNAEs
            st.markdown("#### Análise Detalhada dos CNAEs Encontrados")
            df_rel = pd.DataFrame(relatorio_cnaes)
            st.dataframe(df_rel, use_container_width=True, hide_index=True)

            if algum_cnae_ok:
                st.success("✅ APROVADO (Fase 2)")
                st.markdown("**Motivo:** Natureza Jurídica OK + Pelo menos um CNAE Aderente.")
                st.stop() # Encerra pois já aprovou

            # ==========================================================
            # PASSO 3: CNPJ (REPESCAGEM)
            # ==========================================================
            st.info("⚠️ Nenhum CNAE aderente encontrado. Buscando CNPJ na Lista de Exceções...")
            
            cnpj_key = apenas_numeros(dados['cnpj'])
            df_cp['TEMP_KEY'] = df_cp[c_cp_val].apply(apenas_numeros)
            match_cp = df_cp[df_cp['TEMP_KEY'] == cnpj_key]

            if not match_cp.empty:
                # Busca o resultado na coluna indicada (Aderência ao Plano)
                resultado_planilha = match_cp.iloc[0][c_cp_res]
                
                st.success("✅ APROVADO (Fase 3 - Exceção)")
                st.markdown("**Motivo:** Natureza Jurídica OK + CNPJ na Lista de Exceções.")
                st.markdown(f"**Resultado Indicado na Planilha:** {resultado_planilha}")
            else:
                st.error("❌ REPROVADO (Final)")
                st.markdown("**Resumo da Análise:**")
                st.markdown("1. ✅ Natureza Jurídica: Aderente.")
                st.markdown("2. ❌ CNAEs: Nenhuma atividade compatível encontrada.")
                st.markdown("3. ❌ CNPJ: Não consta na lista de exceções.")
