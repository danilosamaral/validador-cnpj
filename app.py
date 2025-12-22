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
    "col_codigo": "CODIGO",
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

st.title("🏢 Validador de Aderência (Auto-Detect)")
st.markdown("---")

# --- FUNÇÕES ---

def limpar_texto_colunas(df):
    """Remove espaços e deixa maiúsculo para facilitar a busca."""
    if df is not None:
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df

@st.cache_data
def carregar_regras_inteligente(caminho_arquivo, colunas_obrigatorias):
    """
    Lê o arquivo e PROCURA em qual linha está o cabeçalho.
    """
    if not os.path.exists(caminho_arquivo):
        return None, f"Arquivo não encontrado: {caminho_arquivo}"
    
    df_bruto = None
    
    # 1. Leitura Inicial (Sem assumir cabeçalho)
    try:
        if caminho_arquivo.endswith('.parquet'):
            # Parquet geralmente já vem certo, mas vamos garantir
            df_bruto = pd.read_parquet(caminho_arquivo)
        elif caminho_arquivo.endswith('.xlsx') or caminho_arquivo.endswith('.xls'):
            # Lê sem cabeçalho para poder procurar
            df_bruto = pd.read_excel(caminho_arquivo, header=None, dtype=str)
        else:
            try:
                df_bruto = pd.read_csv(caminho_arquivo, sep=';', encoding='latin1', header=None, dtype=str)
            except:
                df_bruto = pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8', header=None, dtype=str)
    except Exception as e:
        return None, str(e)

    # 2. O "Caçador de Cabeçalhos"
    # Se for Parquet, geralmente já tem cabeçalho, então pulamos a busca complexa
    if caminho_arquivo.endswith('.parquet'):
        df_final = limpar_texto_colunas(df_bruto)
        return df_final, None

    # Para Excel/CSV, vamos varrer as primeiras 10 linhas procurando as colunas
    linha_cabecalho_encontrada = -1
    
    # Normaliza as colunas procuradas para maiúsculo
    cols_procuradas = [c.upper() for c in colunas_obrigatorias]
    
    # Varre as primeiras 10 linhas
    for i in range(min(10, len(df_bruto))):
        # Pega a linha, converte para string e maiúsculo
        linha = df_bruto.iloc[i].astype(str).str.strip().str.upper().tolist()
        
        # Verifica se pelo menos a coluna de CÓDIGO está nesta linha
        # (Usamos intersection para ver se as colunas batem)
        colunas_achadas = set(linha).intersection(cols_procuradas)
        
        # Se achou pelo menos a coluna principal (ex: CODIGO), BINGO!
        if len(colunas_achadas) >= 1: 
            linha_cabecalho_encontrada = i
            break
    
    # 3. Recarrega o arquivo com a linha certa
    if linha_cabecalho_encontrada > -1:
        # Pega a linha correta como cabeçalho
        novo_header = df_bruto.iloc[linha_cabecalho_encontrada]
        # Pega os dados dali para baixo
        df_final = df_bruto[linha_cabecalho_encontrada + 1:].copy()
        df_final.columns = novo_header
        df_final = limpar_texto_colunas(df_final)
        return df_final, None
    else:
        # Se não achou em lugar nenhum, tenta usar a linha 0 mesmo (fallback)
        df_bruto.columns = df_bruto.iloc[0]
        df_bruto = df_bruto[1:]
        df_final = limpar_texto_colunas(df_bruto)
        return df_final, f"Não encontrei as colunas {cols_procuradas} nas primeiras 10 linhas."

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

with st.spinner("Calibrando leitura das planilhas..."):
    # Passamos as colunas que TEM QUE EXISTIR para o "Caçador" procurar
    df_nj, erro_nj = carregar_regras_inteligente(ARQUIVO_NJ, [CFG_NJ['col_codigo']])
    df_cn, erro_cn = carregar_regras_inteligente(ARQUIVO_CNAE, [CFG_CNAE['col_codigo']])
    df_cp, erro_cp = carregar_regras_inteligente(ARQUIVO_CNPJ, [CFG_CNPJ['col_cnpj']])

erros_fatais = []

# Validação Final
if erro_nj: erros_fatais.append(f"Erro NJ: {erro_nj}")
elif CFG_NJ['col_justificativa'] not in df_nj.columns:
    # Aviso mais amigável
    st.warning(f"Aviso: Não encontrei a coluna '{CFG_NJ['col_justificativa']}' no arquivo NJ. O sistema vai rodar, mas sem mostrar observações de NJ.")
    # Cria a coluna vazia para não quebrar o código
    df_nj[CFG_NJ['col_justificativa']] = None

if erro_cn: erros_fatais.append(f"Erro CNAE: {erro_cn}")
elif CFG_CNAE['col_justificativa'] not in df_cn.columns:
    st.warning(f"Aviso: Não encontrei a coluna '{CFG_CNAE['col_justificativa']}' no arquivo CNAE. O sistema vai rodar, mas sem mostrar observações de CNAE.")
    df_cn[CFG_CNAE['col_justificativa']] = None

if erro_cp: erros_fatais.append(f"Erro CNPJ: {erro_cp}")

if erros_fatais:
    st.error("🛑 ERRO FATAL: Não consegui encontrar os cabeçalhos.")
    for e in erros_fatais: st.text(e)
    st.stop()
else:
    with st.expander("✅ Status: Configuração Carregada", expanded=False):
        st.write(f"NJ: {len(df_nj)} | CNAE: {len(df_cn)} | CNPJ: {len(df_cp)}")

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
            
            # Pega OBS com segurança
            if CFG_NJ['col_justificativa'] in match_nj.columns:
                val = match_nj.iloc[0][CFG_NJ['col_justificativa']]
                if not pd.isna(val): obs_nj = str(val)

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
            st.markdown("Empresa não atende aos requisitos.")sitos.")