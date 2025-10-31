import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- Importamos los módulos y los workers ---
from . import models, auth, market, settings, portfolio, bot, trading_engine
from .database import engine

# Importamos las funciones de los workers que creamos
from .market import market_data_worker
from .trading_engine import trading_engine_worker

# --- CREAR TABLAS ---
models.Base.metadata.create_all(bind=engine)


# --- GESTOR DE CICLO DE VIDA CENTRALIZADO ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el inicio y apagado de TODAS las tareas de fondo.
    """
    print("Iniciando aplicación y tareas de fondo...")
    
    # Creamos una tarea para cada worker
    market_worker_task = asyncio.create_task(market_data_worker())
    trading_worker_task = asyncio.create_task(trading_engine_worker())
    
    # El 'yield' le pasa el control a la aplicación para que empiece a recibir peticiones
    yield
    
    # --- Lógica de apagado ---
    print("Apagando aplicación y tareas de fondo...")
    market_worker_task.cancel()
    trading_worker_task.cancel()
    
    try:
        # Esperamos a que las tareas se cancelen limpiamente
        await market_worker_task
        await trading_worker_task
    except asyncio.CancelledError:
        print("Workers de mercado y trading detenidos correctamente.")

# --- Instancia de FastAPI ---
# Ahora usa nuestro nuevo lifespan centralizado
app = FastAPI(
    title="Asistente Financiero API",
    description="Backend para el Asistente de Inversiones con IA",
    version="0.2.0", # Incrementamos versión por el nuevo motor
    lifespan=lifespan
)

# --- Middlewares y Routers (sin cambios) ---
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Autenticación"])
app.include_router(market.router, prefix="/api/v1/market", tags=["Mercado"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Configuraciones"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(bot.router, prefix="/api/v1/bot", tags=["Bot Trading"])
# Incluimos el router del nuevo módulo, aunque esté vacío por ahora
app.include_router(trading_engine.router, prefix="/api/v1/engine", tags=["Motor de Trading"])


@app.get("/")
def read_root():
    return {"status": "online", "message": "API del Asistente Financiero está en línea"}