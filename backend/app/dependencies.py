import logging
from functools import lru_cache
from typing import Annotated
 
import httpx
import yfinance as yf
from fastapi import Depends, HTTPException, status
 
from app.config import Settings, get_settings
 
logger = logging.getLogger(__name__)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIA 1: Configuración
# Inyecta el objeto Settings en cualquier endpoint que lo necesite.
# ══════════════════════════════════════════════════════════════════════════════
 
SettingsDep = Annotated[Settings, Depends(get_settings)]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIA 2: Cliente HTTP asíncrono reutilizable
# Un solo cliente httpx para todas las llamadas a APIs externas,
# con timeout configurado para no bloquear el servidor.
# ══════════════════════════════════════════════════════════════════════════════
 
@lru_cache
def _get_http_client() -> httpx.AsyncClient:
    """Crea el cliente HTTP una sola vez (singleton)."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers={"User-Agent": "RiskLab-USTA/1.0"},
    )
 
 
async def get_http_client() -> httpx.AsyncClient:
    """
    Dependencia que provee el cliente HTTP.
    Si la creación falla, lanza 503 en lugar de un error interno genérico.
    """
    try:
        return _get_http_client()
    except Exception as exc:
        logger.error("Error al crear cliente HTTP: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo inicializar el cliente HTTP.",
        ) from exc
 
 
HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIA 3: Servicio de datos de mercado (yfinance)
# Valida que el ticker exista antes de pasarlo a los servicios de cálculo.
# ══════════════════════════════════════════════════════════════════════════════
 
def validate_ticker(ticker: str) -> str:
    """
    Valida que el ticker tenga formato válido.
    No hace llamada a la API aquí — solo valida la forma del string.
    La validación de existencia ocurre en los servicios al descargar datos.
    """
    ticker = ticker.upper().strip()
 
    if len(ticker) < 1 or len(ticker) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticker '{ticker}' inválido. Debe tener entre 1 y 10 caracteres.",
        )
 
    # Solo letras, números, puntos y guiones (cubre ^GSPC, BRK.B, etc.)
    import re
    if not re.match(r"^[\w\.\-\^]+$", ticker):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticker '{ticker}' contiene caracteres no permitidos.",
        )
 
    return ticker
 
 
ValidTickerDep = Annotated[str, Depends(validate_ticker)]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIA 4: Servicio FRED (datos macroeconómicos)
# Provee una función lista para llamar al API de FRED.
# ══════════════════════════════════════════════════════════════════════════════
 
class FredService:
    """
    Servicio para obtener datos macroeconómicos del Federal Reserve (FRED).
    Encapsula las llamadas HTTP y el manejo de errores de conexión.
    """
 
    BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    API_URL = "https://api.stlouisfed.org/fred/series/observations"
 
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self.client = client
        self.api_key = api_key
 
    async def get_series(self, series_id: str, limit: int = 1) -> list[dict]:
        """
        Descarga las últimas `limit` observaciones de una serie FRED.
        Retorna lista de dicts con 'date' y 'value'.
        Lanza HTTP 503 si FRED no responde.
        """
        if not self.api_key:
            # Si no hay key, retorna un valor placeholder
            logger.warning("FRED_API_KEY no configurada. Usando tasa libre de riesgo por defecto.")
            return [{"date": "N/A", "value": "4.5"}]
 
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
 
        try:
            response = await self.client.get(self.API_URL, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("observations", [])
        except httpx.TimeoutException:
            logger.error("Timeout al conectar con FRED para serie %s", series_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El servicio FRED no respondió a tiempo. Intente más tarde.",
            )
        except httpx.HTTPStatusError as exc:
            logger.error("Error HTTP de FRED: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error al obtener datos de FRED: {exc.response.status_code}",
            )
 
 
def get_fred_service(
    client: HttpClientDep,
    settings: SettingsDep,
) -> FredService:
    """Fábrica de FredService — inyectada con Depends()."""
    return FredService(client=client, api_key=settings.fred_api_key)
 
 
FredServiceDep = Annotated[FredService, Depends(get_fred_service)]
 
 
# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIA 5: Decorador de tiempo de ejecución (buenas prácticas Semana 1)
# Cumple el requisito de implementar al menos un decorador personalizado.
# ══════════════════════════════════════════════════════════════════════════════
 
import time
from functools import wraps
from typing import Callable
 
 
def timing_decorator(func: Callable) -> Callable:
    """
    Decorador que registra el tiempo de ejecución de cualquier función.
    Uso: @timing_decorator sobre funciones de servicios pesados (GARCH, Monte Carlo).
    """
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info("[TIMING] %s ejecutó en %.3f segundos", func.__name__, elapsed)
        return result
 
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info("[TIMING] %s ejecutó en %.3f segundos", func.__name__, elapsed)
        return result
 
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
 
 
def cache_result(ttl_seconds: int = 300):
    """
    Decorador de caché simple con TTL (time-to-live).
    Evita llamar a APIs externas en cada request — cumple recomendación del profesor.
    ttl_seconds=300 → los datos se cachean por 5 minutos.
    """
    cache: dict = {}
 
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.time()
 
            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < ttl_seconds:
                    logger.debug("[CACHE HIT] %s", func.__name__)
                    return result
 
            result = func(*args, **kwargs)
            cache[key] = (result, now)
            logger.debug("[CACHE SET] %s", func.__name__)
            return result
 
        return wrapper
    return decorator