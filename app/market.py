import httpx
import yfinance as yf
import pandas as pd
from fastapi import APIRouter, HTTPException, status, Query
from datetime import date, timedelta

router = APIRouter()

@router.get("/mercado/dolar")
async def get_dolar_prices():
    """
    Obtiene las cotizaciones del dólar desde DolarApi.
    """
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

# --- ¡NUEVO ENDPOINT! ---
@router.get("/market/historical/{ticker}")
async def get_historical_data(
    ticker: str, 
    years: int = Query(default=1, ge=1, le=10) # 'ge' >= 1, 'le' <= 10 años
):
    """
    Obtiene datos históricos (OHLCV) para un ticker específico
    usando Yahoo Finance.
    
    Tickers argentinos comunes:
    - GGAL.BA (Grupo Galicia)
    - YPFD.BA (YPF)
    - AAPL (Apple, para CEDEAR)
    - MELI (MercadoLibre, para CEDEAR)
    - AL30.BA (Bono AL30)
    """
    try:
        # 1. Definir el rango de fechas
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)
        
        # 2. Descargar datos con yfinance
        stock_data = yf.download(
            ticker, 
            start=start_date, 
            end=end_date,
            auto_adjust=True  # <-- (Silencia el warning)
        )
        
        if stock_data.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron datos para el ticker '{ticker}'. (Prueba GGAL.BA o AAPL)"
            )
            
        # 3. Limpiar y formatear los datos
        stock_data.reset_index(inplace=True)
        stock_data['Date'] = stock_data['Date'].dt.strftime('%Y-%m-%d')
        
        
        stock_data_json = stock_data.to_dict(orient='split') # <-- REEMPLAZA POR ESTA
        
        stock_data_json.pop('index', None) # No necesitamos el índice, ya tenemos 'Date'

        return {
            "ticker": ticker,
            "period": f"{years} año(s)",
            "data": stock_data_json # 'data' ahora es un dict {'columns': [...], 'data': [[...]]}
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error al obtener datos de yfinance: {str(e)}"
        )