import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DE LAYOUT E CSS (Limpeza Total) ---
st.set_page_config(page_title="InvestSim - Pro", layout="wide")

esconder_menu = """
    <style>
    /* 1. A GUILHOTINA: Corta a direita do cabeçalho para manter só a seta */
    header { clip-path: inset(0 80% 0 0) !important; }
    
    /* 2. Remove decoração e rodapé */
    [data-testid="stDecoration"] {display: none !important;}
    footer {display: none !important;}
    [data-testid="stAppDeployButton"] {display: none !important;}
    [data-testid="viewerBadge"] {display: none !important;}
    .viewerBadge_container {display: none !important;}
    
    /* 3. EXTERMINADOR DE LINKS: Remove os ícones de corrente (#) */
    .header-anchor {display: none !important;}
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
    </style>
    """
st.markdown(esconder_menu, unsafe_allow_html=True)

# ==========================================
# 1. FUNÇÕES DE BACKEND (MATEMÁTICA)
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
    # Ajuste de mercado: 12 meses = 17.5% / 24 meses = 15%
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
        aliquota_atual = 0 if isento_ir else obter_aliquota_ir(mes if mes > 0 else 1)
        imposto_parcial = lucro_parcial * aliquota_atual
        historico.append({
            "Mês": mes,
            "Total Investido": round(total_investido, 2),
            "Saldo Líquido": round(saldo_atual - imposto_parcial, 2),
            "Poder de Compra (Real)": round(saldo_real - imposto_parcial, 2)
        })
    
    lucro_bruto_final = saldo_atual - total_investido
    aliquota_final = 0 if isento_ir else obter_aliquota_ir(meses)
    imposto_final = lucro_bruto_final * aliquota_final
    return pd.DataFrame(historico), total_investido, (saldo_atual - imposto_final), imposto_final, aliquota_final

# ==========================================
# 2. GESTÃO DE ESTADO (BOTÕES DINÂMICOS)
# ==========================================

if "num_ativos" not in st.session_state:
    st.session_state["num_ativos"] = 1

def adicionar_ativo():
    st.session_state["num_ativos"] += 1

def remover_ativo():
    if st.session_state["num_ativos"] > 1:
        st.session_state["num_ativos"] -= 1

# ==========================================
# 3. INTERFACE PRINCIPAL
# ==========================================

st.title("🚀 InvestSim Pro: Simulador e Carteira")
selic, cdi, ipca = obter_taxas_atuais()
st.info(f"**Taxas Oficiais Atualizadas:** Selic: **{selic*100:.2f}% a.a.** | CDI: **{cdi*100:.2f}% a.a.** | IPCA (12m): **{ipca*100:.2f}%**")

# BARRA LATERAL
st.sidebar.header("💰 Configurações Gerais")
cap_inicial = st.sidebar.number_input("Investimento Inicial (R$)", value=1000.0, step=100.0)
aporte = st.sidebar.number_input("Aporte Mensal (R$)", value=500.0, step=100.0)
meses = st.sidebar.slider("Prazo (Meses)", 1, 120, 24)

def menu_ativo(n):
    st.sidebar.markdown(f"### Ativo {n}")
    tipo = st.sidebar.selectbox(f"Tipo", ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], key=f"t{n}")
    taxa = 0.0
    isento = False
    if tipo == "Poupança":
        taxa = (1.005**12-1) if selic > 0.085 else (selic*0.7)
        isento = True
    elif tipo in ["CDB", "LCI/LCA"]:
        perc = st.sidebar.number_input("% do CDI", value=100.0, step=1.0, key=f"p{n}")
        taxa = cdi * (perc/100)
        isento = (tipo == "LCI/LCA")
    elif tipo == "Tesouro Selic": taxa = selic
    elif tipo == "Tesouro Prefixado":
        t_pre = st.sidebar.number_input("Taxa Prefixada (% a.a.)", value=10.5, step=0.1, key=f"pre{n}")
        taxa = t_pre / 100
    elif tipo == "Tesouro IPCA+":
        t_fixa = st.sidebar.number_input("Taxa Fixa + IPCA (% a.a.)", value=5.5, step=0.1, key=f"ipca{n}")
        taxa = ((1 + ipca) * (1 + (t_fixa / 100))) - 1
    return f"{tipo} {n}", taxa, isento

