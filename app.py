import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURAÇÕES E ESTILIZAÇÃO
# ==========================================
st.set_page_config(page_title="InvestSim Pro", layout="wide")

st.markdown("""
    <style>
    header { background-color: transparent !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] {display: none !important;}
    footer {display: none !important;}
    [data-testid="stAppDeployButton"] {display: none !important;}
    [data-testid="viewerBadge"] {display: none !important;}
    .header-anchor {display: none !important;}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. MOTOR FINANCEIRO (BACKEND)
# ==========================================
@st.cache_data(ttl=3600)
def buscar_indicadores():
    """Busca dados do Banco Central com tratamento de exceção específico."""
    try:
        req_selic = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json", timeout=5)
        req_ipca = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json", timeout=5)
        selic = float(req_selic.json()[0]['valor']) / 100
        ipca = float(req_ipca.json()[0]['valor']) / 100
    except (requests.exceptions.RequestException, ValueError, KeyError):
        selic, ipca = 0.1075, 0.0450
    return selic, (selic - 0.001), ipca

def calcular_taxa_anual(tipo, selic, cdi, ipca, extra=0.0):
    """Calcula a taxa bruta anual baseada no tipo de ativo."""
    if tipo == "Poupança":
        return (1.005**12 - 1) if selic > 0.085 else (selic * 0.7), True
    if tipo == "CDB":
        return cdi * (extra / 100), False
    if tipo == "LCI/LCA":
        return cdi * (extra / 100), True
    if tipo == "Tesouro Selic":
        return selic - 0.002, False
    if tipo == "Tesouro Prefixado":
        return (extra / 100) - 0.002, False
    if tipo == "Tesouro IPCA+":
        return (((1 + ipca) * (1 + extra / 100)) - 1) - 0.002, False
    return 0.0, False

def simular(v_ini, v_apo, tx_a, ipca_a, meses, isento):
    """Projeção financeira separando métricas nominais e reais."""
    tx_m = (1 + tx_a)**(1/12) - 1
    inf_m = (1 + ipca_a)**(1/12) - 1
    
    bruto, investido = v_ini, v_ini
    dados = []
    
    def get_ir(m):
        if isento: return 0.0
        if m < 6: return 0.225
        if m < 12: return 0.200
        if m < 24: return 0.175
        return 0.150

    for m in range(meses + 1):
        if m > 0:
            bruto = (bruto * (1 + tx_m)) + v_apo
            investido += v_apo
            
        fator_inflacao = (1 + inf_m)**m
        lucro = max(0, bruto - investido)
        ir_atual = lucro * get_ir(m if m > 0 else 1)
        
        liquido = bruto - ir_atual
        real_bruto = bruto / fator_inflacao if m > 0 else bruto
        real_liquido = liquido / fator_inflacao if m > 0 else liquido
        
        dados.append({
            "Mês": m,
            "Total Investido": investido,
            "Saldo Bruto": bruto,
            "IR Estimado": ir_atual,
            "Saldo Líquido": liquido,
            "Real Bruto": real_bruto,
            "Real Líquido": real_liquido
        })
    return pd.DataFrame(dados)

# ==========================================
# 3. INTERFACE (FRONTEND)
# ==========================================
selic_h, cdi_h, ipca_h = buscar_indicadores()

with st.sidebar:
    st.title("🌍 Cenário Global")
    cenario = st.selectbox("Ambiente Econômico", ["Atual", "Otimista (Juros ↑)", "Pessimista (Juros ↓)"])
    if cenario == "Otimista (Juros ↑)":
        s_s, i_s = selic_h + 0.02, max(0.02, ipca_h - 0.01)
    elif cenario == "Pessimista (Juros ↓)":
        s_s, i_s = max(0.05, selic_h - 0.04), ipca_h + 0.03
    else:
        s_s, i_s = selic_h, ipca_h
    c_s = s_s - 0.001
    st.info(f"Selic Base: {s_s*100:.2f}% | IPCA Base: {i_s*100:.2f}%")

st.title("🚀 InvestSim Pro")
tab1, tab2, tab3 = st.tabs(["📊 Comparador Direto", "🏗️ Carteira Conjunta", "🥧 Alocação Ideal"])

# --- ABA 1: COMPARADOR ---
with tab1:
    col_par1, col_par2, col_par3 = st.columns(3)
    c_ini = col_par1.number_input("Investimento Inicial (R$)", 0.0, 10000000.0, 10000.0, step=1000.0, key="c1")
    c_apo = col_par2.number_input("Aporte Mensal (R$)", 0.0, 1000000.0, 500.0, step=100.0, key="c2")
    c_mes = col_par3.slider("Prazo (Meses)", 1, 360, 24, key="c3")
    
    st.divider()
    
    if "n_comp" not in st.session_state: st.session_state.n_comp = 2
    
    comp_ativos = []
    cols_ativos = st.columns(st.session_state.n_comp)
    
    for i in range(st.session_state.n_comp):
        with cols_ativos[i]:
            st.subheader(f"Ativo {i+1}")
            t = st.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t1_{i}")
            ext = 0.0
            if t in ["CDB", "LCI/LCA"]: ext = st.number_input("% do CDI", 0.0, 300.0, 100.0, key=f"e1_{i}")
            elif t == "Tesouro Prefixado": ext = st.number_input("Taxa % a.a.", 0.0, 30.0, 10.5, key=f"e1_{i}")
            elif t == "Tesouro IPCA+": ext = st.number_input("Taxa Fixa %", 0.0, 15.0, 5.5, key=f"e1_{i}")
            
            tx, isen = calcular_taxa_anual(t, s_s, c_s, i_s, ext)
            comp_ativos.append({"nome": f"{t} #{i+1}", "taxa": tx, "isento": isen, "tipo": t, "extra": ext})

    c_b1, c_b2, _ = st.columns([1,1,4])
    if c_b1.button("➕ Adicionar", key="b1_add"): st.session_state.n_comp += 1; st.rerun()
    if c_b2.button("➖ Remover", key="b1_rem") and st.session_state.n_comp > 1: st.session_state.n_comp -= 1; st.rerun()

    if st.button("🚀 Simular Comparação", type="primary", width="stretch"):
        results = []
        for a in comp_ativos:
            df = simular(c_ini, c_apo, a["taxa"], i_s, c_mes, a["isento"])
            results.append({"nome": a["nome"], "tipo": a["tipo"], "extra": a["extra"], "df": df})
        
        # Resumo Numérico
        res_cols = st.columns(len(results))
        for i, r in enumerate(results):
            with res_cols[i]:
                ult = r["df"].iloc[-1]
                lucro_liq = ult["Saldo Líquido"] - ult["Total Investido"]
                st.metric(r["nome"], f"R$ {ult['Saldo Líquido']:,.2f}", f"Lucro Líquido: R$ {lucro_liq:,.2f}")
                
                if r["tipo"] == "LCI/LCA":
                    equiv = r["extra"] / (1 - (0.15 if c_mes >= 24 else (0.175 if c_mes >= 12 else 0.20)))
                    st.caption(f"💡 Equivale a um CDB de aprox. **{equiv:.1f}% do CDI** no vencimento.")
        
        fig_c = px.line(title="Evolução do Saldo Líquido")
        for r in results:
            fig_c.add_scatter(x=r["df"]["Mês"], y=r["df"]["Saldo Líquido"], name=r["nome"])
        st.plotly_chart(fig_c, use_container_width=True)

# --- ABA 2: CARTEIRA CONJUNTA ---
with tab2:
    st.header("🏗️ Construção de Patrimônio")
    col_j1, col_j2 = st.columns([2,1])
    j_mes = col_j1.slider("Prazo Global (Meses)", 1, 480, 60, key="j_mes")
    j_meta = col_j2.number_input("Meta Alvo (R$)", 0.0, value=100000.0, key="j_meta")
    
    if "n_conj" not in st.session_state: st.session_state.n_conj = 1
    
    ativos_j = []
    for i in range(st.session_state.n_conj):
        with st.expander(f"Ativo {i+1}", expanded=True):
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
            tipo = c1.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t2_{i}")
            v_i = c2.number_input("Inicial (R$)", 0.0, 10000000.0, 5000.0, key=f"v2_i{i}")
            v_a = c3.number_input("Aporte (R$)", 0.0, 1000000.0, 500.0, key=f"v2_a{i}")
            ex = 0.0
            if tipo in ["CDB", "LCI/LCA"]: ex = c4.number_input("% CDI", 0.0, 300.0, 100.0, key=f"v2_e{i}")
            elif tipo == "Tesouro Prefixado": ex = c4.number_input("Taxa %", 0.0, 30.0, 10.5, key=f"v2_e{i}")
            elif tipo == "Tesouro IPCA+": ex = c4.number_input("Fixa %", 0.0, 15.0, 5.5, key=f"v2_e{i}")
            
            tx, isen = calcular_taxa_anual(tipo, s_s, c_s, i_s, ex)
            ativos_j.append({"nome": f"{tipo} #{i+1}", "ini": v_i, "apo": v_a, "taxa": tx, "isento": isen})

    c_bj1, c_bj2, _ = st.columns([1,1,4])
    if c_bj1.button("➕ Adicionar", key="bj_add"): st.session_state.n_conj += 1; st.rerun()
    if c_bj2.button("➖ Remover", key="bj_rem") and st.session_state.n_conj > 1: st.session_state.n_conj -= 1; st.rerun()

    if st.button("🚀 Calcular Carteira", type="primary", width="stretch"):
        dfs = []
        finais = []
        for a in ativos_j:
            df = simular(a["ini"], a["apo"], a["taxa"], i_s, j_mes, a["isento"])
            dfs.append(df)
            finais.append({"Ativo": a["nome"], "Valor Final": df["Saldo Líquido"].iloc[-1]})
            
        df_total = pd.DataFrame({"Mês": dfs[0]["Mês"]})
        df_total["Saldo Líquido"] = sum(d["Saldo Líquido"] for d in dfs)
        df_total["Total Investido"] = sum(d["Total Investido"] for d in dfs)
        df_total["Real Líquido"] = sum(d["Real Líquido"] for d in dfs)
        
        # Proteção contra Divisão por Zero
        t_inv = df_total["Total Investido"].iloc[-1]
        t_liq = df_total["Saldo Líquido"].iloc[-1]
        lucro = t_liq - t_inv
        perc = (lucro / t_inv * 100) if t_inv > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Patrimônio Final (Líquido)", f"R$ {t_liq:,.2f}")
        m2.metric("Total Investido", f"R$ {t_inv:,.2f}")
        m3.metric("Lucro Líquido", f"R$ {lucro:,.2f}", f"{perc:.1f}%")
        
        if j_meta > 0:
            atingiu = df_total[df_total["Saldo Líquido"] >= j_meta]
            if not atingiu.empty:
                st.success(f"🎯 Meta atingida no Mês {atingiu.iloc[0]['Mês']}!")
        
        # Gráficos da Carteira
        g_col1, g_col2 = st.columns([2, 1])
        with g_col1:
            fig_j = px.area(df_total, x="Mês", y=["Saldo Líquido", "Total Investido", "Real Líquido"], 
                            title="Acumulação Nominal vs Real")
            st.plotly_chart(fig_j, use_container_width=True)
            
        with g_col2:
            df_pizza_final = pd.DataFrame(finais)
            fig_pizza_f = px.pie(df_pizza_final, values="Valor Final", names="Ativo", title="Composição Final", hole=0.4)
            st.plotly_chart(fig_pizza_f, use_container_width=True)
        
        with st.expander("📄 Extrato Detalhado da Carteira"):
            st.dataframe(df_total.set_index("Mês"), use_container_width=True)

# --- ABA 3: ALVOS (PIZZA) ---
with tab3:
    st.header("🥧 Alocação Sugerida")
    val_t = st.number_input("Capital para Alocar (R$)", 0.0, 100000000.0, 50000.0)
    
    col_p1, col_p2 = st.columns(2)
    p_pos = col_p1.slider("% Pós-Fixado (Liquidez)", 0, 100, 50)
    p_inf = col_p2.slider("% Inflação/Pre (Longo Prazo)", 0, 100 - p_pos, 30)
    p_res = 100 - p_pos - p_inf
    st.metric("Reserva / Outros", f"{p_res}%")
    
    df_p = pd.DataFrame({"Categoria": ["Pós-Fixado", "Atrelado à Inflação / Prefixado", "Reserva"], 
                         "Valor": [val_t * (p_pos/100), val_t * (p_inf/100), val_t * (p_res/100)]})
    st.plotly_chart(px.pie(df_p, names="Categoria", values="Valor", hole=0.4), use_container_width=True)
