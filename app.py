import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO DE INTERFACE E CSS
# ==========================================
st.set_page_config(page_title="InvestSim Pro", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    header { background-color: transparent !important; }
    [data-testid="stToolbar"] { display: none !important; }
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
# 1. BACKEND: TAXAS E CALCULADORA
# ==========================================

@st.cache_data(ttl=3600)
def buscar_indicadores_mercado():
    """Busca Selic e IPCA das APIs do Banco Central com Fallback seguro."""
    try:
        # Selic (SGS 432)
        r_selic = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json", timeout=5)
        selic = float(r_selic.json()[0]['valor']) / 100
        # IPCA (SGS 13522)
        r_ipca = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json", timeout=5)
        ipca = float(r_ipca.json()[0]['valor']) / 100
    except (requests.exceptions.RequestException, ValueError, KeyError):
        # Fallback caso a API do BC falhe ou demore
        selic, ipca = 0.1075, 0.0450 
    
    return selic, (selic - 0.0010), ipca

def calcular_ir_renda_fixa(meses):
    """Retorna a alíquota de IR baseada na tabela regressiva brasileira."""
    if meses < 6: return 0.225
    if meses < 12: return 0.200
    if meses < 24: return 0.175
    return 0.150

def definir_logica_ativo(tipo, selic, cdi, ipca, param_adicional=0.0):
    """Centraliza a inteligência de taxas de todos os produtos de Renda Fixa."""
    taxa_anual = 0.0
    isento = False
    
    if tipo == "Poupança":
        taxa_anual = (1.005**12 - 1) if selic > 0.085 else (selic * 0.7)
        isento = True
    elif tipo == "CDB":
        taxa_anual = cdi * (param_adicional / 100)
        isento = False
    elif tipo == "LCI/LCA":
        taxa_anual = cdi * (param_adicional / 100)
        isento = True
    elif tipo == "Tesouro Selic":
        taxa_anual = selic - 0.0020 # Taxa B3
        isento = False
    elif tipo == "Tesouro Prefixado":
        taxa_anual = (param_adicional / 100) - 0.0020 # Taxa B3
        isento = False
    elif tipo == "Tesouro IPCA+":
        taxa_anual = (((1 + ipca) * (1 + (param_adicional / 100))) - 1) - 0.0020
        isento = False
        
    return taxa_anual, isento

def executar_simulacao(capital_ini, aporte_mes, taxa_anual, ipca_anual, meses, isento):
    """Simulador core com IR aplicado apenas no resgate final (Precisão Financeira)."""
    t_mensal = (1 + taxa_anual)**(1/12) - 1
    i_mensal = (1 + ipca_anual)**(1/12) - 1
    
    saldo_bruto = capital_ini
    saldo_real = capital_ini
    investido_total = capital_ini
    dados = []
    
    for m in range(meses + 1):
        if m > 0:
            saldo_bruto = (saldo_bruto * (1 + t_mensal)) + aporte_mes
            investido_total += aporte_mes
            # Saldo Real (ajustado pela inflação no tempo)
            saldo_real = (saldo_real * (1 + t_mensal) / (1 + i_mensal)) + (aporte_mes / (1 + i_mensal)**m)

        lucro_bruto = max(0, saldo_bruto - investido_total)
        aliq_ir = 0 if isento else calcular_ir_renda_fixa(m if m > 0 else 1)
        imposto_estimado = lucro_bruto * aliq_ir
        saldo_liquido = saldo_bruto - imposto_estimado
        
        dados.append({
            "Mês": m,
            "Total Investido": round(investido_total, 2),
            "Saldo Bruto": round(saldo_bruto, 2),
            "IR Estimado": round(imposto_estimado, 2),
            "Saldo Líquido": round(saldo_liquido, 2),
            "Poder de Compra (Real)": round(saldo_real - (imposto_estimado / (1 + i_mensal)**m), 2)
        })
        
    return pd.DataFrame(dados)

# ==========================================
# 2. INTERFACE E ESTADO
# ==========================================
selic_hoje, cdi_hoje, ipca_hoje = buscar_indicadores_mercado()

if "n_comp" not in st.session_state: st.session_state.n_comp = 1
if "n_conj" not in st.session_state: st.session_state.n_conj = 1

st.title("🚀 InvestSim Pro")
st.caption("Simulador de Renda Fixa com Precisão Institucional e Teste de Estresse.")

# --- SIDEBAR: CENÁRIOS ---
with st.sidebar:
    st.header("🌍 Cenário Econômico")
    cenario = st.radio("Ambiente", ["Atual", "Otimista (Juros ↑)", "Pessimista (Juros ↓)"])
    
    if cenario == "Otimista (Juros ↑)":
        s_sim, i_sim = selic_hoje + 0.02, max(0.03, ipca_hoje - 0.01)
    elif cenario == "Pessimista (Juros ↓)":
        s_sim, i_sim = max(0.06, selic_hoje - 0.03), ipca_hoje + 0.03
    else:
        s_sim, i_sim = selic_hoje, ipca_hoje
    
    c_sim = s_sim - 0.001
    st.info(f"Selic: {s_sim*100:.2f}% | IPCA: {i_sim*100:.2f}%")

aba1, aba2, aba3 = st.tabs(["📊 Comparador", "🏗️ Carteira Conjunta", "🥧 Alvos"])

# ==========================================
# ABA 1: COMPARADOR
# ==========================================
with aba1:
    with st.sidebar:
        st.divider()
        st.header("⚙️ Config. Comparador")
        ini_c = st.number_input("Investimento Inicial", 0.0, value=10000.0, step=1000.0, key="c_ini")
        apo_c = st.number_input("Aporte Mensal", 0.0, value=500.0, step=100.0, key="c_apo")
        mes_c = st.slider("Prazo (Meses)", 1, 120, 24, key="c_mes")
        
        ativos_c = []
        for i in range(st.session_state.n_comp):
            st.subheader(f"Ativo {i+1}")
            tipo = st.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t_c{i}")
            
            p_adicional = 0.0
            if tipo in ["CDB", "LCI/LCA"]:
                p_adicional = st.number_input("% do CDI", 0.0, value=100.0, key=f"p_c{i}")
            elif tipo == "Tesouro Prefixado":
                p_adicional = st.number_input("Taxa % a.a.", 0.0, value=11.5, key=f"p_c{i}")
            elif tipo == "Tesouro IPCA+":
                p_adicional = st.number_input("Taxa Fixa %", 0.0, value=6.0, key=f"p_c{i}")
                
            taxa, isento = definir_logica_ativo(tipo, s_sim, c_sim, i_sim, p_adicional)
            ativos_c.append({"nome": f"{tipo} ({i+1})", "tipo": tipo, "taxa": taxa, "isento": isento, "param": p_adicional})

        col1, col2 = st.columns(2)
        if col1.button("➕ Ativo", width="stretch"): st.session_state.n_comp += 1; st.rerun()
        if col2.button("➖ Ativo", width="stretch") and st.session_state.n_comp > 1: st.session_state.n_comp -= 1; st.rerun()

    if st.sidebar.button("🚀 Simular Agora", type="primary", width="stretch"):
        res_c = []
        for a in ativos_c:
            df = executar_simulacao(ini_c, apo_c, a["taxa"], i_sim, mes_c, a["isento"])
            res_c.append({"nome": a["nome"], "tipo": a["tipo"], "df": df, "param": a["param"]})
        
        # Cards de Resultado
        cols = st.columns(len(res_c))
        for i, r in enumerate(res_c):
            with cols[i]:
                final = r["df"].iloc[-1]
                st.metric(r["nome"], f"R$ {final['Saldo Líquido']:,.2f}")
                if r["tipo"] == "LCI/LCA":
                    equiv = r["param"] / (1 - calcular_ir_renda_fixa(mes_c))
                    st.caption(f"💡 Equivale a CDB {equiv:.1f}% CDI")
        
        # Gráfico
        plot_df = pd.DataFrame({"Mês": res_c[0]["df"]["Mês"]})
        for r in res_c: plot_df[r["nome"]] = r["df"]["Saldo Líquido"]
        st.plotly_chart(px.line(plot_df, x="Mês", y=plot_df.columns[1:], title="Evolução do Saldo Líquido"), use_container_width=True)
        
        with st.expander("📄 Extrato Mês a Mês"):
            st.dataframe(res_c[0]["df"], use_container_width=True)
    else:
        st.write("Aguardando simulação...")

# ==========================================
# ABA 2: CARTEIRA CONJUNTA
# ==========================================
with aba2:
    st.header("🏗️ Composição da Carteira")
    prazo_j = st.slider("Prazo Global (Meses)", 1, 240, 36)
    meta_j = st.number_input("Meta de Patrimônio (R$)", 0.0, value=100000.0)
    
    ativos_j = []
    for i in range(st.session_state.n_conj):
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
        tipo = c1.selectbox("Tipo", ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"], key=f"t_j{i}")
        v_ini = c2.number_input("Inicial", 0.0, value=10000.0, key=f"v_j{i}")
        v_apo = c3.number_input("Aporte", 0.0, value=1000.0, key=f"a_j{i}")
        
        p_ad = 0.0
        if tipo in ["CDB", "LCI/LCA"]: p_ad = c4.number_input("% CDI", 0.0, value=100.0, key=f"p_j{i}")
        elif tipo == "Tesouro Prefixado": p_ad = c4.number_input("Taxa %", 0.0, value=11.0, key=f"p_j{i}")
        elif tipo == "Tesouro IPCA+": p_ad = c4.number_input("Fixa %", 0.0, value=6.0, key=f"p_j{i}")
        else: c4.write("---")
        
        tx, isen = definir_logica_ativo(tipo, s_sim, c_sim, i_sim, p_ad)
        ativos_j.append({"ini": v_ini, "apo": v_apo, "taxa": tx, "isento": isen})

    col_j1, col_j2 = st.columns([1, 5])
    if col_j1.button("➕ Ativo", key="add_j", width="stretch"): st.session_state.n_conj += 1; st.rerun()
    
    if st.button("🚀 Calcular Patrimônio Total", type="primary", width="stretch"):
        dfs_j = [executar_simulacao(a["ini"], a["apo"], a["taxa"], i_sim, prazo_j, a["isento"]) for a in ativos_j]
        
        df_total = pd.DataFrame({"Mês": dfs_j[0]["Mês"]})
        df_total["Investido"] = sum(d["Total Investido"] for d in dfs_j)
        df_total["Líquido"] = sum(d["Saldo Líquido"] for d in dfs_j)
        
        # Dashboard
        m1, m2, m3 = st.columns(3)
        f_liq = df_total["Líquido"].iloc[-1]
        f_inv = df_total["Investido"].iloc[-1]
        m1.metric("Saldo Líquido Final", f"R$ {f_liq:,.2f}")
        m2.metric("Total Investido", f"R$ {f_inv:,.2f}")
        m3.metric("Lucro Líquido", f"R$ {f_liq - f_inv:,.2f}", f"{( (f_liq/f_inv)-1)*100:.1f}%")
        
        # Meta Radar
        if meta_j > 0:
            atingiu = df_total[df_total["Líquido"] >= meta_j]
            if not atingiu.empty:
                st.success(f"🎯 Meta de R$ {meta_j:,.2f} atingida no **Mês {atingiu.iloc[0]['Mês']}**!")
        
        fig_j = px.area(df_total, x="Mês", y=["Líquido", "Investido"], title="Acúmulo de Patrimônio")
        if meta_j > 0: fig_j.add_hline(y=meta_j, line_dash="dash", line_color="green")
        st.plotly_chart(fig_j, use_container_width=True)

# ==========================================
# ABA 3: ALVOS (CARTEIRA IDEAL)
# ==========================================
with aba3:
    st.header("🥧 Alocação Sugerida")
    total_inv = st.number_input("Capital para Alocar", 0.0, value=50000.0)
    
    c1, c2 = st.columns(2)
    p_rf = c1.slider("% Renda Fixa Pós (Liquidez)", 0, 100, 40)
    p_pre = c2.slider("% Prefixados/IPCA+ (Longo Prazo)", 0, 100 - p_rf, 30)
    p_outros = 100 - p_rf - p_pre
    
    df_pizza = pd.DataFrame({
        "Categoria": ["Pós-Fixado", "Inflação/Pre", "Reserva/Outros"],
        "Valor": [total_inv * (p_rf/100), total_inv * (p_pre/100), total_inv * (p_outros/100)]
    })
    st.plotly_chart(px.pie(df_pizza, values="Valor", names="Categoria", hole=0.5))
