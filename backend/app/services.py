import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional
 
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import HTTPException, status
from scipy import stats
 
from app.dependencies import cache_result, timing_decorator
 
logger = logging.getLogger(__name__)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 1: DataService
# Responsabilidad única: obtener datos limpios desde yfinance.
# ══════════════════════════════════════════════════════════════════════════════
 
class DataService:
    """
    Servicio de datos de mercado.
 
    Encapsula todas las llamadas a yfinance y aplica limpieza
    antes de entregar datos al resto de los servicios.
 
    Métodos principales:
        get_precios()       → DataFrame con OHLCV histórico
        get_rendimientos()  → Serie de rendimientos log-normales
        get_info_activo()   → Metadata del ticker (nombre, sector, etc.)
    """
 
    def __init__(self, years: int = 3):
        """
        Parameters
        ----------
        years : int
            Años de historia a descargar por defecto (mínimo 2 según la guía).
        """
        self.years = years
 
    # ── Método principal: descarga de precios ─────────────────────────────────
 
    @timing_decorator
    def get_precios(
        self,
        ticker: str,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Descarga precios históricos OHLCV de yfinance y los limpia.
 
        Returns
        -------
        pd.DataFrame con columnas: fecha, apertura, maximo, minimo, cierre, volumen
        Lanza HTTPException 404 si el ticker no existe.
        Lanza HTTPException 503 si yfinance no responde.
        """
        # Calcular rango de fechas si no se especifica
        if fecha_fin is None:
            fecha_fin = date.today()
        if fecha_inicio is None:
            fecha_inicio = fecha_fin - timedelta(days=self.years * 365)
 
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(
                start=fecha_inicio.strftime("%Y-%m-%d"),
                end=fecha_fin.strftime("%Y-%m-%d"),
                auto_adjust=True,   # Precios ajustados por dividendos y splits
            )
        except Exception as exc:
            logger.error("Error al conectar con yfinance para %s: %s", ticker, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"No se pudo conectar con Yahoo Finance. Intente más tarde.",
            ) from exc
 
        # Validar que retornó datos
        if df is None or df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticker '{ticker}' no encontrado o sin datos en el rango solicitado.",
            )
 
        # Limpiar y renombrar columnas
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Normalizar nombres de columna a minúsculas para compatibilidad
        df.columns = [str(c).strip() for c in df.columns]
        col_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl == "open":        col_map[c] = "apertura"
            elif cl == "high":      col_map[c] = "maximo"
            elif cl == "low":       col_map[c] = "minimo"
            elif cl == "close":     col_map[c] = "cierre"
            elif cl == "volume":    col_map[c] = "volumen"
        df = df.rename(columns=col_map)

        cols_necesarias = ["apertura", "maximo", "minimo", "cierre", "volumen"]
        cols_presentes = [c for c in cols_necesarias if c in df.columns]
        if len(cols_presentes) < 4:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticker '{ticker}' sin datos OHLCV válidos.",
            )
        df = df[cols_presentes].copy()
        if "volumen" not in df.columns:
            df["volumen"] = 0

        df.index = pd.to_datetime(df.index).normalize()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index.name = "fecha"
 
        # Estrategia de manejo de valores faltantes:
        # - Forward fill para huecos de 1-2 días (fines de semana, feriados)
        # - Drop para huecos mayores que sugieren problema de datos
        df = df.ffill().dropna()
 
        # Forzar tipos correctos
        df["volumen"] = df["volumen"].astype(int)
 
        logger.info("Descargados %d registros para %s", len(df), ticker)
        return df
 
    # ── Información del activo ─────────────────────────────────────────────────
 
    @cache_result(ttl_seconds=3600)   # Info del activo cambia poco — cache 1 hora
    def get_info_activo(self, ticker: str) -> dict:
        """
        Retorna metadata del ticker: nombre, sector, moneda, descripción.
        Usa cache de 1 hora para no llamar a yfinance en cada request.
        """
        try:
            info = yf.Ticker(ticker).info
            return {
                "ticker": ticker,
                "nombre": info.get("longName") or info.get("shortName", ticker),
                "sector": info.get("sector", "Desconocido"),
                "industria": info.get("industry", "Desconocida"),
                "moneda": info.get("currency", "USD"),
                "pais": info.get("country", "Desconocido"),
                "descripcion": (info.get("longBusinessSummary", "")[:300] + "...")
                               if info.get("longBusinessSummary") else "",
            }
        except Exception as exc:
            logger.warning("No se pudo obtener info de %s: %s", ticker, exc)
            # Retorna valores mínimos en lugar de fallar
            return {
                "ticker": ticker,
                "nombre": ticker,
                "sector": "Desconocido",
                "industria": "Desconocida",
                "moneda": "USD",
                "pais": "Desconocido",
                "descripcion": "",
            }
 
    # ── Cálculo de rendimientos ────────────────────────────────────────────────
 
    def get_rendimientos(
        self,
        ticker: str,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Calcula rendimientos simples y logarítmicos a partir de precios de cierre.
 
        Rendimiento simple:  Rt = (Pt - Pt-1) / Pt-1
        Rendimiento log:     rt = ln(Pt / Pt-1)
 
        Se prefieren los log-rendimientos por sus propiedades:
          - Aditividad temporal: r(t,t+n) = r(t,t+1) + ... + r(t+n-1,t+n)
          - Aproximadamente estacionarios
          - Simétricamente distribuidos respecto a ganancias/pérdidas
 
        Returns
        -------
        pd.DataFrame con columnas: rendimiento_simple, rendimiento_log
        Sin la primera fila (NaN por diferencia).
        """
        df_precios = self.get_precios(ticker, fecha_inicio, fecha_fin)
        cierre = df_precios["cierre"]
 
        df_rend = pd.DataFrame(index=cierre.index)
        df_rend["rendimiento_simple"] = cierre.pct_change()
        df_rend["rendimiento_log"] = np.log(cierre / cierre.shift(1))
 
        # Eliminar primer registro (siempre NaN por la diferencia)
        df_rend = df_rend.dropna()
 
        return df_rend
 
    # ── Estadísticas descriptivas ──────────────────────────────────────────────
 
    def calcular_estadisticas(self, rendimientos: pd.Series) -> dict:
        """
        Calcula estadísticas descriptivas y pruebas de normalidad
        para una serie de rendimientos.
 
        Pruebas de normalidad:
          - Jarque-Bera: evalúa si la asimetría y curtosis son consistentes
            con una distribución normal. H0: la serie es normal.
          - Shapiro-Wilk: comprueba si la muestra proviene de una distribución
            normal. Más potente que JB para muestras pequeñas.
 
        Un p-valor < 0.05 rechaza la hipótesis nula de normalidad.
        En finanzas, casi siempre se rechaza → colas pesadas (fat tails).
        """
        # Prueba Jarque-Bera
        jb_stat, jb_pvalue = stats.jarque_bera(rendimientos.dropna())
 
        # Prueba Shapiro-Wilk (máximo 5000 obs para eficiencia)
        muestra_sw = rendimientos.dropna()
        if len(muestra_sw) > 5000:
            muestra_sw = muestra_sw.sample(5000, random_state=42)
        sw_stat, sw_pvalue = stats.shapiro(muestra_sw)
 
        return {
            "media": float(rendimientos.mean()),
            "mediana": float(rendimientos.median()),
            "desviacion_std": float(rendimientos.std()),
            "asimetria": float(rendimientos.skew()),
            "curtosis": float(rendimientos.kurtosis()),    # Exceso de curtosis
            "minimo": float(rendimientos.min()),
            "maximo": float(rendimientos.max()),
            "percentil_5": float(rendimientos.quantile(0.05)),
            "jarque_bera_stat": float(jb_stat),
            "jarque_bera_pvalue": float(jb_pvalue),
            "shapiro_wilk_stat": float(sw_stat),
            "shapiro_wilk_pvalue": float(sw_pvalue),
            # Es normal si AMBAS pruebas no rechazan H0 al 5%
            "es_normal": bool(jb_pvalue > 0.05 and sw_pvalue > 0.05),
        }
 
    # ── Descarga múltiple (para Markowitz y VaR de portafolio) ───────────────
 
    @timing_decorator
    def get_precios_multiples(
        self,
        tickers: list[str],
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Descarga precios de cierre de varios tickers en un solo DataFrame.
        Columnas = tickers, índice = fechas.
        Solo incluye fechas donde TODOS los tickers tienen datos.
        """
        if fecha_fin is None:
            fecha_fin = date.today()
        if fecha_inicio is None:
            fecha_inicio = fecha_fin - timedelta(days=self.years * 365)
 
        try:
            df = yf.download(
                tickers=tickers,
                start=fecha_inicio.strftime("%Y-%m-%d"),
                end=fecha_fin.strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )["Close"]
        except Exception as exc:
            logger.error("Error en descarga múltiple: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudieron descargar los datos del portafolio.",
            ) from exc
 
        # Si solo hay un ticker, yfinance retorna una Serie — convertir a DataFrame
        if isinstance(df, pd.Series):
            df = df.to_frame(name=tickers[0])
 
        # Renombrar columnas a mayúsculas para consistencia
        df.columns = [str(c).upper() for c in df.columns]
 
        # Eliminar fechas con algún NaN (requiere datos completos para el portafolio)
        df = df.dropna()
 
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sin datos para el portafolio {tickers} en el rango solicitado.",
            )
 
        return df
 
    def get_rendimientos_multiples(
        self,
        tickers: list[str],
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Retorna log-rendimientos diarios de múltiples activos.
        Cada columna es un ticker.
        """
        precios = self.get_precios_multiples(tickers, fecha_inicio, fecha_fin)
        return np.log(precios / precios.shift(1)).dropna()
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 2: TechnicalIndicators
# Responsabilidad única: calcular indicadores técnicos sobre precios de cierre.
# ══════════════════════════════════════════════════════════════════════════════
 
class TechnicalIndicators:
    """
    Calcula indicadores técnicos clásicos sobre una serie de precios.
 
    Todos los métodos reciben un pd.Series de precios y retornan
    pd.Series o pd.DataFrame con los valores del indicador.
 
    Indicadores implementados:
        sma()         → Media móvil simple
        ema()         → Media móvil exponencial
        bollinger()   → Bandas de Bollinger
        rsi()         → Relative Strength Index
        macd()        → Moving Average Convergence Divergence
        stochastic()  → Oscilador Estocástico %K y %D
        calcular_todos() → DataFrame con todos los indicadores juntos
    """
 
    # ── SMA: Simple Moving Average ─────────────────────────────────────────────
 
    @staticmethod
    def sma(precios: pd.Series, periodo: int = 20) -> pd.Series:
        """
        Media Móvil Simple.
 
        Fórmula: SMA(t) = (P(t) + P(t-1) + ... + P(t-n+1)) / n
 
        Interpretación:
          - Precio por encima de SMA → tendencia alcista
          - Precio por debajo de SMA → tendencia bajista
          - Cruce SMA corta > SMA larga → Golden Cross (señal de compra)
          - Cruce SMA corta < SMA larga → Death Cross (señal de venta)
        """
        return precios.rolling(window=periodo).mean()
 
    # ── EMA: Exponential Moving Average ───────────────────────────────────────
 
    @staticmethod
    def ema(precios: pd.Series, periodo: int = 20) -> pd.Series:
        """
        Media Móvil Exponencial.
        Da mayor peso a los precios recientes que la SMA.
 
        Factor de suavización: α = 2 / (n + 1)
        EMA(t) = P(t) × α + EMA(t-1) × (1 - α)
 
        Más reactiva a cambios recientes que la SMA.
        """
        return precios.ewm(span=periodo, adjust=False).mean()
 
    # ── Bandas de Bollinger ────────────────────────────────────────────────────
 
    @staticmethod
    def bollinger(
        precios: pd.Series,
        periodo: int = 20,
        desviaciones: float = 2.0,
    ) -> pd.DataFrame:
        """
        Bandas de Bollinger.
 
        Banda media   = SMA(n)
        Banda superior = SMA(n) + k × σ(n)
        Banda inferior = SMA(n) - k × σ(n)
        donde σ(n) es la desviación estándar móvil de n períodos.
 
        Interpretación:
          - Precio toca banda superior → posible sobrecompra (señal de venta)
          - Precio toca banda inferior → posible sobreventa (señal de compra)
          - Las bandas se estrechan → baja volatilidad, posible explosión
          - Las bandas se ensanchan → alta volatilidad
        """
        media = precios.rolling(window=periodo).mean()
        sigma = precios.rolling(window=periodo).std()
 
        return pd.DataFrame({
            "banda_media": media,
            "banda_superior": media + desviaciones * sigma,
            "banda_inferior": media - desviaciones * sigma,
        }, index=precios.index)
 
    # ── RSI: Relative Strength Index ──────────────────────────────────────────
 
    @staticmethod
    def rsi(precios: pd.Series, periodo: int = 14) -> pd.Series:
        """
        Índice de Fuerza Relativa (RSI).
 
        RSI = 100 - (100 / (1 + RS))
        donde RS = promedio_ganancias / promedio_pérdidas en n períodos.
 
        Interpretación:
          - RSI > 70 → sobrecompra (el activo subió demasiado rápido)
          - RSI < 30 → sobreventa (el activo bajó demasiado rápido)
          - RSI entre 30-70 → zona neutral
        """
        delta = precios.diff()
 
        ganancias = delta.clip(lower=0)    # Solo días positivos
        perdidas = (-delta).clip(lower=0)  # Solo días negativos (en positivo)
 
        # Promedios exponenciales (método estándar de Wilder)
        avg_ganancia = ganancias.ewm(com=periodo - 1, adjust=False).mean()
        avg_perdida = perdidas.ewm(com=periodo - 1, adjust=False).mean()
 
        rs = avg_ganancia / avg_perdida.replace(0, float("inf"))
        rsi_values = 100 - (100 / (1 + rs))
 
        return rsi_values
 
    # ── MACD: Moving Average Convergence Divergence ───────────────────────────
 
    @staticmethod
    def macd(
        precios: pd.Series,
        rapida: int = 12,
        lenta: int = 26,
        señal: int = 9,
    ) -> pd.DataFrame:
        """
        MACD — Convergencia/Divergencia de Medias Móviles.
 
        Línea MACD    = EMA(12) - EMA(26)
        Línea señal   = EMA(9) de la línea MACD
        Histograma    = MACD - Señal
 
        Interpretación:
          - MACD cruza señal hacia arriba → señal de compra
          - MACD cruza señal hacia abajo  → señal de venta
          - Histograma positivo y creciente → momentum alcista
          - Histograma negativo y decreciente → momentum bajista
        """
        ema_rapida = precios.ewm(span=rapida, adjust=False).mean()
        ema_lenta = precios.ewm(span=lenta, adjust=False).mean()
 
        linea_macd = ema_rapida - ema_lenta
        linea_senal = linea_macd.ewm(span=señal, adjust=False).mean()
        histograma = linea_macd - linea_senal
 
        return pd.DataFrame({
            "macd": linea_macd,
            "macd_signal": linea_senal,
            "macd_histogram": histograma,
        }, index=precios.index)
 
    # ── Oscilador Estocástico ─────────────────────────────────────────────────
 
    @staticmethod
    def stochastic(
        df_ohlcv: pd.DataFrame,
        k_periodo: int = 14,
        d_periodo: int = 3,
    ) -> pd.DataFrame:
        """
        Oscilador Estocástico %K y %D.
 
        Requiere datos OHLCV (no solo cierre) para calcular máximos y mínimos.
 
        %K = (Cierre - Mínimo_n) / (Máximo_n - Mínimo_n) × 100
        %D = SMA(3) del %K
 
        Interpretación:
          - %K > 80 → sobrecompra
          - %K < 20 → sobreventa
          - %K cruza %D hacia arriba en zona <20 → señal de compra
          - %K cruza %D hacia abajo en zona >80 → señal de venta
        """
        minimo_n = df_ohlcv["minimo"].rolling(window=k_periodo).min()
        maximo_n = df_ohlcv["maximo"].rolling(window=k_periodo).max()
 
        rango = maximo_n - minimo_n
        # Evitar división por cero en activos con rango nulo
        rango = rango.replace(0, float("nan"))
 
        k = ((df_ohlcv["cierre"] - minimo_n) / rango) * 100
        d = k.rolling(window=d_periodo).mean()
 
        return pd.DataFrame({
            "stoch_k": k,
            "stoch_d": d,
        }, index=df_ohlcv.index)
 
    # ── Método consolidador: todos los indicadores en un solo DataFrame ───────
 
    def calcular_todos(
        self,
        df_ohlcv: pd.DataFrame,
        sma_corto: int = 20,
        sma_largo: int = 50,
        ema_periodo: int = 20,
        rsi_periodo: int = 14,
        bb_periodo: int = 20,
        bb_std: float = 2.0,
        macd_rapida: int = 12,
        macd_lenta: int = 26,
        macd_señal: int = 9,
        stoch_k: int = 14,
        stoch_d: int = 3,
    ) -> pd.DataFrame:
        """
        Calcula todos los indicadores técnicos y los une en un DataFrame.
        Parámetros ajustables por el usuario desde el frontend.
 
        Returns
        -------
        pd.DataFrame con columnas: precio_cierre, sma_20, sma_50, ema_20,
        banda_superior, banda_media, banda_inferior, rsi, macd, macd_signal,
        macd_histogram, stoch_k, stoch_d
        """
        cierre = df_ohlcv["cierre"]
 
        # Calcular cada indicador
        bb = self.bollinger(cierre, bb_periodo, bb_std)
        macd_df = self.macd(cierre, macd_rapida, macd_lenta, macd_señal)
        stoch_df = self.stochastic(df_ohlcv, stoch_k, stoch_d)
 
        # Consolidar todo en un DataFrame
        resultado = pd.DataFrame({
            "precio_cierre": cierre,
            "sma_20": self.sma(cierre, sma_corto),
            "sma_50": self.sma(cierre, sma_largo),
            "ema_20": self.ema(cierre, ema_periodo),
            "banda_superior": bb["banda_superior"],
            "banda_media": bb["banda_media"],
            "banda_inferior": bb["banda_inferior"],
            "rsi": self.rsi(cierre, rsi_periodo),
            "macd": macd_df["macd"],
            "macd_signal": macd_df["macd_signal"],
            "macd_histogram": macd_df["macd_histogram"],
            "stoch_k": stoch_df["stoch_k"],
            "stoch_d": stoch_df["stoch_d"],
        })
 
        return resultado
 
    # ── Generador de señales (base para el Módulo 7) ──────────────────────────
 
    def generar_señales(self, df_indicadores: pd.DataFrame) -> dict:
        """
        Evalúa la última fila de indicadores y genera señales de trading.
 
        Retorna un dict con la señal (COMPRA/VENTA/NEUTRAL), valor actual
        y descripción para cada indicador.
 
        Este método es usado por el SignalEngine del Módulo 7.
        """
        ultima = df_indicadores.iloc[-1]
        penultima = df_indicadores.iloc[-2] if len(df_indicadores) > 1 else ultima
 
        señales = {}
 
        # ── RSI ──────────────────────────────────────────────────────────────
        rsi_val = ultima.get("rsi")
        if pd.notna(rsi_val):
            if rsi_val < 30:
                señal_rsi = ("COMPRA", "FUERTE",
                    f"RSI={rsi_val:.1f} — activo en zona de sobreventa. "
                    f"Históricamente una oportunidad de entrada.")
            elif rsi_val > 70:
                señal_rsi = ("VENTA", "FUERTE",
                    f"RSI={rsi_val:.1f} — activo en zona de sobrecompra. "
                    f"El precio puede corregir a la baja.")
            else:
                señal_rsi = ("NEUTRAL", "DÉBIL",
                    f"RSI={rsi_val:.1f} — zona neutral, sin señal clara.")
            señales["RSI"] = {
                "senal": señal_rsi[0], "fuerza": señal_rsi[1],
                "valor_actual": rsi_val, "descripcion": señal_rsi[2],
            }
 
        # ── MACD (cruce de líneas) ────────────────────────────────────────────
        macd_val = ultima.get("macd")
        signal_val = ultima.get("macd_signal")
        prev_macd = penultima.get("macd")
        prev_signal = penultima.get("macd_signal")
 
        if all(pd.notna(v) for v in [macd_val, signal_val, prev_macd, prev_signal]):
            cruce_alcista = (prev_macd <= prev_signal) and (macd_val > signal_val)
            cruce_bajista = (prev_macd >= prev_signal) and (macd_val < signal_val)
            if cruce_alcista:
                señales["MACD"] = {
                    "senal": "COMPRA", "fuerza": "FUERTE",
                    "valor_actual": round(macd_val, 4),
                    "descripcion": "MACD acaba de cruzar la señal hacia arriba (cruce alcista).",
                }
            elif cruce_bajista:
                señales["MACD"] = {
                    "senal": "VENTA", "fuerza": "FUERTE",
                    "valor_actual": round(macd_val, 4),
                    "descripcion": "MACD acaba de cruzar la señal hacia abajo (cruce bajista).",
                }
            else:
                señales["MACD"] = {
                    "senal": "NEUTRAL", "fuerza": "DÉBIL",
                    "valor_actual": round(macd_val, 4),
                    "descripcion": f"Sin cruce reciente. MACD={'por encima' if macd_val > signal_val else 'por debajo'} de la señal.",
                }
 
        # ── Bandas de Bollinger ───────────────────────────────────────────────
        precio = ultima.get("precio_cierre")
        sup = ultima.get("banda_superior")
        inf = ultima.get("banda_inferior")
 
        if all(pd.notna(v) for v in [precio, sup, inf]):
            if precio >= sup:
                señales["Bollinger"] = {
                    "senal": "VENTA", "fuerza": "MODERADA",
                    "valor_actual": round(precio, 2),
                    "descripcion": f"Precio toca o supera la banda superior (${sup:.2f}). Posible sobrecompra.",
                }
            elif precio <= inf:
                señales["Bollinger"] = {
                    "senal": "COMPRA", "fuerza": "MODERADA",
                    "valor_actual": round(precio, 2),
                    "descripcion": f"Precio toca o cae bajo la banda inferior (${inf:.2f}). Posible sobreventa.",
                }
            else:
                señales["Bollinger"] = {
                    "senal": "NEUTRAL", "fuerza": "DÉBIL",
                    "valor_actual": round(precio, 2),
                    "descripcion": "Precio dentro de las bandas. Sin señal de extremo.",
                }
 
        # ── Cruce de medias (Golden/Death Cross) ─────────────────────────────
        sma20 = ultima.get("sma_20")
        sma50 = ultima.get("sma_50")
        prev_sma20 = penultima.get("sma_20")
        prev_sma50 = penultima.get("sma_50")
 
        if all(pd.notna(v) for v in [sma20, sma50, prev_sma20, prev_sma50]):
            golden_cross = (prev_sma20 <= prev_sma50) and (sma20 > sma50)
            death_cross = (prev_sma20 >= prev_sma50) and (sma20 < sma50)
            if golden_cross:
                señales["Medias_Moviles"] = {
                    "senal": "COMPRA", "fuerza": "FUERTE",
                    "valor_actual": round(sma20, 2),
                    "descripcion": "Golden Cross: SMA20 cruza SMA50 hacia arriba. Señal alcista de largo plazo.",
                }
            elif death_cross:
                señales["Medias_Moviles"] = {
                    "senal": "VENTA", "fuerza": "FUERTE",
                    "valor_actual": round(sma20, 2),
                    "descripcion": "Death Cross: SMA20 cruza SMA50 hacia abajo. Señal bajista de largo plazo.",
                }
            else:
                tendencia = "SMA20 > SMA50 (tendencia alcista)" if sma20 > sma50 else "SMA20 < SMA50 (tendencia bajista)"
                señales["Medias_Moviles"] = {
                    "senal": "NEUTRAL", "fuerza": "DÉBIL",
                    "valor_actual": round(sma20, 2),
                    "descripcion": f"Sin cruce reciente. {tendencia}.",
                }
 
        # ── Oscilador Estocástico ─────────────────────────────────────────────
        k_val = ultima.get("stoch_k")
        d_val = ultima.get("stoch_d")
        prev_k = penultima.get("stoch_k")
        prev_d = penultima.get("stoch_d")
 
        if all(pd.notna(v) for v in [k_val, d_val, prev_k, prev_d]):
            cruce_k_sobre_d = (prev_k <= prev_d) and (k_val > d_val) and (k_val < 30)
            cruce_k_bajo_d = (prev_k >= prev_d) and (k_val < d_val) and (k_val > 70)
            if cruce_k_sobre_d:
                señales["Estocastico"] = {
                    "senal": "COMPRA", "fuerza": "FUERTE",
                    "valor_actual": round(k_val, 1),
                    "descripcion": f"%K cruza %D hacia arriba en zona de sobreventa (%K={k_val:.1f}). Señal de compra.",
                }
            elif cruce_k_bajo_d:
                señales["Estocastico"] = {
                    "senal": "VENTA", "fuerza": "FUERTE",
                    "valor_actual": round(k_val, 1),
                    "descripcion": f"%K cruza %D hacia abajo en zona de sobrecompra (%K={k_val:.1f}). Señal de venta.",
                }
            else:
                zona = "sobrecompra" if k_val > 70 else "sobreventa" if k_val < 30 else "neutral"
                señales["Estocastico"] = {
                    "senal": "COMPRA" if k_val < 30 else "VENTA" if k_val > 70 else "NEUTRAL",
                    "fuerza": "MODERADA" if zona != "neutral" else "DÉBIL",
                    "valor_actual": round(k_val, 1),
                    "descripcion": f"Estocástico en zona de {zona} (%K={k_val:.1f}, %D={d_val:.1f}).",
                }
 
        return señales
    
class RiskCalculator:
    """
    Calcula métricas de riesgo para un portafolio o activo individual.
 
    Métodos de VaR implementados:
        1. Paramétrico  → asume distribución normal de rendimientos
        2. Histórico    → usa la distribución empírica real
        3. Monte Carlo  → simula escenarios aleatorios (10,000+)
 
    Cada método tiene sus ventajas. El profesor puede preguntar
    cuál es más adecuado — la respuesta depende de las propiedades
    del portafolio (¿son normales los rendimientos? → usar paramétrico
    solo si Jarque-Bera no rechaza normalidad).
    """
 
    def __init__(self, n_simulaciones: int = 10_000):
        self.n_simulaciones = n_simulaciones
 
    # ── Método 1: VaR Paramétrico ─────────────────────────────────────────────
 
    def var_parametrico(
        self,
        rendimientos: pd.Series,
        nivel_confianza: float = 0.95,
        horizonte_dias: int = 1,
        valor_portafolio: float = 10_000.0,
    ) -> dict:
        """
        VaR Paramétrico (método analítico / varianza-covarianza).
 
        Supuesto: los rendimientos siguen una distribución normal.
        Fórmula: VaR = μ - z × σ × √horizonte
          donde:
            μ = media de rendimientos diarios
            σ = desviación estándar de rendimientos diarios
            z = percentil de la normal estándar (1.645 para 95%, 2.326 para 99%)
            √horizonte = raíz del número de días (regla de la raíz cuadrada del tiempo)
 
        Ventaja: rápido, analítico, fácil de calcular.
        Desventaja: subestima riesgo cuando los rendimientos tienen colas pesadas
                    (fat tails), que es casi siempre en finanzas reales.
        """
        media = rendimientos.mean()
        sigma = rendimientos.std()
        alpha = 1 - nivel_confianza
 
        # Percentil de la distribución normal estándar
        z = stats.norm.ppf(alpha)   # Negativo, ej: -1.645 para alpha=0.05
 
        # VaR diario
        var_pct = -(media + z * sigma) * np.sqrt(horizonte_dias)
        var_pct = max(var_pct, 0)   # El VaR no puede ser negativo
 
        # CVaR paramétrico: E[pérdida | pérdida > VaR] bajo normalidad
        # = μ + σ × φ(z) / α   donde φ es la densidad normal estándar
        cvar_pct = -(media - sigma * stats.norm.pdf(z) / alpha) * np.sqrt(horizonte_dias)
        cvar_pct = max(cvar_pct, var_pct)
 
        return {
            "metodo": "parametrico",
            "var_porcentaje": round(var_pct * 100, 4),
            "var_dolares": round(var_pct * valor_portafolio, 2),
            "cvar_porcentaje": round(cvar_pct * 100, 4),
            "cvar_dolares": round(cvar_pct * valor_portafolio, 2),
            "interpretacion": (
                f"Con {nivel_confianza*100:.0f}% de confianza, la pérdida máxima "
                f"en {horizonte_dias} día(s) no supera el {var_pct*100:.2f}% "
                f"(${var_pct*valor_portafolio:,.2f}). "
                f"En los peores escenarios (más allá del VaR), "
                f"la pérdida promedio sería {cvar_pct*100:.2f}% (CVaR)."
            ),
        }
 
    # ── Método 2: VaR Histórico ───────────────────────────────────────────────
 
    def var_historico(
        self,
        rendimientos: pd.Series,
        nivel_confianza: float = 0.95,
        horizonte_dias: int = 1,
        valor_portafolio: float = 10_000.0,
    ) -> dict:
        """
        VaR por Simulación Histórica.
 
        Idea: usar la distribución real pasada de los rendimientos
        sin suponer ninguna distribución teórica.
 
        Fórmula: VaR = -percentil(rendimientos, 1 - nivel_confianza)
        Para horizonte > 1 día se escala por √horizonte.
 
        Ventaja: captura colas pesadas y asimetría reales.
        Desventaja: asume que el pasado representa el futuro.
                    No captura eventos sin precedente histórico.
        """
        alpha = 1 - nivel_confianza
 
        # El VaR es el percentil (alpha) de la distribución de pérdidas
        var_pct = -float(np.percentile(rendimientos.dropna(), alpha * 100))
        var_pct = max(var_pct, 0) * np.sqrt(horizonte_dias)
 
        # CVaR histórico: promedio de rendimientos peores que el VaR
        umbral = float(np.percentile(rendimientos.dropna(), alpha * 100))
        peores = rendimientos[rendimientos <= umbral]
        cvar_pct = (-peores.mean()) * np.sqrt(horizonte_dias) if len(peores) > 0 else var_pct
        cvar_pct = max(cvar_pct, var_pct)
 
        return {
            "metodo": "historico",
            "var_porcentaje": round(var_pct * 100, 4),
            "var_dolares": round(var_pct * valor_portafolio, 2),
            "cvar_porcentaje": round(cvar_pct * 100, 4),
            "cvar_dolares": round(cvar_pct * valor_portafolio, 2),
            "interpretacion": (
                f"Basado en los rendimientos históricos reales, "
                f"la pérdida máxima en {horizonte_dias} día(s) al {nivel_confianza*100:.0f}% "
                f"de confianza es {var_pct*100:.2f}% "
                f"(${var_pct*valor_portafolio:,.2f}). "
                f"El CVaR histórico de {cvar_pct*100:.2f}% es el promedio "
                f"de las pérdidas más extremas observadas."
            ),
        }
 
    # ── Método 3: VaR Monte Carlo ─────────────────────────────────────────────
 
    @timing_decorator
    def var_montecarlo(
        self,
        rendimientos: pd.Series,
        nivel_confianza: float = 0.95,
        horizonte_dias: int = 1,
        valor_portafolio: float = 10_000.0,
    ) -> dict:
        """
        VaR por Simulación Monte Carlo.
 
        Idea: simular miles de posibles trayectorias del portafolio
        usando los parámetros estadísticos de los rendimientos históricos
        y tomar el percentil de la distribución simulada.
 
        Proceso:
          1. Estimar μ y σ de los rendimientos históricos
          2. Simular N rendimientos de una N(μ, σ²) para el horizonte
          3. El VaR es el percentil (1-nivel_confianza) de esa simulación
 
        Ventaja: flexible, puede incorporar distribuciones no normales,
                 correlaciones, y escenarios de estrés.
        Desventaja: depende de la calidad del modelo generador.
                    Computacionalmente más costoso.
        """
        np.random.seed(42)   # Reproducibilidad
 
        media = rendimientos.mean()
        sigma = rendimientos.std()
 
        # Simular rendimientos acumulados para el horizonte dado
        # Cada fila = un escenario, cada columna = un día
        simulaciones = np.random.normal(
            loc=media,
            scale=sigma,
            size=(self.n_simulaciones, horizonte_dias),
        )
 
        # Rendimiento acumulado de cada escenario
        rendimientos_simulados = simulaciones.sum(axis=1)
 
        alpha = 1 - nivel_confianza
        var_pct = -float(np.percentile(rendimientos_simulados, alpha * 100))
        var_pct = max(var_pct, 0)
 
        # CVaR Monte Carlo
        umbral = float(np.percentile(rendimientos_simulados, alpha * 100))
        peores_sim = rendimientos_simulados[rendimientos_simulados <= umbral]
        cvar_pct = (-peores_sim.mean()) if len(peores_sim) > 0 else var_pct
        cvar_pct = max(cvar_pct, var_pct)
 
        return {
            "metodo": "montecarlo",
            "var_porcentaje": round(var_pct * 100, 4),
            "var_dolares": round(var_pct * valor_portafolio, 2),
            "cvar_porcentaje": round(cvar_pct * 100, 4),
            "cvar_dolares": round(cvar_pct * valor_portafolio, 2),
            "interpretacion": (
                f"Tras simular {self.n_simulaciones:,} escenarios, "
                f"el VaR Monte Carlo al {nivel_confianza*100:.0f}% en "
                f"{horizonte_dias} día(s) es {var_pct*100:.2f}% "
                f"(${var_pct*valor_portafolio:,.2f}). "
                f"CVaR simulado: {cvar_pct*100:.2f}%."
            ),
        }
 
    # ── Calcular los 3 métodos juntos ─────────────────────────────────────────
 
    def calcular_var_completo(
        self,
        rendimientos_portafolio: pd.Series,
        nivel_confianza: float = 0.95,
        horizonte_dias: int = 1,
        valor_portafolio: float = 10_000.0,
    ) -> dict:
        """
        Ejecuta los 3 métodos y recomienda el más adecuado
        según las propiedades estadísticas de los rendimientos.
        """
        resultados = [
            self.var_parametrico(rendimientos_portafolio, nivel_confianza,
                                 horizonte_dias, valor_portafolio),
            self.var_historico(rendimientos_portafolio, nivel_confianza,
                               horizonte_dias, valor_portafolio),
            self.var_montecarlo(rendimientos_portafolio, nivel_confianza,
                                horizonte_dias, valor_portafolio),
        ]
 
        # Recomendar método según normalidad de los rendimientos
        _, jb_pvalue = stats.jarque_bera(rendimientos_portafolio.dropna())
 
        if jb_pvalue > 0.05:
            recomendado = "parametrico"
            razon = "Los rendimientos no rechazan normalidad (Jarque-Bera p>{:.2f}).".format(jb_pvalue)
        else:
            # Colas pesadas detectadas → histórico es más confiable
            kurt = rendimientos_portafolio.kurtosis()
            recomendado = "historico"
            razon = (
                f"Los rendimientos tienen colas pesadas (curtosis={kurt:.2f}). "
                f"El VaR histórico captura mejor los eventos extremos."
            )
 
        return {
            "resultados": resultados,
            "mejor_metodo_recomendado": recomendado,
            "razon_recomendacion": razon,
        }
 
    # ── Rendimientos del portafolio ponderado ─────────────────────────────────
 
    @staticmethod
    def rendimientos_portafolio(
        df_rendimientos: pd.DataFrame,
        pesos: list[float],
        tickers: list[str],
    ) -> pd.Series:
        """
        Calcula la serie de rendimientos del portafolio como
        combinación lineal ponderada de los rendimientos individuales.
 
        r_portafolio(t) = Σ w_i × r_i(t)
        """
        pesos_array = np.array(pesos)
        cols_disponibles = [t for t in tickers if t in df_rendimientos.columns]
 
        if len(cols_disponibles) != len(tickers):
            faltantes = set(tickers) - set(cols_disponibles)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tickers no encontrados en los datos: {faltantes}",
            )
 
        return df_rendimientos[cols_disponibles].dot(pesos_array)
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 4: GARCHService
# Responsabilidad: modelar volatilidad condicional con ARCH/GARCH.
#
# ¿Por qué GARCH y no solo la desviación estándar?
# La desviación estándar histórica asume volatilidad CONSTANTE.
# En realidad, la volatilidad se agrupa (clustering): períodos de alta
# volatilidad tienden a seguir a períodos de alta volatilidad.
# GARCH captura eso — modela la volatilidad de hoy en función de
# shocks y volatilidades pasadas.
# ══════════════════════════════════════════════════════════════════════════════
 
class GARCHService:
    """
    Ajusta y compara modelos de volatilidad condicional.
 
    Modelos implementados:
        ARCH(1)      → volatilidad depende solo del shock de ayer
        GARCH(1,1)   → volatilidad depende del shock de ayer Y la varianza de ayer
        EGARCH(1,1)  → GARCH asimétrico (captura efecto apalancamiento:
                       las caídas aumentan más la volatilidad que las subidas)
 
    Selección de modelo: AIC y BIC (menor valor = mejor ajuste penalizado).
    """
 
    def _ajustar_modelo(
        self,
        rendimientos: pd.Series,
        especificacion: str,
    ) -> dict:
        """
        Ajusta un modelo ARCH/GARCH específico y extrae métricas.
 
        Parameters
        ----------
        especificacion : str
            "ARCH(1)", "GARCH(1,1)" o "EGARCH(1,1)"
        """
        from arch import arch_model
 
        # Escalar a porcentaje para mejor estabilidad numérica del optimizador
        rend_pct = rendimientos * 100
 
        try:
            if especificacion == "ARCH(1)":
                modelo = arch_model(rend_pct, vol="ARCH", p=1, dist="Normal")
            elif especificacion == "GARCH(1,1)":
                modelo = arch_model(rend_pct, vol="GARCH", p=1, q=1, dist="Normal")
            elif especificacion == "EGARCH(1,1)":
                modelo = arch_model(rend_pct, vol="EGARCH", p=1, q=1, dist="Normal")
            else:
                raise ValueError(f"Especificación no soportada: {especificacion}")
 
            # Ajustar el modelo (optimización numérica)
            resultado = modelo.fit(disp="off", show_warning=False)
 
            # Extraer parámetros
            params = resultado.params
 
            # Pronóstico de volatilidad a 1 y 5 días
            pronostico = resultado.forecast(horizon=5, reindex=False)
            vol_1d = float(np.sqrt(pronostico.variance.iloc[-1, 0])) / 100
            vol_5d = float(np.sqrt(pronostico.variance.iloc[-1, 4])) / 100
 
            # Diagnóstico de residuos estandarizados
            residuos_std = resultado.std_resid.dropna()
            jb_stat, jb_pvalue = stats.jarque_bera(residuos_std)
 
            # Extraer coeficientes de forma robusta
            alpha_coef = []
            beta_coef = []
            omega = float(params.get("omega", 0))
 
            for k, v in params.items():
                if k.startswith("alpha["):
                    alpha_coef.append(float(v))
                elif k.startswith("beta["):
                    beta_coef.append(float(v))
 
            return {
                "especificacion": especificacion,
                "log_likelihood": float(resultado.loglikelihood),
                "aic": float(resultado.aic),
                "bic": float(resultado.bic),
                "omega": omega,
                "alpha": alpha_coef if alpha_coef else [0.0],
                "beta": beta_coef if beta_coef else [0.0],
                "jarque_bera_residuos_pvalue": float(jb_pvalue),
                "es_modelo_seleccionado": False,   # Se actualiza después
                "pronostico_volatilidad_1d": round(vol_1d, 6),
                "pronostico_volatilidad_5d": round(vol_5d, 6),
                "convergio": True,
            }
 
        except Exception as exc:
            logger.warning("No convergió %s: %s", especificacion, exc)
            # Retorna resultado vacío si el modelo no converge
            return {
                "especificacion": especificacion,
                "log_likelihood": float("-inf"),
                "aic": float("inf"),
                "bic": float("inf"),
                "omega": 0.0,
                "alpha": [0.0],
                "beta": [0.0],
                "jarque_bera_residuos_pvalue": 0.0,
                "es_modelo_seleccionado": False,
                "pronostico_volatilidad_1d": 0.0,
                "pronostico_volatilidad_5d": 0.0,
                "convergio": False,
            }
 
    # ── Método principal: ajustar y comparar los 3 modelos ───────────────────
 
    @timing_decorator
    def ajustar_modelos(self, rendimientos: pd.Series, ticker: str) -> dict:
        """
        Ajusta ARCH(1), GARCH(1,1) y EGARCH(1,1) sobre una serie de rendimientos,
        los compara por AIC/BIC y selecciona el mejor.
 
        Returns
        -------
        dict con lista de modelos, modelo recomendado e interpretación.
        """
        logger.info("Ajustando modelos GARCH para %s (%d obs)", ticker, len(rendimientos))
 
        especificaciones = ["ARCH(1)", "GARCH(1,1)", "EGARCH(1,1)"]
        modelos = [self._ajustar_modelo(rendimientos, esp) for esp in especificaciones]
 
        # Filtrar solo los que convergieron
        modelos_validos = [m for m in modelos if m["convergio"]]
 
        if not modelos_validos:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Ningún modelo GARCH convergió para {ticker}. "
                       f"Verifica que la serie tenga suficientes observaciones (mín. 100).",
            )
 
        # Seleccionar el mejor por AIC (menor = mejor)
        mejor = min(modelos_validos, key=lambda m: m["aic"])
        mejor["es_modelo_seleccionado"] = True
 
        # Construir interpretación simple
        vol_anualizada = mejor["pronostico_volatilidad_1d"] * np.sqrt(252) * 100
        interpretacion = self._generar_interpretacion(mejor, vol_anualizada, ticker)
 
        return {
            "ticker": ticker,
            "modelos": modelos,
            "modelo_recomendado": mejor["especificacion"],
            "interpretacion": interpretacion,
        }
 
    def _generar_interpretacion(
        self, mejor_modelo: dict, vol_anualizada: float, ticker: str
    ) -> str:
        """
        Genera texto interpretativo simple del modelo seleccionado.
        Importante para la presentación del dashboard.
        """
        esp = mejor_modelo["especificacion"]
        vol_1d = mejor_modelo["pronostico_volatilidad_1d"] * 100
        jb_p = mejor_modelo["jarque_bera_residuos_pvalue"]
        alpha = mejor_modelo["alpha"][0] if mejor_modelo["alpha"] else 0
        beta = mejor_modelo["beta"][0] if mejor_modelo["beta"] else 0
 
        persistencia = alpha + beta if beta > 0 else alpha
 
        if esp == "ARCH(1)":
            desc_modelo = (
                "ARCH(1): la volatilidad de hoy depende directamente del "
                "shock (sorpresa) del día anterior."
            )
        elif esp == "GARCH(1,1)":
            desc_modelo = (
                "GARCH(1,1): la volatilidad de hoy depende del shock de ayer "
                f"(α={alpha:.3f}) y de la propia volatilidad de ayer (β={beta:.3f}). "
                f"Persistencia = α+β = {persistencia:.3f}."
            )
        else:
            desc_modelo = (
                "EGARCH(1,1): modelo asimétrico que captura el efecto "
                "apalancamiento — las malas noticias aumentan más la "
                "volatilidad que las buenas."
            )
 
        diag_residuos = (
            "Los residuos estandarizados son aproximadamente normales "
            f"(Jarque-Bera p={jb_p:.3f} > 0.05)."
            if jb_p > 0.05
            else f"Los residuos aún muestran no normalidad (p={jb_p:.3f}), "
                 f"lo cual es común en series financieras."
        )
 
        nivel_vol = (
            "baja" if vol_anualizada < 15
            else "moderada" if vol_anualizada < 30
            else "alta"
        )
 
        return (
            f"Modelo seleccionado: {esp} (menor AIC entre los tres ajustados). "
            f"{desc_modelo} "
            f"Volatilidad pronosticada mañana: {vol_1d:.2f}% diario "
            f"({vol_anualizada:.1f}% anualizado — volatilidad {nivel_vol}). "
            f"{diag_residuos}"
        )
    
