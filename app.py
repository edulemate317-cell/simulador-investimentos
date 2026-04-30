import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# ==========================================
# CONFIGURAÇÃO DE LAYOUT E CSS 
# ==========================================
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
# 1. FUNÇÕES DE BACKEND (Com Proteção de Parse e Type Hints)
# ==========================================
@st.cache_data(ttl=3600)
def obter_taxas_atuais() -> tuple[float, float, float, bool]:
    url_selic = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
    url_ipca = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
    
    try:
        with requests.Session() as s:
            r_selic = s.get(url_selic, timeout=(3.05, 10))
            r_ipca = s.get(url_ipca, timeout=(3.05, 10))
            r_selic.raise_for_status()
            r_ipca.raise_for_status()
            
            dados_selic = r_selic.json()
            dados_ipca = r_ipca.json()
            
            if not dados_selic or not dados_ipca:
                raise ValueError("Resposta vazia da API")
            
            # Proteção contra vírgulas na resposta do Banco Central
            selic = float(str(dados_selic[0]['valor']).replace(',', '.')) / 100
            ipca = float(str(dados_ipca[0]['valor']).replace(',', '.')) / 100
            cdi = selic - 0.0010
            return selic, cdi, ipca, False
    except (requests.exceptions.RequestException, ValueError, KeyError, IndexError): 
        return 0.1050, 0.1040, 0.0450, True

def obter_aliquota_ir(meses: int) -> float:
    if meses <= 6: return 0.225
    elif meses <= 12: return 0.200
    elif meses <= 24: return 0.175
    else: return 0.150

def calcular_taxa_ativo(tipo: str, selic: float, cdi: float, ipca: float, perc_cdi: float = 100.0, taxa_fixa: float = 0.0) -> tuple[float, bool]:
    if tipo == "Poupança": 
        return (1.005**12-1) if selic > 0.085 else (selic*0.7), True
    elif tipo in ["CDB", "LCI/LCA"]:
        return cdi * (perc_cdi/100), (tipo == "LCI/LCA")
    elif tipo == "Tesouro Selic": 
        return selic - 0.002, False
    elif tipo == "Tesouro Prefixado": 
        return (taxa_fixa/100) - 0.002, False
    elif tipo == "Tesouro IPCA+": 
        return (((1+ipca)*(1+(taxa_fixa/100)))-1) - 0.002, False
    return 0.0, False

def simular_evolucao(capital_inicial: float, aporte_mensal: float, taxa_anual: float, ipca_anual: float, meses: int, isento_ir: bool) -> tuple[pd.DataFrame, float, float, float, float]:
    taxa_mensal = (1 + taxa_anual) ** (1 / 12) - 1
    inflacao_mensal = (1 + ipca_anual) ** (1 / 12) - 1
    
    saldo_bruto = capital_inicial
    total_investido = capital_inicial
    historico = []
    
    for mes in range(0, meses + 1):
        if mes > 0:
            saldo_bruto = (saldo_bruto * (1 + taxa_mensal)) + aporte_mensal
            total_investido += aporte_mensal
            
        lucro_parcial = max(0, saldo_bruto - total_investido)
        aliq = 0 if isento_ir else obter_aliquota_ir(mes if mes > 0 else 1)
        imposto_estimado = lucro_parcial * aliq
        
        saldo_liquido = saldo_bruto - imposto_estimado
        fator_inflacao = (1 + inflacao_mensal) ** mes if mes > 0 else 1.0
        poder_compra_real = saldo_liquido / fator_inflacao
        
        historico.append({
            "Mês": mes,
            "Total Investido (R$)": round(total_investido, 2),
            "Poder de Compra Real (R$)": round(poder_compra_real, 2),
            "Saldo Líquido (R$)": round(saldo_liquido, 2)
        })
    
    lucro_final = max(0, saldo_bruto - total_investido)
    aliq_f = 0 if isento_ir else obter_aliquota_ir(meses)
    imposto_final = lucro_final * aliq_f
    saldo_liquido_final = saldo_bruto - imposto_final
    
    return pd.DataFrame(historico), total_investido, saldo_liquido_final, imposto_final, aliq_f

# ==========================================
# 2. GESTÃO DE ESTADO
# ==========================================
if "num_ativos_comp" not in st.session_state: st.session_state["num_ativos_comp"] = 1
if "num_ativos_conj" not in st.session_state: st.session_state["num_ativos_conj"] = 1

