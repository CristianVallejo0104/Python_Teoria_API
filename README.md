# RiskLab USTA — Dashboard de Riesgo Financiero & API REST

**RiskLab USTA** es una plataforma integral para el análisis cuantitativo y la gestión de riesgo financiero de portafolios de renta variable. El sistema actúa como una **aduana financiera**: utiliza **FastAPI** y **Pydantic v2** para validar la integridad de los modelos matemáticos antes de ejecutar cálculos de volatilidad, VaR, CAPM y optimización de Markowitz, conectándose en tiempo real a APIs financieras externas.

### Autores

* **Cristian Vallejo** — Estudiante de Estadística, Universidad Santo Tomás
* **USTA 2026-1**
* **Profesor:** Javier Mauricio Sierra
* **Materias:** Teoría del Riesgo + Electiva Python para APIs e IA

---

## 🏗️ Arquitectura del Sistema

El proyecto sigue una arquitectura **cliente-servidor desacoplada**:

* **Backend (FastAPI — puerto 8000):** motor de cálculo científico, validación de entrada con Pydantic v2, métricas de riesgo y exposición de 9 endpoints REST documentados automáticamente en `/docs`.
* **Frontend (Streamlit — puerto 8501):** cliente interactivo que consume el backend por HTTP, visualiza resultados y presenta gráficos de riesgo en tiempo real usando Plotly.

```
Streamlit (8501) ──HTTP/JSON──► FastAPI (8000) ──► yfinance / FRED API
                                      │
                              Pydantic v2 (validación)
                              services.py (cálculos)
                              config.py (BaseSettings)
                              dependencies.py (Depends)
```

La capa del backend se organiza en cinco módulos:

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Punto de entrada, CORS, 9 routers, fábricas de servicios |
| `models.py` | Esquemas Pydantic, `@field_validator`, `@model_validator` |
| `services.py` | 8 clases: `DataService`, `TechnicalIndicators`, `RiskCalculator`, `GARCHService`, `CAPMService`, `MarkowitzService`, `SignalEngine`, `MacroService` |
| `config.py` | `Settings(BaseSettings)` + `@lru_cache`, carga el `.env` |
| `dependencies.py` | `Depends()`, cliente HTTP, validador de tickers, decoradores `@timing_decorator` y `@cache_result` |

---

## 📊 APIs Externas Consumidas

El proyecto no utiliza datos estáticos — todo se obtiene en tiempo real:

| API | Uso | Acceso |
|---|---|---|
| **Yahoo Finance** (`yfinance`) | Precios OHLCV históricos y en tiempo real | Gratuito, sin API key |
| **FRED API** (Federal Reserve) | Tasa libre de riesgo (`DGS3MO`), inflación (`CPIAUCSL`) | Gratuito con API key |

---

## ⚙️ Instalación

### Requisitos previos
- Python 3.12+
- Git

```powershell
# 1. Clonar el repositorio
git clone https://github.com/CristianVallejo0104/Teoria_API.git
cd Teoria_API

# 2. Crear entorno virtual dentro de backend/
python -m venv backend\venv

# 3. Instalar dependencias del backend
backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 4. Instalar dependencias del frontend (Streamlit)
backend\venv\Scripts\python.exe -m pip install streamlit requests
```

---

## 🔑 Configuración de Variables de Entorno

Crea el archivo `backend/.env` copiando el ejemplo:

```powershell
copy backend\.env.example backend\.env
```

Edita `backend/.env` con tus API keys reales:

```env
# FRED API — obtener en: https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY=tu_key_aqui

# Finnhub (opcional) — obtener en: https://finnhub.io/
FINNHUB_API_KEY=tu_key_aqui

# Parámetros del análisis
DEFAULT_TICKERS=["AAPL","MSFT","GOOGL","AMZN","TSLA"]
VAR_CONFIDENCE_LEVEL=0.95
MONTECARLO_SIMULATIONS=10000
```

> ⚠️ **Importante:** El archivo `.env` está en `.gitignore` y **nunca** debe subirse al repositorio. Solo `.env.example` (con placeholders) va al repo.

**¿Dónde obtener las API keys?**
- **FRED:** Registro gratuito en [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) — se obtiene al instante.
- **yfinance:** No requiere API key.

---

## ▶️ Ejecución

Abre **dos terminales separadas** desde la raíz del proyecto (`Teoria_API/`).

### Terminal 1 — Backend

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### Terminal 2 — Frontend

