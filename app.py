import streamlit as st
import pdfplumber
import pandas as pd
import re
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador Corporativo", layout="wide")

# ==============================================================================
# 🔧 ÁREA DE CONFIGURAÇÃO (Onde você define os arquivos e colunas)
# ==============================================================================

# 1. NOMES DOS ARQUIVOS (Devem estar na mesma pasta do script)
ARQUIVO_NJ = "regras_nj.csv"
ARQUIVO_CNAE = "regras_cnae.xlsx"
ARQUIVO_CNPJ = "regras_cnpj.parquet"

# 2. MAPEAMENTO DAS COLUNAS (Ajuste conforme o cabeçalho real das suas planilhas)

# Configuração para Natureza Jurídica (.csv)
CFG_NJ = {
    "col_codigo": "NATJUR",         # Nome da coluna com o código (ex: 213-5)
    "col_regra": "ADERENCIA"        # Nome da coluna com Sim/Não
}

# Configuração para CNAEs (.xlsx)
CFG_CNAE = {
    "col_codigo": "CNAE",           # Nome da coluna com o código (ex: 47.11-3-02)
    "col_regra": "PERMITIDO"        # Nome da coluna com Sim/Não
}

# Configuração para Exceções de CNPJ (.parquet)
CFG_CNPJ = {
    "col_cnpj": "CNPJ",             # Nome da coluna com o número do CNPJ
    "col_resultado": "RESULTADO"    # Nome da coluna com a justificativa (ex: 'Aderente por CNAE X')
}
# ==============================================================================

st.title("🏢 Validador de Aderência (Versão Corporativa)")
st.markdown("""
**Instrução:** O sistema utiliza as regras vigentes carregadas automaticamente.
Arraste o **Cartão CNPJ (PDF)** abaixo para iniciar a validação.
""")
st.markdown("---")

# --- FUNÇÕES DO SISTEMA ---

@st.cache_data
def carregar_regras_nativas(caminho_arquivo):
    """Lê CSV, Excel ou PARQUET automaticamente."""
    if not os.path.exists(caminho_arquivo):
        return None, f"Arquivo não encontrado: {caminho_arquivo}"
    
    try:
        # 1. PARQUET (Leitura ultra rápida)
        if caminho_arquivo.endswith('.parquet'):
            return pd.read_parquet(caminho_arquivo), None

        # 2. EXCEL
        elif caminho_arquivo.endswith('.xlsx') or caminho_arquivo.endswith('.xls'):
            return pd.read_excel(caminho_arquivo, dtype=str), None
        
        # 3. CSV (Tenta detectar separador e encoding)
        else:
            try:
                # Tenta padrão Brasil (; e Latin1)
                return pd.read_csv(caminho_arquivo, sep=';', encoding='latin1', dtype=str), None
            except:
                # Se falhar, tenta padrão universal (, e UTF-8)
                return pd.read_csv(caminho_arquivo, sep=',', encoding='utf-8', dtype=str), None
    except Exception as e:
        return None, str(e)

def apenas_numeros(texto):
    """Remove pontuação para comparação."""
    if not texto: return ""
    return re.sub(r'\D', '', str(texto))

def limpar_espacos(texto):
    """Limpa quebras de linha e espaços extras."""
    if not texto: return ""
    return re.sub(r'\s+', ' ', texto).strip()

def validar_regra_sim(valor):
    """Verifica se o valor é positivo (Sim, S, OK, Aderente)."""
    if pd.isna(valor): return False
    v = str(valor).strip().upper()
    return v in ['SIM', 'S', 'PERMITIDO', 'OK', 'VERDADEIRO', 'YES', 'ADERENTE']

def extrair_dados_completos(pdf_file):
    """Extrai informações vitais do PDF."""
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

    # Regex para extração
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

# --- CARREGAMENTO INICIAL DAS REGRAS (Nativo) ---
msg_container = st.empty()

with st.spinner("Carregando regras de negócio..."):
    df_nj, erro_nj = carregar_regras_nativas(ARQUIVO_NJ)
    df_cn, erro_cn = carregar_regras_nativas(ARQUIVO_CNAE)
    df_cp, erro_cp = carregar_regras_nativas(ARQUIVO_CNPJ)

# Validação crítica dos arquivos
erros = []
if erro_nj: erros.append(f"Erro NJ ({ARQUIVO_NJ}): {erro_nj}")
if erro_cn: erros.append(f"Erro CNAE ({ARQUIVO_CNAE}): {erro_cn}")
if erro_cp: erros.append(f"Erro CNPJ ({ARQUIVO_CNPJ}): {erro_cp}")

# Validação das colunas
if not erros:
    if CFG_NJ['col_codigo'] not in df_nj.columns: erros.append(f"Coluna '{CFG_NJ['col_codigo']}' não existe em {ARQUIVO_NJ}")
    if CFG_CNAE['col_codigo'] not in df_cn.columns: erros.append(f"Coluna '{CFG_CNAE['col_codigo']}' não existe em {ARQUIVO_CNAE}")
    if CFG_CNPJ['col_cnpj'] not in df_cp.columns: erros.append(f"Coluna '{CFG_CNPJ['col_cnpj']}' não existe em {ARQUIVO_CNPJ}")

