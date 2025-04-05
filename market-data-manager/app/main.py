import os
import asyncio
import logging # Import logging
from datetime import date, datetime, timezone
from typing import List, Optional

import httpx
import sqlalchemy # Import the base sqlalchemy library
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks # Import BackgroundTasks
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import retry, stop_after_attempt, wait_fixed # For retry logic

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Environment Variables & Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://stockuser:stockpassword@core-database:5432/stock_insights")
DATA_SOURCE_PROXY_URL = os.getenv("DATA_SOURCE_PROXY_URL", "http://data-source-proxy:8001")

# --- Database Setup (SQLAlchemy Async) ---
engine = create_async_engine(DATABASE_URL, echo=False) # Set echo=True for SQL debugging
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Define SQLAlchemy model mirroring the market_data_daily table
class MarketDataDaily(Base):
    __tablename__ = 'market_data_daily'

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(index=True)
    date: Mapped[date]
    open: Mapped[Optional[float]]
    high: Mapped[Optional[float]]
    low: Mapped[Optional[float]]
    close: Mapped[Optional[float]]
    adjusted_close: Mapped[Optional[float]]
    volume: Mapped[Optional[int]]
    # Explicitly map to TIMESTAMP WITH TIME ZONE and remove model default
    fetched_at: Mapped[datetime] = mapped_column(sqlalchemy.TIMESTAMP(timezone=True))

    # Add unique constraint if not already defined in init.sql (belt and suspenders)
    # __table_args__ = (UniqueConstraint('ticker', 'date', name='_ticker_date_uc'),)

# Dependency to get DB session
async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session

# --- FastAPI App ---
app = FastAPI(
    title="Market Data Manager",
    description="Fetches market data via Data Source Proxy and stores it in the database.",
    version="0.1.0"
)

# --- Helper Functions ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def fetch_tickers_from_db(db: AsyncSession) -> List[str]:
    """Fetches the list of tickers to track from the 'stocks' table."""
    try:
        result = await db.execute(text("SELECT ticker FROM stocks"))
        tickers = [row[0] for row in result.fetchall()]
        if not tickers:
            logging.warning("No tickers found in the database.")
        return tickers
    except Exception as e:
        logging.error(f"Error fetching tickers from DB: {e}", exc_info=True)
        raise # Reraise to trigger retry

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def fetch_daily_data_from_proxy(ticker: str) -> dict:
    """Fetches daily data for a ticker from the data-source-proxy."""
    url = f"{DATA_SOURCE_PROXY_URL}/stock/{ticker}/daily"
    async with httpx.AsyncClient(timeout=20.0) as client: # Increased timeout for proxy call
        try:
            logging.info(f"Calling data-source-proxy for {ticker}: {url}")
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            logging.error(f"Error requesting data from proxy for {ticker}: {e}", exc_info=True)
            raise # Reraise to trigger retry
        except httpx.HTTPStatusError as e:
             logging.error(f"Proxy returned error for {ticker}: {e.response.status_code} - {e.response.text}")
             # Don't retry on 4xx errors from proxy (like 404 Not Found, 429 Rate Limit)
             if 400 <= e.response.status_code < 500:
                 return {"error": True, "status_code": e.response.status_code, "detail": e.response.text}
             raise # Reraise 5xx errors to trigger retry
        except Exception as e:
            logging.error(f"Unexpected error fetching data from proxy for {ticker}: {e}", exc_info=True)
            raise # Reraise to trigger retry


async def save_market_data(db: AsyncSession, ticker: str, polygon_data: dict):
    """Parses Polygon.io data and saves it to the market_data_daily table."""
    if not polygon_data or polygon_data.get("resultsCount", 0) == 0 or not polygon_data.get("results"):
        logging.info(f"No data to save for {ticker}")
        return 0

    rows_to_insert = []
    for bar in polygon_data["results"]:
        # Polygon uses milliseconds timestamp (t), convert to date
        # v=volume, vw=volume weighted avg price, o=open, c=close, h=high, l=low, n=number of transactions
        ts_millis = bar.get('t')
        if ts_millis is None: continue # Skip if timestamp is missing

        try:
            bar_date = datetime.fromtimestamp(ts_millis / 1000, tz=timezone.utc).date()
            rows_to_insert.append({
                "ticker": ticker,
                "date": bar_date,
                "open": bar.get('o'),
                "high": bar.get('h'),
                "low": bar.get('l'),
                "close": bar.get('c'),
                "adjusted_close": bar.get('c'), # Polygon free tier doesn't provide adjusted close directly in daily bars, using close as placeholder
                "volume": bar.get('v'),
                "fetched_at": datetime.now(timezone.utc) # Provide datetime object directly
            })
        except Exception as e:
            logging.error(f"Error processing bar for {ticker} on {ts_millis}: {e} - Data: {bar}", exc_info=True)
            continue # Skip this bar

    if not rows_to_insert:
        logging.warning(f"No valid rows processed for {ticker}")
        return 0

    # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING to avoid duplicates
    stmt = pg_insert(MarketDataDaily).values(rows_to_insert)
    stmt = stmt.on_conflict_do_nothing(index_elements=['ticker', 'date'])

    try:
        result = await db.execute(stmt)
        await db.commit()
        logging.info(f"Saved/updated {len(rows_to_insert)} data points for {ticker}. Result proxy rowcount: {result.rowcount}")
        return len(rows_to_insert) # Return number processed
    except Exception as e:
        await db.rollback()
        logging.error(f"Error saving data for {ticker} to DB: {e}", exc_info=True)
        return 0


