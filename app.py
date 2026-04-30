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
    [data-testid="stDecoration"] { display: none !important; }
    footer { display: none !important; }
    [data-testid="stAppDeployButton"] { display: none !important; }
    [data-testid="viewerBadge"] { display: none !important; }
    .header-anchor { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. MOTOR FINANCEIRO
# ==========================================

@st.cache_data(ttl=3600)
def buscar_indicadores():
    try:
        url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        url_ipca = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"

        r_selic = requests.get(url_selic, timeout=5)
        r_ipca = requests.get(url_ipca, timeout=5)

        r_selic.raise_for_status()
        r_ipca.raise_for_status()

        selic = float(r_selic.json()[0]["valor"]) / 100
        ipca = float(r_ipca.json()[0]["valor"]) / 100

    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError):
        selic, ipca = 0.1075, 0.0450

    cdi = selic - 0.001
    return selic, cdi, ipca

def calcular_taxa_anual(tipo, selic, cdi, ipca, extra=0.0):
    if tipo == "Poupança":
        taxa = (1.005**12 - 1) if selic > 0.085 else (selic * 0.7)
        return taxa, True

    if tipo == "CDB":
        return cdi * (extra / 100), False

    if tipo == "LCI/LCA":
        return cdi * (extra / 100), True

    if tipo == "Tesouro Selic":
        return max(0.0, selic - 0.002), False

    if tipo == "Tesouro Prefixado":
        return max(0.0, (extra / 100) - 0.002), False

    if tipo == "Tesouro IPCA+":
        return max(0.0, (((1 + ipca) * (1 + extra / 100)) - 1) - 0.002), False

    return 0.0, False

def aliquota_ir(meses):
    if meses < 6:
        return 0.225
    if meses < 12:
        return 0.200
    if meses < 24:
        return 0.175
    return 0.150

def simular(v_ini, v_apo, tx_a, ipca_a, meses, isento):
    tx_m = (1 + tx_a) ** (1 / 12) - 1
    inf_m = (1 + ipca_a) ** (1 / 12) - 1

    bruto = v_ini
    real_bruto = v_ini
    investido = v_ini
    dados = []

    for m in range(meses + 1):
        if m > 0:
            bruto = (bruto * (1 + tx_m)) + v_apo
            investido += v_apo
            real_bruto = (real_bruto * (1 + tx_m) / (1 + inf_m)) + (v_apo / ((1 + inf_m) ** m))

        lucro = max(0, bruto - investido)
        ir = 0.0 if isento else lucro * aliquota_ir(m)
        liquido = bruto - ir
        real_liquido = real_bruto - (ir / ((1 + inf_m) ** m))

        dados.append({
            "Mês": m,
            "Investido": round(investido, 2),
            "Saldo Bruto": round(bruto, 2),
            "IR Estimado": round(ir, 2),
            "Saldo Líquido": round(liquido, 2),
            "Saldo Real Bruto": round(real_bruto, 2),
            "Saldo Real Líquido": round(real_liquido, 2),
        })

    return pd.DataFrame(dados)

# ==========================================
# 3. INTERFACE
# ==========================================
selic_h, cdi_h, ipca_h = buscar_indicadores()

if "n_comp" not in st.session_state:
    st.session_state.n_comp = 2

if "n_conj" not in st.session_state:
    st.session_state.n_conj = 1

st.title("🚀 InvestSim Pro")
st.caption("Simulador de Renda Fixa com projeção nominal e real.")

with st.sidebar:
    st.header("🌍 Cenário Econômico")
    cenario = st.selectbox("Cenário", ["Atual", "Otimista (Juros ↑)", "Pessimista (Juros ↓)"])

    if cenario == "Otimista (Juros ↑)":
        selic_sim = selic_h + 0.02
        ipca_sim = max(0.02, ipca_h - 0.01)
    elif cenario == "Pessimista (Juros ↓)":
        selic_sim = max(0.05, selic_h - 0.04)
        ipca_sim = ipca_h + 0.03
    else:
        selic_sim = selic_h
        ipca_sim = ipca_h

    cdi_sim = selic_sim - 0.001
    st.info(f"Selic: {selic_sim*100:.2f}% | CDI: {cdi_sim*100:.2f}% | IPCA: {ipca_sim*100:.2f}%")

tab1, tab2, tab3 = st.tabs(["📊 Comparador", "🏗️ Carteira Conjunta", "🥧 Alvos"])

