import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface Stock {
  ticker: string;
  company_name: string;
  industry: string;
}

interface MarketData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface NewsInsight {
  text_source_id: number;
  content: string;
  published_at: string;
  metadata: any;
  analysis_type: string;
  llm_result: any;
}

function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [marketData, setMarketData] = useState<MarketData[]>([]);
  const [newsInsights, setNewsInsights] = useState<NewsInsight[]>([]);

  useEffect(() => {
    axios.get('http://localhost:8004/stocks')
      .then(res => setStocks(res.data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    if (!selectedTicker) return;
    axios.get(`http://localhost:8004/stocks/${selectedTicker}/market-data`)
      .then(res => setMarketData(res.data))
      .catch(err => console.error(err));

    axios.get(`http://localhost:8004/stocks/${selectedTicker}/news-insights`)
      .then(res => setNewsInsights(res.data))
      .catch(err => console.error(err));
  }, [selectedTicker]);

  return (
    <div style={{ padding: '1rem' }}>
      <h1>Stock Insights</h1>
      <h2>Tracked Stocks</h2>
      <ul>
        {stocks.map(stock => (
          <li key={stock.ticker}>
            <button onClick={() => setSelectedTicker(stock.ticker)}>
              {stock.ticker} - {stock.company_name}
            </button>
          </li>
        ))}
      </ul>

      {selectedTicker && (
        <>
          <h2>Market Data for {selectedTicker}</h2>
          <table border={1} cellPadding={4}>
            <thead>
              <tr>
                <th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Volume</th>
              </tr>
            </thead>
            <tbody>
              {marketData.map(d => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td>{d.open}</td>
                  <td>{d.high}</td>
                  <td>{d.low}</td>
                  <td>{d.close}</td>
                  <td>{d.volume}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>News & LLM Insights</h2>
          {newsInsights.map(n => (
            <div key={n.text_source_id} style={{ border: '1px solid #ccc', margin: '1rem 0', padding: '0.5rem' }}>
              <strong>{n.metadata?.title}</strong>
              <p>{n.content}</p>
              <small>Published: {n.published_at}</small>
              <pre>{JSON.stringify(n.llm_result, null, 2)}</pre>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export default App;