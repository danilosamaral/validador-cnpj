import streamlit as st
import pdfplumber
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Corporativo", layout="wide")

# ==============================================================================
# 🔧 ÁREA DE CONFIGURAÇÃO (AJUSTADA)
# ==============================================================================

# 1. NOMES DOS ARQUIVOS
ARQUIVO_NJ = "regras_nj.csv"
ARQUIVO_CNAE = "regras_cnae.xlsx"
ARQUIVO_CNPJ = "regras_cnpj.parquet"

# 2. MAPEAMENTO DAS COLUNAS

# Natureza Jurídica (ATUALIZADO COM COLUNA 'OBS')
CFG_NJ = {
    "col_codigo": "NATJUR",
    "col_regra": "ADERENCIA",
    "col_justificativa": "WHY"      # <--- NOVA COLUNA SOLICITADA
}

# CNAEs (ATUALIZADO PARA 'JUST')
CFG_CNAE = {
    "col_codigo": "CNAE",
    "col_regra": "PERMITIDO",
    "col_justificativa": "JUST"     # <--- NOME ALTERADO
}

# Exceções de CNPJ
CFG_CNPJ = {
    "col_cnpj": "CNPJ",
    "col_resultado": "RESULTADO"
}
# ==============================================================================

st.title("🏢 Validador de Aderência (Versão Final)")
st.markdown("---")

# --- FUNÇÕES ---

@st.cache_data
def carregar_regras_nativas(caminho_arquivo):
    """Lê CSV, Excel ou PARQUET."""
    if not os.path.exists(caminho_arquivo):
        return None, f"Arquivo não encontrado: {caminho_arquivo}"
    
    try:
        if caminho_arquivo.endswith('.parquet'):
            return pd.read_parquet(caminho_arquivo), None
        elif caminho_arquivo.endswith('.xlsx') or caminho_arquivo.endswith('.xls'):
            return pd.read_excel(caminho_arquivo, dtype=str), None
        else:
            try:
                return pd.read_csv(caminho_arquivo, sep=';', encoding='latin1', dtype=str), None
            except:
                return pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8', dtype=str), None
    except Exception as e:
        return None, str(e)

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
with st.spinner("Carregando regras..."):
    df_nj, erro_nj = carregar_regras_nativas(ARQUIVO_NJ)
    df_cn, erro_cn = carregar_regras_nativas(ARQUIVO_CNAE)
    df_cp, erro_cp = carregar_regras_nativas(ARQUIVO_CNPJ)

erros = []
if erro_nj: erros.append(f"Erro NJ: {erro_nj}")
if erro_cn: erros.append(f"Erro CNAE: {erro_cn}")
if erro_cp: erros.append(f"Erro CNPJ: {erro_cp}")

if not erros:
    if CFG_NJ['col_codigo'] not in df_nj.columns: erros.append(f"Coluna '{CFG_NJ['col_codigo']}' não existe em {ARQUIVO_NJ}")
    # Verifica OBS na NJ
    if CFG_NJ['col_justificativa'] not in df_nj.columns: erros.append(f"Coluna '{CFG_NJ['col_justificativa']}' (OBS) não existe em {ARQUIVO_NJ}")
    
    if CFG_CNAE['col_codigo'] not in df_cn.columns: erros.append(f"Coluna '{CFG_CNAE['col_codigo']}' não existe em {ARQUIVO_CNAE}")
    # Verifica JUST no CNAE
    if CFG_CNAE['col_justificativa'] not in df_cn.columns: erros.append(f"Coluna '{CFG_CNAE['col_justificativa']}' (JUST) não existe em {ARQUIVO_CNAE}")

if erros:
    st.error("🚨 ERRO DE CONFIGURAÇÃO DAS PLANILHAS")
    for e in erros: st.text(e)
    st.stop()
else:
    with st.expander("✅ Status das Regras", expanded=False):
        st.write("Todas as bases carregadas com sucesso.")