ativos_configurados = []
for i in range(1, st.session_state["num_ativos"] + 1):
    st.sidebar.divider()
    n_at, t_at, i_at = menu_ativo(i)
    ativos_configurados.append({"nome": n_at, "taxa": t_at, "isento": i_at})

st.sidebar.divider()

# BOTÕES DE ADICIONAR E REMOVER LADO A LADO
col_add, col_rem = st.sidebar.columns(2)
with col_add:
    st.button("➕ Adicionar", on_click=adicionar_ativo, use_container_width=True)
with col_rem:
    # O botão de remover só aparece se houver mais de 1 ativo
    if st.session_state["num_ativos"] > 1:
        st.button("➖ Remover", on_click=remover_ativo, use_container_width=True)

btn_simular = st.sidebar.button("🚀 Simular Investimento", type="primary", use_container_width=True)

# RESULTADOS
aba_simulador, aba_carteira = st.tabs(["📊 Simulador", "🥧 Distribuição de Carteira"])

with aba_simulador:
    if btn_simular:
        resultados = []
        for cfg in ativos_configurados:
            df, total, liq, imp, aliq = simular_evolucao(cap_inicial, aporte, cfg["taxa"], ipca, meses, cfg["isento"])
            resultados.append({"nome": cfg["nome"], "df": df, "total": total, "liquido": liq, "imposto": imp, "aliquota": aliq})
        
        st.success(f"**Total Investido (Aportes):** R$ {resultados[0]['total']:,.2f}")
        col_res = st.columns(len(resultados))
        for idx, res in enumerate(resultados):
            with col_res[idx]:
                st.subheader(res["nome"])
                g_real = res['df']['Poder de Compra (Real)'].iloc[-1] - res['total']
                st.metric("Resgate Líquido", f"R$ {res['liquido']:,.2f}", f"Ganho Real: R$ {g_real:,.2f}")
                if res['aliquota'] == 0: st.info("🟢 **Isento de IR**")
                else: st.warning(f"🔴 **IR Retido:** R$ {res['imposto']:,.2f} ({res['aliquota']*100:.1f}%)")

        chart_data = pd.DataFrame({"Mês": resultados[0]['df']["Mês"]}).set_index("Mês")
        chart_data["Seu Dinheiro"] = resultados[0]['df']["Total Investido"]
        for res in resultados: chart_data[res["nome"]] = res['df']["Poder de Compra (Real)"]
        st.line_chart(chart_data)
    else: st.write("👈 Configure e clique em **Simular**.")

with aba_carteira:
    st.subheader("Planeja a sua Carteira Ideal")
    pat_total = st.number_input("Patrimônio Total (R$)", value=50000.0, step=1000.0)
    c_p1, c_p2, c_p3 = st.columns(3)
    p_cdb = c_p1.slider("Renda Fixa", 0, 100, 50)
    max_lci = 100 - p_cdb
    if max_lci > 0: p_lci = c_p2.slider("Isentos", 0, max_lci, 30 if max_lci >= 30 else max_lci)
    else: p_lci = c_p2.slider("Isentos", 0, 100, 0, disabled=True)
    p_caixa = 100 - p_cdb - p_lci
    c_p3.metric("Reserva de Emergência", f"{p_caixa}%")
    
    dados_c = pd.DataFrame({"Tipo": ["Renda Fixa", "LCI/LCA", "Reserva"], "Valor": [pat_total*(p_cdb/100), pat_total*(p_lci/100), pat_total*(p_caixa/100)]})
    cg, ct = st.columns([2, 1])
    with cg:
        fig = px.pie(dados_c, values='Valor', names='Tipo', hole=0.4, color_discrete_sequence=['#3b82f6', '#10b981', '#f59e0b'])
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
    with ct:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.dataframe(dados_c.style.format({"Valor": "R$ {:,.2f}"}), hide_index=True)
