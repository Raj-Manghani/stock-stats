import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

app = FastAPI(title="Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/stocks")
async def list_stocks():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT ticker, company_name, industry FROM stocks"))
        stocks = [{"ticker": r[0], "company_name": r[1], "industry": r[2]} for r in result.fetchall()]
        return stocks

@app.get("/stocks/{ticker}/market-data")
async def get_market_data(ticker: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT date, open, high, low, close, volume FROM market_data_daily WHERE ticker = :ticker ORDER BY date DESC LIMIT 30"),
            {"ticker": ticker}
        )
        data = [
            {
                "date": str(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": r[5]
            } for r in result.fetchall()
        ]
        return data

@app.get("/stocks/{ticker}/news-insights")
async def get_news_and_insights(ticker: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
            SELECT ts.id, ts.content, ts.published_at, ts.meta_data, lar.analysis_type, lar.result
            FROM text_sources ts
            LEFT JOIN llm_analysis_results lar ON lar.text_source_id = ts.id
            WHERE ts.meta_data->>'title' ILIKE :pattern
            ORDER BY ts.published_at DESC
            LIMIT 20
            """),
            {"pattern": f"%{ticker}%"}
        )
        articles = []
        for r in result.fetchall():
            articles.append({
                "text_source_id": r[0],
                "content": r[1],
                "published_at": r[2],
                "metadata": r[3],
                "analysis_type": r[4],
                "llm_result": r[5]
            })
        return articles

@app.get("/stocks/{ticker}/prediction")
async def get_prediction(ticker: str):
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                response = await session.execute(
                    text("SELECT * FROM llm_analysis_results LIMIT 1")
                )
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://analysis-engine:8005/predict/{ticker}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))