class CAPMService:
    """
    Calcula Beta, rendimiento esperado CAPM, Alpha de Jensen
    y R² para cada activo del portafolio respecto a un benchmark.
    """
 
    def calcular_beta(
        self,
        rendimientos_activo: pd.Series,
        rendimientos_mercado: pd.Series,
    ) -> dict:
        """
        Calcula Beta mediante regresión lineal simple.
 
        Modelo: r_activo = α + β × r_mercado + ε
 
        Beta = Cov(r_activo, r_mercado) / Var(r_mercado)
 
        Interpretación de Beta:
          β > 1.2  → Agresivo: se mueve más que el mercado
          0.8–1.2  → Neutro: se mueve similar al mercado
          β < 0.8  → Defensivo: se mueve menos que el mercado
          β < 0    → Inverso: se mueve en sentido contrario (raro en acciones)
        """
        # Alinear las dos series por fecha
        df = pd.concat(
            [rendimientos_activo.rename("activo"),
             rendimientos_mercado.rename("mercado")],
            axis=1,
        ).dropna()
 
        if len(df) < 30:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Se necesitan al menos 30 observaciones para calcular Beta.",
            )
 
        # Regresión lineal: OLS
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            df["mercado"], df["activo"]
        )
 
        return {
            "beta": round(float(slope), 4),
            "alpha_regresion": round(float(intercept), 6),  # Alpha diario de Jensen
            "r_cuadrado": round(float(r_value ** 2), 4),
            "p_value_beta": round(float(p_value), 4),
        }
 
    def calcular_capm_completo(
        self,
        tickers: list[str],
        benchmark_ticker: str,
        tasa_libre_riesgo_anual: float,
        data_service: "DataService",
    ) -> list[dict]:
        """
        Calcula CAPM completo para una lista de activos.
 
        Parameters
        ----------
        tasa_libre_riesgo_anual : float
            Tasa en porcentaje (ej: 4.5 para 4.5% anual).
            Se convierte a diaria para la regresión.
        """
        # Tasa libre de riesgo diaria
        rf_diario = (tasa_libre_riesgo_anual / 100) / 252
 
        # Descargar todos los rendimientos juntos (activos + benchmark)
        todos_tickers = list(set(tickers + [benchmark_ticker]))
        df_rend = data_service.get_rendimientos_multiples(todos_tickers)
 
        if benchmark_ticker not in df_rend.columns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Benchmark '{benchmark_ticker}' no encontrado.",
            )
 
        rend_mercado = df_rend[benchmark_ticker]
        rm_diario = float(rend_mercado.mean())
        rm_anual = float((1 + rm_diario) ** 252 - 1)
 
        resultados = []
 
        for ticker in tickers:
            if ticker not in df_rend.columns:
                logger.warning("Ticker %s no encontrado, omitiendo.", ticker)
                continue
 
            rend_activo = df_rend[ticker]
            reg = self.calcular_beta(rend_activo, rend_mercado)
 
            beta = reg["beta"]
            alpha_diario = reg["alpha_regresion"]
 
            # Rendimiento esperado CAPM anualizado
            prima_riesgo = beta * (rm_anual - tasa_libre_riesgo_anual / 100)
            rend_esperado = (tasa_libre_riesgo_anual / 100) + prima_riesgo
 
            # Alpha de Jensen anualizado
            rend_real_anual = float((1 + rend_activo.mean()) ** 252 - 1)
            alpha_jensen = rend_real_anual - rend_esperado
 
            # Clasificación del activo
            if beta > 1.2:
                clasificacion = "Agresivo"
            elif beta >= 0.8:
                clasificacion = "Neutro"
            elif beta >= 0:
                clasificacion = "Defensivo"
            else:
                clasificacion = "Inverso"
 
            resultados.append({
                "ticker": ticker,
                "beta": beta,
                "clasificacion": clasificacion,
                "rendimiento_mercado_anual": round(rm_anual * 100, 4),
                "tasa_libre_riesgo_anual": round(tasa_libre_riesgo_anual, 4),
                "rendimiento_esperado_capm": round(rend_esperado * 100, 4),
                "prima_riesgo": round(prima_riesgo * 100, 4),
                "r_cuadrado": reg["r_cuadrado"],
                "alpha_jensen": round(alpha_jensen * 100, 4),
            })
 
        return resultados
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 6: MarkowitzService
# Responsabilidad: construir la frontera eficiente y encontrar portafolios
# óptimos (máximo Sharpe y mínima varianza).
#
# Idea central de Markowitz (1952):
# La diversificación reduce el riesgo. Combinando activos con baja
# correlación entre sí, se puede obtener el mismo rendimiento esperado
# con menor riesgo, o mayor rendimiento con el mismo riesgo.
# La frontera eficiente es el conjunto de portafolios que maximizan
# el rendimiento para cada nivel de riesgo dado.
# ══════════════════════════════════════════════════════════════════════════════
 
