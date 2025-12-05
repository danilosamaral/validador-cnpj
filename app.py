import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Detalhado", layout="wide")

st.title("🔎 Validador de Aderência (Relatório Detalhado)")
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
        "cnae_principal_completo": "Não identificado",
        "cnae_principal_cod": "",
        "cnaes_secundarios": []
    }

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

# 3. CNPJs (COM CAMPO EXTRA)
st.sidebar.markdown("---")
st.sidebar.markdown("### 3️⃣ Exceções (CNPJs)")
f_cp = st.sidebar.file_uploader("Arquivo CNPJ", type=["csv","xlsx"], key="f_cp")
df_cp, c_cp_val, c_cp_cnae = None, None, None
if f_cp:
    df_cp = carregar_dados(f_cp)
    if df_cp is not None:
        c_cp_val = st.sidebar.selectbox("Coluna CNPJ", df_cp.columns, key="cpc")
        # NOVIDADE: Seleção da coluna que contém o CNAE de referência
        c_cp_cnae = st.sidebar.selectbox("Coluna que indica o CNAE da Exceção", df_cp.columns, index=min(1, len(df_cp.columns)-1), key="cp_ref")

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
            with c2:
                st.markdown(f"**CNPJ:** {dados['cnpj']}")
            st.divider()

            # --- VARIÁVEIS DE CONTROLE ---
            decisao_final = "REPROVADO"
            motivo_final = ""
            detalhe_final = ""
            fase_aprovacao = 0 # 1=NJ, 2=CNAE, 3=CNPJ

            # Preparar chaves limpas
            nj_key = apenas_numeros(dados['nat_jur_cod'])
            cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
            cnpj_key = apenas_numeros(dados['cnpj'])

            # ==========================================================
            # FASE 1: NATUREZA JURÍDICA
            # ==========================================================
            df_nj['TEMP_KEY'] = df_nj[c_nj_cod].apply(apenas_numeros)
            match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

            if not match_nj.empty:
                regra = match_nj.iloc[0][c_nj_reg]
                if validar_regra_sim(regra):
                    decisao_final = "APROVADO"
                    motivo_final = "Natureza Jurídica Aderente"
                    detalhe_final = f"Código {dados['nat_jur_cod']} permitido na planilha 1."
                    fase_aprovacao = 1

            # ==========================================================
            # FASE 2: ANÁLISE COMPLETA DE CNAES (Se FASE 1 falhou)
            # ==========================================================
            relatorio_cnaes = [] # Lista para guardar o status de TODOS
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
                
                relatorio_cnaes.append({
                    "Tipo": "Principal",
                    "Código": dados['cnae_principal_cod'],
                    "Descrição": dados['cnae_principal_completo'],
                    "Status": status_p
                })

                # 2.2 Analisar Secundários (TODOS)
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

                # Verifica se houve aprovação nesta fase
                if algum_cnae_aprovado:
                    decisao_final = "APROVADO"
                    motivo_final = "Aderência por Atividade Econômica (CNAE)"
                    detalhe_final = "Pelo menos um CNAE foi identificado como permitido (veja lista abaixo)."
                    fase_aprovacao = 2

            # ==========================================================
            # FASE 3: LISTA DE CNPJ (Se FASE 1 e 2 falharam)
            # ==========================================================
            cnae_referencia_cnpj = None

            if fase_aprovacao == 0:
                df_cp['TEMP_KEY'] = df_cp[c_cp_val].apply(apenas_numeros)
                match_cnpj = df_cp[df_cp['TEMP_KEY'] == cnpj_key]

                if not match_cnpj.empty:
                    decisao_final = "APROVADO"
                    motivo_final = "CNPJ em Lista de Exceção"
                    fase_aprovacao = 3
                    
                    # Leitura do CNAE de referência na planilha 3
                    try:
                        cnae_referencia_cnpj = match_cnpj.iloc[0][c_cp_cnae]
                        detalhe_final = f"CNPJ encontrado. CNAE de Referência na lista: {cnae_referencia_cnpj}"
                    except:
                        detalhe_final = "CNPJ encontrado na lista de exceções."

            # ==========================================================
            # EXIBIÇÃO DOS RESULTADOS
            # ==========================================================
            st.subheader("Resultado Final da Análise")

            if decisao_final == "APROVADO":
                st.success(f"✅ APROVADO")
                st.markdown(f"**Critério de Aprovação:** {motivo_final}")
                st.info(detalhe_final)
            else:
                st.error("❌ REPROVADO")
                st.markdown("**A empresa não atende aos critérios do Plano de Comércio.**")

            st.markdown("---")

            # --- EXIBIÇÃO CONDICIONAL DE DETALHES ---
            
            # 1. Se foi para a Fase 2 (CNAEs), mostramos o relatório completo de CNAEs
            # (Mostramos isso mesmo se aprovou no CNAE ou se reprovou e foi tentar CNPJ)
            if fase_aprovacao >= 2 or (fase_aprovacao == 0 and relatorio_cnaes):
                st.subheader("📊 Relatório Detalhado de CNAEs")
                st.caption("Abaixo, o resultado da análise individual de cada atividade encontrada:")
                
                # Transforma a lista em DataFrame para mostrar bonito
                df_relatorio = pd.DataFrame(relatorio_cnaes)
                st.dataframe(
                    df_relatorio, 
                    column_config={
                        "Status": st.column_config.TextColumn("Aderência"),
                        "Descrição": st.column_config.TextColumn("Atividade", width="large")
                    },
                    hide_index=True,
                    use_container_width=True
                )

            # 2. Se foi para a Fase 3 (CNPJ) e APROVOU
            if fase_aprovacao == 3 and cnae_referencia_cnpj:
                st.markdown("#### 📋 Dados da Lista de Exceção")
                col_ex1, col_ex2 = st.columns(2)
                col_ex1.metric("CNPJ Validado", dados['cnpj'])
                col_ex2.metric("CNAE de Referência (Planilha)", str(cnae_referencia_cnpj))