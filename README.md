# RiskLab USTA — Dashboard de Riesgo Financiero & API REST

**RiskLab USTA** es una plataforma integral para el análisis cuantitativo y la gestión de riesgo financiero. El sistema actúa como una **aduana financiera**: utiliza **FastAPI** y **Pydantic v2** para validar la integridad de los modelos matemáticos (como la restricción presupuestaria en portafolios) antes de ejecutar cálculos de volatilidad o valor en riesgo.

### Autor
* **Cristian Vallejo**
* Estudiante de Estadística — Universidad Santo Tomás
* **USTA 2026**

---

### 🏗️ Arquitectura del Sistema
El proyecto implementa una arquitectura desacoplada para separar la lógica de negocio de la interfaz de usuario:
1.  **Backend (FastAPI):** Núcleo de cálculo científico, consumo asíncrono de APIs externas y exposición de servicios REST.
2.  **Frontend (Streamlit):** Interfaz interactiva para la visualización de datos, gráficos de velas y optimización de portafolios.

### 📊 Dataset & APIs Externas
El sistema no utiliza datos estáticos; consume información en tiempo real de fuentes oficiales:
* **Yahoo Finance API:** Series de tiempo históricas de precios y volumen para activos de renta variable.
* **FRED API (Federal Reserve):** Obtención dinámica de la Tasa Libre de Riesgo (10-Year Treasury) para el modelo CAPM e indicadores macroeconómicos.

---

### 🚀 Instalación

```powershell
# 1. Clonar el repositorio
git clone [https://github.com/CristianVallejo0104/Teoria_API.git](https://github.com/CristianVallejo0104/Teoria_API.git)
cd Teoria_API

# 2. Crear entorno virtual
python -m venv venv

# Activar en Windows:
.\venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt
⚙️ EjecuciónPara que el sistema funcione correctamente, se deben ejecutar ambos servicios simultáneamente en terminales separadas:Terminal 1 (Backend - FastAPI):PowerShellcd backend
uvicorn main:app --reload --port 8000
Terminal 2 (Frontend - Streamlit):PowerShellcd frontend
streamlit run app.py
InterfazURLDashboard (Streamlit)http://localhost:8501Swagger UI (Backend)http://127.0.0.1:8000/docsRedochttp://127.0.0.1:8000/redoc🛣️ Endpoints Principales (API REST)VerboRutaDescripciónGET/api/v1/mercado/preciosObtiene precios históricos y retornos logarítmicos.POST/api/v1/riesgo/varCalcula VaR y CVaR (Histórico, Paramétrico, Monte Carlo).GET/api/v1/riesgo/normalidadEjecuta pruebas de Jarque-Bera y Shapiro-Wilk.POST/api/v1/riesgo/garchModela la volatilidad condicional de los activos.POST/api/v1/riesgo/markowitzGenera la frontera eficiente y portafolios óptimos.GET/api/v1/macro/indicadoresExtrae Inflación (CPI) y Tasas oficiales desde FRED.🛡️ Validaciones Críticas (Pydantic)El sistema garantiza la consistencia de los modelos mediante validadores personalizados:Restricción de Pesos: El modelo rechaza portafolios donde la suma de pesos sea diferente a 1.0 (100%), asegurando la viabilidad de la optimización de Markowitz.Integridad de Tickers: Validación de existencia de activos antes de realizar peticiones a servicios externos.Parámetros de Confianza: Restricción de niveles de confianza $\alpha$ para cálculos de VaR entre 0 y 1.📂 Estructura del ProyectoPlaintextTeoria_API/
├── backend/                # API REST (FastAPI)
│   ├── main.py             # Punto de entrada y configuración de Routers
│   ├── app/
│   │   ├── api/            # Endpoints modulares
│   │   ├── models/         # Esquemas Pydantic y validadores (@model_validator)
│   │   └── services/       # Lógica matemática (RiskCalculator, DataService)
├── frontend/               # Interfaz de Usuario (Streamlit)
│   ├── app.py              # Dashboard interactivo y cliente HTTP
│   └── components/         # Visualizaciones en Plotly
├── requirements.txt        # Librerías y dependencias
└── README.md
🛠️ Tecnologías & LibreríasLibreríaVersiónFunciónFastAPI0.133.1Framework del BackendPydantic2.12.5Validación de datos y esquemasStreamlit1.42.0Framework del FrontendPandas2.2.xManipulación de series de tiempoyfinance0.2.xConsumo de datos financierosScipy1.13.xPruebas estadísticas y optimizaciónArch7.xModelos de volatilidad GARCH/ARCHPlotly5.24.xGráficas interactivasUvicorn0.41.0Servidor ASGI✅ Cumplimiento de Rúbrica[x] Conexión a APIs financieras dinámicas.[x] Indicadores técnicos interactivos (SMA, EMA, RSI, MACD, Bollinger, Estocástico).[x] Rendimientos, momentos estadísticos y pruebas de normalidad.[x] Modelado de volatilidad condicional (ARCH/GARCH).[x] Cálculo de VaR (3 métodos) y Expected Shortfall (CVaR).[x] Estimación de Beta y aplicación de CAPM.[x] Frontera Eficiente de Markowitz.[x] BONO: Implementación de API REST propia con FastAPI.[x] BONO: Integración de datos macroeconómicos desde FRED API.