# ==========================================
# 3. INTERFACE PRINCIPAL
# ==========================================
st.title("🚀 InvestSim Pro: Inteligência Financeira")
selic, cdi, ipca, erro_api = obter_taxas_atuais()

if erro_api:
    st.warning(f"⚠️ Instabilidade no Banco Central. Usando projeções padrão: Selic {selic*100:.2f}% | IPCA {ipca*100:.2f}%")
else:
    st.info(f"**Taxas Atuais:** Selic: {selic*100:.2f}% a.a. | CDI: {cdi*100:.2f}% a.a. | IPCA (12m): {ipca*100:.2f}%")

aba_comp, aba_conj, aba_ideal = st.tabs(["📊 Comparador Direto", "🏗️ Construção de Patrimônio", "🥧 Alvos de Carteira"])

# --- ABA 1: COMPARADOR ---
with aba_comp:
    st.sidebar.header("⚙️ Configurações do Comparador")
    c_ini = st.sidebar.number_input("Investimento Inicial (R$)", value=1000.0, step=100.0, key="ini_c")
    c_apo = st.sidebar.number_input("Aporte Mensal (R$)", value=500.0, step=100.0, key="apo_c")
    c_mes = st.sidebar.slider("Prazo (Meses)", 1, 120, 24, key="mes_c")

    def input_ativo_comp(n):
        st.sidebar.subheader(f"Ativo {n}")
        t = st.sidebar.selectbox("Tipo", ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], key=f"tc{n}")
        
        perc = 100.0
        t_fixa = 10.5
        
        if t in ["CDB", "LCI/LCA"]:
            perc = st.sidebar.number_input("% do CDI", min_value=0.0, value=100.0, step=1.0, key=f"pc{n}")
        elif t == "Tesouro Prefixado": 
            t_fixa = st.sidebar.number_input("Taxa % a.a.", min_value=0.0, value=10.5, step=0.1, key=f"pre_c{n}")
        elif t == "Tesouro IPCA+": 
            t_fixa = st.sidebar.number_input("Taxa Fixa %", min_value=0.0, value=5.5, step=0.1, key=f"ipca_c{n}")
            
        tx, isen = calcular_taxa_ativo(t, selic, cdi, ipca, perc, t_fixa)
        return {"nome": f"{t} {n}", "tipo": t, "taxa": tx, "isento": isen, "perc": perc}

    configs_comp = [input_ativo_comp(i+1) for i in range(st.session_state["num_ativos_comp"])]
    
    col_a, col_r = st.sidebar.columns(2)
    if col_a.button("➕ Adicionar", key="add_c", use_container_width=True): 
        st.session_state["num_ativos_comp"] += 1
        st.rerun()
    if col_r.button("➖ Remover", key="rem_c", use_container_width=True) and st.session_state["num_ativos_comp"] > 1: 
        st.session_state["num_ativos_comp"] -= 1
        st.rerun()
    
    st.sidebar.divider()
    if st.sidebar.button("🚀 Simular Comparação", type="primary", use_container_width=True):
        res_comp = []
        for c in configs_comp:
            df, tot, liq, imp, ali = simular_evolucao(c_ini, c_apo, c["taxa"], ipca, c_mes, c["isento"])
            res_comp.append({"nome": c["nome"], "tipo": c["tipo"], "perc": c["perc"], "df": df, "total": tot, "liq": liq, "imp": imp, "ali": ali})
        
        st.success(f"**Total Investido (Aportes):** R$ {res_comp[0]['total']:,.2f}")
        cols = st.columns(len(res_comp))
        
        for i, r in enumerate(res_comp):
            with cols[i]:
                st.subheader(r["nome"])
                valor_real_final = r['df']['Poder de Compra Real (R$)'].iloc[-1]
                st.metric("Resgate Líquido", f"R$ {r['liq']:,.2f}", f"Poder de Compra: R$ {valor_real_final:,.2f}")
                
                if r["tipo"] == "LCI/LCA":
                    equiv_cdb = r["perc"] / (1 - obter_aliquota_ir(c_mes))
                    st.caption(f"💡 Equivale a um CDB de **{equiv_cdb:.1f}%**")
                
                if r['ali'] == 0: 
                    st.info("🟢 **Isento de IR**")
                else: 
                    st.warning(f"🔴 **IR Retido:** R$ {r['imp']:,.2f} ({r['ali']*100:.1f}%)")
        
        st.subheader("Evolução do Poder de Compra Real")
        c_data = pd.DataFrame({"Mês": res_comp[0]["df"]["Mês"]}).set_index("Mês")
        c_data["Seu Dinheiro"] = res_comp[0]["df"]["Total Investido (R$)"]
        for r in res_comp: 
            c_data[r["nome"]] = r["df"]["Poder de Compra Real (R$)"]
            
        fig_comp = px.line(c_data, x=c_data.index, y=c_data.columns, color_discrete_sequence=px.colors.qualitative.Plotly)
        fig_comp.update_layout(xaxis_title="Meses", yaxis_title="Valor (R$)", legend_title_text="", hovermode="x unified")
        st.plotly_chart(fig_comp, use_container_width=True)
        
        with st.expander("📄 Ver Extrato Detalhado Mês a Mês"):
            extrato_comp = pd.DataFrame({"Mês": res_comp[0]["df"]["Mês"]}).set_index("Mês")
            for r in res_comp:
                extrato_comp[f"{r['nome']} (Líquido)"] = r["df"]["Saldo Líquido (R$)"]
            st.dataframe(extrato_comp, use_container_width=True)
        
        st.divider()
        csv_comp = c_data.reset_index().to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Baixar Comparação (CSV)", csv_comp, "comparacao.csv", "text/csv", use_container_width=True)
    else:
        st.write("👈 Configure os ativos na barra lateral e clique em **Simular Comparação**.")

