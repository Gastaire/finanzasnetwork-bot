import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

# --- Importaciones del proyecto ---
from .database import SessionLocal
from .models import KLine
from ppi_client.ppi import PPI

# --- CONFIGURACIÓN DEL WORKER ---
# Lista de activos a monitorear. ¡Podemos ampliarla en el futuro!
# Formato: (Ticker, Tipo, Plazo)
TICKERS_TO_MONITOR = [
    ("GGAL", "ACCIONES", "A-48HS"),
    ("AAPL", "CEDEARS", "A-48HS"),
    ("AL30", "BONOS", "INMEDIATA"),
]
# Intervalo de espera del worker en segundos (ej. 5 minutos)
WORKER_SLEEP_INTERVAL = 300

# Creamos el router. Aún puede tener endpoints si los necesitamos.
router = APIRouter()

# --- LÓGICA SÍNCRONA DE INGESTA DE DATOS ---
def _fetch_and_store_ppi_market_data(db: Session, ticker: str, instrument_type: str, settlement: str):
    """
    Función síncrona que:
    1. Se conecta a PPI (sin autenticación para datos de mercado).
    2. Busca datos históricos del último año.
    3. Los guarda en la base de datos usando un UPSERT para eficiencia.
    """
    try:
        print(f"[{datetime.now()}] Worker: Iniciando ingesta para {ticker}...")
        ppi = PPI(sandbox=True)
        
        # 1. Definir el rango de fechas (últimos 365 días)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        # 2. Buscar datos históricos en la API de PPI
        market_data = ppi.marketdata.search(ticker, instrument_type, settlement, start_date, end_date)

        if not market_data:
            print(f"Worker: No se encontraron datos para {ticker}.")
            return

        # 3. Preparar los datos para la base de datos
        klines_to_upsert = []
        for d in market_data:
            # La API devuelve 'date' como string, lo convertimos a objeto datetime
            timestamp = datetime.fromisoformat(d['date'].replace('Z', '+00:00'))
            
            klines_to_upsert.append({
                "symbol": ticker,
                "interval": "1d", # La API de PPI devuelve datos diarios
                "timestamp": timestamp,
                "open": d.get('openingPrice', 0.0),
                "high": d.get('max', 0.0),
                "low": d.get('min', 0.0),
                "close": d.get('price', 0.0),
                "volume": d.get('volume', 0.0)
            })

        if not klines_to_upsert:
            return

        # 4. Lógica de UPSERT (INSERT ... ON CONFLICT) para PostgreSQL
        # Esto es clave para la eficiencia: si la vela ya existe (misma symbol, interval, timestamp),
        # no hace nada. Si no existe, la inserta.
        stmt = pg_insert(KLine).values(klines_to_upsert)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['symbol', 'interval', 'timestamp']
        )
        db.execute(stmt)
        db.commit()

        print(f"Worker: Ingesta para {ticker} completada. {len(klines_to_upsert)} velas procesadas.")

    except Exception as e:
        print(f"ERROR en el worker de ingesta para {ticker}: {e}")
        db.rollback() # Revertir cambios si algo falla


# --- WORKER ASÍNCRONO ---
async def market_data_worker():
    """
    Tarea de fondo que se ejecuta en un bucle infinito para
    actualizar los datos de mercado periódicamente.
    """
    print(">>> Worker de datos de mercado iniciado. <<<")
    while True:
        try:
            # Creamos una sesión de BBDD nueva para este ciclo del worker
            with SessionLocal() as db:
                for ticker, instrument_type, settlement in TICKERS_TO_MONITOR:
                    # Ejecutamos la función síncrona en un hilo separado
                    # para no bloquear el bucle de eventos de asyncio.
                    await asyncio.to_thread(
                        _fetch_and_store_ppi_market_data, 
                        db, ticker, instrument_type, settlement
                    )
                    await asyncio.sleep(1) # Pequeña pausa para no saturar la API

            print(f"Worker: Ciclo completado. Durmiendo por {WORKER_SLEEP_INTERVAL} segundos...")
            await asyncio.sleep(WORKER_SLEEP_INTERVAL)

        except Exception as e:
            print(f"ERROR CRÍTICO en el bucle principal del worker: {e}")
            # En caso de un error grave, esperamos antes de reintentar
            await asyncio.sleep(60)


# --- Endpoints del Router (si los necesitamos en el futuro) ---
# Por ahora, mantenemos el endpoint de DolarAPI que ya tenías.
@router.get("/dolar")
async def get_dolar_prices():
    """
    Obtiene las cotizaciones del dólar desde DolarApi.
    """
    # Reimportamos httpx aquí para mantener el módulo limpio
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://dolarapi.com/v1/dolares")
            response.raise_for_status() 
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail=f"Error al contactar la API de dólar: {e.response.text}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"Error interno del servidor: {str(e)}"
            )