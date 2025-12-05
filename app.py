import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador CNPJ - Versão 10", layout="wide")

st.title("🔎 Validador de Aderência (Correção de Leitura)")
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
    # Remove quebras de linha e múltiplos espaços
    return re.sub(r'\s+', ' ', texto).strip()

def validar_regra_sim(valor):
    """Aceita 'Sim', 'S', 'OK', etc."""
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
        "cnae_principal_completo": "Não identificado", # Texto cheio para exibição
        "cnae_principal_cod": "", # Só números para busca
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

    # 4. CNAE Principal (CORREÇÃO DE LEITURA)
    # Procura por "ECONÔMICA" ou "ECONÓMICA" ou "ECONOMICA"
    # Em seguida, procura o primeiro padrão de CNAE (00.00-0-00) que aparecer depois disso.
    match_header_cnae = re.search(r"ATIVIDADE ECON[ÔÓO]MICA PRINCIPAL", texto_completo, re.IGNORECASE)
    
    if match_header_cnae:
        # Pega todo o texto a partir do fim do título "ATIVIDADE...PRINCIPAL"
        inicio_busca = match_header_cnae.end()
        texto_pos_header = texto_completo[inicio_busca:]
        
        # Procura o primeiro padrão de CNAE neste trecho
        # Captura o código + o resto da linha (descrição)
        match_cnae_valor = re.search(r"(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n[A-Z]|$)", texto_pos_header, re.DOTALL)
        
        if match_cnae_valor:
            txt_full = limpar_espacos(match_cnae_valor.group(1))
            dados['cnae_principal_completo'] = txt_full
            
            # Extrai só o código limpo dentro desse texto capturado
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

# --- SIDEBAR (CONFIGURAÇÃO) ---
st.sidebar.header("⚙️ Configuração")

# 1. NJ
st.sidebar.markdown("### 1️⃣ Natureza Jurídica")
f_nj = st.sidebar.file_uploader("Arquivo NJ", type=["csv","xlsx"], key="f_nj")
df_nj, c_nj_cod, c_nj_reg = None, None, None
if f_nj:
    df_nj = carregar_dados(f_nj)
    if df_nj is not None:
        c_nj_cod = st.sidebar.selectbox("Coluna Código", df_nj.columns, key="njc")
        c_nj_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_nj.columns, index=1, key="njr")

# 2. CNAEs
st.sidebar.markdown("---")
st.sidebar.markdown("### 2️⃣ CNAEs")
f_cn = st.sidebar.file_uploader("Arquivo CNAE", type=["csv","xlsx"], key="f_cn")
df_cn, c_cn_cod, c_cn_reg = None, None, None
if f_cn:
    df_cn = carregar_dados(f_cn)
    if df_cn is not None:
        c_cn_cod = st.sidebar.selectbox("Coluna Código", df_cn.columns, key="cnc")
        c_cn_reg = st.sidebar.selectbox("Coluna Regra (Sim/Não)", df_cn.columns, index=1, key="cnr")

# 3. CNPJs
st.sidebar.markdown("---")
st.sidebar.markdown("### 3️⃣ Exceções (CNPJs)")
f_cp = st.sidebar.file_uploader("Arquivo CNPJ", type=["csv","xlsx"], key="f_cp")
df_cp, c_cp_val, c_cp_cnae = None, None, None
if f_cp:
    df_cp = carregar_dados(f_cp)
    if df_cp is not None:
        c_cp_val = st.sidebar.selectbox("Coluna CNPJ", df_cp.columns, key="cpc")
        c_cp_cnae = st.sidebar.selectbox("Coluna CNAE Referência", df_cp.columns, index=min(1, len(df_cp.columns)-1), key="cp_ref")

# --- ÁREA PRINCIPAL ---
if not (df_nj is not None and df_cn is not None and df_cp is not None):
    st.warning("👈 Configure as 3 planilhas no menu lateral.")