if erros:
    st.error("🚨 ERRO DE CONFIGURAÇÃO")
    for e in erros: st.text(e)
    st.info("Verifique se os arquivos estão na pasta e se os nomes das colunas batem com a 'ÁREA DE CONFIGURAÇÃO' no código.")
    st.stop()
else:
    # Mostra status discreto de sucesso
    with st.expander("✅ Base de regras carregada", expanded=False):
        st.write(f"• Natureza Jurídica: {len(df_nj)} registros")
        st.write(f"• CNAEs: {len(df_cn)} registros")
        st.write(f"• Exceções CNPJ: {len(df_cp)} registros")

# --- ÁREA PRINCIPAL ---
pdf_file = st.file_uploader("Upload do Cartão CNPJ", type=["pdf"])

if pdf_file:
    with st.spinner("Analisando documento..."):
        dados = extrair_dados_completos(pdf_file)
        
        # --- EXIBIÇÃO DOS DADOS ---
        st.subheader("🏢 Dados Extraídos")
        c1, c2 = st.columns([2,1])
        with c1:
            st.markdown(f"**Empresa:** {dados['nome_empresarial']}")
            st.markdown(f"**Nat. Jurídica:** {dados['nat_jur_completa']}")
        with c2:
            st.markdown(f"**CNPJ:** {dados['cnpj']}")
        st.divider()

        # --- LÓGICA DE VALIDAÇÃO ---
        
        # FASE 1: NATUREZA JURÍDICA (Eliminatória)
        nj_key = apenas_numeros(dados['nat_jur_cod'])
        nj_aprovada = False
        justificativa_nj = ""
        
        df_nj['TEMP_KEY'] = df_nj[CFG_NJ['col_codigo']].apply(apenas_numeros)
        match_nj = df_nj[df_nj['TEMP_KEY'] == nj_key]

        if not match_nj.empty:
            regra = match_nj.iloc[0][CFG_NJ['col_regra']]
            if validar_regra_sim(regra):
                nj_aprovada = True
                justificativa_nj = "Natureza Jurídica Aderente."
            else:
                justificativa_nj = "Natureza Jurídica não permitida."
        else:
            justificativa_nj = f"Código {dados['nat_jur_cod']} não encontrado na base."

        if not nj_aprovada:
            st.error("❌ REPROVADO (Fase 1)")
            st.markdown("**Motivo:** Natureza Jurídica Incompatível.")
            st.warning(f"**Justificativa:** {justificativa_nj}")
            st.stop()
        
        st.success("✅ FASE 1 OK: Natureza Jurídica. Verificando CNAEs...")
        
        # FASE 2: CNAES (Busca Aderência)
        cnae_p_key = apenas_numeros(dados['cnae_principal_cod'])
        df_cn['TEMP_KEY'] = df_cn[CFG_CNAE['col_codigo']].apply(apenas_numeros)
        
        relatorio_cnaes = []
        algum_cnae_ok = False

        # Verifica Principal
        status_p = "❌ Não Aderente"
        match_p = df_cn[df_cn['TEMP_KEY'] == cnae_p_key]
        if not match_p.empty:
            if validar_regra_sim(match_p.iloc[0][CFG_CNAE['col_regra']]):
                status_p = "✅ Aderente"
                algum_cnae_ok = True
        
        relatorio_cnaes.append({"Tipo": "Principal", "Código": dados['cnae_principal_cod'], "Desc": dados['cnae_principal_completo'], "Status": status_p})

        # Verifica Secundários
        for cod, desc in dados['cnaes_secundarios']:
            s_key = apenas_numeros(cod)
            status_s = "❌ Não Aderente"
            match_s = df_cn[df_cn['TEMP_KEY'] == s_key]
            if not match_s.empty:
                if validar_regra_sim(match_s.iloc[0][CFG_CNAE['col_regra']]):
                    status_s = "✅ Aderente"
                    algum_cnae_ok = True
            
            relatorio_cnaes.append({"Tipo": "Secundário", "Código": cod, "Desc": desc, "Status": status_s})

        # Mostra tabela sempre
        st.dataframe(pd.DataFrame(relatorio_cnaes), use_container_width=True, hide_index=True)

        if algum_cnae_ok:
            st.success("✅ APROVADO (Fase 2)")
            st.markdown("**Motivo:** Possui pelo menos uma atividade econômica (CNAE) aderente.")
            st.stop()

        # FASE 3: CNPJ (Exceção)
        st.info("⚠️ Nenhum CNAE compatível. Buscando na Lista de Exceções...")
        
        cnpj_key = apenas_numeros(dados['cnpj'])
        df_cp['TEMP_KEY'] = df_cp[CFG_CNPJ['col_cnpj']].apply(apenas_numeros)
        match_cp = df_cp[df_cp['TEMP_KEY'] == cnpj_key]

        if not match_cp.empty:
            resultado_planilha = match_cp.iloc[0][CFG_CNPJ['col_resultado']]
            st.success("✅ APROVADO (Fase 3 - Exceção)")
            st.markdown(f"**Justificativa na Planilha:** {resultado_planilha}")
        else:
            st.error("❌ REPROVADO (Final)")
            st.markdown("**Resumo da Análise:**")
            st.markdown("1. ✅ Natureza Jurídica: Aderente.")
            st.markdown("2. ❌ CNAEs: Nenhuma atividade compatível.")
            st.markdown("3. ❌ CNPJ: Não consta na lista de exceções.")