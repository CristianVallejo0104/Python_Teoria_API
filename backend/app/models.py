from datetime import date, datetime
from typing import Annotated, Optional
 
from pydantic import BaseModel, Field, field_validator, model_validator
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MODELOS BASE
# ══════════════════════════════════════════════════════════════════════════════
 
class APIResponse(BaseModel):
    """Envoltorio genérico para todas las respuestas de la API."""
    status: str = Field(default="ok", description="Estado de la respuesta")
    message: str = Field(default="", description="Mensaje informativo opcional")
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /activos
# ══════════════════════════════════════════════════════════════════════════════
 
class ActivoInfo(BaseModel):
    """Información básica de un activo del portafolio."""
    ticker: str = Field(..., description="Símbolo bursátil", examples=["AAPL"])
    nombre: str = Field(..., description="Nombre de la empresa")
    sector: str = Field(default="Desconocido", description="Sector económico")
    moneda: str = Field(default="USD", description="Moneda de cotización")
 
 
class ActivosResponse(APIResponse):
    """Respuesta del endpoint GET /activos."""
    activos: list[ActivoInfo] = Field(..., description="Lista de activos disponibles")
    total: int = Field(..., description="Número total de activos", ge=1)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /precios/{ticker}
# ══════════════════════════════════════════════════════════════════════════════
 
class PreciosPrecioRow(BaseModel):
    """Una fila de precios históricos (un día de trading)."""
    fecha: date = Field(..., description="Fecha de la sesión")
    apertura: float = Field(..., description="Precio de apertura", ge=0)
    maximo: float = Field(..., description="Precio máximo del día", ge=0)
    minimo: float = Field(..., description="Precio mínimo del día", ge=0)
    cierre: float = Field(..., description="Precio de cierre ajustado", ge=0)
    volumen: int = Field(..., description="Volumen negociado", ge=0)
 
 
class PreciosResponse(APIResponse):
    """Respuesta del endpoint GET /precios/{ticker}."""
    ticker: str
    fecha_inicio: date
    fecha_fin: date
    total_registros: int = Field(..., ge=1)
    precios: list[PreciosPrecioRow]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /rendimientos/{ticker}
# ══════════════════════════════════════════════════════════════════════════════
 
class EstadisticasDescriptivas(BaseModel):
    """Estadísticas descriptivas de una serie de rendimientos."""
    media: float = Field(..., description="Media aritmética de los rendimientos")
    mediana: float = Field(..., description="Mediana")
    desviacion_std: float = Field(..., description="Desviación estándar (volatilidad histórica)", ge=0)
    asimetria: float = Field(..., description="Skewness — valores negativos indican cola izquierda pesada")
    curtosis: float = Field(..., description="Exceso de curtosis — >0 indica colas más pesadas que la normal")
    minimo: float = Field(..., description="Rendimiento mínimo observado (peor día)")
    maximo: float = Field(..., description="Rendimiento máximo observado (mejor día)")
    percentil_5: float = Field(..., description="Percentil 5 — base para VaR histórico")
 
    # Pruebas de normalidad
    jarque_bera_stat: float = Field(..., description="Estadístico Jarque-Bera")
    jarque_bera_pvalue: float = Field(..., description="p-valor Jarque-Bera — <0.05 rechaza normalidad", ge=0, le=1)
    shapiro_wilk_stat: float = Field(..., description="Estadístico Shapiro-Wilk")
    shapiro_wilk_pvalue: float = Field(..., description="p-valor Shapiro-Wilk", ge=0, le=1)
    es_normal: bool = Field(..., description="True si ambas pruebas no rechazan normalidad al 5%")
 
 
class RendimientoRow(BaseModel):
    """Rendimiento diario de un activo."""
    fecha: date
    rendimiento_simple: float = Field(..., description="Rt = (Pt - Pt-1) / Pt-1")
    rendimiento_log: float = Field(..., description="rt = ln(Pt / Pt-1)")
 
 
class RendimientosResponse(APIResponse):
    """Respuesta del endpoint GET /rendimientos/{ticker}."""
    ticker: str
    total_observaciones: int = Field(..., ge=1)
    rendimientos: list[RendimientoRow]
    estadisticas: EstadisticasDescriptivas
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /indicadores/{ticker}
# ══════════════════════════════════════════════════════════════════════════════
 
