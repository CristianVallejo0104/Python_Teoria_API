"""
main.py
Punto de entrada de la API RiskLab USTA.
 
Para correr el servidor:
    uvicorn app.main:app --reload --port 8000
 
Documentación interactiva disponible en:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""
 
import logging
from datetime import date, datetime
from typing import Optional
 
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
 
from app.config import Settings, get_settings
from app.dependencies import (
    FredServiceDep,
    HttpClientDep,
    SettingsDep,
    ValidTickerDep,
    validate_ticker,
)
from app.models import (
    ActivoInfo,
    ActivosResponse,
    AlertasResponse,
    CAPMResponse,
    FronteraRequest,
    FronteraResponse,
    GARCHResponse,
    IndicadoresResponse,
    MacroResponse,
    PortafolioOptimo,
    PreciosResponse,
    PuntoFrontera,
    RendimientosResponse,
    VaRRequest,
    VaRResponse,
)
from app.services import (
    CAPMService,
    DataService,
    GARCHService,
    MacroService,
    MarkowitzService,
    RiskCalculator,
    SignalEngine,
    TechnicalIndicators,
)
 
# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# FÁBRICAS DE SERVICIOS (inyectables con Depends)
# Las rutas reciben servicios ya construidos — nunca instancian clases ellas mismas.
# ══════════════════════════════════════════════════════════════════════════════
 
def get_data_service(settings: SettingsDep) -> DataService:
    return DataService(years=settings.default_years)
 
 
def get_risk_calculator(settings: SettingsDep) -> RiskCalculator:
    return RiskCalculator(n_simulaciones=settings.montecarlo_simulations)
 
 
def get_garch_service() -> GARCHService:
    return GARCHService()
 
 
def get_capm_service() -> CAPMService:
    return CAPMService()
 
 
def get_markowitz_service(settings: SettingsDep) -> MarkowitzService:
    return MarkowitzService(n_portafolios=settings.markowitz_portfolios)
 
 
def get_signal_engine(
    settings: SettingsDep,
    data_service: DataService = Depends(get_data_service),
) -> SignalEngine:
    return SignalEngine(data_service=data_service)
 
 
def get_macro_service(fred_service: FredServiceDep) -> MacroService:
    return MacroService(fred_service=fred_service)
 
 
def get_technical_indicators() -> TechnicalIndicators:
    return TechnicalIndicators()
 
 
# ══════════════════════════════════════════════════════════════════════════════
# APLICACIÓN FASTAPI
# ══════════════════════════════════════════════════════════════════════════════
 
def create_app() -> FastAPI:
    settings = get_settings()
 
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "API de análisis de riesgo financiero — Proyecto Integrador USTA.\n\n"
            "Provee endpoints para análisis técnico, rendimientos, ARCH/GARCH, "
            "VaR/CVaR, CAPM, optimización de Markowitz, señales de trading "
            "y datos macroeconómicos.\n\n"
            "**Frontend:** Streamlit en `http://localhost:8501`\n"
            "**Datos:** Yahoo Finance + FRED API"
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        debug=settings.debug,
    )
 
    # ── CORS: permite que Streamlit (puerto 8501) consuma esta API ────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
 
    # ── Registrar routers ─────────────────────────────────────────────────────
    app.include_router(router_activos)
    app.include_router(router_precios)
    app.include_router(router_rendimientos)
    app.include_router(router_indicadores)
    app.include_router(router_var)
    app.include_router(router_capm)
    app.include_router(router_frontera)
    app.include_router(router_alertas)
    app.include_router(router_macro)
 
    @app.get("/", tags=["Health"])
    async def health_check():
        """Verifica que el servidor esté corriendo."""
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }
 
    return app
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 1 — GET /activos
# Lista los activos disponibles en el portafolio por defecto.
# ══════════════════════════════════════════════════════════════════════════════
 
router_activos = APIRouter(tags=["Activos"])
 
 
@router_activos.get(
    "/activos",
    response_model=ActivosResponse,
    summary="Lista de activos del portafolio",
    description="Retorna los activos disponibles con su metadata (sector, moneda, nombre).",
)
async def get_activos(
    settings: SettingsDep,
    data_service: DataService = Depends(get_data_service),
):
    tickers = settings.default_tickers
    activos = []
 
    for ticker in tickers:
        info = data_service.get_info_activo(ticker)
        activos.append(ActivoInfo(
            ticker=info["ticker"],
            nombre=info["nombre"],
            sector=info["sector"],
            moneda=info["moneda"],
        ))
 
    return ActivosResponse(
        activos=activos,
        total=len(activos),
        message=f"{len(activos)} activos disponibles en el portafolio.",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 2 — GET /precios/{ticker}
# Precios históricos OHLCV de un activo.
# ══════════════════════════════════════════════════════════════════════════════
 
router_precios = APIRouter(tags=["Precios"])
 
 
@router_precios.get(
    "/precios/{ticker}",
    response_model=PreciosResponse,
    summary="Precios históricos de un activo",
    description=(
        "Retorna el historial de precios OHLCV (apertura, máximo, mínimo, "
        "cierre, volumen) para el ticker solicitado."
    ),
)
async def get_precios(
    ticker: ValidTickerDep,
    fecha_inicio: Optional[date] = Query(
        default=None,
        description="Fecha de inicio (YYYY-MM-DD). Por defecto: hace 3 años.",
    ),
    fecha_fin: Optional[date] = Query(
        default=None,
        description="Fecha de fin (YYYY-MM-DD). Por defecto: hoy.",
    ),
    data_service: DataService = Depends(get_data_service),
):
    df = data_service.get_precios(ticker, fecha_inicio, fecha_fin)
    df_reset = df.reset_index()
 
    from app.models import PreciosPrecioRow
    filas = [
        PreciosPrecioRow(
            fecha=row["fecha"].date() if hasattr(row["fecha"], "date") else row["fecha"],
            apertura=round(row["apertura"], 4),
            maximo=round(row["maximo"], 4),
            minimo=round(row["minimo"], 4),
            cierre=round(row["cierre"], 4),
            volumen=int(row["volumen"]),
        )
        for _, row in df_reset.iterrows()
    ]
 
    return PreciosResponse(
        ticker=ticker,
        fecha_inicio=df_reset["fecha"].iloc[0].date(),
        fecha_fin=df_reset["fecha"].iloc[-1].date(),
        total_registros=len(filas),
        precios=filas,
        message=f"Precios históricos de {ticker} ({len(filas)} registros).",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 3 — GET /rendimientos/{ticker}
# Rendimientos simples, logarítmicos y estadísticas descriptivas.
# ══════════════════════════════════════════════════════════════════════════════
 
router_rendimientos = APIRouter(tags=["Rendimientos"])
 
 
@router_rendimientos.get(
    "/rendimientos/{ticker}",
    response_model=RendimientosResponse,
    summary="Rendimientos y estadísticas descriptivas",
    description=(
        "Calcula rendimientos simples y logarítmicos diarios. "
        "Incluye estadísticas descriptivas y pruebas de normalidad "
        "(Jarque-Bera y Shapiro-Wilk)."
    ),
)
async def get_rendimientos(
    ticker: ValidTickerDep,
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin: Optional[date] = Query(default=None),
    data_service: DataService = Depends(get_data_service),
):
    df_rend = data_service.get_rendimientos(ticker, fecha_inicio, fecha_fin)
    stats_dict = data_service.calcular_estadisticas(df_rend["rendimiento_log"])
 
    from app.models import EstadisticasDescriptivas, RendimientoRow
    filas = [
        RendimientoRow(
            fecha=idx.date() if hasattr(idx, "date") else idx,
            rendimiento_simple=round(row["rendimiento_simple"], 6),
            rendimiento_log=round(row["rendimiento_log"], 6),
        )
        for idx, row in df_rend.iterrows()
    ]
 
    estadisticas = EstadisticasDescriptivas(**stats_dict)
 
    return RendimientosResponse(
        ticker=ticker,
        total_observaciones=len(filas),
        rendimientos=filas,
        estadisticas=estadisticas,
        message=(
            f"Rendimientos de {ticker}. "
            f"{'Los rendimientos son aproximadamente normales.' if stats_dict['es_normal'] else 'Los rendimientos tienen colas pesadas (no normales).'}"
        ),
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 4 — GET /indicadores/{ticker}
# Todos los indicadores técnicos calculados.
# ══════════════════════════════════════════════════════════════════════════════
 
router_indicadores = APIRouter(tags=["Indicadores Técnicos"])
 
 
@router_indicadores.get(
    "/indicadores/{ticker}",
    response_model=IndicadoresResponse,
    summary="Indicadores técnicos",
    description=(
        "Calcula SMA, EMA, Bandas de Bollinger, RSI, MACD e "
        "Indicador Estocástico. Todos los parámetros son ajustables."
    ),
)
async def get_indicadores(
    ticker: ValidTickerDep,
    sma_corto: int = Query(default=20, ge=5, le=100, description="Período SMA corta"),
    sma_largo: int = Query(default=50, ge=10, le=200, description="Período SMA larga"),
    ema_periodo: int = Query(default=20, ge=5, le=100),
    rsi_periodo: int = Query(default=14, ge=5, le=50),
    bb_periodo: int = Query(default=20, ge=5, le=100, description="Período Bandas de Bollinger"),
    bb_std: float = Query(default=2.0, ge=1.0, le=4.0, description="Desviaciones estándar Bollinger"),
    data_service: DataService = Depends(get_data_service),
    ti: TechnicalIndicators = Depends(get_technical_indicators),
):
    df_ohlcv = data_service.get_precios(ticker)
    df_ind = ti.calcular_todos(
        df_ohlcv,
        sma_corto=sma_corto,
        sma_largo=sma_largo,
        ema_periodo=ema_periodo,
        rsi_periodo=rsi_periodo,
        bb_periodo=bb_periodo,
        bb_std=bb_std,
    )
 
    from app.models import IndicadoresFila
 
    def safe(val):
        import math
        if val is None:
            return None
        try:
            return None if math.isnan(float(val)) else round(float(val), 4)
        except (TypeError, ValueError):
            return None
 
    filas = [
        IndicadoresFila(
            fecha=idx.date() if hasattr(idx, "date") else idx,
            precio_cierre=safe(row.get("precio_cierre")),
            sma_20=safe(row.get("sma_20")),
            sma_50=safe(row.get("sma_50")),
            ema_20=safe(row.get("ema_20")),
            banda_superior=safe(row.get("banda_superior")),
            banda_media=safe(row.get("banda_media")),
            banda_inferior=safe(row.get("banda_inferior")),
            rsi=safe(row.get("rsi")),
            macd=safe(row.get("macd")),
            macd_signal=safe(row.get("macd_signal")),
            macd_histogram=safe(row.get("macd_histogram")),
            stoch_k=safe(row.get("stoch_k")),
            stoch_d=safe(row.get("stoch_d")),
        )
        for idx, row in df_ind.iterrows()
    ]
 
    return IndicadoresResponse(
        ticker=ticker,
        total_registros=len(filas),
        indicadores=filas,
        message=f"Indicadores técnicos de {ticker} calculados con parámetros ajustados.",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 5 — POST /var
# VaR y CVaR con tres métodos para un portafolio.
# ══════════════════════════════════════════════════════════════════════════════
 
router_var = APIRouter(tags=["Riesgo — VaR y CVaR"])
 
 
@router_var.post(
    "/var",
    response_model=VaRResponse,
    summary="Value at Risk y CVaR del portafolio",
    description=(
        "Calcula VaR y CVaR usando tres métodos: paramétrico, histórico "
        "y Monte Carlo. Recomienda el método más adecuado según las "
        "propiedades estadísticas de los rendimientos."
    ),
)
async def calcular_var(
    body: VaRRequest,
    data_service: DataService = Depends(get_data_service),
    risk_calc: RiskCalculator = Depends(get_risk_calculator),
):
    # Descargar rendimientos del portafolio
    df_rend = data_service.get_rendimientos_multiples(body.tickers)
 
    # Calcular rendimientos ponderados del portafolio
    rend_portafolio = RiskCalculator.rendimientos_portafolio(
        df_rend, body.pesos, body.tickers
    )
 
    # Calcular los 3 métodos
    resultado = risk_calc.calcular_var_completo(
        rendimientos_portafolio=rend_portafolio,
        nivel_confianza=body.nivel_confianza,
        horizonte_dias=body.horizonte_dias,
        valor_portafolio=body.valor_portafolio,
    )
 
    from app.models import VaRResultado
    resultados_modelo = [VaRResultado(**r) for r in resultado["resultados"]]
 
    return VaRResponse(
        ticker_portafolio=body.tickers,
        pesos=body.pesos,
        nivel_confianza=body.nivel_confianza,
        horizonte_dias=body.horizonte_dias,
        valor_portafolio=body.valor_portafolio,
        resultados=resultados_modelo,
        mejor_metodo_recomendado=resultado["mejor_metodo_recomendado"],
        message=resultado.get("razon_recomendacion", ""),
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 6 — GET /capm
# Beta y rendimiento esperado CAPM para todos los activos del portafolio.
# ══════════════════════════════════════════════════════════════════════════════
 
router_capm = APIRouter(tags=["Riesgo — CAPM y Beta"])
 
 
@router_capm.get(
    "/capm",
    response_model=CAPMResponse,
    summary="CAPM y Beta de cada activo",
    description=(
        "Calcula Beta, rendimiento esperado (CAPM), Alpha de Jensen y R² "
        "para cada activo respecto al benchmark. "
        "La tasa libre de riesgo se obtiene automáticamente desde FRED."
    ),
)
async def get_capm(
    tickers: list[str] = Query(
        default=None,
        description="Tickers a analizar. Si se omite, usa los activos por defecto.",
    ),
    benchmark: str = Query(default=None, description="Ticker del benchmark (default: ^GSPC)"),
    settings: SettingsDep = None,
    data_service: DataService = Depends(get_data_service),
    capm_service: CAPMService = Depends(get_capm_service),
    fred_service: FredServiceDep = None,
    macro_service: MacroService = Depends(get_macro_service),
):
    tickers_usar = tickers or settings.default_tickers
    benchmark_usar = benchmark or settings.benchmark_ticker
 
    # Tasa libre de riesgo desde FRED
    rf = await macro_service.get_tasa_libre_riesgo()
 
    # Calcular CAPM para cada activo
    resultados_raw = capm_service.calcular_capm_completo(
        tickers=tickers_usar,
        benchmark_ticker=benchmark_usar,
        tasa_libre_riesgo_anual=rf,
        data_service=data_service,
    )
 
    from app.models import CAPMActivoResultado
    activos_resultado = [CAPMActivoResultado(**r) for r in resultados_raw]
 
    return CAPMResponse(
        benchmark=benchmark_usar,
        periodo_analisis=f"{settings.default_years} años",
        tasa_libre_riesgo_fuente="FRED - US Treasury 3M",
        activos=activos_resultado,
        message=f"CAPM calculado para {len(activos_resultado)} activos. Rf = {rf:.2f}%.",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 7 — POST /frontera-eficiente
# Frontera eficiente de Markowitz con portafolios óptimos.
# ══════════════════════════════════════════════════════════════════════════════
 
router_frontera = APIRouter(tags=["Optimización — Markowitz"])
 
 
@router_frontera.post(
    "/frontera-eficiente",
    response_model=FronteraResponse,
    summary="Frontera eficiente de Markowitz",
    description=(
        "Simula portafolios aleatorios y construye la frontera eficiente. "
        "Retorna el portafolio de máximo Sharpe y el de mínima varianza "
        "con su composición exacta por activo."
    ),
)
async def calcular_frontera(
    body: FronteraRequest,
    data_service: DataService = Depends(get_data_service),
    markowitz: MarkowitzService = Depends(get_markowitz_service),
    macro_service: MacroService = Depends(get_macro_service),
):
    # Obtener Rf si no se especificó
    rf = body.tasa_libre_riesgo
    if rf is None:
        rf_pct = await macro_service.get_tasa_libre_riesgo()
        rf = rf_pct / 100   # Convertir a decimal
 
    df_rend = data_service.get_rendimientos_multiples(body.tickers)
 
    resultado = markowitz.construir_frontera(
        tickers=body.tickers,
        df_rendimientos=df_rend,
        tasa_libre_riesgo_anual=rf,
    )
 
    # Construir modelos de respuesta
    def build_portafolio(d: dict) -> PortafolioOptimo:
        return PortafolioOptimo(
            nombre=d["nombre"],
            pesos=d["pesos"],
            rendimiento_anual=d["rendimiento_anual"],
            volatilidad_anual=d["volatilidad_anual"],
            ratio_sharpe=d["ratio_sharpe"],
        )
 
    frontera = [PuntoFrontera(**p) for p in resultado["frontera_eficiente"]]
    nube = [PuntoFrontera(**p) for p in resultado["nube_portafolios"]]
 
    return FronteraResponse(
        tickers=resultado["tickers"],
        n_portafolios_simulados=resultado["n_portafolios_simulados"],
        tasa_libre_riesgo_usada=resultado["tasa_libre_riesgo_usada"],
        portafolio_max_sharpe=build_portafolio(resultado["portafolio_max_sharpe"]),
        portafolio_min_varianza=build_portafolio(resultado["portafolio_min_varianza"]),
        frontera_eficiente=frontera,
        nube_portafolios=nube,
        message=(
            f"Frontera eficiente construida con {body.n_portafolios:,} portafolios. "
            f"Rf usada: {rf*100:.2f}%."
        ),
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 8 — GET /alertas
# Panel de señales y alertas de trading por activo.
# ══════════════════════════════════════════════════════════════════════════════
 
router_alertas = APIRouter(tags=["Señales y Alertas"])
 
 
@router_alertas.get(
    "/alertas",
    response_model=AlertasResponse,
    summary="Señales de trading por activo",
    description=(
        "Evalúa MACD, RSI, Bollinger, Medias Móviles y Estocástico "
        "para cada activo y genera señales de COMPRA, VENTA o NEUTRAL "
        "con un resumen tipo semáforo."
    ),
)
async def get_alertas(
    tickers: list[str] = Query(
        default=None,
        description="Tickers a evaluar. Si se omite, usa los activos por defecto.",
    ),
    settings: SettingsDep = None,
    signal_engine: SignalEngine = Depends(get_signal_engine),
):
    tickers_usar = tickers or settings.default_tickers
    resultados = []
 
    for ticker in tickers_usar:
        try:
            ticker_limpio = validate_ticker(ticker)
            analisis = signal_engine.analizar_activo(ticker_limpio)
            resultados.append(analisis)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error analizando señales de %s: %s", ticker, exc)
            # Continúa con el siguiente ticker en lugar de fallar todo
            continue
 
    if not resultados:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudieron calcular señales para ningún activo.",
        )
 
    from app.models import AlertaIndividual, AlertasActivo
 
    activos_response = [
        AlertasActivo(
            ticker=r["ticker"],
            precio_actual=r["precio_actual"],
            senales=[AlertaIndividual(**s) for s in r["senales"]],
            resumen_semaforo=r["resumen_semaforo"],
            señales_compra=r["señales_compra"],
            señales_venta=r["señales_venta"],
            señales_neutral=r["señales_neutral"],
            interpretacion_global=r["interpretacion_global"],
        )
        for r in resultados
    ]
 
    return AlertasResponse(
        fecha_analisis=datetime.now(),
        activos_analizados=activos_response,
        message=f"Señales generadas para {len(activos_response)} activos.",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ROUTER 9 — GET /macro
# Indicadores macroeconómicos y métricas vs benchmark.
# ══════════════════════════════════════════════════════════════════════════════
 
router_macro = APIRouter(tags=["Macro y Benchmark"])
 
 
@router_macro.get(
    "/macro",
    response_model=MacroResponse,
    summary="Indicadores macroeconómicos y benchmark",
    description=(
        "Retorna tasa libre de riesgo (FRED), inflación y tasa real. "
        "Opcionalmente compara el portafolio contra el benchmark con "
        "Alpha de Jensen, Tracking Error, Information Ratio y Drawdown."
    ),
)
async def get_macro(
    tickers: list[str] = Query(default=None),
    pesos: list[float] = Query(
        default=None,
        description="Pesos del portafolio para el cálculo vs benchmark.",
    ),
    benchmark: str = Query(default=None),
    settings: SettingsDep = None,
    macro_service: MacroService = Depends(get_macro_service),
    data_service: DataService = Depends(get_data_service),
):
    # Obtener datos macro desde FRED
    rf = await macro_service.get_tasa_libre_riesgo()
    inflacion = await macro_service.get_inflacion_usa()
 
    indicadores_raw = await macro_service.get_indicadores_macro(rf, inflacion)
 
    from app.models import IndicadorMacro, MetricasBenchmark
 
    indicadores = [IndicadorMacro(**i) for i in indicadores_raw]
 
    # Calcular métricas vs benchmark si se provee un portafolio
    metricas = None
    if tickers and pesos and len(tickers) == len(pesos):
        try:
            benchmark_usar = benchmark or settings.benchmark_ticker
            pesos_dict = dict(zip([t.upper() for t in tickers], pesos))
            metricas_raw = macro_service.calcular_metricas_benchmark(
                pesos_portafolio=pesos_dict,
                benchmark_ticker=benchmark_usar,
                rf_anual=rf,
                data_service=data_service,
            )
            metricas = MetricasBenchmark(**metricas_raw)
        except Exception as exc:
            logger.warning("No se pudo calcular benchmark: %s", exc)
 
    return MacroResponse(
        fecha_actualizacion=datetime.now(),
        indicadores=indicadores,
        metricas_benchmark=metricas,
        message=f"Datos macro actualizados. Rf={rf:.2f}%, Inflación={inflacion:.2f}%.",
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════
 
app = create_app()