# --- ABA 2: CONSTRUÇÃO DE PATRIMÔNIO ---
with aba_conj:
    st.subheader("🏗️ Simulador de Rendimento Conjunto")
    st.write("Aqui você define valores diferentes para cada investimento e vê o resultado somado do seu patrimônio.")
    
    c_p1, c_p2 = st.columns([2, 1])
    p_meses = c_p1.slider("Prazo Global (Meses)", 1, 120, 24, key="mes_conj")
    meta_alvo = c_p2.number_input("🎯 Meta Financeira Opcional (R$)", min_value=0.0, value=0.0, step=10000.0, help="Deixe 0 se não quiser usar.")
    st.divider()
    
    def row_ativo_conj(n):
        st.markdown(f"**Investimento {n}**")
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
        t = c1.selectbox("Tipo", ["CDB", "LCI/LCA", "Poupança", "Tesouro Selic", "Tesouro Prefixado", "Tesouro IPCA+"], key=f"tj{n}")
        ini = c2.number_input("Inicial (R$)", min_value=0.0, step=1000.0, value=5000.0, key=f"ij{n}")
        apo = c3.number_input("Aporte (R$)", min_value=0.0, step=100.0, value=200.0, key=f"aj{n}")
        
        perc = 100.0
        t_fixa = 10.5
        
        if t in ["CDB", "LCI/LCA"]:
            perc = c4.number_input("% CDI", min_value=0.0, value=100.0, step=1.0, key=f"pj{n}")
        elif t == "Tesouro Selic": 
            c4.caption(f"-0,2% B3")
        elif t == "Tesouro Prefixado": 
            t_fixa = c4.number_input("% a.a.", min_value=0.0, value=10.5, step=0.1, key=f"prej{n}")
        elif t == "Tesouro IPCA+": 
            t_fixa = c4.number_input("Taxa Fixa", min_value=0.0, value=5.5, step=0.1, key=f"ipcaj{n}")
            
        tx, isen = calcular_taxa_ativo(t, selic, cdi, ipca, perc, t_fixa)
        return {"ini": ini, "apo": apo, "taxa": tx, "isento": isen, "nome": f"{t}"}

    configs_conj = [row_ativo_conj(i+1) for i in range(st.session_state["num_ativos_conj"])]
    
    st.write("")
    c_b1, c_b2, _ = st.columns([1,1,3])
    if c_b1.button("➕ Adicionar Ativo", key="btn_add_j", use_container_width=True): 
        st.session_state["num_ativos_conj"] += 1
        st.rerun()
    if c_b2.button("➖ Remover Ativo", key="btn_rem_j", use_container_width=True) and st.session_state["num_ativos_conj"] > 1: 
        st.session_state["num_ativos_conj"] -= 1
        st.rerun()

    st.divider()
    if st.button("🚀 Calcular Patrimônio Conjunto", type="primary", use_container_width=True):
        all_dfs = []
        total_final = 0; total_inv = 0; total_imp = 0
        
        for c in configs_conj:
            df, inv, liq, imp, ali = simular_evolucao(c["ini"], c["apo"], c["taxa"], ipca, p_meses, c["isento"])
            all_dfs.append(df)
            total_final += liq
            total_inv += inv
            total_imp += imp
            
        df_sum = all_dfs[0][["Mês"]].copy()
        df_sum["Total Investido (R$)"] = sum(d["Total Investido (R$)"] for d in all_dfs)
        df_sum["Patrimônio Líquido (R$)"] = sum(d["Saldo Líquido (R$)"] for d in all_dfs)
        
        if meta_alvo > 0:
            atingiu = df_sum[df_sum["Patrimônio Líquido (R$)"] >= meta_alvo]
            if not atingiu.empty:
                mes_meta = atingiu.iloc[0]["Mês"]
                st.success(f"🎯 **Meta Atingida!** Você alcançará R$ {meta_alvo:,.2f} no **Mês {mes_meta}** (aproximadamente {mes_meta/12:.1f} anos).")
            else:
                st.warning(f"⏳ Com esses aportes e prazos, você não alcançará a meta de R$ {meta_alvo:,.2f} dentro dos {p_meses} meses.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investido (Do seu bolso)", f"R$ {total_inv:,.2f}")
        c2.metric("Patrimônio Líquido Final", f"R$ {total_final:,.2f}", f"Lucro: R$ {total_final-total_inv:,.2f}")
        c3.metric("Imposto de Renda Total", f"R$ {total_imp:,.2f}")
        
        st.subheader("Evolução do Patrimônio Somado")
        fig_conj = px.line(df_sum, x="Mês", y=["Patrimônio Líquido (R$)", "Total Investido (R$)"], 
                           color_discrete_map={"Patrimônio Líquido (R$)": "#3b82f6", "Total Investido (R$)": "#f59e0b"})
        
        if meta_alvo > 0:
            fig_conj.add_hline(y=meta_alvo, line_dash="dash", line_color="#10b981", 
                               annotation_text="🎯 Sua Meta", annotation_position="top left",
                               annotation_font=dict(color="#10b981", size=14))
            
        fig_conj.update_layout(xaxis_title="Meses", yaxis_title="Valor (R$)", legend_title_text="", hovermode="x unified")
        st.plotly_chart(fig_conj, use_container_width=True)

        with st.expander("📄 Ver Extrato Detalhado da Carteira"):
            st.dataframe(df_sum.set_index("Mês"), use_container_width=True)

        csv_conj = df_sum.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Baixar Dados da Carteira (CSV)", csv_conj, "carteira_conjunta.csv", "text/csv", use_container_width=True)