class IndicadoresFila(BaseModel):
    """Fila de indicadores técnicos para una fecha dada."""
    fecha: date
    precio_cierre: float = Field(..., ge=0)
    sma_20: Optional[float] = Field(None, description="Media móvil simple 20 períodos")
    sma_50: Optional[float] = Field(None, description="Media móvil simple 50 períodos")
    ema_20: Optional[float] = Field(None, description="Media móvil exponencial 20 períodos")
    banda_superior: Optional[float] = Field(None, description="Banda de Bollinger superior")
    banda_media: Optional[float] = Field(None, description="Banda de Bollinger media (SMA20)")
    banda_inferior: Optional[float] = Field(None, description="Banda de Bollinger inferior")
    rsi: Optional[float] = Field(None, description="RSI (0-100)", ge=0, le=100)
    macd: Optional[float] = Field(None, description="Línea MACD")
    macd_signal: Optional[float] = Field(None, description="Línea de señal del MACD")
    macd_histogram: Optional[float] = Field(None, description="Histograma MACD = MACD - Señal")
    stoch_k: Optional[float] = Field(None, description="Oscilador Estocástico %K", ge=0, le=100)
    stoch_d: Optional[float] = Field(None, description="Oscilador Estocástico %D", ge=0, le=100)
 
 
class IndicadoresResponse(APIResponse):
    """Respuesta del endpoint GET /indicadores/{ticker}."""
    ticker: str
    total_registros: int = Field(..., ge=1)
    indicadores: list[IndicadoresFila]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /var
# ══════════════════════════════════════════════════════════════════════════════
 
class VaRRequest(BaseModel):
    """
    Request para el cálculo de VaR y CVaR de un portafolio.
    Incluye validadores personalizados — punto clave para la sustentación.
    """
    tickers: list[str] = Field(
        ...,
        description="Lista de tickers del portafolio",
        min_length=1,
        max_length=20,
        examples=[["AAPL", "MSFT", "GOOGL"]],
    )
    pesos: list[float] = Field(
        ...,
        description="Pesos de cada activo. Deben sumar 1.0",
        min_length=1,
        max_length=20,
        examples=[[0.4, 0.35, 0.25]],
    )
    nivel_confianza: float = Field(
        default=0.95,
        description="Nivel de confianza del VaR (ej: 0.95 para 95%)",
        ge=0.90,
        le=0.999,
    )
    horizonte_dias: int = Field(
        default=1,
        description="Horizonte temporal en días hábiles",
        ge=1,
        le=252,
    )
    valor_portafolio: float = Field(
        default=10_000.0,
        description="Valor total del portafolio en USD para expresar VaR en dinero",
        gt=0,
    )
 
    # ── Validadores personalizados (@field_validator) ─────────────────────────
 
    @field_validator("tickers")
    @classmethod
    def tickers_en_mayusculas(cls, v: list[str]) -> list[str]:
        """Normaliza todos los tickers a mayúsculas y elimina espacios."""
        return [t.upper().strip() for t in v]
 
    @field_validator("pesos")
    @classmethod
    def pesos_positivos(cls, v: list[float]) -> list[float]:
        """Todos los pesos deben ser positivos."""
        if any(p < 0 for p in v):
            raise ValueError("Todos los pesos deben ser mayores o iguales a 0.")
        return v
 
    @model_validator(mode="after")
    def validar_consistencia_portafolio(self) -> "VaRRequest":
        """
        Validación cruzada entre tickers y pesos:
        1. La cantidad de tickers debe coincidir con la cantidad de pesos.
        2. Los pesos deben sumar 1.0 (con tolerancia de ±0.01).
        """
        if len(self.tickers) != len(self.pesos):
            raise ValueError(
                f"La cantidad de tickers ({len(self.tickers)}) debe coincidir "
                f"con la cantidad de pesos ({len(self.pesos)})."
            )
 
        suma = sum(self.pesos)
        if abs(suma - 1.0) > 0.01:
            raise ValueError(
                f"Los pesos deben sumar 1.0. Suma actual: {suma:.4f}. "
                f"Ajusta los pesos o usa pesos iguales (1/n cada uno)."
            )
 
        return self
 
 
class VaRResultado(BaseModel):
    """Resultado de VaR y CVaR para un método específico."""
    metodo: str = Field(..., description="Método utilizado: parametrico, historico, montecarlo")
    var_porcentaje: float = Field(..., description="VaR expresado como porcentaje del portafolio")
    var_dolares: float = Field(..., description="VaR en USD (basado en valor_portafolio)")
    cvar_porcentaje: float = Field(..., description="CVaR (Expected Shortfall) en porcentaje")
    cvar_dolares: float = Field(..., description="CVaR en USD")
    interpretacion: str = Field(..., description="Texto explicativo del resultado en lenguaje simple")
 
 
