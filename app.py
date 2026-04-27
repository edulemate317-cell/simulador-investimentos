import streamlit as st
import requests
import pandas as pd
import io

# ==========================================
# 1. FUNÇÕES DE BACKEND (DADOS E MATEMÁTICA)
# ==========================================

@st.cache_data
def obter_taxas_atuais():
    # Séries: 432 (Selic Meta), 13522 (IPCA acumulado 12m)
    try:
        url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        url_ipca = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
        
        selic = float(requests.get(url_selic).json()[0]['valor']) / 100
        ipca = float(requests.get(url_ipca).json()[0]['valor']) / 100
        cdi = selic - 0.0010
        return selic, cdi, ipca
    except:
        return 0.1050, 0.1040, 0.0450 # Fallback: Selic 10.5%, CDI 10.4%, IPCA 4.5%

def obter_aliquota_ir(meses):
    dias = meses * 30
    if dias <= 180: return 0.225
    elif dias <= 360: return 0.200
    elif dias <= 720: return 0.175
    else: return 0.150

def simular_evolucao(capital_inicial, aporte_mensal, taxa_anual, ipca_anual, meses, isento_ir):
    taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1
    inflacao_mensal = (1 + ipca_anual) ** (1 / 12) - 1
    
    saldo_atual = capital_inicial
    saldo_real = capital_inicial # Saldo descontando a inflação
    total_investido = capital_inicial
    
    historico = []
    
    for mes in range(0, meses + 1):
        if mes > 0:
            saldo_atual = (saldo_atual * (1 + taxa_mensal)) + aporte_mensal
            # O saldo real é o saldo nominal "trazido a valor presente" pela inflação
            saldo_real = (saldo_real * (1 + taxa_mensal) / (1 + inflacao_mensal)) + (aporte_mensal / ((1 + inflacao_mensal) ** mes))
            total_investido += aporte_mensal
        
        lucro_parcial = saldo_atual - total_investido
        aliquota_atual = 0 if isento_ir else obter_aliquota_ir(mes if mes > 0 else 1)
        saldo_liquido = saldo_atual - (lucro_parcial * aliquota_atual)
        
        historico.append({
            "Mês": mes,
            "Total Investido": round(total_investido, 2),
            "Saldo Líquido": round(saldo_liquido, 2),
            "Poder de Compra (Real)": round(saldo_real - (lucro_parcial * aliquota_atual if not isento_ir else 0), 2)
        })
    
    return pd.DataFrame(historico), total_investido, saldo_liquido

# ==========================================
# 2. FRONTEND (INTERFACE)
# ==========================================

st.set_page_config(page_title="InvestSim - Pro", layout="wide")
st.title("🚀 InvestSim Pro: Comparador com Ganho Real")

selic, cdi, ipca = obter_taxas_atuais()

# Cabeçalho com taxas
col_a, col_b, col_c = st.columns(3)
col_a.metric("Selic (BCB)", f"{selic*100:.2f}%")
col_b.metric("CDI (Estimado)", f"{cdi*100:.2f}%")
col_c.metric("IPCA (Últimos 12m)", f"{ipca*100:.2f}%")

# Sidebar
st.sidebar.header("💰 Configurações")
cap_inicial = st.sidebar.number_input("Investimento Inicial (R$)", value=1000.0)
aporte = st.sidebar.number_input("Aporte Mensal (R$)", value=500.0)
meses = st.sidebar.slider("Prazo (Meses)", 1, 120, 24)

def menu_ativo(n):
    st.sidebar.subheader(f"Ativo {n}")
    tipo = st.sidebar.selectbox(f"Tipo", ["CDB", "LCI/LCA", "Poupança"], key=f"t{n}")
    if tipo == "Poupança":
        taxa = (1.005**12-1) if selic > 0.085 else (selic*0.7)
        isento = True
    else:
        perc = st.sidebar.number_input("% do CDI", value=100.0, key=f"p{n}")
        taxa = cdi * (perc/100)
        isento = (tipo == "LCI/LCA")
    return f"{tipo} {n}", taxa, isento

n1, t1, i1 = menu_ativo(1)
n2, t2, i2 = menu_ativo(2)

if st.sidebar.button("Simular e Comparar", type="primary", use_container_width=True):
    df1, total, liq1 = simular_evolucao(cap_inicial, aporte, t1, ipca, meses, i1)
    df2, _, liq2 = simular_evolucao(cap_inicial, aporte, t2, ipca, meses, i2)
    
    # Cards de Resultado
    st.subheader("Análise de Resultados")
    c1, c2, c3 = st.columns(3)
    c1.metric("Dinheiro Investido", f"R$ {total:,.2f}")
    
    # Ativo 1
    ganho_real1 = df1["Poder de Compra (Real)"].iloc[-1] - total
    c2.metric(n1, f"R$ {liq1:,.2f}", f"Ganho Real: R$ {ganho_real1:,.2f}", delta_color="normal")
    
    # Ativo 2
    ganho_real2 = df2["Poder de Compra (Real)"].iloc[-1] - total
    c3.metric(n2, f"R$ {liq2:,.2f}", f"Ganho Real: R$ {ganho_real2:,.2f}", delta_color="normal")

    # Gráfico
    st.subheader("Evolução do Poder de Compra (Ganho Real)")
    chart_data = pd.DataFrame({
        "Mês": df1["Mês"],
        f"{n1} (Real)": df1["Poder de Compra (Real)"],
        f"{n2} (Real)": df2["Poder de Compra (Real)"],
        "Investimento": df1["Total Investido"]
    }).set_index("Mês")
    st.line_chart(chart_data)

    # Exportação
    st.subheader("📥 Exportar Dados")
    csv_buffer = io.StringIO()
    # Criamos um DF combinado para o Excel
    df_export = df1.copy()
    df_export.columns = [f"{c} ({n1})" if c != "Mês" else c for c in df_export.columns]
    df_export[f"Saldo Líquido ({n2})"] = df2["Saldo Líquido"]
    df_export[f"Poder de Compra Real ({n2})"] = df2["Poder de Compra (Real)"]
    
    df_export.to_csv(csv_buffer, index=False)
    st.download_button(
        label="Baixar Simulação em CSV (Excel)",
        data=csv_buffer.getvalue(),
        file_name=f"simulacao_investimento_{meses}meses.csv",
        mime="text/csv",
    )