```powershell
# Desde la raíz del proyecto
.\backend\venv\Scripts\python.exe -m streamlit run frontend\app.py
```

Accede a:

| Servicio | URL |
|---|---|
| **Dashboard Streamlit** | `http://localhost:8501` |
| **Swagger UI (FastAPI)** | `http://127.0.0.1:8000/docs` |
| **ReDoc** | `http://127.0.0.1:8000/redoc` |
| **Health check** | `http://127.0.0.1:8000/` |

---

## 🛣️ Endpoints Principales

| Método | Ruta | Módulo | Descripción |
|---|---|---|---|
| `GET` | `/activos` | — | Lista los activos del portafolio con metadata (sector, moneda). |
| `GET` | `/precios/{ticker}` | 1 | Retorna precios históricos OHLCV. Parámetros: `fecha_inicio`, `fecha_fin`. |
| `GET` | `/rendimientos/{ticker}` | 2 | Rendimientos simples y log + estadísticas descriptivas + Jarque-Bera + Shapiro-Wilk. |
| `GET` | `/indicadores/{ticker}` | 1 | SMA, EMA, Bollinger, RSI, MACD, Estocástico. Todos los parámetros son ajustables. |
| `POST` | `/var` | 5 | VaR + CVaR con métodos paramétrico, histórico y Monte Carlo. Body: `VaRRequest`. |
| `GET` | `/capm` | 4 | Beta, rendimiento esperado CAPM, Alpha de Jensen, R². Rf obtenida de FRED. |
| `POST` | `/frontera-eficiente` | 6 | Frontera eficiente de Markowitz. Body: `FronteraRequest`. |
| `GET` | `/alertas` | 7 | Señales COMPRA/VENTA/NEUTRAL + semáforo por activo. |
| `GET` | `/macro` | 8 | Indicadores macroeconómicos FRED + métricas vs benchmark. |

La documentación interactiva completa (con ejemplos de request/response) está disponible en `/docs`.

---

## 🛡️ Validaciones con Pydantic v2 — Aduana Financiera

El backend valida cada request **antes** de ejecutar cualquier cálculo. Si los datos son inválidos, retorna `422 Unprocessable Entity` con el detalle del error.

Ejemplo — `VaRRequest` en `models.py`:

```python
@field_validator("tickers")
@classmethod
def tickers_en_mayusculas(cls, v: list[str]) -> list[str]:
    return [t.upper().strip() for t in v]   # Normaliza

@field_validator("pesos")
@classmethod
def pesos_positivos(cls, v: list[float]) -> list[float]:
    if any(p < 0 for p in v):
        raise ValueError("Todos los pesos deben ser >= 0")
    return v

@model_validator(mode="after")
def validar_consistencia_portafolio(self) -> "VaRRequest":
    if len(self.tickers) != len(self.pesos):
        raise ValueError("len(tickers) debe ser igual a len(pesos)")
    if abs(sum(self.pesos) - 1.0) > 0.01:
        raise ValueError(f"Los pesos deben sumar 1.0. Suma actual: {sum(self.pesos):.4f}")
    return self
```

---

## 📁 Estructura del Proyecto

```text
Teoria_API/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py         # BaseSettings + @lru_cache
│   │   ├── dependencies.py   # Depends(), decoradores, FredService
│   │   ├── main.py           # FastAPI app, 9 routers, CORS
│   │   ├── models.py         # Pydantic v2 Request/Response
│   │   └── services.py       # 8 clases de lógica matemática
│   ├── venv/                 # Entorno virtual (no en Git)
│   ├── .env                  # API keys reales (no en Git)
│   ├── .env.example          # Plantilla de variables (sí en Git)
│   └── requirements.txt
├── frontend/
│   ├── app.py                # Dashboard Streamlit (8 módulos)
├── .gitignore
└── README.md
```

---

## 📈 Activos Seleccionados y Justificación

Se escogieron cinco acciones del mercado estadounidense de sectores distintos para garantizar diversificación real en el análisis de Markowitz:

| Ticker | Empresa | Sector | Justificación |
|---|---|---|---|
| **AAPL** | Apple Inc. | Tecnología (hardware) | Mayor capitalización mundial, alta liquidez, datos históricos extensos y confiables. |
| **MSFT** | Microsoft Corp. | Tecnología (nube/software) | Diversifica dentro del sector tech. Correlación moderada con AAPL. |
| **GOOGL** | Alphabet Inc. | Internet / Publicidad digital | Modelo de negocio diferente a AAPL y MSFT. Reduce correlación del portafolio. |
| **AMZN** | Amazon.com | E-commerce / Nube (AWS) | Exposición a consumo discrecional y computación en nube. Beta moderado. |
| **TSLA** | Tesla Inc. | Vehículos eléctricos | Beta alto (~1.8). Agrega varianza al portafolio y es representativo de sectores de crecimiento. |

La combinación cubre tecnología, consumo discrecional y vehículos eléctricos, asegurando que la matriz de correlación de Markowitz tenga variabilidad suficiente para construir una frontera eficiente significativa.

---

## 🧩 Tecnologías Principales

| Librería | Versión | Uso |
|---|---|---|
| `fastapi` | `0.115.5` | Framework del backend REST |
| `uvicorn[standard]` | `0.32.1` | Servidor ASGI |
| `pydantic` | `2.10.3` | Validación y modelado de datos |
| `pydantic-settings` | `2.6.1` | Configuración desde `.env` |
| `yfinance` | `1.2.2` | Descarga de datos financieros |
| `pandas` | `2.2.3` | Manipulación de series de tiempo |
| `numpy` | `1.26.4` | Cálculo numérico vectorizado |
| `scipy` | `1.14.1` | Pruebas estadísticas (Jarque-Bera, Shapiro-Wilk, linregress) |
| `statsmodels` | `0.14.4` | Análisis estadístico adicional |
| `arch` | `7.1.0` | Modelos ARCH/GARCH/EGARCH |
| `cvxpy` | `1.5.3` | Optimización de portafolios |
| `plotly` | `5.24.1` | Visualizaciones interactivas |
| `streamlit` | `1.41.1` | Interfaz web del dashboard |
| `httpx` | `0.28.0` | Cliente HTTP asíncrono para FRED |
| `requests` | `2.32.3` | Consumo HTTP desde Streamlit |
| `python-dotenv` | `1.0.1` | Gestión de variables de entorno |

---

## ✅ Cumplimiento de Rúbrica

- [x] Conexión a APIs financieras dinámicas (Yahoo Finance + FRED). Sin datasets estáticos.
- [x] Indicadores técnicos interactivos: SMA, EMA, RSI, MACD, Bollinger, Estocástico.
- [x] Rendimientos simples y logarítmicos, estadísticas descriptivas, pruebas de normalidad.
- [x] Modelado de volatilidad condicional: ARCH(1), GARCH(1,1), EGARCH(1,1). Selección por AIC.
- [x] VaR paramétrico, histórico y Monte Carlo (10,000 simulaciones).
- [x] CVaR / Expected Shortfall como medida complementaria.
- [x] Beta y CAPM con tasa libre de riesgo obtenida automáticamente de FRED.
- [x] Frontera eficiente de Markowitz con 10,000 portafolios simulados.
- [x] Señales y alertas automatizadas tipo semáforo (Módulo 7).
- [x] Contexto macro y métricas vs benchmark — Alpha, Tracking Error, IR, Drawdown (Módulo 8).
- [x] **Backend FastAPI** con Pydantic v2, `Depends()`, `BaseSettings`, `async/await`, `HTTPException`.
- [x] Decoradores personalizados: `@timing_decorator`, `@cache_result`.
- [x] `.env` con API keys fuera del repositorio. `.gitignore` configurado.
- [x] `requirements.txt` con versiones fijas.

---

## 🤖 Uso de Herramientas de IA

Durante el desarrollo de este proyecto se utilizó **Claude (Anthropic)** como asistente de programación en las siguientes áreas:

- **Estructuración del proyecto:** definición de la arquitectura backend/frontend y organización de módulos.
- **Generación de código base:** implementación inicial de los servicios (`services.py`), modelos Pydantic (`models.py`) y endpoints (`main.py`), posteriormente revisados, adaptados y comprendidos por el autor.
- **Depuración:** resolución de incompatibilidades con `yfinance 0.2.50` (cambios en estructura de columnas MultiIndex), errores de entorno virtual en Windows y problemas de importación de módulos.
- **Documentación:** asistencia en la redacción de docstrings, este README y el informe ejecutivo.

**Criterio de uso responsable:** todo el código generado con asistencia de IA fue revisado, entendido y probado por el autor antes de incorporarlo al proyecto. El estudiante es capaz de explicar cualquier sección del código en la sustentación oral.