class MarkowitzService:
    """
    Construye la frontera eficiente de Markowitz simulando
    portafolios aleatorios y usando optimización numérica.
    """
 
    def __init__(self, n_portafolios: int = 10_000):
        self.n_portafolios = n_portafolios
 
    @timing_decorator
    def construir_frontera(
        self,
        tickers: list[str],
        df_rendimientos: pd.DataFrame,
        tasa_libre_riesgo_anual: float = 0.045,
    ) -> dict:
        """
        Simula portafolios aleatorios, calcula sus métricas y
        encuentra los portafolios óptimos.
 
        Proceso:
          1. Calcular media y matriz de covarianza de rendimientos
          2. Simular N portafolios con pesos aleatorios que sumen 1
          3. Para cada portafolio calcular rendimiento, volatilidad y Sharpe
          4. El portafolio óptimo = mayor ratio de Sharpe
          5. El de mínima varianza = menor volatilidad
 
        Parameters
        ----------
        tasa_libre_riesgo_anual : float
            En decimales (ej: 0.045 para 4.5%).
        """
        np.random.seed(42)
 
        # Filtrar solo los tickers disponibles
        cols = [t for t in tickers if t in df_rendimientos.columns]
        rend = df_rendimientos[cols].dropna()
 
        n_activos = len(cols)
 
        # Parámetros anualizados
        media_anual = rend.mean() * 252
        cov_anual = rend.cov() * 252
 
        # ── Simulación de portafolios aleatorios ──────────────────────────────
        resultados_sim = np.zeros((self.n_portafolios, 3 + n_activos))
 
        for i in range(self.n_portafolios):
            # Pesos aleatorios que suman 1
            pesos = np.random.random(n_activos)
            pesos = pesos / pesos.sum()
 
            rend_p = float(np.dot(pesos, media_anual))
            vol_p = float(np.sqrt(np.dot(pesos.T, np.dot(cov_anual, pesos))))
            sharpe_p = (rend_p - tasa_libre_riesgo_anual) / vol_p if vol_p > 0 else 0
 
            resultados_sim[i, 0] = rend_p
            resultados_sim[i, 1] = vol_p
            resultados_sim[i, 2] = sharpe_p
            resultados_sim[i, 3:] = pesos
 
        # Convertir a DataFrame
        col_names = ["rendimiento", "volatilidad", "sharpe"] + [f"w_{t}" for t in cols]
        df_sim = pd.DataFrame(resultados_sim, columns=col_names)
 
        # ── Portafolio de máximo Sharpe ───────────────────────────────────────
        idx_max_sharpe = df_sim["sharpe"].idxmax()
        fila_sharpe = df_sim.iloc[idx_max_sharpe]
        pesos_max_sharpe = {
            t: round(float(fila_sharpe[f"w_{t}"]), 4) for t in cols
        }
 
        portafolio_max_sharpe = {
            "nombre": "Máximo Sharpe",
            "pesos": pesos_max_sharpe,
            "rendimiento_anual": round(float(fila_sharpe["rendimiento"]) * 100, 4),
            "volatilidad_anual": round(float(fila_sharpe["volatilidad"]) * 100, 4),
            "ratio_sharpe": round(float(fila_sharpe["sharpe"]), 4),
        }
 
        # ── Portafolio de mínima varianza ─────────────────────────────────────
        idx_min_var = df_sim["volatilidad"].idxmin()
        fila_minvar = df_sim.iloc[idx_min_var]
        pesos_min_var = {
            t: round(float(fila_minvar[f"w_{t}"]), 4) for t in cols
        }
 
        portafolio_min_varianza = {
            "nombre": "Mínima Varianza",
            "pesos": pesos_min_var,
            "rendimiento_anual": round(float(fila_minvar["rendimiento"]) * 100, 4),
            "volatilidad_anual": round(float(fila_minvar["volatilidad"]) * 100, 4),
            "ratio_sharpe": round(float(fila_minvar["sharpe"]), 4),
        }
 
        # ── Frontera eficiente (subconjunto ordenado para graficar) ───────────
        # Ordenamos por volatilidad y tomamos los puntos del "borde superior"
        df_sorted = df_sim.sort_values("volatilidad")
 
        # Agrupamos en bins de volatilidad y tomamos el de mayor rendimiento
        df_sorted["vol_bin"] = pd.cut(df_sorted["volatilidad"], bins=50)
        frontera = (
            df_sorted.groupby("vol_bin", observed=True)
            .apply(lambda g: g.loc[g["rendimiento"].idxmax()])
            .reset_index(drop=True)
            .dropna(subset=["rendimiento", "volatilidad"])
        )
 
        puntos_frontera = [
            {
                "rendimiento": round(float(r["rendimiento"]) * 100, 4),
                "volatilidad": round(float(r["volatilidad"]) * 100, 4),
                "ratio_sharpe": round(float(r["sharpe"]), 4),
            }
            for _, r in frontera.iterrows()
        ]
 
        # ── Muestra de la nube (máx 500 puntos para no sobrecargar el frontend)
        muestra = df_sim.sample(min(500, self.n_portafolios), random_state=42)
        nube = [
            {
                "rendimiento": round(float(r["rendimiento"]) * 100, 4),
                "volatilidad": round(float(r["volatilidad"]) * 100, 4),
                "ratio_sharpe": round(float(r["sharpe"]), 4),
            }
            for _, r in muestra.iterrows()
        ]
 
        # ── Matriz de correlación (para el heatmap del frontend) ──────────────
        corr_matrix = rend.corr().round(4).to_dict()
 
        return {
            "tickers": cols,
            "n_portafolios_simulados": self.n_portafolios,
            "tasa_libre_riesgo_usada": tasa_libre_riesgo_anual,
            "portafolio_max_sharpe": portafolio_max_sharpe,
            "portafolio_min_varianza": portafolio_min_varianza,
            "frontera_eficiente": puntos_frontera,
            "nube_portafolios": nube,
            "matriz_correlacion": corr_matrix,
        }
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 7: SignalEngine
# Responsabilidad: consolidar señales del Módulo 7 por activo y
# construir el panel de alertas tipo semáforo.
# ══════════════════════════════════════════════════════════════════════════════
 
