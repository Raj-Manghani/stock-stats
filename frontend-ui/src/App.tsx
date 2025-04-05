import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

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

  const chartData = {
    labels: marketData.map(d => d.date),
    datasets: [
      {
        label: 'Close Price',
        data: marketData.map(d => d.close),
        borderColor: 'blue',
        backgroundColor: 'lightblue',
        fill: false,
      }
    ]
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { position: 'top' as const },
      title: { display: true, text: `Price Chart for ${selectedTicker}` }
    }
  };

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
          <div style={{ maxWidth: '800px' }}>
            <Line data={chartData} options={chartOptions} />
          </div>

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