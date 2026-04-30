import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURAÇÕES
# ==========================================
st.set_page_config(page_title="InvestSim Pro", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 2. MOTOR FINANCEIRO
# ==========================================
@st.cache_data(ttl=3600)
def buscar_indicadores():
    try:
        r_selic = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?format=json", timeout=3)
        r_ipca = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?format=json", timeout=3)
        selic = float(r_selic.json()[0]["valor"]) / 100
        ipca = float(r_ipca.json()[0]["valor"]) / 100
    except Exception:
        selic, ipca = 0.1075, 0.0450
    return selic, (selic - 0.001), ipca

def calcular_taxa_anual(tipo, selic, cdi, ipca, extra=0.0):
    if tipo == "Poupança": return (1.005**12 - 1) if selic > 0.085 else (selic * 0.7), True
    if tipo == "CDB": return cdi * (extra / 100), False
    if tipo == "LCI/LCA": return cdi * (extra / 100), True
    if tipo == "Tesouro Selic": return max(0.0, selic - 0.002), False
    if tipo == "Tesouro Prefixado": return max(0.0, (extra / 100) - 0.002), False
    if tipo == "Tesouro IPCA+": return max(0.0, (((1 + ipca) * (1 + extra / 100)) - 1) - 0.002), False
    return 0.0, False

def simular(v_ini, v_apo, tx_a, ipca_a, meses, isento):
    tx_m, inf_m = (1 + tx_a)**(1/12) - 1, (1 + ipca_a)**(1/12) - 1
    bruto, investido = v_ini, v_ini
    dados = []
    for m in range(meses + 1):
        if m > 0:
            bruto = (bruto * (1 + tx_m)) + v_apo
            investido += v_apo
        ir = 0.0 if isento else max(0, bruto - investido) * (0.225 if m < 6 else 0.20 if m < 12 else 0.175 if m < 24 else 0.15)
        dados.append({"Mês": m, "Investido": investido, "Saldo Bruto": bruto, "IR Estimado": ir, "Saldo Líquido": bruto - ir})
    return pd.DataFrame(dados)

# ==========================================
# 3. INTERFACE
# ==========================================
selic_base, cdi_base, ipca_base = buscar_indicadores()

with st.sidebar:
    st.header("🌍 Cenário Econômico")
    cenario = st.selectbox("Cenário", ["Atual", "Otimista (Juros ↑)", "Pessimista (Juros ↓)"])
    if cenario == "Otimista (Juros ↑)": selic_sim, ipca_sim = selic_base + 0.02, max(0.02, ipca_base - 0.01)
    elif cenario == "Pessimista (Juros ↓)": selic_sim, ipca_sim = max(0.05, selic_base - 0.04), ipca_base + 0.03
    else: selic_sim, ipca_sim = selic_base, ipca_base
    cdi_sim = selic_sim - 0.001
    st.info(f"Selic: {selic_sim*100:.2f}% | CDI: {cdi_sim*100:.2f}% | IPCA: {ipca_sim*100:.2f}%")

st.title("🚀 InvestSim Pro")
tab1, tab2, tab3 = st.tabs(["📊 Comparador", "🏗️ Carteira Conjunta", "🥧 Alvos"])

# ABA 1: COMPARADOR
with tab1:
    col1, col2, col3 = st.columns(3)
    c_ini = col1.number_input("Investimento Inicial", 0.0, value=10000.0, step=1000.0)
    c_apo = col2.number_input("Aporte Mensal", 0.0, value=500.0, step=100.0)
    c_mes = col3.slider("Prazo (meses)", 1, 360, 24)

    if "n_comp" not in st.session_state: st.session_state.n_comp = 1
    
    comp_ativos = []
    cols = st.columns(st.session_state.n_comp)
    for i in range(st.session_state.n_comp):
        with cols[i]:
            t = st.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t1_{i}")
            e = st.number_input("% ou Taxa", value=100.0, key=f"e1_{i}")
            tx, isen = calcular_taxa_anual(t, selic_sim, cdi_sim, ipca_sim, e)
            comp_ativos.append({"nome": f"{t} #{i+1}", "tx": tx, "isen": isen, "t": t})
            
    if st.button("➕ Adicionar", key="add1"): st.session_state.n_comp += 1; st.rerun()
    if st.button("🚀 Simular Comparação", type="primary"):
        res = [simular(c_ini, c_apo, a["tx"], ipca_sim, c_mes, a["isen"]) for a in comp_ativos]
        fig = px.line(title="Evolução do Saldo Líquido")
        for i, r in enumerate(res): fig.add_scatter(x=r["Mês"], y=r["Saldo Líquido"], name=comp_ativos[i]["nome"])
        st.plotly_chart(fig, use_container_width=True)

# ABA 2: CARTEIRA CONJUNTA
with tab2:
    if "n_conj" not in st.session_state: st.session_state.n_conj = 1
    j_mes = st.slider("Prazo Global (meses)", 1, 360, 60)
    ativos_j = []
    for i in range(st.session_state.n_conj):
        with st.expander(f"Ativo {i+1}", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            t = c1.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t2_{i}")
            ini = c2.number_input("Ini", value=5000.0, key=f"i2_{i}")
            apo = c3.number_input("Apo", value=200.0, key=f"a2_{i}")
            e = c4.number_input("%", value=100.0, key=f"e2_{i}")
            tx, isen = calcular_taxa_anual(t, selic_sim, cdi_sim, ipca_sim, e)
            ativos_j.append({"ini": ini, "apo": apo, "tx": tx, "isen": isen})
            
    if st.button("➕ Adicionar", key="add2"): st.session_state.n_conj += 1; st.rerun()
    if st.button("🚀 Calcular Carteira", type="primary"):
        dfs = [simular(a["ini"], a["apo"], a["tx"], ipca_sim, j_mes, a["isen"]) for a in ativos_j]
        total = sum(d["Saldo Líquido"] for d in dfs)
        st.metric("Patrimônio Líquido Final", f"R$ {total.iloc[-1]:,.2f}")

# ABA 3: ALVOS
with tab3:
    v = st.number_input("Valor Total", value=100000.0)
    p = st.slider("% Pós-fixado", 0, 100, 50)
    st.plotly_chart(px.pie(names=["Pós", "Outros"], values=[p, 100-p]))
