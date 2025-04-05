import os
import pandas as pd
import joblib
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

app = FastAPI(title="Analysis Engine")

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

MODEL_PATH = "model.joblib"

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/train")
async def train_model():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT ts.id, ts.content, lar.result, md.close
            FROM text_sources ts
            JOIN llm_analysis_results lar ON lar.text_source_id = ts.id
            JOIN market_data_daily md ON md.ticker = ts.metadata->>'ticker' AND md.date = ts.published_at::date
            WHERE lar.analysis_type = 'sentiment'
        """))
        rows = result.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No training data found")

    df = pd.DataFrame(rows, columns=["id", "content", "sentiment", "close"])
    df['sentiment_score'] = df['sentiment'].apply(lambda x: x.get('score', 0) if isinstance(x, dict) else 0)
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    df.dropna(inplace=True)

    X = df[['sentiment_score']]
    y = df['target']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBClassifier()
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)

    joblib.dump(model, MODEL_PATH)

    return {"message": "Model trained", "accuracy": acc}

@app.get("/predict/{ticker}")
async def predict(ticker: str):
    if not os.path.exists(MODEL_PATH):
        raise HTTPException(status_code=404, detail="Model not trained yet")

    model = joblib.load(MODEL_PATH)

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT lar.result
            FROM text_sources ts
            JOIN llm_analysis_results lar ON lar.text_source_id = ts.id
            WHERE ts.metadata->>'ticker' = :ticker
            ORDER BY ts.published_at DESC
            LIMIT 1
        """), {"ticker": ticker})
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No recent LLM analysis found")

    sentiment = row[0]
    score = sentiment.get('score', 0) if isinstance(sentiment, dict) else 0

    prob = model.predict_proba([[score]])[0][1]

    return {"ticker": ticker, "score": score, "probability_up": prob}