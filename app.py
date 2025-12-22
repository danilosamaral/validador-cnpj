import streamlit as st
import pdfplumber
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Corporativo", layout="wide")

# ==============================================================================
# 🔧 ÁREA DE CONFIGURAÇÃO
# ==============================================================================
ARQUIVO_NJ = "regras_nj.csv"
ARQUIVO_CNAE = "regras_cnae.xlsx"
ARQUIVO_CNPJ = "regras_cnpj.parquet"

# Natureza Jurídica
CFG_NJ = {
    "col_codigo": "NATJUR",
    "col_regra": "ADERENCIA",
    "col_justificativa": "OBS" 
}

# CNAEs
CFG_CNAE = {
    "col_codigo": "CNAE",
    "col_regra": "PERMITIDO",
    "col_justificativa": "JUST"
}

# CNPJ
CFG_CNPJ = {
    "col_cnpj": "CNPJ",
    "col_resultado": "RESULTADO"
}
# ==============================================================================

st.title("🏢 Validador de Aderência (Versão Diagnóstico)")
st.markdown("---")

# --- FUNÇÕES ---

@st.cache_data
def carregar_regras_nativas(caminho_arquivo):
    """Lê arquivos e LIMPA os nomes das colunas (tira espaços extras)."""
    if not os.path.exists(caminho_arquivo):
        return None, f"Arquivo não encontrado: {caminho_arquivo}"
    
    df = None
    erro = None

    try:
        # Leitura
        if caminho_arquivo.endswith('.parquet'):
            df = pd.read_parquet(caminho_arquivo)
        elif caminho_arquivo.endswith('.xlsx') or caminho_arquivo.endswith('.xls'):
            df = pd.read_excel(caminho_arquivo, dtype=str)
        else:
            try:
                df = pd.read_csv(caminho_arquivo, sep=';', encoding='latin1', dtype=str)
            except:
                df = pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8', dtype=str)
        
        # --- CORREÇÃO AUTOMÁTICA DE CABEÇALHOS ---
        # Remove espaços antes/depois e converte para maiúsculo para facilitar
        if df is not None:
            df.columns = [str(c).strip() for c in df.columns]
            
    except Exception as e:
        erro = str(e)
    
    return df, erro

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

    match_nome = re.search(r"NOME EMPRESARIAL\s*\n(.*?)\n\s*(?:TÍTULO|PORTE)", texto_completo, re.DOTALL)
    if match_nome: dados['nome_empresarial'] = limpar_espacos(match_nome.group(1))

    match_cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto_completo)
    if match_cnpj: dados['cnpj'] = match_cnpj.group(0)

    match_nj = re.search(r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?\n(\d{3}-\d.*?)(?:\n|$)", texto_completo, re.DOTALL)
    if match_nj:
        txt = limpar_espacos(match_nj.group(1))
        dados['nat_jur_completa'] = txt
        if m := re.search(r'\d{3}-\d', txt): dados['nat_jur_cod'] = m.group(0)

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

    match_bloco = re.search(r"CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS(.*?)CÓDIGO E DESCRIÇÃO DA NATUREZA", texto_completo, re.DOTALL)
    if match_bloco:
        bloco = match_bloco.group(1)
        linhas = re.findall(r'(\d{2}\.\d{2}-\d-\d{2}.*?)(?:\n|$)', bloco)
        for l in linhas:
            l_limpa = limpar_espacos(l)
            if m := re.search(r'\d{2}\.\d{2}-\d-\d{2}', l_limpa):
                dados['cnaes_secundarios'].append((m.group(0), l_limpa))

    return dados

# --- CARREGAMENTO ---
status_placeholder = st.empty()

with st.spinner("Carregando e validando regras..."):
    df_nj, erro_nj = carregar_regras_nativas(ARQUIVO_NJ)
    df_cn, erro_cn = carregar_regras_nativas(ARQUIVO_CNAE)
    df_cp, erro_cp = carregar_regras_nativas(ARQUIVO_CNPJ)

erros_fatais = []

# Validação do Arquivo NJ
if erro_nj:
    erros_fatais.append(f"Erro ao abrir {ARQUIVO_NJ}: {erro_nj}")
else:
    # Validação detalhada das colunas
    cols_nj = list(df_nj.columns)
    if CFG_NJ['col_codigo'] not in cols_nj: 
        erros_fatais.append(f"⚠️ {ARQUIVO_NJ}: Coluna '{CFG_NJ['col_codigo']}' não encontrada. Colunas existentes: {cols_nj}")
    if CFG_NJ['col_justificativa'] not in cols_nj: 
        erros_fatais.append(f"⚠️ {ARQUIVO_NJ}: Coluna '{CFG_NJ['col_justificativa']}' não encontrada. Colunas existentes: {cols_nj}")

# Validação do Arquivo CNAE
if erro_cn:
    erros_fatais.append(f"Erro ao abrir {ARQUIVO_CNAE}: {erro_cn}")
else:
    cols_cn = list(df_cn.columns)
    if CFG_CNAE['col_codigo'] not in cols_cn:
        erros_fatais.append(f"⚠️ {ARQUIVO_CNAE}: Coluna '{CFG_CNAE['col_codigo']}' não encontrada. Colunas existentes: {cols_cn}")
    if CFG_CNAE['col_justificativa'] not in cols_cn:
        erros_fatais.append(f"⚠️ {ARQUIVO_CNAE}: Coluna '{CFG_CNAE['col_justificativa']}' não encontrada. Colunas existentes: {cols_cn}")

# Validação do Arquivo CNPJ
if erro_cp:
    erros_fatais.append(f"Erro ao abrir {ARQUIVO_CNPJ}: {erro_cp}")

# EXIBIÇÃO DE ERROS OU SUCESSO
if erros_fatais:
    status_placeholder.error("🛑 OCORREU UM PROBLEMA NA LEITURA DAS COLUNAS")
    for e in erros_fatais:
        st.code(e, language="text") # Mostra o erro em formato de código para facilitar leitura
    st.info("Dica: Verifique se os nomes das colunas no Excel estão idênticos aos listados acima (sem espaços extras).")
    st.stop()
else:
    with st.expander("✅ Status do Sistema: Operacional", expanded=False):
        st.write("Bases carregadas e colunas verificadas.")

# --- EXECUÇÃO DO APP ---
pdf_file = st.file_uploader("Upload do Cartão CNPJ", type=["pdf"])

if pdf_file:
    with st.spinner("Analisando..."):
        dados = extrair_dados_completos(pdf_file)
        
        st.subheader("🏢 Dados Extraídos")
        c1, c2 = st.columns([2,1])
        with c1:
            st.markdown(f"**Empresa:** {dados['nome_empresarial']}")
            st.markdown(f"**Nat. Jurídica:** {dados['nat_jur_completa']}")
        with c2:
            st.markdown(f"**CNPJ:** {dados['cnpj']}")
        st.divider()

        # FASE 1: NATUREZA JURÍDICA
        nj_key = apenas_numeros(dados['nat_jur_cod'])
        nj_aprovada = False
        msg_nj = ""
        obs_nj = ""
        
        df_nj['TEMP_KEY'] = df_nj[CFG_NJ['col_codigo']].apply(apenas_numeros)
        match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

        if not match_nj.empty:
            regra = match_nj.iloc[0][CFG_NJ['col_regra']]
            
            # Tenta pegar OBS
            if CFG_NJ['col_justificativa'] in match_nj.columns:
                val_obs = match_nj.iloc[0][CFG_NJ['col_justificativa']]
                if not pd.isna(val_obs): obs_nj = str(val_obs)

            if validar_regra_sim(regra):
                nj_aprovada = True
                msg_nj = "Natureza Jurídica Aderente."
            else:
                msg_nj = "Natureza Jurídica não permitida."
        else:
            msg_nj = f"Código {dados['nat_jur_cod']} não encontrado na base."

        if not nj_aprovada:
            st.error("❌ REPROVADO (Fase 1)")
            st.markdown("**Motivo:** Natureza Jurídica Incompatível.")
            st.warning(f"**Status:** {msg_nj}")
            if obs_nj: st.info(f"**Observação (OBS):** {obs_nj}")
            st.stop()
        
        st.success("✅ FASE 1 OK: Natureza Jurídica. Analisando CNAEs...")
        if obs_nj: st.caption(f"Nota: {obs_nj}")
        
        # FASE 2: CNAES
        cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
        df_cn['TEMP_KEY'] = df_cn[CFG_CNAE['col_codigo']].apply(apenas_numeros)
        
        relatorio_cnaes = []
        algum_cnae_ok = False

        # Principal
        status_p = "❌ Não Aderente"
        obs_p = ""
        match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
        if not match_p.empty:
            if validar_regra_sim(match_p.iloc[0][CFG_CNAE['col_regra']]):
                status_p = "✅ Aderente"
                algum_cnae_ok = True
            
            if CFG_CNAE['col_justificativa'] in match_p.columns:
                val = match_p.iloc[0][CFG_CNAE['col_justificativa']]
                if not pd.isna(val): obs_p = str(val)
        
        relatorio_cnaes.append({"Tipo": "Principal", "Código": dados['cnae_principal_cod'], "Descrição": dados['cnae_principal_completo'], "Status": status_p, "Observação": obs_p})

        # Secundários
        for cod, desc in dados['cnaes_secundarios']:
            s_key = apenas_numeros(cod)
            status_s = "❌ Não Aderente"
            obs_s = ""
            
            match_s = df_cn[df_cn['TEMP_KEY'] == s_key]
            if not match_s.empty:
                if validar_regra_sim(match_s.iloc[0][CFG_CNAE['col_regra']]):
                    status_s = "✅ Aderente"
                    algum_cnae_ok = True
                
                if CFG_CNAE['col_justificativa'] in match_s.columns:
                    val = match_s.iloc[0][CFG_CNAE['col_justificativa']]
                    if not pd.isna(val): obs_s = str(val)
            
            relatorio_cnaes.append({"Tipo": "Secundário", "Código": cod, "Descrição": desc, "Status": status_s, "Observação": obs_s})

        st.dataframe(pd.DataFrame(relatorio_cnaes), use_container_width=True, hide_index=True)

        if algum_cnae_ok:
            st.success("✅ APROVADO (Fase 2)")
            st.markdown("**Motivo:** Possui CNAE aderente.")
            st.stop()

        # FASE 3: CNPJ
        st.info("⚠️ CNAEs não aderentes. Checando exceções...")
        cnpj_key = apenas_numeros(dados['cnpj'])
        df_cp['TEMP_KEY'] = df_cp[CFG_CNPJ['col_cnpj']].apply(apenas_numeros)
        match_cp = df_cp[df_cp['TEMP_KEY'] == cnpj_key]

        if not match_cp.empty:
            res = match_cp.iloc[0][CFG_CNPJ['col_resultado']]
            st.success("✅ APROVADO (Fase 3 - Exceção)")
            st.markdown(f"**Justificativa na Planilha:** {res}")
        else:
            st.error("❌ REPROVADO (Final)")
            st.markdown("Empresa não atende aos requisitos.")