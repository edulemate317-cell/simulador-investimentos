import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DE LAYOUT E CSS (Guilhotina e Limpeza) ---
st.set_page_config(page_title="InvestSim - Pro", layout="wide")

st.markdown("""
    <style>
    header { clip-path: inset(0 80% 0 0) !important; }
    [data-testid="stDecoration"] {display: none !important;}
    footer {display: none !important;}
    [data-testid="stAppDeployButton"] {display: none !important;}
    [data-testid="viewerBadge"] {display: none !important;}
    .viewerBadge_container {display: none !important;}
    .header-anchor {display: none !important;}
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 1. FUNÇÕES DE BACKEND
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
    except: return 0.1175, 0.1165, 0.0450 

def obter_aliquota_ir(meses):
    if meses < 6: return 0.225
    elif meses < 12: return 0.200
    elif meses < 24: return 0.175
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
        aliq = 0 if isento_ir else obter_aliquota_ir(mes if mes > 0 else 1)
        historico.append({
            "Mês": mes,
            "Investido": total_investido,
            "Líquido": saldo_atual - (lucro_parcial * aliq),
            "Real": saldo_real - (lucro_parcial * aliq)
        })
    
    lucro_final = saldo_atual - total_investido
    aliq_f = 0 if isento_ir else obter_aliquota_ir(meses)
    return pd.DataFrame(historico), total_investido, (saldo_atual - (lucro_final * aliq_f)), (lucro_final * aliq_f), aliq_f

# ==========================================
# 2. GESTÃO DE ESTADO
# ==========================================
if "num_ativos_comp" not in st.session_state: st.session_state["num_ativos_comp"] = 1
if "num_ativos_conj" not in st.session_state: st.session_state["num_ativos_conj"] = 1

# ==========================================
# 3. INTERFACE
# ==========================================
st.title("🚀 InvestSim Pro: Inteligência Financeira")
selic, cdi, ipca = obter_taxas_atuais()
st.info(f"**Taxas Atuais:** Selic: {selic*100:.2f}% | CDI: {cdi*100:.2f}% | IPCA: {ipca*100:.2f}%")

aba_comp, aba_conj, aba_ideal = st.tabs(["📊 Comparador Direto", "🏗️ Construção de Patrimônio", "🥧 Alvos de Carteira"])

# --- ABA 1: COMPARADOR (DINHEIRO IGUAL PARA TODOS) ---
with aba_comp:
    st.sidebar.header("⚙️ Configurações do Comparador")
    c_ini = st.sidebar.number_input("Investimento Inicial (R$)", value=1000.0, step=100.0, key="ini_c")
    c_apo = st.sidebar.number_input("Aporte Mensal (R$)", value=500.0, step=100.0, key="apo_c")
    c_mes = st.sidebar.slider("Prazo (Meses)", 1, 120, 24, key="mes_c")

    def input_ativo_comp(n):
        st.sidebar.subheader(f"Ativo {n}")
        t = st.sidebar.selectbox("Tipo", ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], key=f"tc{n}")
        tx = 0.0; isen = False
        if t == "Poupança": tx = (1.005**12-1) if selic > 0.085 else (selic*0.7); isen = True
        elif t in ["CDB", "LCI/LCA"]:
            p = st.sidebar.number_input("% do CDI", min_value=0.0, value=100.0, step=1.0, key=f"pc{n}")
            tx = cdi*(p/100)
            isen = (t == "LCI/LCA")
        elif t == "Tesouro Selic": tx = selic
        elif t == "Tesouro Prefixado": 
            p = st.sidebar.number_input("Taxa % a.a.", min_value=0.0, value=10.5, step=0.1, key=f"pre_c{n}")
            tx = p/100
        elif t == "Tesouro IPCA+": 
            p = st.sidebar.number_input("Taxa Fixa %", min_value=0.0, value=5.5, step=0.1, key=f"ipca_c{n}")
            tx = ((1+ipca)*(1+(p/100)))-1
        return {"nome": f"{t} {n}", "taxa": tx, "isento": isen}

    configs_comp = [input_ativo_comp(i+1) for i in range(st.session_state["num_ativos_comp"])]
    
    col_a, col_r = st.sidebar.columns(2)
    if col_a.button("➕ Ativo", key="add_c"): st.session_state["num_ativos_comp"] += 1; st.rerun()
    if col_r.button("➖ Ativo", key="rem_c") and st.session_state["num_ativos_comp"] > 1: st.session_state["num_ativos_comp"] -= 1; st.rerun()
    
    if st.sidebar.button("🚀 Simular Comparação", type="primary", use_container_width=True):
        res_comp = []
        for c in configs_comp:
            df, tot, liq, imp, ali = simular_evolucao(c_ini, c_apo, c["taxa"], ipca, c_mes, c["isento"])
            res_comp.append({"nome": c["nome"], "df": df, "total": tot, "liq": liq, "imp": imp, "ali": ali})
        
        st.subheader(f"Resultado da Comparação ({c_mes} meses)")
        cols = st.columns(len(res_comp))
        for i, r in enumerate(res_comp):
            with cols[i]:
                st.metric(r["nome"], f"R$ {r['liq']:,.2f}")
                st.caption(f"IR: R$ {r['imp']:,.2f} ({r['ali']*100:.1f}%)")
        
        c_data = pd.DataFrame({"Mês": res_comp[0]["df"]["Mês"]}).set_index("Mês")
        for r in res_comp: c_data[r["nome"]] = r["df"]["Líquido"]
        st.line_chart(c_data)

# --- ABA 2: CONSTRUÇÃO DE PATRIMÔNIO (DINHEIRO DIFERENTE EM CADA UM) ---
with aba_conj:
    st.subheader("🏗️ Simulador de Rendimento Conjunto")
    st.write("Aqui você define valores diferentes para cada investimento e vê o resultado somado.")
    
    p_meses = st.slider("Prazo Global (Meses)", 1, 120, 24, key="mes_conj")
    
    def row_ativo_conj(n):
        st.markdown(f"**Investimento {n}**")
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
        t = c1.selectbox("Tipo de Ativo", ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], key=f"tj{n}")
        ini = c2.number_input("Incial (R$)", 0.0, step=1000.0, value=5000.0, key=f"ij{n}")
        apo = c3.number_input("Aporte (R$)", 0.0, step=100.0, value=200.0, key=f"aj{n}")
        
        tx = 0.0; isen = False
        if t == "Poupança": tx = (1.005**12-1) if selic > 0.085 else (selic*0.7); isen = True
        elif t in ["CDB", "LCI/LCA"]:
            p = c4.number_input("% CDI", min_value=0.0, value=100.0, step=1.0, key=f"pj{n}")
            tx = cdi*(p/100)
            isen = (t == "LCI/LCA")
        elif t == "Tesouro Selic": tx = selic; c4.write(f"Selic")
       elif t == "Tesouro Prefixado": 
            p = c4.number_input("% a.a.", min_value=0.0, value=10.5, step=0.1, key=f"prej{n}")
            tx = p/100
        elif t == "Tesouro IPCA+": 
            p = c4.number_input("Taxa Fixa", min_value=0.0, value=5.5, step=0.1, key=f"ipcaj{n}")
            tx = ((1+ipca)*(1+(p/100)))-1
        
        return {"ini": ini, "apo": apo, "taxa": tx, "isento": isen, "nome": f"{t}"}

    configs_conj = [row_ativo_conj(i+1) for i in range(st.session_state["num_ativos_conj"])]
    
    c_b1, c_b2, _ = st.columns([1,1,2])
    if c_b1.button("➕ Adicionar Ativo", key="btn_add_j"): st.session_state["num_ativos_conj"] += 1; st.rerun()
    if c_b2.button("➖ Remover Ativo", key="btn_rem_j") and st.session_state["num_ativos_conj"] > 1: st.session_state["num_ativos_conj"] -= 1; st.rerun()

    if st.button("🚀 Calcular Patrimônio Conjunto", type="primary", use_container_width=True):
        all_dfs = []
        total_final = 0; total_inv = 0; total_imp = 0
        
        for c in configs_conj:
            df, inv, liq, imp, ali = simular_evolucao(c["ini"], c["apo"], c["taxa"], ipca, p_meses, c["isento"])
            all_dfs.append(df)
            total_final += liq
            total_inv += inv
            total_imp += imp
            
        # Soma os resultados mês a mês
        df_sum = all_dfs[0][["Mês"]].copy()
        df_sum["Total Líquido"] = sum(d["Líquido"] for d in all_dfs)
        df_sum["Total Investido"] = sum(d["Investido"] for d in all_dfs)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investido", f"R$ {total_inv:,.2f}")
        c2.metric("Patrimônio Líquido Final", f"R$ {total_final:,.2f}", f"Lucro: R$ {total_final-total_inv:,.2f}")
        c3.metric("Imposto Total", f"R$ {total_imp:,.2f}")
        
        st.subheader("Evolução do Patrimônio Total Somado")
        st.area_chart(df_sum.set_index("Mês"))

        # Botão de Exportar
        csv = df_sum.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Baixar Dados da Carteira (Excel)", csv, "carteira_conjunta.csv", "text/csv", use_container_width=True)

# --- ABA 3: ALVOS (CARTEIRA IDEAL) ---
with aba_ideal:
    st.subheader("🥧 Definição de Alvos da Carteira")
    pat_t = st.number_input("Capital Total", 0.0, step=1000.0, value=50000.0, key="pat_i")
    col1, col2, col3 = st.columns(3)
    p1 = col1.slider("Renda Fixa", 0, 100, 50)
    max2 = 100 - p1
    p2 = col2.slider("Isentos", 0, max2, 30 if max2 >= 30 else max2)
    p3 = 100 - p1 - p2
    col3.metric("Reserva", f"{p3}%")
    
    df_pie = pd.DataFrame({"Tipo": ["Renda Fixa", "LCI/LCA", "Reserva"], "Valor": [pat_t*p1/100, pat_t*p2/100, pat_t*p3/100]})
    fig = px.pie(df_pie, values='Valor', names='Tipo', hole=0.4, color_discrete_sequence=['#3b82f6', '#10b981', '#f59e0b'])
    st.plotly_chart(fig, use_container_width=True)
