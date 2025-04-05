-- Create the stocks table to store information about the tracked tickers
CREATE TABLE IF NOT EXISTS stocks (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255),
    industry VARCHAR(100),
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create the table for daily market data (OHLCV)
CREATE TABLE IF NOT EXISTS market_data_daily (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL REFERENCES stocks(ticker) ON DELETE CASCADE,
    date DATE NOT NULL,
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    adjusted_close NUMERIC(12, 4),
    volume BIGINT,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ticker, date) -- Ensure only one entry per stock per day
);

-- Optional: Create indexes for faster querying
CREATE INDEX IF NOT EXISTS idx_market_data_daily_ticker_date ON market_data_daily (ticker, date DESC);

-- Create table for raw text data (news articles, social media posts, etc.)
CREATE TABLE IF NOT EXISTS text_sources (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL, -- e.g., 'news_api', 'twitter', 'reddit'
    source_identifier TEXT NOT NULL, -- e.g., URL, tweet ID, post ID
    content TEXT NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE, -- When the original content was published
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB, -- Store source-specific metadata (e.g., author, publication)
    UNIQUE (source_type, source_identifier)
);

-- Create table for structured LLM analysis results
CREATE TABLE IF NOT EXISTS llm_analysis_results (
    id SERIAL PRIMARY KEY,
    text_source_id INTEGER NOT NULL REFERENCES text_sources(id) ON DELETE CASCADE,
    llm_provider VARCHAR(50) NOT NULL, -- e.g., 'openai', 'anthropic', 'google'
    model_name VARCHAR(100), -- e.g., 'gpt-4', 'claude-3-opus', 'gemini-pro'
    analysis_type VARCHAR(50) NOT NULL, -- e.g., 'sentiment', 'event_extraction', 'entity_recognition', 'summary'
    result JSONB NOT NULL, -- Store the structured JSON output from the LLM
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Optional: Indexes for faster querying on analysis results
CREATE INDEX IF NOT EXISTS idx_llm_analysis_results_text_source_id ON llm_analysis_results (text_source_id);
CREATE INDEX IF NOT EXISTS idx_llm_analysis_results_analysis_type ON llm_analysis_results (analysis_type);


-- Pre-populate the stocks table with the initial list of tickers
-- Using INSERT ... ON CONFLICT DO NOTHING to avoid errors if the script runs multiple times
INSERT INTO stocks (ticker, company_name, industry) VALUES
    ('AAPL', 'Apple Inc.', 'Technology'),
    ('XOM', 'Exxon Mobil Corporation', 'Energy'),
    ('JNJ', 'Johnson & Johnson', 'Healthcare'),
    ('TSLA', 'Tesla, Inc.', 'Automotive'),
    ('AMZN', 'Amazon.com, Inc.', 'Consumer Discretionary'),
    ('MSFT', 'Microsoft Corporation', 'Technology'),
    ('BRK.B', 'Berkshire Hathaway Inc.', 'Financials'),
    ('KO', 'The Coca-Cola Company', 'Consumer Staples'),
    ('NKE', 'Nike, Inc.', 'Consumer Discretionary'),
    ('CAT', 'Caterpillar Inc.', 'Industrials'),
    ('NVDA', 'NVIDIA Corporation', 'Technology'),
    ('GOOG', 'Alphabet Inc. (Class C)', 'Technology'),
    ('META', 'Meta Platforms, Inc.', 'Technology')
ON CONFLICT (ticker) DO NOTHING;
