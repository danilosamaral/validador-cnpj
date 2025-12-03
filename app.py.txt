import streamlit as st
import pdfplumber
import pandas as pd
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Validador de CNPJ - Etapa 1", layout="wide")

st.title("🏢 Validador de Aderência - Plano de Comércio")
st.markdown("""
Esta ferramenta cruza os dados do **Cartão CNPJ (PDF)** com a **Tabela de Regras (CSV)**.
""")
st.markdown("---")

# --- FUNÇÕES AUXILIARES ---

@st.cache_data
def carregar_csv(arquivo):
    """Lê o CSV tentando diferentes codificações para evitar erros de acentuação."""
    try:
        # Tenta ler com separador padrão de sistemas brasileiros (;) e encoding latin1 (Excel padrão)
        df = pd.read_csv(arquivo, sep=';', encoding='latin1', dtype=str)
        return df
    except:
        try:
            # Segunda tentativa: utf-8
            df = pd.read_csv(arquivo, sep=';', encoding='utf-8', dtype=str)
            return df
        except Exception as e:
            st.error(f"Erro ao ler o arquivo: {e}")
            return None

def extrair_dados_pdf(pdf_file):
    """Extrai texto do PDF e busca a Natureza Jurídica via Regex."""
    texto_completo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
            
    # Regex para capturar o padrão "214-3" ou "206-2" logo após o título
    # Procura especificamente o padrão numérico NNN-N
    padrao_nat_jur = r"CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA.*?(\d{3}-\d)"
    
    # Flags: re.DOTALL permite que o ponto (.) pegue quebras de linha
    match = re.search(padrao_nat_jur, texto_completo, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    return None

# --- BARRA LATERAL: CONFIGURAÇÃO DAS REGRAS ---
st.sidebar.header("1. Configuração da Regra")
arquivo_regras = st.sidebar.file_uploader("Carregar 'Tabela Natureza Jurídica.csv'", type=["csv"])

df_regras = None
coluna_codigo = None
coluna_validacao = None
valor_aceite = None

if arquivo_regras:
    df_regras = carregar_csv(arquivo_regras)
    
    if df_regras is not None:
        st.sidebar.success("✅ Tabela carregada com sucesso!")
        
        # --- SELEÇÃO INTELIGENTE DE COLUNAS ---
        st.sidebar.markdown("### Mapeamento de Colunas")
        st.sidebar.info("Confirme abaixo quais colunas o sistema deve ler.")
        
        colunas_disponiveis = df_regras.columns.tolist()
        
        # Tenta adivinhar a coluna de código (procura por 'COD' ou 'NATUREZA')
        index_cod = next((i for i, c in enumerate(colunas_disponiveis) if 'COD' in c.upper()), 0)
        coluna_codigo = st.sidebar.selectbox("Qual coluna tem o CÓDIGO (ex: 213-5)?", colunas_disponiveis, index=index_cod)
        
        # Tenta adivinhar a coluna de validação (procura por 'COMERCIO', 'PLANO', 'LIBERADO')
        index_val = next((i for i, c in enumerate(colunas_disponiveis) if 'COMERCIO' in c.upper() or 'STATUS' in c.upper()), 0)
        coluna_validacao = st.sidebar.selectbox("Qual coluna define a REGRA (Sim/Não)?", colunas_disponiveis, index=index_val)
        
        # Define o critério de sucesso
        valor_aceite = st.sidebar.text_input("Qual valor na planilha indica APROVAÇÃO?", value="SIM")
        
        # Mostra uma prévia para o usuário conferir
        with st.expander("👀 Ver prévia da Tabela de Regras"):
            st.dataframe(df_regras.head())

# --- ÁREA PRINCIPAL: ANÁLISE DO CLIENTE ---
st.header("2. Validação do Cliente")

if df_regras is None:
    st.warning("👈 Por favor, carregue o arquivo CSV na barra lateral para começar.")
else:
    arquivo_pdf = st.file_uploader("Upload do Cartão CNPJ (PDF)", type=["pdf"])

    if arquivo_pdf:
        with st.spinner("Analisando documento..."):
            # 1. Extração
            codigo_pdf = extrair_dados_pdf(arquivo_pdf)
            
            st.subheader("Resultado da Análise")
            col1, col2 = st.columns(2)
            
            # --- MOSTRAR O QUE FOI LIDO NO PDF ---
            with col1:
                st.markdown("#### 📄 Dados do PDF")
                if codigo_pdf:
                    st.metric("Natureza Jurídica Extraída", codigo_pdf)
                else:
                    st.error("Não foi possível encontrar a Natureza Jurídica no PDF.")
                    st.stop()

            # --- CRUZAR COM O CSV ---
            with col2:
                st.markdown("#### 🔍 Cruzamento com Regras")
                
                # Busca o código na tabela
                # Removemos espaços em branco para garantir o "match"
                linha_encontrada = df_regras[df_regras[coluna_codigo].str.strip() == codigo_pdf]
                
                if not linha_encontrada.empty:
                    # Pega o valor da regra (ex: "SIM" ou "NÃO")
                    status_regra = linha_encontrada.iloc[0][coluna_validacao]
                    
                    # Verifica a descrição (se houver uma coluna com 'DESC' no nome, mostramos para contexto)
                    col_desc = next((c for c in df_regras.columns if 'DESC' in c.upper()), None)
                    descricao = linha_encontrada.iloc[0][col_desc] if col_desc else "Sem descrição"
                    
                    st.write(f"**Descrição:** {descricao}")
                    st.write(f"**Status na Tabela:** {status_regra}")
                    
                    # COMPARAÇÃO FINAL
                    # Normaliza tudo para maiúsculo para evitar erros (Sim vs sim)
                    if str(status_regra).strip().upper() == valor_aceite.strip().upper():
                        st.success(f"✅ APROVADO: Empresa aderente ao Plano de Comércio.")
                    else:
                        st.error(f"❌ REPROVADO: Natureza Jurídica não aceita neste plano.")
                else:
                    st.warning(f"⚠️ O código {codigo_pdf} não foi encontrado na tabela de regras.")