else:
    pdf_file = st.file_uploader("Arraste o PDF do Cartão CNPJ aqui", type=["pdf"])

    if pdf_file:
        with st.spinner("Analisando..."):
            dados = extrair_dados_completos(pdf_file)
            
            # --- MOSTRAR DADOS BÁSICOS ---
            st.subheader("🏢 Dados Extraídos")
            c1, c2 = st.columns([2,1])
            with c1:
                st.markdown(f"**Empresa:** {dados['nome_empresarial']}")
                st.markdown(f"**Nat. Jurídica:** {dados['nat_jur_completa']}")
                # DEBUG VISUAL: Mostra o que foi lido como principal para garantir
                if dados['cnae_principal_cod']:
                    st.success(f"**Ativ. Principal:** {dados['cnae_principal_completo']}")
                else:
                    st.error("**Ativ. Principal:** Não identificada (Verifique o PDF)")

            with c2:
                st.markdown(f"**CNPJ:** {dados['cnpj']}")
            st.divider()

            # --- LÓGICA DE VALIDAÇÃO ---
            decisao_final = "REPROVADO"
            motivo_final = ""
            detalhe_final = ""
            fase_aprovacao = 0 # 1=NJ, 2=CNAE, 3=CNPJ

            nj_key = apenas_numeros(dados['nat_jur_cod'])
            cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
            cnpj_key = apenas_numeros(dados['cnpj'])

            # FASE 1: NATUREZA JURÍDICA
            df_nj['TEMP_KEY'] = df_nj[c_nj_cod].apply(apenas_numeros)
            match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

            if not match_nj.empty:
                regra = match_nj.iloc[0][c_nj_reg]
                if validar_regra_sim(regra):
                    decisao_final = "APROVADO"
                    motivo_final = "Natureza Jurídica Aderente"
                    detalhe_final = f"Código {dados['nat_jur_cod']} permitido na planilha 1."
                    fase_aprovacao = 1

            # FASE 2: CNAES (Se FASE 1 falhou)
            relatorio_cnaes = []
            algum_cnae_aprovado = False

            if fase_aprovacao == 0:
                df_cn['TEMP_KEY'] = df_cn[c_cn_cod].apply(apenas_numeros)

                # 2.1 Analisar Principal
                status_p = "❌ Não Aderente"
                match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
                if not match_p.empty:
                    if validar_regra_sim(match_p.iloc[0][c_cn_reg]):
                        status_p = "✅ Aderente"
                        algum_cnae_aprovado = True
                else:
                    # Se não achou na tabela ou não achou no PDF
                    if not cnae_p_key: status_p = "⚠️ Não identificado no PDF"
                    else: status_p = "❌ Não encontrado na tabela"

                relatorio_cnaes.append({
                    "Tipo": "Principal",
                    "Código": dados['cnae_principal_cod'],
                    "Descrição": dados['cnae_principal_completo'],
                    "Status": status_p
                })

                # 2.2 Analisar Secundários
                for cod, desc in dados['cnaes_secundarios']:
                    sec_key = apenas_numeros(cod)
                    status_s = "❌ Não Aderente"
                    match_s = df_cn[df_cn['TEMP_KEY'] == sec_key]
                    
                    if not match_s.empty:
                        if validar_regra_sim(match_s.iloc[0][c_cn_reg]):
                            status_s = "✅ Aderente"
                            algum_cnae_aprovado = True
                    
                    relatorio_cnaes.append({
                        "Tipo": "Secundário",
                        "Código": cod,
                        "Descrição": desc,
                        "Status": status_s
                    })

                if algum_cnae_aprovado:
                    decisao_final = "APROVADO"
                    motivo_final = "Aderência por Atividade Econômica (CNAE)"
                    detalhe_final = "Pelo menos um CNAE (Principal ou Secundário) é permitido."
                    fase_aprovacao = 2

            # FASE 3: CNPJ (Se FASE 1 e 2 falharam)
            cnae_ref = None
            if fase_aprovacao == 0:
                df_cp['TEMP_KEY'] = df_cp[c_cp_val].apply(apenas_numeros)
                match_cp = df_cp[df_cp['TEMP_KEY'] == cnpj_key]

                if not match_cp.empty:
                    decisao_final = "APROVADO"
                    motivo_final = "CNPJ em Lista de Exceção"
                    fase_aprovacao = 3
                    try:
                        cnae_ref = match_cp.iloc[0][c_cp_cnae]
                        detalhe_final = f"CNAE de Referência da Exceção: {cnae_ref}"
                    except:
                        detalhe_final = "CNPJ listado como exceção."

            # --- RESULTADO FINAL ---
            st.subheader("Resultado Final da Análise")

            if decisao_final == "APROVADO":
                st.success(f"✅ APROVADO")
                st.markdown(f"**Critério:** {motivo_final}")
                st.info(detalhe_final)
            else:
                st.error("❌ REPROVADO")
                st.markdown("**Empresa sem aderência nos 3 níveis.**")

            st.markdown("---")

            # --- RELATÓRIO DE CNAES (Sempre mostra se chegou na Fase 2 ou 3) ---
            if fase_aprovacao >= 2 or (fase_aprovacao == 0 and relatorio_cnaes):
                st.subheader("📊 Relatório Detalhado de CNAEs")
                df_rel = pd.DataFrame(relatorio_cnaes)
                st.dataframe(
                    df_rel, 
                    column_config={
                        "Status": st.column_config.TextColumn("Status"),
                        "Descrição": st.column_config.TextColumn("Atividade", width="large")
                    },
                    hide_index=True,
                    use_container_width=True
                )