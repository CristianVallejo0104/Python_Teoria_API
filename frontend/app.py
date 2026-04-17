"""
frontend/app.py
Dashboard RiskLab USTA — Streamlit
 
Corre con:
    streamlit run frontend/app.py
    (desde la raíz del proyecto, con el backend corriendo en :8000)
 
Consume los 9 endpoints del backend FastAPI.
"""
 
import requests
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
 
# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="RiskLab USTA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
# ── Estilos CSS personalizados ────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
 
    html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
 
    /* Header principal */
    .main-header {
        background: linear-gradient(135deg, #3D008D 0%, #ED1E79 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .main-header p  { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.9rem; }
 
    /* Tarjetas de métricas */
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        border-left: 4px solid #3D008D;
        margin-bottom: 0.5rem;
    }
    .metric-card .label { font-size: 0.75rem; color: #64748b; font-weight: 600;
                          text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-card .value { font-size: 1.5rem; font-weight: 700; color: #1e293b; }
    .metric-card .delta { font-size: 0.8rem; margin-top: 0.2rem; }
 
    /* Semáforo */
    .semaforo-verde  { background:#dcfce7; border:2px solid #16a34a;
                       border-radius:10px; padding:1rem; text-align:center; }
    .semaforo-rojo   { background:#fee2e2; border:2px solid #dc2626;
                       border-radius:10px; padding:1rem; text-align:center; }
    .semaforo-amarillo { background:#fef9c3; border:2px solid #ca8a04;
                        border-radius:10px; padding:1rem; text-align:center; }
 
    /* Sidebar */
    .css-1d391kg { background: linear-gradient(180deg,#001A4D,#002868); }
 
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 0.82rem;
    }
</style>
""", unsafe_allow_html=True)
 
# ── Configuración del backend ─────────────────────────────────────────────────
BACKEND_URL = "http://127.0.0.1:8000"
 
 
# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
 
def api_get(endpoint: str, params: dict = None) -> dict | None:
    """Llama al backend con GET. Muestra error si falla."""
    try:
        r = requests.get(f"{BACKEND_URL}{endpoint}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ No se puede conectar con el backend. "
                 "Asegúrate de que esté corriendo en `http://127.0.0.1:8000`.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Error del servidor: {e.response.status_code} — "
                 f"{e.response.json().get('detail', str(e))}")
        return None
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")
        return None
 
 
def api_post(endpoint: str, body: dict) -> dict | None:
    """Llama al backend con POST."""
    try:
        r = requests.post(f"{BACKEND_URL}{endpoint}", json=body, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ No se puede conectar con el backend.")
        return None
    except requests.exceptions.HTTPError as e:
        detail = e.response.json().get("detail", str(e))
        st.error(f"❌ Error {e.response.status_code}: {detail}")
        return None
    except Exception as e:
        st.error(f"❌ Error inesperado: {e}")
        return None
 
 
def color_senal(senal: str) -> str:
    return {"COMPRA": "🟢", "VENTA": "🔴", "NEUTRAL": "🟡"}.get(senal, "⚪")
 
 
def fmt_pct(val: float) -> str:
    return f"{val:+.2f}%" if val else "N/A"
 
 
# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
 
with st.sidebar:
    st.markdown("## ⚙️ Configuración")
    st.markdown("---")
 
    # ── Tickers ──────────────────────────────────────────────────────────────
    TICKERS_DISPONIBLES = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "AMD", "INTC", "CRM", "ORCL", "ADBE", "NFLX", "UBER", "LYFT",
        "JPM", "BAC", "GS", "MS", "WFC", "BRK-B", "V", "MA", "AXP",
        "JNJ", "PFE", "MRK", "ABBV", "UNH", "CVS",
        "XOM", "CVX", "COP", "SLB",
        "WMT", "HD", "MCD", "SBUX", "NKE", "KO", "PEP",
        "SPY", "QQQ", "DIA", "IWM", "GLD",
    ]

    tickers = st.multiselect(
        "📦 Tickers del portafolio",
        options=TICKERS_DISPONIBLES,
        default=["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
        help="Selecciona entre 2 y 10 activos para analizar.",
    )

    ticker_custom = st.text_input(
        "➕ Agregar ticker personalizado",
        placeholder="Ej: TSM, BABA, BRK-A",
        help="Si tu ticker no aparece arriba, escríbelo aquí separado por comas.",
    )
    if ticker_custom.strip():
        extras = [t.strip().upper() for t in ticker_custom.split(",") if t.strip()]
        tickers = tickers + [t for t in extras if t not in tickers]

    if len(tickers) < 2:
        st.warning("⚠️ Selecciona al menos 2 activos.")
    elif len(tickers) > 10:
        st.warning("⚠️ Máximo 10 activos. Se usarán los primeros 10.")
        tickers = tickers[:10]

    # ── Benchmark ─────────────────────────────────────────────────────────────
    benchmark = st.selectbox(
        "📊 Benchmark",
        options=["^GSPC", "^DJI", "^IXIC", "^RUT", "QQQ", "SPY"],
        index=0,
        format_func=lambda x: {
            "^GSPC": "^GSPC — S&P 500",
            "^DJI":  "^DJI  — Dow Jones",
            "^IXIC": "^IXIC — NASDAQ Composite",
            "^RUT":  "^RUT  — Russell 2000",
            "QQQ":   "QQQ   — NASDAQ-100 ETF",
            "SPY":   "SPY   — S&P 500 ETF",
        }.get(x, x),
        help="Índice contra el cual comparar el portafolio.",
    )
 
    fecha_inicio = st.date_input(
        "Fecha inicio",
        value=date.today() - timedelta(days=3 * 365),
        max_value=date.today() - timedelta(days=30),
    )
    fecha_fin = st.date_input(
        "Fecha fin",
        value=date.today(),
        max_value=date.today(),
    )
 
    confianza_var = st.slider(
        "Nivel de confianza VaR",
        min_value=0.90, max_value=0.99,
        value=0.95, step=0.01,
        format="%.2f",
    )
 
    valor_portafolio = st.number_input(
        "Valor del portafolio (USD)",
        min_value=1_000.0, max_value=10_000_000.0,
        value=100_000.0, step=10_000.0,
    )
 
    st.markdown("---")
    st.markdown("**Pesos del portafolio**")
    peso_igual = st.checkbox("Pesos iguales", value=True)
    if peso_igual:
        pesos = [round(1 / len(tickers), 4) for _ in tickers]
        st.caption(f"Cada activo: {pesos[0]*100:.1f}%")
    else:
        pesos = []
        for t in tickers:
            p = st.number_input(f"Peso {t}", 0.0, 1.0,
                                value=round(1/len(tickers), 2), step=0.05)
            pesos.append(p)
        suma = sum(pesos)
        if abs(suma - 1.0) > 0.01:
            st.warning(f"⚠️ Los pesos suman {suma:.2f}, no 1.0")
 
    st.markdown("---")
    st.markdown(
        "<small>**RiskLab USTA** · Prof. Javier Mauricio Sierra · "
        "Teoría del Riesgo + Python APIs</small>",
        unsafe_allow_html=True,
    )
 
# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
 
st.markdown(f"""
<div class="main-header">
    <h1>📊 RiskLab USTA — Análisis de Riesgo Financiero</h1>
    <p>Portafolio: <strong>{' · '.join(tickers)}</strong> &nbsp;|&nbsp;
       Benchmark: <strong>{benchmark}</strong> &nbsp;|&nbsp;
       Período: <strong>{fecha_inicio} → {fecha_fin}</strong></p>
</div>
""", unsafe_allow_html=True)
 
# ══════════════════════════════════════════════════════════════════════════════
# TABS PRINCIPALES (8 módulos)
# ══════════════════════════════════════════════════════════════════════════════
 
tabs = st.tabs([
    "📈 Mód.1 Análisis Técnico",
    "📉 Mód.2 Rendimientos",
    "🌊 Mód.3 ARCH/GARCH",
    "🎯 Mód.4 CAPM y Beta",
    "🛡️ Mód.5 VaR y CVaR",
    "⚡ Mód.6 Markowitz",
    "🚦 Mód.7 Señales",
    "🌐 Mód.8 Macro",
])
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 1 — ANÁLISIS TÉCNICO
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[0]:
    st.subheader("📈 Análisis Técnico e Indicadores")
 
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        ticker_sel = st.selectbox("Activo", tickers, key="m1_ticker")
    with col_ctrl2:
        indicador_sel = st.multiselect(
            "Indicadores a mostrar",
            ["SMA", "EMA", "Bollinger", "RSI", "MACD", "Estocástico"],
            default=["SMA", "Bollinger", "RSI"],
        )
 
    with st.spinner(f"Descargando indicadores de {ticker_sel}..."):
        data = api_get(f"/indicadores/{ticker_sel}", params={
            "sma_corto": 20, "sma_largo": 50, "rsi_periodo": 14,
        })
 
    if data:
        df = pd.DataFrame(data["indicadores"])
        df["fecha"] = pd.to_datetime(df["fecha"])
        df = df[(df["fecha"] >= pd.to_datetime(fecha_inicio)) &
                (df["fecha"] <= pd.to_datetime(fecha_fin))]
 
        # ── Gráfico de precios + indicadores ─────────────────────────────────
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["fecha"], y=df["precio_cierre"],
            name="Precio", line=dict(color="#3D008D", width=2),
        ))
        if "SMA" in indicador_sel:
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["sma_20"],
                name="SMA 20", line=dict(color="#ED1E79", width=1.2, dash="dot")))
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["sma_50"],
                name="SMA 50", line=dict(color="#F59E0B", width=1.2, dash="dash")))
        if "EMA" in indicador_sel:
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["ema_20"],
                name="EMA 20", line=dict(color="#10B981", width=1.2)))
        if "Bollinger" in indicador_sel:
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["banda_superior"],
                name="BB Superior", line=dict(color="rgba(100,100,200,0.5)", width=1),
                fill=None))
            fig.add_trace(go.Scatter(x=df["fecha"], y=df["banda_inferior"],
                name="BB Inferior", line=dict(color="rgba(100,100,200,0.5)", width=1),
                fill="tonexty", fillcolor="rgba(100,100,200,0.07)"))
 
        fig.update_layout(
            title=f"{ticker_sel} — Precios e indicadores",
            xaxis_title="Fecha", yaxis_title="Precio (USD)",
            hovermode="x unified", height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)
 
        # ── RSI ───────────────────────────────────────────────────────────────
        if "RSI" in indicador_sel:
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(x=df["fecha"], y=df["rsi"],
                name="RSI", line=dict(color="#6366F1", width=2)))
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red",
                              annotation_text="Sobrecompra (70)")
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green",
                              annotation_text="Sobreventa (30)")
            fig_rsi.update_layout(title="RSI (14)", height=220,
                                  yaxis=dict(range=[0, 100]))
            st.plotly_chart(fig_rsi, use_container_width=True)
 
        # ── MACD ──────────────────────────────────────────────────────────────
        if "MACD" in indicador_sel:
            fig_macd = go.Figure()
            fig_macd.add_trace(go.Scatter(x=df["fecha"], y=df["macd"],
                name="MACD", line=dict(color="#3D008D", width=1.5)))
            fig_macd.add_trace(go.Scatter(x=df["fecha"], y=df["macd_signal"],
                name="Señal", line=dict(color="#ED1E79", width=1.5)))
            colors = ["green" if v >= 0 else "red"
                      for v in df["macd_histogram"].fillna(0)]
            fig_macd.add_trace(go.Bar(x=df["fecha"], y=df["macd_histogram"],
                name="Histograma", marker_color=colors, opacity=0.6))
            fig_macd.update_layout(title="MACD", height=220)
            st.plotly_chart(fig_macd, use_container_width=True)
 
        # ── Estocástico ───────────────────────────────────────────────────────
        if "Estocástico" in indicador_sel:
            fig_stoch = go.Figure()
            fig_stoch.add_trace(go.Scatter(x=df["fecha"], y=df["stoch_k"],
                name="%K", line=dict(color="#0EA5E9", width=1.5)))
            fig_stoch.add_trace(go.Scatter(x=df["fecha"], y=df["stoch_d"],
                name="%D", line=dict(color="#F97316", width=1.5)))
            fig_stoch.add_hline(y=80, line_dash="dash", line_color="red")
            fig_stoch.add_hline(y=20, line_dash="dash", line_color="green")
            fig_stoch.update_layout(title="Oscilador Estocástico", height=220,
                                    yaxis=dict(range=[0, 100]))
            st.plotly_chart(fig_stoch, use_container_width=True)
 
        with st.expander("ℹ️ Interpretación de indicadores"):
            st.markdown("""
            | Indicador | Señal alcista | Señal bajista |
            |---|---|---|
            | **SMA/EMA** | Precio > media, Golden Cross | Precio < media, Death Cross |
            | **Bollinger** | Precio toca banda inferior | Precio toca banda superior |
            | **RSI** | RSI < 30 (sobreventa) | RSI > 70 (sobrecompra) |
            | **MACD** | MACD cruza señal ↑ | MACD cruza señal ↓ |
            | **Estocástico** | %K cruza %D ↑ en zona <20 | %K cruza %D ↓ en zona >80 |
            """)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 2 — RENDIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[1]:
    st.subheader("📉 Rendimientos y Propiedades Empíricas")
 
    ticker_r = st.selectbox("Activo", tickers, key="m2_ticker")
 
    with st.spinner("Calculando rendimientos..."):
        data_r = api_get(f"/rendimientos/{ticker_r}")
 
    if data_r:
        df_r = pd.DataFrame(data_r["rendimientos"])
        df_r["fecha"] = pd.to_datetime(df_r["fecha"])
        est = data_r["estadisticas"]
 
        # ── Métricas descriptivas ─────────────────────────────────────────────
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Media diaria", f"{est['media']*100:.4f}%")
        c2.metric("Volatilidad diaria", f"{est['desviacion_std']*100:.4f}%")
        c3.metric("Asimetría", f"{est['asimetria']:.3f}")
        c4.metric("Curtosis exceso", f"{est['curtosis']:.3f}")
        c5.metric("Peor día (5%)", f"{est['percentil_5']*100:.2f}%")
 
        st.markdown("---")
        col_a, col_b = st.columns(2)
 
        with col_a:
            # Serie de rendimientos log
            fig_rend = go.Figure()
            fig_rend.add_trace(go.Scatter(
                x=df_r["fecha"], y=df_r["rendimiento_log"] * 100,
                name="Rend. log diario", line=dict(color="#3D008D", width=0.8),
                fill="tozeroy", fillcolor="rgba(61,0,141,0.08)",
            ))
            fig_rend.update_layout(
                title="Serie de rendimientos log diarios (%)",
                yaxis_title="%", height=300,
            )
            st.plotly_chart(fig_rend, use_container_width=True)
 
        with col_b:
            # Histograma con curva normal superpuesta
            rend_vals = df_r["rendimiento_log"] * 100
            mu, sigma = rend_vals.mean(), rend_vals.std()
            x_norm = np.linspace(rend_vals.min(), rend_vals.max(), 200)
            y_norm = (1 / (sigma * np.sqrt(2 * np.pi))) * \
                     np.exp(-0.5 * ((x_norm - mu) / sigma) ** 2)
 
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=rend_vals, nbinsx=60, name="Distribución real",
                histnorm="probability density",
                marker_color="#ED1E79", opacity=0.6,
            ))
            fig_hist.add_trace(go.Scatter(
                x=x_norm, y=y_norm, name="Normal teórica",
                line=dict(color="#3D008D", width=2),
            ))
            fig_hist.update_layout(title="Distribución de rendimientos vs normal",
                                   height=300)
            st.plotly_chart(fig_hist, use_container_width=True)
 
        # ── Q-Q Plot y Boxplot ────────────────────────────────────────────────
        col_c, col_d = st.columns(2)
 
        with col_c:
            rend_sorted = np.sort(df_r["rendimiento_log"].dropna() * 100)
            n = len(rend_sorted)
            cuantiles_teo = stats_norm_ppf = [
                float(np.percentile(
                    np.random.normal(mu, sigma, 10000), i / n * 100
                ))
                for i in range(1, n + 1)
            ]
            fig_qq = go.Figure()
            fig_qq.add_trace(go.Scatter(
                x=cuantiles_teo, y=list(rend_sorted),
                mode="markers", name="Datos",
                marker=dict(color="#6366F1", size=3, opacity=0.6),
            ))
            fig_qq.add_trace(go.Scatter(
                x=[min(cuantiles_teo), max(cuantiles_teo)],
                y=[min(cuantiles_teo), max(cuantiles_teo)],
                name="Normal perfecta", line=dict(color="red", dash="dash"),
            ))
            fig_qq.update_layout(
                title="Q-Q Plot vs distribución normal",
                xaxis_title="Cuantiles teóricos",
                yaxis_title="Cuantiles observados",
                height=300,
            )
            st.plotly_chart(fig_qq, use_container_width=True)
 
        with col_d:
            fig_box = go.Figure()
            for t in tickers[:5]:
                dr = api_get(f"/rendimientos/{t}")
                if dr:
                    vals = [x["rendimiento_log"] * 100
                            for x in dr["rendimientos"]]
                    fig_box.add_trace(go.Box(y=vals, name=t, boxpoints="outliers"))
            fig_box.update_layout(
                title="Boxplot de rendimientos por activo (%)",
                height=300,
            )
            st.plotly_chart(fig_box, use_container_width=True)
 
        # ── Pruebas de normalidad ─────────────────────────────────────────────
        st.markdown("#### Pruebas de normalidad")
        col_e, col_f, col_g = st.columns(3)
        col_e.metric(
            "Jarque-Bera p-valor", f"{est['jarque_bera_pvalue']:.4f}",
            delta="Normal" if est['jarque_bera_pvalue'] > 0.05 else "No normal",
            delta_color="normal" if est['jarque_bera_pvalue'] > 0.05 else "inverse",
        )
        col_f.metric(
            "Shapiro-Wilk p-valor", f"{est['shapiro_wilk_pvalue']:.4f}",
            delta="Normal" if est['shapiro_wilk_pvalue'] > 0.05 else "No normal",
            delta_color="normal" if est['shapiro_wilk_pvalue'] > 0.05 else "inverse",
        )
        col_g.metric(
            "Conclusión",
            "✅ Normal" if est["es_normal"] else "⚠️ No normal",
        )
 
        with st.expander("ℹ️ Hechos estilizados de los rendimientos financieros"):
            st.markdown("""
            Los rendimientos financieros típicamente exhiben:
            - **Colas pesadas (fat tails):** curtosis > 3 → más eventos extremos que la normal predice
            - **Agrupamiento de volatilidad:** períodos de alta volatilidad se suceden entre sí
            - **Asimetría negativa:** las caídas suelen ser más pronunciadas que las subidas
            - **Efecto apalancamiento:** las malas noticias aumentan más la volatilidad que las buenas
            
            Estos hechos justifican usar GARCH (Módulo 3) y VaR histórico/Monte Carlo (Módulo 5).
            """)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3 — ARCH/GARCH
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[2]:
    st.subheader("🌊 Volatilidad Condicional — ARCH/GARCH")
    st.info(
        "Los modelos ARCH/GARCH capturan el **agrupamiento de volatilidad**: "
        "períodos agitados tienden a seguir a períodos agitados. "
        "La volatilidad no es constante — depende del pasado.",
        icon="💡",
    )
 
    ticker_g = st.selectbox("Activo para modelar", tickers, key="m3_ticker")
 
    if st.button("🔄 Ajustar modelos ARCH/GARCH", key="btn_garch"):
        with st.spinner("Ajustando ARCH(1), GARCH(1,1) y EGARCH(1,1)..."):
            data_g = api_get(f"/rendimientos/{ticker_g}")

        if data_g:
            import numpy as np
            est_g = data_g["estadisticas"]
            rend_vals = [x["rendimiento_log"] for x in data_g["rendimientos"]]

            # ── Gráfico de volatility clustering ─────────────────────────
            df_rend_g = pd.DataFrame(data_g["rendimientos"])
            df_rend_g["fecha"] = pd.to_datetime(df_rend_g["fecha"])
            df_rend_g["vol_movil"] = (
                df_rend_g["rendimiento_log"].rolling(21).std() * np.sqrt(252) * 100
            )
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Scatter(
                x=df_rend_g["fecha"],
                y=df_rend_g["rendimiento_log"].abs() * 100,
                name="|Rendimiento| diario",
                line=dict(color="rgba(61,0,141,0.3)", width=0.7),
            ))
            fig_vol.add_trace(go.Scatter(
                x=df_rend_g["fecha"], y=df_rend_g["vol_movil"],
                name="Volatilidad móvil 21 días",
                line=dict(color="#ED1E79", width=2),
            ))
            fig_vol.update_layout(
                title="Agrupamiento de volatilidad (Volatility Clustering)",
                yaxis_title="%", height=320,
            )
            st.plotly_chart(fig_vol, use_container_width=True)

            # ── Ajustar modelos GARCH ─────────────────────────────────────
            st.markdown("#### Comparativa de modelos ARCH/GARCH")
            try:
                from arch import arch_model
                from scipy import stats
                rend_pct = pd.Series(rend_vals) * 100
                modelos_resultados = []
                for esp, vol, p, q in [
                    ("ARCH(1)",    "ARCH",   1, 0),
                    ("GARCH(1,1)", "GARCH",  1, 1),
                    ("EGARCH(1,1)","EGARCH", 1, 1),
                ]:
                    try:
                        if vol == "ARCH":
                            m = arch_model(rend_pct, vol="ARCH", p=p)
                        else:
                            m = arch_model(rend_pct, vol=vol, p=p, q=q)
                        res = m.fit(disp="off", show_warning=False)
                        fc = res.forecast(horizon=5, reindex=False)
                        vol1d = float(np.sqrt(fc.variance.iloc[-1, 0])) / 100
                        jb_p = float(stats.jarque_bera(res.std_resid.dropna())[1])
                        params = res.params
                        alpha = [float(v) for k, v in params.items() if "alpha[" in k]
                        beta  = [float(v) for k, v in params.items() if "beta[" in k]
                        pers  = sum(alpha) + sum(beta) if beta else sum(alpha)
                        modelos_resultados.append({
                            "Modelo": esp,
                            "AIC": round(res.aic, 2),
                            "BIC": round(res.bic, 2),
                            "Log-Lik": round(res.loglikelihood, 2),
                            "Persistencia (α+β)": round(pers, 4),
                            "Pronóst. vol. 1d (%)": round(vol1d * 100, 4),
                            "JB residuos p-val": round(jb_p, 4),
                            "Mejor (AIC)": "",
                        })
                    except Exception:
                        pass

                if modelos_resultados:
                    mejor_aic = min(modelos_resultados, key=lambda x: x["AIC"])
                    for r in modelos_resultados:
                        r["Mejor (AIC)"] = "⭐" if r["Modelo"] == mejor_aic["Modelo"] else ""

                    df_garch = pd.DataFrame(modelos_resultados).set_index("Modelo")
                    st.dataframe(df_garch, use_container_width=True)

                    vol_anual = mejor_aic["Pronóst. vol. 1d (%)"] * np.sqrt(252)
                    st.success(
                        f"**Modelo seleccionado: {mejor_aic['Modelo']}** "
                        f"(menor AIC = {mejor_aic['AIC']}). "
                        f"Volatilidad pronosticada mañana: **{mejor_aic['Pronóst. vol. 1d (%)']:.4f}%** diario "
                        f"(**{vol_anual:.2f}%** anualizado). "
                        f"Persistencia α+β = {mejor_aic['Persistencia (α+β)']} "
                        f"{'— muy persistente, la volatilidad tarda en calmarse.' if mejor_aic['Persistencia (α+β)'] > 0.9 else '— volatilidad moderadamente persistente.'}"
                    )
            except ImportError:
                st.warning("Librería `arch` no instalada. Ejecuta: pip install arch")
    
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 4 — CAPM Y BETA
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[3]:
    st.subheader("🎯 CAPM y Riesgo Sistemático")
 
    if st.button("🔄 Calcular CAPM", key="btn_capm"):
        with st.spinner("Calculando Beta y CAPM (obteniendo Rf desde FRED)..."):
            data_capm = api_get("/capm", params={
                "tickers": tickers,
                "benchmark": benchmark,
            })
 
        if data_capm:
            st.success(f"Rf = **{data_capm['activos'][0]['tasa_libre_riesgo_anual']:.2f}%** "
                       f"(FRED Treasury 3M) | Benchmark: **{data_capm['benchmark']}**")
 
            df_capm = pd.DataFrame(data_capm["activos"])
 
            # ── Métricas por activo ───────────────────────────────────────────
            cols = st.columns(len(df_capm))
            for i, (_, row) in enumerate(df_capm.iterrows()):
                color = ("🔴" if row["clasificacion"] == "Agresivo"
                         else "🟢" if row["clasificacion"] == "Defensivo"
                         else "🟡")
                cols[i].metric(
                    f"{color} {row['ticker']}",
                    f"β = {row['beta']:.3f}",
                    delta=row["clasificacion"],
                )
 
            # ── Tabla resumen ─────────────────────────────────────────────────
            df_display = df_capm[[
                "ticker", "beta", "clasificacion",
                "rendimiento_esperado_capm", "prima_riesgo",
                "alpha_jensen", "r_cuadrado",
            ]].copy()
            df_display.columns = [
                "Ticker", "Beta", "Clasificación",
                "Rend. Esperado CAPM (%)", "Prima de Riesgo (%)",
                "Alpha Jensen (%)", "R²",
            ]
            st.dataframe(df_display.set_index("Ticker"), use_container_width=True)
 
            # ── Gráfico de Beta ───────────────────────────────────────────────
            fig_beta = go.Figure()
            colores = ["#dc2626" if b > 1.2 else "#16a34a" if b < 0.8 else "#f59e0b"
                       for b in df_capm["beta"]]
            fig_beta.add_trace(go.Bar(
                x=df_capm["ticker"], y=df_capm["beta"],
                marker_color=colores, name="Beta",
            ))
            fig_beta.add_hline(y=1.0, line_dash="dash",
                               annotation_text="β = 1 (igual al mercado)")
            fig_beta.update_layout(
                title="Beta por activo — Riesgo sistemático",
                yaxis_title="Beta", height=350,
            )
            st.plotly_chart(fig_beta, use_container_width=True)
 
            # ── Gráfico Security Market Line (SML) ───────────────────────────
            rf = df_capm.iloc[0]["tasa_libre_riesgo_anual"]
            rm = df_capm.iloc[0]["rendimiento_mercado_anual"]
            betas_sml = np.linspace(0, 2, 100)
            rend_sml = rf + betas_sml * (rm - rf)
 
            fig_sml = go.Figure()
            fig_sml.add_trace(go.Scatter(
                x=betas_sml, y=rend_sml,
                name="Security Market Line",
                line=dict(color="#3D008D", width=2),
            ))
            for _, row in df_capm.iterrows():
                fig_sml.add_trace(go.Scatter(
                    x=[row["beta"]], y=[row["rendimiento_esperado_capm"]],
                    mode="markers+text",
                    text=[row["ticker"]], textposition="top right",
                    marker=dict(size=10), name=row["ticker"],
                ))
            fig_sml.update_layout(
                title="Security Market Line (SML)",
                xaxis_title="Beta", yaxis_title="Rendimiento esperado (%)",
                height=380,
            )
            st.plotly_chart(fig_sml, use_container_width=True)
 
            with st.expander("ℹ️ Riesgo sistemático vs no sistemático"):
                st.markdown("""
                - **Riesgo sistemático** (β): afecta a todo el mercado. **No se puede diversificar.**
                  El mercado solo compensa este tipo de riesgo con rendimiento adicional.
                - **Riesgo no sistemático** (1 - R²): específico del activo. **Se elimina diversificando.**
                - **Alpha de Jensen > 0**: el activo rindió más de lo que el CAPM predice.
                  Indica habilidad del gestor o factores no capturados por el modelo.
                """)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 5 — VaR y CVaR
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[4]:
    st.subheader("🛡️ Valor en Riesgo (VaR) y CVaR")
 
    if st.button("🔄 Calcular VaR y CVaR", key="btn_var"):
        with st.spinner("Calculando VaR (paramétrico, histórico y Monte Carlo)..."):
            body_var = {
                "tickers": tickers,
                "pesos": pesos,
                "nivel_confianza": confianza_var,
                "horizonte_dias": 1,
                "valor_portafolio": valor_portafolio,
            }
            data_var = api_post("/var", body_var)
 
        if data_var:
            st.success(
                f"Portafolio: ${valor_portafolio:,.0f} | "
                f"Nivel de confianza: {confianza_var*100:.0f}% | "
                f"Método recomendado: **{data_var['mejor_metodo_recomendado'].upper()}**"
            )
            st.caption(data_var.get("message", ""))
 
            # ── Tabla comparativa ─────────────────────────────────────────────
            resultados = data_var["resultados"]
            df_var = pd.DataFrame([{
                "Método": r["metodo"].capitalize(),
                "VaR (%)": f"{r['var_porcentaje']:.4f}%",
                "VaR ($)": f"${r['var_dolares']:,.2f}",
                "CVaR (%)": f"{r['cvar_porcentaje']:.4f}%",
                "CVaR ($)": f"${r['cvar_dolares']:,.2f}",
            } for r in resultados])
            st.dataframe(df_var.set_index("Método"), use_container_width=True)
 
            # ── Gráfico comparativo ───────────────────────────────────────────
            metodos = [r["metodo"].capitalize() for r in resultados]
            vars_pct = [r["var_porcentaje"] for r in resultados]
            cvars_pct = [r["cvar_porcentaje"] for r in resultados]
 
            fig_var = go.Figure()
            fig_var.add_trace(go.Bar(x=metodos, y=vars_pct,
                name=f"VaR {confianza_var*100:.0f}%",
                marker_color="#3D008D"))
            fig_var.add_trace(go.Bar(x=metodos, y=cvars_pct,
                name="CVaR (Expected Shortfall)",
                marker_color="#ED1E79"))
            fig_var.update_layout(
                title="Comparativa VaR vs CVaR por método (%)",
                barmode="group", yaxis_title="%", height=350,
            )
            st.plotly_chart(fig_var, use_container_width=True)
 
            # ── Interpretaciones ──────────────────────────────────────────────
            for r in resultados:
                with st.expander(f"📖 Interpretación — {r['metodo'].capitalize()}"):
                    st.info(r["interpretacion"])
 
            with st.expander("ℹ️ ¿Qué método usar?"):
                st.markdown(f"""
                | Método | Supuesto | Ventaja | Desventaja |
                |---|---|---|---|
                | **Paramétrico** | Rendimientos normales | Rápido, analítico | Subestima fat tails |
                | **Histórico** | El pasado = el futuro | Captura distribución real | No anticipa eventos nuevos |
                | **Monte Carlo** | Simula {10000:,} escenarios | Flexible, adaptable | Depende del modelo generador |
                
                **El backend recomienda:** `{data_var['mejor_metodo_recomendado']}` basado en la prueba Jarque-Bera sobre los rendimientos del portafolio.
                """)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 6 — MARKOWITZ
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[5]:
    st.subheader("⚡ Optimización de Markowitz — Frontera Eficiente")
 
    n_port = st.slider("Portafolios a simular", 1000, 10000, 5000, step=1000)
 
    if st.button("🔄 Construir frontera eficiente", key="btn_markowitz"):
        with st.spinner(f"Simulando {n_port:,} portafolios..."):
            body_frontera = {
                "tickers": tickers,
                "n_portafolios": n_port,
                "tasa_libre_riesgo": None,
            }
            data_mk = api_post("/frontera-eficiente", body_frontera)
 
        if data_mk:
            rf_usado = data_mk["tasa_libre_riesgo_usada"] * 100
            st.success(f"Rf utilizada: **{rf_usado:.2f}%** | "
                       f"Portafolios simulados: **{data_mk['n_portafolios_simulados']:,}**")
 
            # ── Gráfico de la frontera eficiente ─────────────────────────────
            nube = pd.DataFrame(data_mk["nube_portafolios"])
            frontera = pd.DataFrame(data_mk["frontera_eficiente"])
            ms = data_mk["portafolio_max_sharpe"]
            mv = data_mk["portafolio_min_varianza"]

            st.markdown("#### Matriz de correlación entre activos")
            if "matriz_correlacion" in data_mk:
                corr_dict = data_mk["matriz_correlacion"]
                corr_df = pd.DataFrame(corr_dict)
                
                fig_corr = go.Figure(data=go.Heatmap(
                    z=corr_df.values,
                    x=corr_df.columns.tolist(),
                    y=corr_df.index.tolist(),
                    colorscale="RdBu",
                    zmin=-1, zmax=1,
                    text=corr_df.round(2).values,
                    texttemplate="%{text}",
                    textfont={"size": 11},
                    colorbar=dict(title="Correlación"),
                ))
                fig_corr.update_layout(
                    title="Correlación entre activos (rendimientos diarios)",
                    height=350,
                )
                st.plotly_chart(fig_corr, use_container_width=True)
                st.caption("Correlaciones cercanas a 1 = se mueven juntos · Cercanas a -1 = se mueven opuesto · "
                        "Correlaciones bajas entre activos = mejor diversificación")

            fig_mk = go.Figure()
 
            # Nube de portafolios (conjunto factible)
            fig_mk.add_trace(go.Scatter(
                x=nube["volatilidad"], y=nube["rendimiento"],
                mode="markers", name="Portafolios simulados",
                marker=dict(
                    color=nube["ratio_sharpe"],
                    colorscale="Viridis", size=4, opacity=0.5,
                    colorbar=dict(title="Sharpe"),
                ),
            ))
 
            # Frontera eficiente
            frontera_sorted = frontera.sort_values("volatilidad")
            fig_mk.add_trace(go.Scatter(
                x=frontera_sorted["volatilidad"],
                y=frontera_sorted["rendimiento"],
                mode="lines", name="Frontera eficiente",
                line=dict(color="#ED1E79", width=3),
            ))
 
            # Portafolio máximo Sharpe
            fig_mk.add_trace(go.Scatter(
                x=[ms["volatilidad_anual"]], y=[ms["rendimiento_anual"]],
                mode="markers+text", name="Máx. Sharpe ⭐",
                text=["Máx. Sharpe"], textposition="top right",
                marker=dict(color="gold", size=15, symbol="star",
                            line=dict(color="black", width=1)),
            ))
 
            # Portafolio mínima varianza
            fig_mk.add_trace(go.Scatter(
                x=[mv["volatilidad_anual"]], y=[mv["rendimiento_anual"]],
                mode="markers+text", name="Mín. Varianza 🔵",
                text=["Mín. Varianza"], textposition="top right",
                marker=dict(color="#3D008D", size=12, symbol="diamond"),
            ))
 
            fig_mk.update_layout(
                title="Frontera Eficiente de Markowitz",
                xaxis_title="Volatilidad anual (%)",
                yaxis_title="Rendimiento esperado anual (%)",
                height=500,
            )
            st.plotly_chart(fig_mk, use_container_width=True)
 
            # ── Composición de portafolios óptimos ───────────────────────────
            col_ms, col_mv = st.columns(2)
 
            with col_ms:
                st.markdown("#### ⭐ Portafolio Máximo Sharpe")
                st.metric("Rendimiento anual", f"{ms['rendimiento_anual']:.2f}%")
                st.metric("Volatilidad anual", f"{ms['volatilidad_anual']:.2f}%")
                st.metric("Ratio de Sharpe", f"{ms['ratio_sharpe']:.4f}")
                df_ms = pd.DataFrame(
                    list(ms["pesos"].items()), columns=["Ticker", "Peso"]
                )
                df_ms["Peso %"] = df_ms["Peso"].map(lambda x: f"{x*100:.1f}%")
                fig_pie_ms = px.pie(df_ms, values="Peso", names="Ticker",
                                   title="Composición")
                st.plotly_chart(fig_pie_ms, use_container_width=True)
 
            with col_mv:
                st.markdown("#### 🔵 Portafolio Mínima Varianza")
                st.metric("Rendimiento anual", f"{mv['rendimiento_anual']:.2f}%")
                st.metric("Volatilidad anual", f"{mv['volatilidad_anual']:.2f}%")
                st.metric("Ratio de Sharpe", f"{mv['ratio_sharpe']:.4f}")
                df_mv = pd.DataFrame(
                    list(mv["pesos"].items()), columns=["Ticker", "Peso"]
                )
                df_mv["Peso %"] = df_mv["Peso"].map(lambda x: f"{x*100:.1f}%")
                fig_pie_mv = px.pie(df_mv, values="Peso", names="Ticker",
                                   title="Composición")
                st.plotly_chart(fig_pie_mv, use_container_width=True)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 7 — SEÑALES Y ALERTAS
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[6]:
    st.subheader("🚦 Señales y Alertas de Trading")

    # INYECCIÓN DE CSS PARA ARREGLAR EL CONTRASTE
    st.markdown("""
        <style>
        /* Forzar tamaño base para todo el contenido dentro de las tarjetas */
        .semaforo-verde, .semaforo-rojo, .semaforo-amarillo,
        .semaforo-verde * , .semaforo-rojo * , .semaforo-amarillo * {
            font-size: 13px !important;
            line-height: 1.35 !important;
            font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
            color: inherit !important;
        }

        .semaforo-verde {
            background-color: rgba(16,185,129,0.12);
            border: 1px solid #10b981;
            padding: 10px 12px;
            border-radius: 8px;
            color: #ffffff !important;
        }
        .semaforo-rojo {
            background-color: rgba(239,68,68,0.12);
            border: 1px solid #ef4444;
            padding: 10px 12px;
            border-radius: 8px;
            color: #ffffff !important;
        }
        .semaforo-amarillo {
            background-color: #fef08a;
            border: 1px solid #facc15;
            padding: 10px 12px;
            border-radius: 8px;
            color: #1a1a1a !important;
        }

        /* Título dentro de la tarjeta */
        .semaforo-title {
            font-weight: 700 !important;
            font-size: 15px !important;
            margin: 0 0 6px 0;
            display: block;
        }

        /* Descripción: más pequeña y con ajuste de texto */
        .semaforo-desc {
            font-size: 12px !important;
            margin: 0;
            display: block;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }

        /* Evitar que Streamlit aplique márgenes extra a <p> o <small> */
        .semaforo-amarillo p, .semaforo-rojo p, .semaforo-verde p {
            margin: 0;
            padding: 0;
        }

        /* Responsive: reducir aún más en pantallas pequeñas */
        @media (max-width: 520px) {
            .semaforo-verde, .semaforo-rojo, .semaforo-amarillo,
            .semaforo-verde * , .semaforo-rojo * , .semaforo-amarillo * {
                font-size: 11px !important;
            }
            .semaforo-title { font-size: 13px !important; }
            .semaforo-desc  { font-size: 11px !important; }
        }
        </style>
    """, unsafe_allow_html=True)




    if st.button("🔄 Generar señales", key="btn_alertas"):
        with st.spinner("Evaluando indicadores técnicos para cada activo..."):
            data_al = api_get("/alertas", params={"tickers": tickers})

        if data_al:
            st.caption(f"Análisis al {data_al['fecha_analisis'][:19]}")

            for activo in data_al["activos_analizados"]:
                semaforo = activo["resumen_semaforo"]
                clase_css = {
                    "VERDE": "semaforo-verde",
                    "ROJO": "semaforo-rojo",
                    "AMARILLO": "semaforo-amarillo",
                }[semaforo]
                emoji = {"VERDE": "🟢", "ROJO": "🔴", "AMARILLO": "🟡"}[semaforo]

                st.markdown(f"### {emoji} {activo['ticker']} — ${activo['precio_actual']:.2f}")

                # Tarjetas de semáforo
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                with c1:
                    st.markdown(
                        f'<div class="{clase_css}">'
                        f'<span class="semaforo-title">{semaforo}</span>'
                        f'<span class="semaforo-desc">{activo["interpretacion_global"]}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                c2.metric("🟢 Compra", activo["señales_compra"])
                c3.metric("🔴 Venta", activo["señales_venta"])
                c4.metric("🟡 Neutral", activo["señales_neutral"])

                # Tabla de señales individuales
                df_señales = pd.DataFrame([{
                    "Indicador": s["indicador"],
                    "Señal": f"{color_senal(s['senal'])} {s['senal']}",
                    "Fuerza": s["fuerza"],
                    "Valor": s["valor_actual"],
                    "Descripción": s["descripcion"],
                } for s in activo["senales"]])

                st.dataframe(df_señales.set_index("Indicador"),
                             use_container_width=True)
                st.markdown("---")
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 8 — MACRO Y BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════
 
with tabs[7]:
    st.subheader("🌐 Contexto Macroeconómico y Benchmark")
 
    if st.button("🔄 Cargar datos macro y benchmark", key="btn_macro"):
        params_macro: dict = {"benchmark": benchmark}
        if not peso_igual or len(tickers) > 1:
            for t, p in zip(tickers, pesos):
                params_macro.setdefault("tickers", []).append(t)
                params_macro.setdefault("pesos", []).append(p)
 
        with st.spinner("Consultando FRED y calculando métricas vs benchmark..."):
            data_macro = api_get("/macro", params=params_macro)
 
        if data_macro:
            st.caption(f"Actualizado: {data_macro['fecha_actualizacion'][:19]}")
 
            # ── Indicadores macro ─────────────────────────────────────────────
            st.markdown("#### 📊 Indicadores Macroeconómicos")
            cols_macro = st.columns(len(data_macro["indicadores"]))
            for i, ind in enumerate(data_macro["indicadores"]):
                cols_macro[i].metric(
                    label=ind["nombre"],
                    value=f"{ind['valor']:.2f}{ind['unidad']}",
                    help=ind["descripcion"],
                )
 
            # ── Métricas vs benchmark ─────────────────────────────────────────
            if data_macro.get("metricas_benchmark"):
                mb = data_macro["metricas_benchmark"]
                st.markdown(f"#### 📈 Portafolio vs {mb['benchmark_ticker']}")
 
                if mb["supera_benchmark"]:
                    st.success(
                        f"✅ El portafolio **superó** al benchmark (Sharpe portafolio "
                        f"{mb['ratio_sharpe_portafolio']:.3f} > benchmark {mb['ratio_sharpe_benchmark']:.3f})"
                    )
                else:
                    st.warning(
                        f"⚠️ El portafolio **no superó** al benchmark (Sharpe portafolio "
                        f"{mb['ratio_sharpe_portafolio']:.3f} < benchmark {mb['ratio_sharpe_benchmark']:.3f})"
                    )
 
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Rend. acumulado portafolio",
                            f"{mb['rendimiento_acumulado_portafolio']:.2f}%")
                col2.metric("Rend. acumulado benchmark",
                            f"{mb['rendimiento_acumulado_benchmark']:.2f}%")
                col3.metric("Alpha de Jensen",
                            f"{mb['alpha_jensen']:.4f}%",
                            delta="Positivo ✅" if mb['alpha_jensen'] > 0 else "Negativo ⚠️",
                            delta_color="normal" if mb['alpha_jensen'] > 0 else "inverse")
                col4.metric("Information Ratio",
                            f"{mb['information_ratio']:.4f}",
                            help="Alpha / Tracking Error. >0 indica valor añadido vs benchmark.")
 
                col5, col6, col7, col8 = st.columns(4)
                col5.metric("Tracking Error", f"{mb['tracking_error']:.4f}%",
                            help="Desviación del portafolio respecto al benchmark")
                col6.metric("Máx. Drawdown portafolio",
                            f"{mb['maximo_drawdown_portafolio']:.2f}%")
                col7.metric("Máx. Drawdown benchmark",
                            f"{mb['maximo_drawdown_benchmark']:.2f}%")
                col8.metric("Sharpe portafolio",
                            f"{mb['ratio_sharpe_portafolio']:.4f}")
 
                with st.expander("ℹ️ Interpretación de métricas"):
                    st.markdown("""
                    - **Alpha de Jensen:** rendimiento extra sobre lo que predice el CAPM.
                      Si es positivo, el portafolio generó valor por encima del riesgo asumido.
                    - **Tracking Error:** qué tan diferente se mueve el portafolio del benchmark.
                      Un TE alto significa que el gestor tomó apuestas activas importantes.
                    - **Information Ratio = Alpha / TE:** eficiencia del gestor activo.
                      IR > 0.5 se considera bueno; IR > 1.0, excelente.
                    - **Máximo Drawdown:** la mayor caída desde un pico histórico.
                      Mide el peor escenario vivido. Un inversionista debe poder tolerarlo.
                    """)