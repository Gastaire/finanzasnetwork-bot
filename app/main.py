from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# --- IMPORTACIONES RELATIVAS CORRECTAS ---
from . import models, auth, market, settings, portfolio, bot
from .database import engine

# --- CREAR TABLAS ---
# Esto le dice a SQLAlchemy que cree todas las tablas
# que definiste en models.py usando la 'Base'
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Asistente Financiero API",
    description="Backend para el Asistente de Inversiones con IA",
    version="0.1.0",
)

# Configuración de CORS
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

# --- Incluir Routers ---
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Autenticación"])
app.include_router(market.router, prefix="/api/v1/market", tags=["Mercado"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Configuraciones"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
app.include_router(bot.router, prefix="/api/v1/bot", tags=["Bot Trading"])


@app.get("/")
def read_root():
    return {"status": "online", "message": "API del Asistente Financiero está en línea"}