# --- ABA 3: ALVOS (CARTEIRA IDEAL) ---
with aba_ideal:
    st.subheader("🥧 Definição de Alvos da Carteira")
    pat_t = st.number_input("Capital Total (R$)", 0.0, step=1000.0, value=50000.0, key="pat_i")
    col1, col2, col3 = st.columns(3)
    p1 = col1.slider("Renda Fixa Geral", 0, 100, 50)
    max2 = 100 - p1
    
    if max2 > 0:
        p2 = col2.slider("Isentos (LCI/LCA)", 0, max2, 30 if max2 >= 30 else max2)
    else:
        p2 = col2.slider("Isentos (LCI/LCA)", 0, 100, 0, disabled=True)
        
    p3 = 100 - p1 - p2
    col3.metric("Reserva de Emergência", f"{p3}%")
    
    df_pie = pd.DataFrame({
        "Tipo": ["Renda Fixa Geral", "LCI/LCA", "Reserva de Emergência"], 
        "Valor": [pat_t*p1/100, pat_t*p2/100, pat_t*p3/100]
    })
    
    fig = px.pie(df_pie, values='Valor', names='Tipo', hole=0.4, color_discrete_sequence=['#3b82f6', '#10b981', '#f59e0b'])
    st.plotly_chart(fig, use_container_width=True)
