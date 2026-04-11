# RiskLab USTA — Dashboard de Riesgo Financiero & API REST

**RiskLab USTA** es una plataforma integral para el análisis cuantitativo y la gestión de riesgo financiero. El sistema actúa como una **aduana financiera**: utiliza **FastAPI** y **Pydantic v2** para validar la integridad de los modelos matemáticos (especialmente la restricción presupuestaria en portafolios) antes de ejecutar cálculos de volatilidad, VaR y optimización.

### Autor

* **Cristian Vallejo**
* Estudiante de Estadística — Universidad Santo Tomás
* **USTA 2026**

---

## 🏗️ Arquitectura del Sistema

El proyecto está diseñado con una arquitectura desacoplada que separa claramente la lógica de negocio del consumo y la visualización.

* **Backend (FastAPI):** Núcleo de cálculo científico, validación de entrada, métricas de riesgo y exposición de servicios REST.
* **Frontend (Streamlit):** Cliente interactivo que consume la API, visualiza resultados y presenta gráficos de riesgo en tiempo real.

La capa del backend se organiza en:

* `backend/app/main.py` — punto de entrada, configuración de FastAPI, CORS y routers.
* `backend/app/models.py` — esquemas Pydantic y validaciones robustas.
* `backend/app/services.py` — lógica matemática y financiera: `DataService`, `RiskCalculator`, `GARCHService`, `CAPMService`, `MarkowitzService`, `MacroService` y `SignalEngine`.

---

## 📊 APIs Externas

Este proyecto no utiliza datos estáticos. Consume datos en tiempo real de:

* **Yahoo Finance** a través de `yfinance` para descargar precios OHLCV y construir rendimientos.
* **FRED API** (Federal Reserve) para obtener indicadores macroeconómicos dinámicos, especialmente la tasa libre de riesgo con la serie `DGS3MO` y la inflación con `CPIAUCSL`.

---

## ⚙️ Instalación

```powershell
# 1. Clonar el repositorio
git clone https://github.com/CristianVallejo0104/Teoria_API.git
cd Teoria_API

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar el entorno (Windows)
.\venv\Scripts\activate

# 4. Instalar dependencias del backend
cd backend
pip install -r requirements.txt

# 5. Instalar dependencias del frontend
cd ..\frontend
pip install -r requerimentsfrontend.txt
```

---

## ▶️ Ejecución

Abre dos terminales separadas.

Terminal 1 — Backend:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — Frontend:

```powershell
cd frontend
streamlit run app.py
```

Accede a:

* **Dashboard Streamlit:** `http://localhost:8501`
* **Swagger UI (FastAPI):** `http://127.0.0.1:8000/docs`
* **Redoc:** `http://127.0.0.1:8000/redoc`

---

## 🛣️ Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/activos` | Lista los activos del portafolio por defecto con metadata básica. |
| `GET` | `/precios/{ticker}` | Retorna precios históricos OHLCV para el ticker solicitado. |
| `GET` | `/rendimientos/{ticker}` | Calcula rendimientos simples y logarítmicos, más estadísticas descriptivas. |
| `GET` | `/indicadores/{ticker}` | Genera SMA, EMA, Bollinger, RSI, MACD y Estocástico para el ticker. |
| `POST` | `/var` | Calcula VaR y CVaR del portafolio usando métodos paramétrico, histórico y Monte Carlo. |
| `GET` | `/capm` | Calcula Beta, rendimiento esperado (CAPM), Alpha de Jensen y R² para los activos. |
| `POST` | `/frontera-eficiente` | Construye la frontera eficiente de Markowitz y devuelve portafolios óptimos. |
| `GET` | `/alertas` | Genera señales de trading (COMPRA, VENTA, NEUTRAL) con resumen tipo semáforo. |
| `GET` | `/macro` | Retorna indicadores macroeconómicos y métricas vs benchmark. |

---

## 🛡️ Validaciones críticas (Aduana Financiera)

El backend usa Pydantic v2 para validar cada request antes de ejecutar los cálculos.

* `backend/app/models.py` define `VaRRequest`, `VaRResultado` y `VaRResponse`.
* `@field_validator("tickers")` normaliza los tickers a mayúsculas y elimina espacios.
* `@field_validator("pesos")` asegura que todos los pesos sean positivos.
* `@model_validator(mode="after")` valida que `len(tickers) == len(pesos)` y que `sum(pesos)` sea igual a `1.0` con tolerancia `±0.01`.

Esta lógica actúa como una verdadera **Aduana Financiera**: rechaza portafolios inválidos antes de cargar el cálculo del riesgo.

---

## 📁 Estructura principal del proyecto

```text
Teoria_API/
├── backend/
│   ├── app/
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── services.py
│   └── requirements.txt
├── frontend/
│   ├── app.py
│   └── requerimentsfrontend.txt
└── README.md
```

---

## 🧩 Tecnologías principales

| Librería | Versión | Uso |
| --- | --- | --- |
| `fastapi` | `0.115.5` | Framework del backend REST. |
| `uvicorn[standard]` | `0.32.1` | Servidor ASGI para FastAPI. |
| `pydantic` | `2.10.3` | Validación y modelado de datos. |
| `pydantic-settings` | `2.6.1` | Configuración basada en settings. |
| `yfinance` | `0.2.50` | Descarga de datos financieros históricos. |
| `pandas` | `2.2.3` | Manipulación de series de tiempo. |
| `numpy` | `1.26.4` | Cálculo numérico y vectorizado. |
| `scipy` | `1.14.1` | Pruebas estadísticas y funciones de distribución. |
| `statsmodels` | `0.14.4` | Análisis estadístico adicional. |
| `arch` | `7.1.0` | Modelos ARCH/GARCH. |
| `cvxpy` | `1.5.3` | Optimización de Markowitz. |
| `plotly` | `5.24.1` | Visualización en el frontend y pruebas. |
| `streamlit` | `1.41.1` | Interfaz web interactiva. |
| `requests` | `2.32.3` | Consumo HTTP desde Streamlit. |
| `python-dotenv` | `1.0.1` | Gestión de variables de entorno. |

---

## ✅ Cumplimiento de Rúbrica

* [x] Conexión a APIs financieras dinámicas (Yahoo Finance + FRED).
* [x] Indicadores técnicos interactivos (`SMA`, `EMA`, `RSI`, `MACD`, `Bollinger`, `Estocástico`).
* [x] Cálculo de rendimientos, momentos estadísticos y pruebas de normalidad.
* [x] Modelado de volatilidad condicional con `ARCH(1)`, `GARCH(1,1)` y `EGARCH(1,1)`.
* [x] Cálculo de `VaR` con métodos paramétrico, histórico y `Monte Carlo`.
* [x] Estimación de `CVaR` / Expected Shortfall.
* [x] Cálculo de `Beta` y aplicación de `CAPM` con tasa libre de riesgo de FRED.
* [x] Construcción de la frontera eficiente de `Markowitz` y portafolios óptimos.
* [x] Implementación de API REST propia con FastAPI y validaciones Pydantic.
* [x] Integración de datos macroeconómicos desde la API FRED.