# ==========================================
# ABA 1: COMPARADOR
# ==========================================
with tab1:
    st.subheader("Comparador de ativos")

    col1, col2, col3 = st.columns(3)
    c_ini = col1.number_input("Investimento Inicial", min_value=0.0, value=10000.0, step=1000.0)
    c_apo = col2.number_input("Aporte Mensal", min_value=0.0, value=500.0, step=100.0)
    c_mes = col3.slider("Prazo (meses)", 1, 360, 24)

    st.divider()

    cols_ativos = st.columns(st.session_state.n_comp)
    comp_ativos = []

    for i in range(st.session_state.n_comp):
        with cols_ativos[i]:
            st.markdown(f"### Ativo {i + 1}")
            tipo = st.selectbox(
                "Tipo",
                ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"],
                key=f"comp_tipo_{i}"
            )

            extra = 0.0
            if tipo in ["CDB", "LCI/LCA"]:
                extra = st.number_input("% do CDI", min_value=0.0, max_value=500.0, value=100.0, step=1.0, key=f"comp_extra_{i}")
            elif tipo == "Tesouro Prefixado":
                extra = st.number_input("Taxa % a.a.", min_value=0.0, max_value=50.0, value=11.0, step=0.1, key=f"comp_extra_{i}")
            elif tipo == "Tesouro IPCA+":
                extra = st.number_input("Taxa Fixa %", min_value=0.0, max_value=20.0, value=6.0, step=0.1, key=f"comp_extra_{i}")

            taxa, isento = calcular_taxa_anual(tipo, selic_sim, cdi_sim, ipca_sim, extra)
            comp_ativos.append({"nome": f"{tipo} #{i+1}", "taxa": taxa, "isento": isento, "tipo": tipo, "extra": extra})

    c_add, c_rem, _ = st.columns([1, 1, 4])
    if c_add.button("➕ Adicionar ativo", use_container_width=True):
        st.session_state.n_comp += 1
        st.rerun()

    if c_rem.button("➖ Remover ativo", use_container_width=True) and st.session_state.n_comp > 1:
        st.session_state.n_comp -= 1
        st.rerun()

    if st.button("🚀 Simular comparação", type="primary", use_container_width=True):
        resultados = []
        for a in comp_ativos:
            df = simular(c_ini, c_apo, a["taxa"], ipca_sim, c_mes, a["isento"])
            resultados.append({"nome": a["nome"], "tipo": a["tipo"], "extra": a["extra"], "df": df})

        cards = st.columns(len(resultados))
        for i, r in enumerate(resultados):
            final = r["df"].iloc[-1]
            with cards[i]:
                st.metric("Saldo Líquido Final", f"R$ {final['Saldo Líquido']:,.2f}")
                st.caption(f"Saldo Bruto: R$ {final['Saldo Bruto']:,.2f}")
                st.caption(f"IR Estimado: R$ {final['IR Estimado']:,.2f}")

                if r["tipo"] == "LCI/LCA":
                    aliq = aliquota_ir(c_mes)
                    equiv = r["extra"] / (1 - aliq) if aliq < 1 else 0
                    st.caption(f"Equivale aprox. a um CDB de {equiv:.1f}% do CDI no vencimento.")

        st.subheader("Evolução do saldo líquido")
        fig = px.line(title="Evolução do Saldo Líquido")
        for r in resultados:
            fig.add_scatter(x=r["df"]["Mês"], y=r["df"]["Saldo Líquido"], mode="lines", name=r["nome"])
        fig.update_layout(xaxis_title="Mês", yaxis_title="R$")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Extrato mês a mês"):
            tabela = pd.DataFrame({"Mês": resultados[0]["df"]["Mês"]})
            for r in resultados:
                tabela[r["nome"]] = r["df"]["Saldo Líquido"].values
            st.dataframe(tabela.set_index("Mês"), use_container_width=True)

    else:
        st.info("Configure os ativos e clique em simular.")