class SignalEngine:
    """
    Motor de señales y alertas de trading.
 
    Usa TechnicalIndicators.generar_señales() como base y
    agrega la lógica de semáforo y el texto interpretativo global.
    """
 
    def __init__(self, data_service: "DataService"):
        self.data_service = data_service
        self.ti = TechnicalIndicators()
 
    def analizar_activo(self, ticker: str) -> dict:
        """
        Genera el panel de alertas completo para un activo.
        Retorna un dict compatible con AlertasActivo de models.py.
        """
        # Obtener datos y calcular indicadores
        df_ohlcv = self.data_service.get_precios(ticker)
        df_ind = self.ti.calcular_todos(df_ohlcv)
 
        # Generar señales individuales
        señales_raw = self.ti.generar_señales(df_ind)
 
        # Convertir al formato de AlertaIndividual
        señales_lista = [
            {
                "indicador": nombre,
                "senal": datos["senal"],
                "valor_actual": datos["valor_actual"],
                "descripcion": datos["descripcion"],
                "fuerza": datos["fuerza"],
            }
            for nombre, datos in señales_raw.items()
        ]
 
        # Conteo de señales
        compras = sum(1 for s in señales_lista if s["senal"] == "COMPRA")
        ventas = sum(1 for s in señales_lista if s["senal"] == "VENTA")
        neutrales = sum(1 for s in señales_lista if s["senal"] == "NEUTRAL")
        total = len(señales_lista)
 
        # Semáforo
        if total == 0:
            semaforo = "AMARILLO"
        elif compras / total >= 0.6:
            semaforo = "VERDE"
        elif ventas / total >= 0.6:
            semaforo = "ROJO"
        else:
            semaforo = "AMARILLO"
 
        # Precio actual
        precio_actual = float(df_ohlcv["cierre"].iloc[-1])
 
        # Interpretación global
        interpretacion = self._interpretar_semaforo(
            ticker, semaforo, compras, ventas, neutrales, precio_actual
        )
 
        return {
            "ticker": ticker,
            "precio_actual": round(precio_actual, 2),
            "senales": señales_lista,
            "resumen_semaforo": semaforo,
            "señales_compra": compras,
            "señales_venta": ventas,
            "señales_neutral": neutrales,
            "interpretacion_global": interpretacion,
        }
 
    @staticmethod
    def _interpretar_semaforo(
        ticker: str,
        semaforo: str,
        compras: int,
        ventas: int,
        neutrales: int,
        precio: float,
    ) -> str:
        total = compras + ventas + neutrales
        if semaforo == "VERDE":
            return (
                f"{ticker} muestra {compras} de {total} señales de compra. "
                f"La mayoría de los indicadores técnicos sugieren presión alcista "
                f"al precio actual de ${precio:.2f}. "
                f"Un inversionista técnico consideraría una posición larga."
            )
        elif semaforo == "ROJO":
            return (
                f"{ticker} muestra {ventas} de {total} señales de venta. "
                f"Los indicadores técnicos sugieren presión bajista "
                f"al precio actual de ${precio:.2f}. "
                f"Un inversionista técnico consideraría reducir exposición."
            )
        else:
            return (
                f"{ticker} muestra señales mixtas ({compras} compra, "
                f"{ventas} venta, {neutrales} neutral) al precio de ${precio:.2f}. "
                f"Sin consenso claro entre los indicadores. "
                f"Se recomienda esperar una señal más definida."
            )
 
 