# --- EXECUÇÃO ---
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

        # ------------------------------------------------------------------
        # FASE 1: NATUREZA JURÍDICA
        # ------------------------------------------------------------------
        nj_key = apenas_numeros(dados['nat_jur_cod'])
        nj_aprovada = False
        msg_nj = ""
        obs_nj = "" # Variável para guardar o texto da coluna OBS
        
        df_nj['TEMP_KEY'] = df_nj[CFG_NJ['col_codigo']].apply(apenas_numeros)
        match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

        if not match_nj.empty:
            # Pega regra
            regra = match_nj.iloc[0][CFG_NJ['col_regra']]
            
            # Pega observação (coluna OBS)
            val_obs = match_nj.iloc[0][CFG_NJ['col_justificativa']]
            if not pd.isna(val_obs):
                obs_nj = str(val_obs)

            if validar_regra_sim(regra):
                nj_aprovada = True
                msg_nj = "Natureza Jurídica Aderente."
            else:
                msg_nj = "Natureza Jurídica não permitida."
        else:
            msg_nj = f"Código {dados['nat_jur_cod']} não encontrado."

        if not nj_aprovada:
            st.error("❌ REPROVADO (Fase 1)")
            st.markdown("**Motivo:** Natureza Jurídica Incompatível.")
            st.warning(f"**Status:** {msg_nj}")
            
            # Se tiver observação na planilha (ex: explicando pq é proibido), mostra aqui:
            if obs_nj:
                st.info(f"**Observação da Planilha (OBS):** {obs_nj}")
            
            st.stop()
        
        st.success("✅ FASE 1 OK: Natureza Jurídica. Verificando CNAEs...")
        if obs_nj:
            st.caption(f"Nota sobre a Natureza Jurídica: {obs_nj}")
        
        # ------------------------------------------------------------------
        # FASE 2: CNAES
        # ------------------------------------------------------------------
        cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
        df_cn['TEMP_KEY'] = df_cn[CFG_CNAE['col_codigo']].apply(apenas_numeros)
        
        relatorio_cnaes = []
        algum_cnae_ok = False

        # --- Principal ---
        status_p = "❌ Não Aderente"
        obs_p = ""
        
        match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
        if not match_p.empty:
            if validar_regra_sim(match_p.iloc[0][CFG_CNAE['col_regra']]):
                status_p = "✅ Aderente"
                algum_cnae_ok = True
            
            # Pega a justificativa (Coluna JUST)
            val_obs = match_p.iloc[0][CFG_CNAE['col_justificativa']]
            if not pd.isna(val_obs):
                obs_p = str(val_obs)
        
        relatorio_cnaes.append({
            "Tipo": "Principal", 
            "Código": dados['cnae_principal_cod'], 
            "Descrição": dados['cnae_principal_completo'], 
            "Status": status_p,
            "Observação (JUST)": obs_p
        })

        # --- Secundários ---
        for cod, desc in dados['cnaes_secundarios']:
            s_key = apenas_numeros(cod)
            status_s = "❌ Não Aderente"
            obs_s = ""
            
            match_s = df_cn[df_cn['TEMP_KEY'] == s_key]
            if not match_s.empty:
                if validar_regra_sim(match_s.iloc[0][CFG_CNAE['col_regra']]):
                    status_s = "✅ Aderente"
                    algum_cnae_ok = True
                
                # Pega a justificativa (Coluna JUST)
                val_obs = match_s.iloc[0][CFG_CNAE['col_justificativa']]
                if not pd.isna(val_obs):
                    obs_s = str(val_obs)
            
            relatorio_cnaes.append({
                "Tipo": "Secundário", 
                "Código": cod, 
                "Descrição": desc, 
                "Status": status_s,
                "Observação (JUST)": obs_s
            })

        # Exibe a tabela
        st.dataframe(
            pd.DataFrame(relatorio_cnaes), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Observação (JUST)": st.column_config.TextColumn("Observação", width="medium")
            }
        )

        if algum_cnae_ok:
            st.success("✅ APROVADO (Fase 2)")
            st.markdown("**Motivo:** Possui CNAE aderente.")
            st.stop()

        # ------------------------------------------------------------------
        # FASE 3: CNPJ
        # ------------------------------------------------------------------
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