class VaRResponse(APIResponse):
    """Respuesta del endpoint POST /var."""
    ticker_portafolio: list[str]
    pesos: list[float]
    nivel_confianza: float
    horizonte_dias: int
    valor_portafolio: float
    resultados: list[VaRResultado]
    mejor_metodo_recomendado: str = Field(
        ..., description="Método recomendado según las propiedades del portafolio"
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /capm
# ══════════════════════════════════════════════════════════════════════════════
 
class CAPMActivoResultado(BaseModel):
    """Resultado CAPM para un activo individual."""
    ticker: str
    beta: float = Field(..., description="Beta respecto al benchmark")
    clasificacion: str = Field(
        ..., description="Agresivo (beta>1.2), Neutro (0.8-1.2), Defensivo (<0.8)"
    )
    rendimiento_mercado_anual: float = Field(..., description="Rendimiento anualizado del benchmark")
    tasa_libre_riesgo_anual: float = Field(..., description="Tasa libre de riesgo obtenida de FRED (%)")
    rendimiento_esperado_capm: float = Field(
        ..., description="E(Ri) = Rf + β × (Rm - Rf)"
    )
    prima_riesgo: float = Field(..., description="β × (Rm - Rf) — premio por riesgo sistemático")
    r_cuadrado: float = Field(..., description="R² de la regresión — % del riesgo explicado por el mercado", ge=0, le=1)
    alpha_jensen: float = Field(..., description="α = rendimiento real - rendimiento CAPM esperado")
 
 
class CAPMResponse(APIResponse):
    """Respuesta del endpoint GET /capm."""
    benchmark: str
    periodo_analisis: str
    tasa_libre_riesgo_fuente: str = Field(default="FRED - US Treasury 3M")
    activos: list[CAPMActivoResultado]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /frontera-eficiente
# ══════════════════════════════════════════════════════════════════════════════
 
class FronteraRequest(BaseModel):
    """Request para construir la frontera eficiente de Markowitz."""
    tickers: list[str] = Field(
        ...,
        description="Tickers del universo de activos a analizar",
        min_length=2,
        max_length=15,
        examples=[["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]],
    )
    n_portafolios: int = Field(
        default=10_000,
        description="Número de portafolios aleatorios a simular",
        ge=1_000,
        le=50_000,
    )
    tasa_libre_riesgo: Optional[float] = Field(
        default=None,
        description="Tasa libre de riesgo anual (si None, se obtiene automáticamente de FRED)",
        ge=0,
        le=0.20,
    )
 
    @field_validator("tickers")
    @classmethod
    def tickers_validos(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("No se permiten tickers duplicados en el portafolio.")
        return [t.upper().strip() for t in v]
 
 
class PortafolioOptimo(BaseModel):
    """Composición y métricas de un portafolio óptimo específico."""
    nombre: str = Field(..., description="Ej: 'Máximo Sharpe' o 'Mínima Varianza'")
    pesos: dict[str, float] = Field(..., description="Ticker → peso en el portafolio")
    rendimiento_anual: float = Field(..., description="Rendimiento esperado anualizado")
    volatilidad_anual: float = Field(..., description="Desviación estándar anualizada (riesgo)")
    ratio_sharpe: float = Field(..., description="(Rendimiento - Rf) / Volatilidad")
 
 
class PuntoFrontera(BaseModel):
    """Un punto de la frontera eficiente (para graficar)."""
    rendimiento: float
    volatilidad: float
    ratio_sharpe: float
 
 
class FronteraResponse(APIResponse):
    """Respuesta del endpoint POST /frontera-eficiente."""
    tickers: list[str]
    n_portafolios_simulados: int
    tasa_libre_riesgo_usada: float
    portafolio_max_sharpe: PortafolioOptimo
    portafolio_min_varianza: PortafolioOptimo
    frontera_eficiente: list[PuntoFrontera] = Field(
        ..., description="Puntos de la frontera (subconjunto para graficar)"
    )
    nube_portafolios: list[PuntoFrontera] = Field(
        ..., description="Muestra de portafolios aleatorios para visualizar el conjunto factible"
    )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /alertas
# ══════════════════════════════════════════════════════════════════════════════
 
class TipoSenal(str):
    COMPRA = "COMPRA"
    VENTA = "VENTA"
    NEUTRAL = "NEUTRAL"
 
 
class AlertaIndividual(BaseModel):
    """Una señal de trading generada por un indicador."""
    indicador: str = Field(..., description="Nombre del indicador que genera la señal")
    senal: str = Field(..., description="COMPRA, VENTA o NEUTRAL")
    valor_actual: float = Field(..., description="Valor actual del indicador")
    descripcion: str = Field(..., description="Explicación en lenguaje simple de la señal")
    fuerza: str = Field(..., description="FUERTE, MODERADA o DÉBIL")
 
 
class AlertasActivo(BaseModel):
    """Resumen de señales para un activo."""
    ticker: str
    precio_actual: float = Field(..., ge=0)
    senales: list[AlertaIndividual]
    resumen_semaforo: str = Field(
        ..., description="VERDE (mayoría compra), ROJO (mayoría venta), AMARILLO (mixto)"
    )
    señales_compra: int = Field(..., ge=0)
    señales_venta: int = Field(..., ge=0)
    señales_neutral: int = Field(..., ge=0)
    interpretacion_global: str = Field(..., description="Texto interpretativo consolidado")
 
 
class AlertasResponse(APIResponse):
    """Respuesta del endpoint GET /alertas."""
    fecha_analisis: datetime
    activos_analizados: list[AlertasActivo]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /macro
# ══════════════════════════════════════════════════════════════════════════════
 
class IndicadorMacro(BaseModel):
    """Un indicador macroeconómico individual."""
    nombre: str = Field(..., description="Nombre del indicador")
    valor: float = Field(..., description="Valor actual")
    unidad: str = Field(..., description="Unidad: %, USD, índice, etc.")
    fuente: str = Field(..., description="Fuente de datos: FRED, Banco de la República, etc.")
    fecha_dato: str = Field(..., description="Fecha del último dato disponible")
    descripcion: str = Field(..., description="Qué representa este indicador")
 
 
class MetricasBenchmark(BaseModel):
    """Comparación del portafolio vs benchmark."""
    benchmark_ticker: str
    rendimiento_acumulado_portafolio: float
    rendimiento_acumulado_benchmark: float
    alpha_jensen: float = Field(..., description="Retorno adicional vs lo esperado por CAPM")
    tracking_error: float = Field(..., description="Desviación estándar del error de seguimiento", ge=0)
    information_ratio: float = Field(
        ..., description="Alpha / Tracking Error — mide eficiencia del gestor"
    )
    maximo_drawdown_portafolio: float = Field(
        ..., description="Máxima caída desde un pico — medida de riesgo a la baja", le=0
    )
    maximo_drawdown_benchmark: float = Field(..., le=0)
    ratio_sharpe_portafolio: float
    ratio_sharpe_benchmark: float
    supera_benchmark: bool = Field(..., description="True si el portafolio supera al benchmark en Sharpe")
 
 
class MacroResponse(APIResponse):
    """Respuesta del endpoint GET /macro."""
    fecha_actualizacion: datetime
    indicadores: list[IndicadorMacro]
    metricas_benchmark: Optional[MetricasBenchmark] = None
 
 
# ══════════════════════════════════════════════════════════════════════════════
# MODELOS PARA ARCH/GARCH (usados internamente por services.py)
# ══════════════════════════════════════════════════════════════════════════════
 
class ModeloGARCHResultado(BaseModel):
    """Resultado del ajuste de un modelo ARCH/GARCH."""
    especificacion: str = Field(..., description="Ej: GARCH(1,1), ARCH(1), EGARCH(1,1)")
    log_likelihood: float
    aic: float = Field(..., description="Criterio de información de Akaike — menor es mejor")
    bic: float = Field(..., description="Criterio de información Bayesiano — menor es mejor")
    omega: float = Field(..., description="Constante de la ecuación de varianza")
    alpha: list[float] = Field(..., description="Coeficientes ARCH (efecto de shocks pasados)")
    beta: list[float] = Field(..., description="Coeficientes GARCH (efecto de varianza pasada)")
    jarque_bera_residuos_pvalue: float = Field(..., ge=0, le=1)
    es_modelo_seleccionado: bool = Field(..., description="True si este modelo tiene el menor AIC")
    pronostico_volatilidad_1d: float = Field(..., description="Volatilidad pronosticada para el próximo día", ge=0)
    pronostico_volatilidad_5d: float = Field(..., description="Volatilidad pronosticada a 5 días", ge=0)
 
 
class GARCHResponse(APIResponse):
    """Respuesta interna del análisis GARCH (retornada por el endpoint de rendimientos)."""
    ticker: str
    modelos: list[ModeloGARCHResultado]
    modelo_recomendado: str
    interpretacion: str