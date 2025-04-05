from fastapi import FastAPI, HTTPException
import os
import httpx # Using httpx for async requests
from datetime import date, timedelta, datetime # Import date/timedelta/datetime

# TODO: Choose and configure a specific stock API provider (e.g., Alpha Vantage, Polygon.io)
# Store API key securely, e.g., via environment variable
STOCK_API_KEY = os.getenv("STOCK_API_KEY")
STOCK_API_BASE_URL = os.getenv("STOCK_API_BASE_URL") # e.g., "https://www.alphavantage.co/query"

if not STOCK_API_KEY or not STOCK_API_BASE_URL:
    print("Warning: STOCK_API_KEY or STOCK_API_BASE_URL environment variables not set.")
    # Allow startup for testing basic routes, but API calls will fail
    # raise ValueError("STOCK_API_KEY and STOCK_API_BASE_URL environment variables are required")


app = FastAPI(
    title="Data Source Proxy",
    description="Handles communication with external data APIs (Stock, News, LLM).",
    version="0.1.0"
)

@app.get("/")
async def read_root():
    return {"message": "Data Source Proxy is running"}

@app.get("/health")
async def health_check():
    # Basic health check, can be expanded later
    return {"status": "ok"}

# Endpoint to proxy a request for daily stock data using Polygon.io Aggregates API
# Fetches approximately the last month of data by default
@app.get("/stock/{ticker}/daily")
async def get_stock_daily(ticker: str, days_back: int = 35): # Fetch ~1 month + buffer
    if not STOCK_API_KEY or not STOCK_API_BASE_URL:
        raise HTTPException(status_code=503, detail="Stock API (Polygon.io) not configured")

    # Calculate date range
    today = date.today()
    start_date = today - timedelta(days=days_back) # Look back ~35 days to ensure we get ~1 month of trading days
    end_date = today # Up to today

    # Polygon.io Aggregates (Bars) API endpoint structure
    # GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}
    api_url = f"{STOCK_API_BASE_URL}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start_date.isoformat()}/{end_date.isoformat()}"

    params = {
        "adjusted": "true",
        "sort": "asc", # Oldest first
        "apiKey": STOCK_API_KEY
        # Note: Free plan has 5 calls/min limit. Consider adding rate limiting if needed.
    }

    async with httpx.AsyncClient(timeout=15.0) as client: # Set a reasonable timeout
        try:
            print(f"Calling Polygon API: {api_url} with params: adjusted=true, sort=asc") # Debug print
            response = await client.get(api_url, params=params)
            response.raise_for_status() # Raise exception for 4xx or 5xx status codes

            data = response.json()

            # Polygon.io specific error/status checking
            if data.get("status") == "ERROR":
                 error_message = data.get("error", "Unknown Polygon.io API Error")
                 raise HTTPException(status_code=400, detail=f"Polygon API Error: {error_message}")
            if data.get("status") == "DELAYED":
                 print(f"Warning: Polygon.io data for {ticker} is delayed.") # Log or handle as needed

            if data.get("queryCount", 0) == 0 or data.get("resultsCount", 0) == 0:
                 # It's possible to get 0 results for valid requests (e.g., weekend, holiday, future date range)
                 # Return empty results instead of raising 404 immediately
                 print(f"No daily aggregate data found for {ticker} in range {start_date} to {end_date}")
                 # Return structure consistent with successful response but empty results
                 return {
                     "ticker": data.get("ticker"),
                     "queryCount": data.get("queryCount"),
                     "resultsCount": 0,
                     "adjusted": data.get("adjusted"),
                     "results": [],
                     "status": data.get("status"),
                     "request_id": data.get("request_id"),
                     "count": 0
                 }

            # Optional: Add transformation logic here if needed before returning
            # For now, return the raw Polygon.io response structure
            return data

        except httpx.TimeoutException:
             raise HTTPException(status_code=504, detail="Request to Polygon API timed out.")
        except httpx.RequestError as exc:
            # Network errors, DNS errors etc.
            raise HTTPException(status_code=503, detail=f"Error contacting Polygon API: {exc}")
        except httpx.HTTPStatusError as exc:
            # Handle specific HTTP errors from Polygon
            status_code = exc.response.status_code
            detail = f"Polygon API returned error {status_code}"
            try:
                # Try to get more specific error from response body
                error_data = exc.response.json()
                detail += f": {error_data.get('error', exc.response.text)}"
            except Exception:
                detail += f": {exc.response.text}"

            if status_code == 429: # Too Many Requests
                detail = "Polygon API rate limit likely exceeded (5 calls/min for free tier)."

            raise HTTPException(status_code=status_code, detail=detail)
        except Exception as exc:
             # Catch potential JSON parsing errors or other unexpected issues
             print(f"Unexpected error processing Polygon API response: {exc}") # Log the error
             raise HTTPException(status_code=500, detail=f"Internal server error processing API response: {type(exc).__name__}")

# Add placeholders for News and LLM proxy endpoints later
# @app.get("/news/...")
# async def get_news(...): ...

# @post("/llm/analyze")
# async def analyze_text(...): ...

if __name__ == "__main__":
    import uvicorn
    # This is for local debugging only, Uvicorn running via Docker Compose is preferred
    uvicorn.run(app, host="0.0.0.0", port=8001)
