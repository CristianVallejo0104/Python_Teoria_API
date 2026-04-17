from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
 
 
class Settings(BaseSettings):
    """
    Clase de configuración global.
    Cada atributo puede sobreescribirse con una variable de entorno del mismo nombre
    (en mayúsculas) o desde el archivo .env ubicado en backend/.env
    """
 
    # ── Metadatos de la aplicación ────────────────────────────────────────────
    app_name: str = "RiskLab USTA API"
    app_version: str = "1.0.0"
    debug: bool = False
 
    # ── API Keys externas ─────────────────────────────────────────────────────
    # Obtener en: https://fred.stlouisfed.org/docs/api/api_key.html
    fred_api_key: str = ""
 
    # Obtener en: https://finnhub.io/
    finnhub_api_key: str = ""
 
    # Obtener en: https://www.alphavantage.co/support/#api-key
    alpha_vantage_api_key: str = ""
 
    # ── Parámetros por defecto del análisis de riesgo ─────────────────────────
    # Activos predeterminados del portafolio (al menos 5, de distintos sectores)
    default_tickers: list[str] = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
 
    # Horizonte histórico en años para descarga de datos
    default_years: int = 3
 
    # Ticker del índice de mercado usado como benchmark
    benchmark_ticker: str = "^GSPC"  # S&P 500
 
    # Nivel de confianza para VaR (0.95 = 95%)
    var_confidence_level: float = 0.95
 
    # Número de simulaciones Monte Carlo
    montecarlo_simulations: int = 10_000
 
    # Número de portafolios aleatorios para frontera eficiente
    markowitz_portfolios: int = 10_000
 
    # Parámetros de indicadores técnicos
    sma_short_period: int = 20
    sma_long_period: int = 50
    ema_period: int = 20
    rsi_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    stochastic_k_period: int = 14
    stochastic_d_period: int = 3
 
    # ── Series FRED para datos macro ──────────────────────────────────────────
    # DGS3MO = Treasury 3-Month (tasa libre de riesgo proxy)
    fred_risk_free_series: str = "DGS3MO"
    # CPIAUCSL = Consumer Price Index (inflación USA)
    fred_inflation_series: str = "CPIAUCSL"
 
    # ── CORS (permite que el frontend Streamlit consuma el backend) ───────────
    cors_origins: list[str] = ["http://localhost:8501", "http://127.0.0.1:8501"]
 
    # ── Configuración del archivo .env ────────────────────────────────────────
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Permite ignorar variables extra que no estén definidas aquí
        extra="ignore",
    )
 
 
@lru_cache
def get_settings() -> Settings:
    """
    Retorna una instancia única de Settings (patrón singleton via lru_cache).
    Al estar cacheada, el archivo .env solo se lee una vez durante toda
    la vida de la aplicación — no en cada request.
 
    Uso en endpoints:
        settings: Settings = Depends(get_settings)
    """
    return Settings()