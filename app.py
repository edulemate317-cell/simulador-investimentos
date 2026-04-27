import streamlit as st
import requests
import pandas as pd
import io
import plotly.express as px

# ==========================================
# 1. FUNÇÕES DE BACKEND (DADOS E MATEMÁTICA)
# ==========================================

@st.cache_data
def obter_taxas_atuais():
    try:
        url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        url_ipca = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
        
        selic = float(requests.get(url_selic).json()[0]['valor']) / 100
        ipca = float(requests.get(url_ipca).json()[0]['valor']) / 100
        cdi = selic - 0.0010
        return selic, cdi, ipca
    except:
        return 0.1050, 0.1040, 0.0450 

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
    saldo_real = capital_inicial
    total_investido = capital_inicial
    
    historico = []
    
    for mes in range(0, meses + 1):
        if mes > 0:
            saldo_atual = (saldo_atual * (1 + taxa_mensal)) + aporte_mensal
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
st.title("🚀 InvestSim Pro: Simulador e Carteira")

selic, cdi, ipca = obter_taxas_atuais()

st.info(f"**Taxas Oficiais Atualizadas:** Selic: **{selic*100:.2f}% a.a.** | CDI: **{cdi*100:.2f}% a.a.** | IPCA (12m): **{ipca*100:.2f}%**")

# ==========================================
# BARRA LATERAL (CONTROLES COM TESOURO)
# ==========================================
st.sidebar.header("💰 Configurações Gerais")

cap_inicial = st.sidebar.number_input("Investimento Inicial (R$)", value=1000.0, help="O valor que você já tem em mãos para começar a investir hoje.")
aporte = st.sidebar.number_input("Aporte Mensal (R$)", value=500.0, help="Quanto você vai depositar todos os meses.")
meses = st.sidebar.slider("Prazo (Meses)", 1, 120, 24, help="Tempo total do investimento.")

def menu_ativo(n):
    st.sidebar.markdown(f"### Ativo {n}")
    
    # Adicionamos os títulos do Tesouro Direto aqui!
    tipo = st.sidebar.selectbox(
        f"Tipo", 
        ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], 
        key=f"t{n}", 
        help="CDB e Tesouro sofrem desconto de IR. LCI, LCA e Poupança são isentos."
    )
    
    isento = False # Por padrão, todos pagam IR, exceto se alterarmos abaixo
    taxa = 0.0
    
    if tipo == "Poupança":
        taxa = (1.005**12-1) if selic > 0.085 else (selic*0.7)
        isento = True
        st.sidebar.caption("Isenta de IR.")
        
    elif tipo in ["CDB", "LCI/LCA"]:
        perc = st.sidebar.number_input("% do CDI", value=100.0, key=f"p{n}")
        taxa = cdi * (perc/100)
        isento = (tipo == "LCI/LCA")
        
    elif tipo == "Tesouro Selic":
        taxa = selic
        st.sidebar.caption("Rende 100% da Taxa Selic.")
        
    elif tipo == "Tesouro Prefixado":
        taxa_pre = st.sidebar.number_input("Taxa Prefixada (% a.a.)", value=10.5, step=0.1, key=f"pre{n}", help="Taxa fixa anual que não muda.")
        taxa = taxa_pre / 100
        
    elif tipo == "Tesouro IPCA+":
        taxa_fixa = st.sidebar.number_input("Taxa Fixa + IPCA (% a.a.)", value=5.5, step=0.1, key=f"ipca{n}", help="Paga a inflação (IPCA) mais esta taxa fixa.")
        # Matemática de juros sobre juros (Inflação + Taxa)
        taxa = ((1 + ipca) * (1 + (taxa_fixa / 100))) - 1

    return f"{tipo} {n}", taxa, isento

st.sidebar.divider()
n1, t1, i1 = menu_ativo(1)
st.sidebar.divider()
n2, t2, i2 = menu_ativo(2)

btn_simular = st.sidebar.button("Simular e Comparar", type="primary", use_container_width=True)

# ==========================================
# ÁREA PRINCIPAL
# ==========================================
aba_comparador, aba_carteira = st.tabs(["📊 Comparador de Ativos", "🥧 Distribuição de Carteira"])

with aba_comparador:
    if btn_simular:
        df1, total, liq1 = simular_evolucao(cap_inicial, aporte, t1, ipca, meses, i1)
        df2, _, liq2 = simular_evolucao(cap_inicial, aporte, t2, ipca, meses, i2)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Dinheiro Investido", f"R$ {total:,.2f}", help="Soma do valor inicial com os aportes.")
        c2.metric(n1, f"R$ {liq1:,.2f}", f"Ganho Real: R$ {df1['Poder de Compra (Real)'].iloc[-1] - total:,.2f}", delta_color="normal")
        c3.metric(n2, f"R$ {liq2:,.2f}", f"Ganho Real: R$ {df2['Poder de Compra (Real)'].iloc[-1] - total:,.2f}", delta_color="normal")

        st.subheader("Evolução do Poder de Compra (Ganho Real)")
        chart_data = pd.DataFrame({
            "Mês": df1["Mês"],
            f"{n1} (Real)": df1["Poder de Compra (Real)"],
            f"{n2} (Real)": df2["Poder de Compra (Real)"],
            "Investimento": df1["Total Investido"]
        }).set_index("Mês")
        st.line_chart(chart_data)
    else:
        st.write("👈 Configure os seus investimentos na barra lateral e clique em **Simular e Comparar**.")

with aba_carteira:
    st.subheader("Planeie a sua Carteira Ideal")
    st.write("Ajuste os pesos percentuais abaixo para ver a distribuição do seu patrimônio.")
    
    patrimonio_total = st.number_input("Patrimônio Total Disponível (R$)", value=50000.0, step=1000.0)
    
    col_p1, col_p2, col_p3 = st.columns(3)
    perc_cdb = col_p1.slider("Renda Fixa (CDB e Tesouro)", 0, 100, 50)
    perc_lci = col_p2.slider("Isentos (LCI/LCA)", 0, 100, 30)
    perc_caixa = col_p3.slider("Reserva de Emergência", 0, 100, 20)
    
    total_perc = perc_cdb + perc_lci + perc_caixa
    
    if total_perc != 100:
        st.error(f"⚠️ Atenção: A soma das percentagens está em **{total_perc}%**. Ajuste para exatamente 100%.")
    else:
        dados_carteira = pd.DataFrame({
            "Investimento": ["Renda Fixa Geral", "LCI/LCA", "Reserva (Poupança)"],
            "Valor (R$)": [
                patrimonio_total * (perc_cdb / 100),
                patrimonio_total * (perc_lci / 100),
                patrimonio_total * (perc_caixa / 100)
            ]
        })
        
        c_grafico, c_tabela = st.columns([2, 1])
        
        with c_grafico:
            fig = px.pie(
                dados_carteira, 
                values='Valor (R$)', 
                names='Investimento', 
                hole=0.4,
                color_discrete_sequence=['#3b82f6', '#10b981', '#f59e0b']
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
            
        with c_tabela:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.dataframe(
                dados_carteira.style.format({"Valor (R$)": "R$ {:,.2f}"}),
                hide_index=True,
                use_container_width=True
            )