# --- API Endpoints ---
@app.get("/")
async def read_root():
    return {"message": "Market Data Manager is running"}

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # Check DB connection as part of health
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db_connection": "ok"}
    except Exception as e:
        logging.error(f"Health check DB connection failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Database connection error: {e}")


@app.post("/fetch-all-initial", status_code=202) # Revert status code to 202 Accepted
async def trigger_fetch_all_initial(background_tasks: BackgroundTasks): # Add BackgroundTasks back
    """
    Endpoint to trigger fetching initial (~1 month) daily data for all tickers in the 'stocks' table.
    Runs asynchronously in the background.
    """
    logging.info("Received request to fetch initial data for all tickers.")
    # Use FastAPI's BackgroundTasks to run the function
    background_tasks.add_task(fetch_and_store_all_tickers)
    return {"message": "Initial data fetch for all tickers initiated."} # Revert message


# --- Dummy Background Task for Testing ---
async def dummy_background_task(): # Keep dummy task for now if needed later
    """A simple task to test BackgroundTasks execution."""
    logging.info("!!! Dummy background task started !!!")
    await asyncio.sleep(5) # Simulate some work
    logging.info("!!! Dummy background task finished !!!")


# --- Background Task Logic ---
async def fetch_and_store_all_tickers(): # Keep this function as is
     """Fetches list of tickers and then fetches/stores data for each."""
     logging.info("Starting background task: fetch_and_store_all_tickers")
     # Create a new session specifically for this background task
     async with AsyncSessionFactory() as db_session:
         try:
             tickers = await fetch_tickers_from_db(db_session)
             if not tickers:
                 logging.warning("No tickers configured to fetch data for.")
                 return # Correctly indented return

             logging.info(f"Found tickers: {tickers}")
             # Correctly indent the rest of the function logic within the main try block
             total_saved_count = 0
             for ticker in tickers:
                 try:
                     logging.info(f"Fetching data for {ticker}...")
                     polygon_data = await fetch_daily_data_from_proxy(ticker)

                     # Check if proxy returned an error structure
                     if isinstance(polygon_data, dict) and polygon_data.get("error"):
                          logging.warning(f"Skipping save for {ticker} due to proxy error: {polygon_data.get('status_code')} - {polygon_data.get('detail')}")
                          # Implement delay if rate limited (429)
                          if polygon_data.get("status_code") == 429:
                               logging.warning("Rate limit hit, sleeping for 65 seconds...")
                               await asyncio.sleep(65) # Sleep longer than a minute for Polygon free tier
                          continue # Skip to next ticker

                     saved_count = await save_market_data(db_session, ticker, polygon_data)
                     total_saved_count += saved_count
                     logging.info(f"Processed {ticker}, saved {saved_count} new/updated records.")
                     # Add a small delay between API calls to respect rate limits (Polygon free = 5/min)
                     await asyncio.sleep(13) # Sleep 13 seconds -> ~4.6 calls per minute

                 except Exception as e:
                     # Catch errors during processing of a single ticker
                     logging.error(f"Error processing ticker {ticker}: {e}", exc_info=True)
                     # Consider adding more specific error handling or retry logic here if needed
                     continue # Continue to the next ticker

             # This print should be inside the outer try but outside the for loop
             logging.info(f"Background task finished. Total records processed/saved attempt: {total_saved_count}")

         except Exception as e:
             # Catch errors during the overall task (e.g., fetching tickers)
             logging.error(f"Error in background task fetch_and_store_all_tickers: {e}", exc_info=True)
     # The 'async with AsyncSessionFactory()' context manager handles closing the session


if __name__ == "__main__":
    # This is for local debugging only, Uvicorn running via Docker Compose is preferred
    # You might need to manually set environment variables or use a .env file locally
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True) # Use different port (8002)
