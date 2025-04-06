import asyncio
from fastapi import FastAPI
import feedparser
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import select, text
from datetime import datetime
import httpx

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    task1 = asyncio.create_task(fetch_and_store_rss())
    task2 = asyncio.create_task(analyze_new_articles())
    yield
    task1.cancel()
    task2.cancel()
    await asyncio.gather(task1, task2, return_exceptions=True)

app = FastAPI(title="Text Processor Service", lifespan=lifespan)

DATABASE_URL = os.getenv("DATABASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.llmprovider.com")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

class TextSource(Base):
    __tablename__ = "text_sources"
    __table_args__ = (UniqueConstraint('source_type', 'source_identifier', name='uix_source_type_identifier'),)

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50), nullable=False)
    source_identifier = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    published_at = Column(TIMESTAMP(timezone=True))
    fetched_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    meta_data = Column("meta_data", JSONB)

class LLMAnalysisResult(Base):
    __tablename__ = "llm_analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    text_source_id = Column(Integer, nullable=False)
    llm_provider = Column(String(50), nullable=False)
    model_name = Column(String(100))
    analysis_type = Column(String(50), nullable=False)
    result = Column(JSONB, nullable=False)
    analyzed_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US",
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=MSFT&region=US&lang=en-US",
]

@app.get("/health")
async def health_check():
    return {"status": "ok"}

async def fetch_and_store_rss():
    while True:
        async with AsyncSessionLocal() as session:
            for feed_url in RSS_FEEDS:
                try:
                    parsed = feedparser.parse(feed_url)
                    for entry in parsed.entries:
                        source_identifier = entry.get("id") or entry.get("link")
                        published = None
                        try:
                            published = datetime(*entry.published_parsed[:6])
                        except:
                            pass
                        stmt = select(TextSource).where(
                            TextSource.source_type == "rss",
                            TextSource.source_identifier == source_identifier
                        )
                        result = await session.execute(stmt)
                        existing = result.scalar_one_or_none()
                        if existing:
                            continue
                        new_article = TextSource(
                            source_type="rss",
                            source_identifier=source_identifier,
                            content=entry.get("title", "") + "\n" + entry.get("summary", ""),
                            published_at=published,
                            fetched_at=datetime.utcnow(),
                            metadata={
                                "link": entry.get("link"),
                                "title": entry.get("title"),
                                "summary": entry.get("summary")
                            }
                        )
                        session.add(new_article)
                        print(f"Stored new article: {entry.get('title')}")
                    await session.commit()
                except Exception as e:
                    print(f"Error fetching/parsing RSS feed {feed_url}: {e}")
        await asyncio.sleep(900)

async def analyze_new_articles():
    while True:
        async with AsyncSessionLocal() as session:
            try:
                from sqlalchemy import text as sa_text
                stmt = sa_text(
                    """
                    SELECT ts.id, ts.content FROM text_sources ts
                    WHERE NOT EXISTS (
                        SELECT 1 FROM llm_analysis_results lar WHERE lar.text_source_id = ts.id
                    )
                    LIMIT 5
                    """
                )
                result = await session.execute(stmt)
                rows = result.fetchall()
                for row in rows:
                    text_source_id, content = row
                    try:
                        prompt = f"""
Please analyze the following financial news article and provide:
1. A concise summary (2-3 sentences).
2. Sentiment score (-1 to 1) and label (positive, neutral, negative).
3. List of key events (earnings, M&A, product launches, regulations, etc.).
4. List of mentioned companies, people, and products.
5. Main topics or themes.

Article:
{content}
"""

                        async with httpx.AsyncClient(timeout=60) as client:
                            response = await client.post(
                                f"{LLM_API_BASE_URL}/chat/completions",
                                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                                json={
                                    "model": "mistralai/mixtral-8x7b-instruct",
                                    "messages": [
                                        {"role": "system", "content": "You are a financial news analyst."},
                                        {"role": "user", "content": prompt}
                                    ],
                                    "max_tokens": 1000,
                                    "temperature": 0.7
                                }
                            )
                            response.raise_for_status()
                            llm_result = response.json()
                    except Exception as e:
                        print(f"Error calling LLM API: {e}")
                        continue
                    new_result = LLMAnalysisResult(
                        text_source_id=text_source_id,
                        llm_provider="your-llm-provider",
                        model_name="your-model-name",
                        analysis_type="sentiment",
                        result=llm_result,
                        analyzed_at=datetime.utcnow()
                    )
                    session.add(new_result)
                    print(f"Stored LLM analysis for article ID {text_source_id}")
                await session.commit()
            except Exception as e:
                print(f"Error analyzing articles: {e}")
        await asyncio.sleep(10)