# ══════════════════════════════════════════════════════════════════════════════
# CLASE 8: MacroService
# Responsabilidad: obtener indicadores macroeconómicos y comparar
# el portafolio óptimo contra el benchmark (Módulo 8).
# ══════════════════════════════════════════════════════════════════════════════
 
class MacroService:
    """
    Obtiene indicadores macro desde FRED y calcula métricas de
    desempeño del portafolio vs benchmark.
 
    Indicadores macro:
      - Tasa libre de riesgo (Treasury 3M)
      - Inflación (CPI)
      - Tipo de cambio USD/COP (para contexto colombiano)
 
    Métricas vs benchmark:
      - Alpha de Jensen
      - Tracking Error
      - Information Ratio
      - Máximo Drawdown
      - Ratio de Sharpe comparado
    """
 
    def __init__(self, fred_service: "FredService"):
        self.fred_service = fred_service
 
    # ── Tasa libre de riesgo desde FRED ──────────────────────────────────────
 
    async def get_tasa_libre_riesgo(self) -> float:
        """
        Obtiene la tasa libre de riesgo actual desde FRED (Treasury 3M).
        Retorna el valor en porcentaje (ej: 4.5 para 4.5%).
        """
        observaciones = await self.fred_service.get_series("DGS3MO", limit=1)
        if not observaciones:
            logger.warning("Sin datos de FRED. Usando tasa por defecto 4.5%.")
            return 4.5
        try:
            valor = float(observaciones[0]["value"])
            return valor
        except (ValueError, KeyError, IndexError):
            logger.warning("Error parseando tasa de FRED. Usando 4.5%.")
            return 4.5
 
    async def get_inflacion_usa(self) -> float:
        """
        Obtiene la variación anual del CPI desde FRED.
        Retorna el valor en porcentaje.
        """
        obs = await self.fred_service.get_series("CPIAUCSL", limit=13)
        if len(obs) < 13:
            return 3.0   # Valor por defecto
 
        try:
            reciente = float(obs[0]["value"])
            hace_un_año = float(obs[12]["value"])
            inflacion = ((reciente - hace_un_año) / hace_un_año) * 100
            return round(inflacion, 2)
        except (ValueError, KeyError, IndexError):
            return 3.0
 
    # ── Métricas de desempeño vs benchmark ───────────────────────────────────
 
    def calcular_metricas_benchmark(
        self,
        pesos_portafolio: dict[str, float],
        benchmark_ticker: str,
        rf_anual: float,
        data_service: "DataService",
    ) -> dict:
        """
        Compara el portafolio óptimo contra el benchmark en las métricas
        clave del Módulo 8.
 
        Métricas calculadas:
          - Rendimiento acumulado (base 100)
          - Alpha de Jensen
          - Tracking Error: desviación estándar de (r_p - r_b)
          - Information Ratio: alpha / tracking_error
          - Máximo Drawdown: mayor caída desde un pico histórico
          - Ratio de Sharpe
        """
        tickers = list(pesos_portafolio.keys())
        pesos = list(pesos_portafolio.values())
 
        todos = list(set(tickers + [benchmark_ticker]))
        df_rend = data_service.get_rendimientos_multiples(todos)
 
        if benchmark_ticker not in df_rend.columns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Benchmark '{benchmark_ticker}' sin datos.",
            )
 
        # Rendimientos del portafolio ponderado
        cols_validas = [t for t in tickers if t in df_rend.columns]
        pesos_validos = [
            pesos[tickers.index(t)] for t in cols_validas
        ]
        # Renormalizar si faltan tickers
        suma = sum(pesos_validos)
        pesos_validos = [p / suma for p in pesos_validos]
 
        rend_portafolio = df_rend[cols_validas].dot(np.array(pesos_validos))
        rend_benchmark = df_rend[benchmark_ticker]
 
        # Alinear
        df_comp = pd.concat(
            [rend_portafolio.rename("portafolio"),
             rend_benchmark.rename("benchmark")],
            axis=1,
        ).dropna()
 
        # Rendimientos acumulados
        acum_p = float((1 + df_comp["portafolio"]).prod() - 1) * 100
        acum_b = float((1 + df_comp["benchmark"]).prod() - 1) * 100
 
        # Tracking Error (TE): σ del diferencial de rendimientos
        diferencial = df_comp["portafolio"] - df_comp["benchmark"]
        tracking_error = float(diferencial.std() * np.sqrt(252)) * 100
 
        # Alpha de Jensen (anualizado)
        beta_p = float(
            df_comp["portafolio"].cov(df_comp["benchmark"])
            / df_comp["benchmark"].var()
        )
        rm_anual = float((1 + df_comp["benchmark"].mean()) ** 252 - 1) * 100
        alpha_jensen = (
            float((1 + df_comp["portafolio"].mean()) ** 252 - 1) * 100
            - (rf_anual + beta_p * (rm_anual - rf_anual))
        )
 
        # Information Ratio = alpha / TE
        information_ratio = alpha_jensen / tracking_error if tracking_error > 0 else 0.0
 
        # Máximo Drawdown
        def max_drawdown(rend_serie: pd.Series) -> float:
            acumulado = (1 + rend_serie).cumprod()
            maximo_historico = acumulado.cummax()
            drawdown = (acumulado - maximo_historico) / maximo_historico
            return float(drawdown.min()) * 100
 
        mdd_p = max_drawdown(df_comp["portafolio"])
        mdd_b = max_drawdown(df_comp["benchmark"])
 
        # Sharpe
        vol_p = float(df_comp["portafolio"].std() * np.sqrt(252)) * 100
        vol_b = float(df_comp["benchmark"].std() * np.sqrt(252)) * 100
 
        rend_p_anual = float((1 + df_comp["portafolio"].mean()) ** 252 - 1) * 100
        rend_b_anual = float((1 + df_comp["benchmark"].mean()) ** 252 - 1) * 100
 
        sharpe_p = (rend_p_anual - rf_anual) / vol_p if vol_p > 0 else 0.0
        sharpe_b = (rend_b_anual - rf_anual) / vol_b if vol_b > 0 else 0.0
 
        return {
            "benchmark_ticker": benchmark_ticker,
            "rendimiento_acumulado_portafolio": round(acum_p, 4),
            "rendimiento_acumulado_benchmark": round(acum_b, 4),
            "alpha_jensen": round(alpha_jensen, 4),
            "tracking_error": round(tracking_error, 4),
            "information_ratio": round(information_ratio, 4),
            "maximo_drawdown_portafolio": round(mdd_p, 4),
            "maximo_drawdown_benchmark": round(mdd_b, 4),
            "ratio_sharpe_portafolio": round(sharpe_p, 4),
            "ratio_sharpe_benchmark": round(sharpe_b, 4),
            "supera_benchmark": bool(sharpe_p > sharpe_b),
        }
 
    # ── Construir lista de indicadores macro para el endpoint /macro ──────────
 
    async def get_indicadores_macro(
        self,
        rf: float,
        inflacion: float,
    ) -> list[dict]:
        """
        Construye la lista de IndicadorMacro para la respuesta JSON.
        """
        hoy = datetime.now().strftime("%Y-%m-%d")
 
        return [
            {
                "nombre": "Tasa libre de riesgo (Treasury 3M)",
                "valor": rf,
                "unidad": "%",
                "fuente": "FRED - Federal Reserve",
                "fecha_dato": hoy,
                "descripcion": (
                    "Rendimiento del bono del Tesoro de EE.UU. a 3 meses. "
                    "Se usa como proxy de la tasa sin riesgo en el CAPM y el ratio de Sharpe. "
                    f"Valor actual: {rf:.2f}%."
                ),
            },
            {
                "nombre": "Inflación anual USA (CPI)",
                "valor": inflacion,
                "unidad": "%",
                "fuente": "FRED - Bureau of Labor Statistics",
                "fecha_dato": hoy,
                "descripcion": (
                    "Variación porcentual anual del Índice de Precios al Consumidor. "
                    "Indicador clave del poder adquisitivo y política monetaria. "
                    f"Valor actual: {inflacion:.2f}%."
                ),
            },
            {
                "nombre": "Tasa real libre de riesgo",
                "valor": round(rf - inflacion, 4),
                "unidad": "%",
                "fuente": "Calculada: Rf - CPI",
                "fecha_dato": hoy,
                "descripcion": (
                    "Tasa nominal menos inflación. "
                    "Representa el rendimiento real después de inflación. "
                    f"Si es negativa ({rf - inflacion:.2f}%), el dinero pierde poder adquisitivo."
                ),
            },
        ]