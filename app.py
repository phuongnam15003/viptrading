import ccxt
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()
exchange = ccxt.binance({'enableRateLimit': True})

def get_smc_data(symbol='BTC/USDT', timeframe='4h'):
    # 1. Lấy dữ liệu từ Binance
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=200)
    df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    
    # Định dạng thời gian chuẩn cho TradingView (Timestamp tính bằng giây hoặc chuỗi YYYY-MM-DD)
    df['time'] = df['time'] / 1000  
    
    # 2. Thuật toán quét FVG
    df['bullish_fvg'] = (df['low'] > df['high'].shift(2)) & (df['close'].shift(1) > df['open'].shift(1))
    df['bearish_fvg'] = (df['high'] < df['low'].shift(2)) & (df['close'].shift(1) < df['open'].shift(1))
    
    # 3. Thuật toán quét BOS và OB
    df['local_high'] = df['high'][(df['high'] > df['high'].shift(1)) & (df['high'] > df['high'].shift(-1))]
    df['local_low'] = df['low'][(df['low'] < df['low'].shift(1)) & (df['low'] < df['low'].shift(-1))]
    df['last_high'] = df['local_high'].ffill()
    df['last_low'] = df['local_low'].ffill()
    
    df['BOS'] = ""
    df['OB'] = ""
    
    for i in range(2, len(df) - 2):
        # Kiểm tra đóng nến phá vỡ cấu trúc (BOS)
        if df['close'].iloc[i] > df['last_high'].iloc[i-1]:
            df.at[df.index[i], 'BOS'] = 'Bullish'
        elif df['close'].iloc[i] < df['last_low'].iloc[i-1]:
            df.at[df.index[i], 'BOS'] = 'Bearish'
            
        # Kiểm tra khối OB uy tín đi kèm FVG
        if df['close'].iloc[i] < df['open'].iloc[i] and df['low'].iloc[i+2] > df['high'].iloc[i]:
            df.at[df.index[i], 'OB'] = 'Bullish'
        elif df['close'].iloc[i] > df['open'].iloc[i] and df['high'].iloc[i+2] < df['low'].iloc[i]:
            df.at[df.index[i], 'OB'] = 'Bearish'
            
    return df

@app.get("/api/signals")
def signals(symbol: str = "BTC/USDT", timeframe: str = "4h"):
    """API trả về dữ liệu nến và các điểm SMC cho Frontend vẽ"""
    df = get_smc_data(symbol, timeframe)
    # Thay thế các giá trị NaN để tránh lỗi JSON
    df = df.fillna(0)
    return df.to_dict(orient='records')

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Giao diện Dashboard Website tích hợp đồ thị TradingView"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SMC Realtime Dashboard</title>
        <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body { background-color: #0c0d14; color: #fff; font-family: Arial, sans-serif; margin: 30px; }
            #chart { width: 100%; height: 600px; border: 1px solid #1e222d; }
            .panel { margin-bottom: 15px; padding: 10px; background: #161a25; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="panel">
            <h2>🤖 HỆ THỐNG PHÂN TÍCH SMC & PRICE ACTION TỰ ĐỘNG</h2>
            <p>Khung thời gian đang quét: <b>4H (Bóp cò) dựa trên cấu trúc xu hướng</b></p>
        </div>
        <div id="chart"></div>

        <script>
            const chart = LightweightCharts.createChart(document.getElementById('chart'), {
                width: document.getElementById('chart').clientWidth,
                height: 600,
                layout: { backgroundColor: '#0c0d14', textColor: '#d1d4dc' },
                grid: { vertLines: { color: '#1f222e' }, horzLines: { color: '#1f222e' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                priceScale: { borderColor: '#2b2e3a' },
                timeScale: { borderColor: '#2b2e3a', timeVisible: true }
            });

            const candlestickSeries = chart.addCandlestickSeries({
                upColor: '#26a69a', downColor: '#ef5350',
                borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350'
            });

            // Gọi API từ Backend Python để lấy dữ liệu thời gian thực
            fetch('/api/signals?symbol=BTC/USDT&timeframe=4h')
                .then(res => res.json())
                .then(data => {
                    // Định dạng cấu trúc nến cho thư viện TradingView
                    const chartData = data.map(d => ({
                        time: d.time, open: d.open, high: d.high, low: d.low, close: d.close
                    }));
                    candlestickSeries.setData(chartData);

                    // Đánh dấu các điểm có tín hiệu BOS hoặc OB lên màn hình
                    const markers = [];
                    data.forEach(d => {
                        if (d.BOS === 'Bullish') {
                            markers.push({ time: d.time, position: 'aboveBar', color: '#00ffcc', shape: 'arrowDown', text: 'BOS Tăng' });
                        } else if (d.BOS === 'Bearish') {
                            markers.push({ time: d.time, position: 'belowBar', color: '#ff3366', shape: 'arrowUp', text: 'BOS Giảm' });
                        }
                        if (d.OB === 'Bullish') {
                            markers.push({ time: d.time, position: 'belowBar', color: '#ffeb3b', shape: 'circle', text: 'Vùng OB Cầu' });
                        }
                    });
                    candlestickSeries.setMarkers(markers);
                });
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    # Chạy cục bộ server tại máy nhà mày
    uvicorn.run(app, host="127.0.0.1", port=8000)