# ==========================================
# ABA 2: CARTEIRA CONJUNTA
# ==========================================
with tab2:
    st.subheader("Construção de patrimônio")
    col1, col2 = st.columns([2, 1])
    j_mes = col1.slider("Prazo global (meses)", 1, 480, 60)
    j_meta = col2.number_input("Meta alvo (R$)", min_value=0.0, value=100000.0)

    ativos_j = []
    cols_j = st.columns(1)

    for i in range(st.session_state.n_conj):
        with st.expander(f"Ativo {i + 1}", expanded=True):
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
            tipo = c1.selectbox(
                "Tipo",
                ["CDB", "LCI/LCA", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+", "Poupança"],
                key=f"conj_tipo_{i}"
            )
            ini = c2.number_input("Inicial (R$)", min_value=0.0, value=5000.0, step=1000.0, key=f"conj_ini_{i}")
            apo = c3.number_input("Aporte (R$)", min_value=0.0, value=500.0, step=100.0, key=f"conj_apo_{i}")

            extra = 0.0
            if tipo in ["CDB", "LCI/LCA"]:
                extra = c4.number_input("% do CDI", min_value=0.0, max_value=500.0, value=100.0, step=1.0, key=f"conj_extra_{i}")
            elif tipo == "Tesouro Prefixado":
                extra = c4.number_input("Taxa % a.a.", min_value=0.0, max_value=50.0, value=11.0, step=0.1, key=f"conj_extra_{i}")
            elif tipo == "Tesouro IPCA+":
                extra = c4.number_input("Taxa Fixa %", min_value=0.0, max_value=20.0, value=6.0, step=0.1, key=f"conj_extra_{i}")
            else:
                c4.write("")

            taxa, isento = calcular_taxa_anual(tipo, selic_sim, cdi_sim, ipca_sim, extra)
            ativos_j.append({"ini": ini, "apo": apo, "taxa": taxa, "isento": isento, "tipo": tipo})

    c_add, c_rem, _ = st.columns([1, 1, 4])
    if c_add.button("➕ Adicionar ativo", key="add_conj", use_container_width=True):
        st.session_state.n_conj += 1
        st.rerun()

    if c_rem.button("➖ Remover ativo", key="rem_conj", use_container_width=True) and st.session_state.n_conj > 1:
        st.session_state.n_conj -= 1
        st.rerun()

    if st.button("🚀 Calcular carteira", type="primary", use_container_width=True):
        dfs = [simular(a["ini"], a["apo"], a["taxa"], ipca_sim, j_mes, a["isento"]) for a in ativos_j]

        df_total = pd.DataFrame({"Mês": dfs[0]["Mês"]})
        df_total["Saldo Líquido"] = sum(d["Saldo Líquido"] for d in dfs)
        df_total["Investido"] = sum(d["Investido"] for d in dfs)
        df_total["Saldo Real Bruto"] = sum(d["Saldo Real Bruto"] for d in dfs)
        df_total["Saldo Real Líquido"] = sum(d["Saldo Real Líquido"] for d in dfs)

        total_inv = df_total["Investido"].iloc[-1]
        total_liq = df_total["Saldo Líquido"].iloc[-1]
        lucro = total_liq - total_inv
        perc = (lucro / total_inv * 100) if total_inv > 0 else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("Saldo Líquido Final", f"R$ {total_liq:,.2f}")
        m2.metric("Total Investido", f"R$ {total_inv:,.2f}")
        m3.metric("Lucro Líquido", f"R$ {lucro:,.2f}", f"{perc:.1f}%")

        if j_meta > 0:
            atingiu = df_total[df_total["Saldo Líquido"] >= j_meta]
            if not atingiu.empty:
                st.success(f"🎯 Meta atingida no mês {int(atingiu.iloc[0]['Mês'])}.")

        fig = px.area(
            df_total,
            x="Mês",
            y=["Saldo Líquido", "Investido", "Saldo Real Líquido"],
            title="Patrimônio nominal vs. real"
        )
        fig.update_layout(xaxis_title="Mês", yaxis_title="R$")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Extrato detalhado"):
            st.dataframe(df_total.set_index("Mês"), use_container_width=True)

# ==========================================
# ABA 3: ALVOS
# ==========================================
with tab3:
    st.subheader("Alocação sugerida")
    valor_total = st.number_input("Valor total", min_value=0.0, value=100000.0)

    c1, c2 = st.columns(2)
    p_pos = c1.slider("% Pós-fixado", 0, 100, 50)
    p_inf = c2.slider("% Inflação", 0, 100 - p_pos, 30)
    p_pre = 100 - p_pos - p_inf

    st.metric("Prefixado / Reserva", f"{p_pre}%")

    df_pie = pd.DataFrame({
        "Categoria": ["Pós-fixado", "Inflação", "Prefixado / Reserva"],
        "Valor": [
            valor_total * (p_pos / 100),
            valor_total * (p_inf / 100),
            valor_total * (p_pre / 100),
        ]
    })

    fig_pie = px.pie(df_pie, names="Categoria", values="Valor", hole=0.4)
    st.plotly_chart(fig_pie, use_container_width=True)
