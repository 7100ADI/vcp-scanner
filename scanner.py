import yfinance as yf
import pandas as pd
import numpy as np
import time
import json
import os
import urllib.request
import urllib.parse

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram_alert(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req) as response:
            pass
    except Exception:
        pass

def get_us_tickers():
    print("Lade US-Aktien (S&P 500)...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(url)
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'BRK-B', 'AMD', 'NFLX']

def get_global_tickers():
    print("Lade internationale Märkte (Europa, China, Japan)...")
    return {
        "EUROPA": [
            'SAP.DE', 'SIE.DE', 'ALV.DE', 'MBG.DE', 'RHM.DE', 'BMW.DE', 'DB1.DE',
            'IFX.DE', 'DTE.DE', 'MUV2.DE', 'ASML.AS', 'ADYEN.AS', 'MC.PA', 'OR.PA', 
            'TTE.PA', 'AIR.PA', 'SHEL.L', 'AZN.L', 'HSBA.L', 'BP.L', 'NESN.SW', 'NOVN.SW', 'ROG.SW'
        ],
        "CHINA_HK": ['9988.HK', '700.HK', '3690.HK', '9618.HK', 'BYDDF', 'BIDU', 'NTES'],
        "JAPAN": ['7203.T', '6758.T', '9984.T', '8035.T', '6861.T', '9432.T', '7974.T']
    }

def analyze_stock(ticker, region):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="15mo")

        if len(df) < 150:
            return None

        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_150'] = df['Close'].rolling(window=150).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['Vol_SMA_20'] = df['Volume'].rolling(window=20).mean()

        latest = df.iloc[-1]
        current_price = latest['Close']
        
        low_52w = df['Close'].tail(250).min()
        high_52w = df['Close'].tail(250).max()

        recent_20 = df.tail(20)
        recent_high = recent_20['Close'].max()
        recent_low = recent_20['Close'].min()
        volatility_range = (recent_high - recent_low) / recent_low

        avg_turnover = (df['Volume'].tail(20) * df['Close'].tail(20)).mean()
        if avg_turnover < 2_000_000:
            return None

        cond_trend = (
            current_price > latest['SMA_150'] and
            current_price > latest['SMA_200']
        )
        if not cond_trend:
            return None

        dist_to_high = abs((current_price / high_52w) - 1) * 100
        avg_vol = latest['Vol_SMA_20']
        curr_vol = latest['Volume']
        vol_ratio = (curr_vol / avg_vol) if (pd.notnull(avg_vol) and avg_vol > 0) else 1.0

        score = 100 - (volatility_range * 100 * 2) - (dist_to_high * 1.5) + (min(vol_ratio, 2.5) * 8)
        score = round(score, 2)

        history_prices = df['Close'].tail(5).tolist()
        return {
            'Score': score,
            'Region': region,
            'Ticker': ticker,
            'Kurs': round(current_price, 2),
            '20D_Range_%': round(volatility_range * 100, 2),
            'Abstand_52W_Hoch_%': round(((current_price / high_52w) - 1) * 100, 2),
            'Vol_Ratio': round(vol_ratio, 2),
            'History': [round(p, 2) for p in history_prices]
        }
    except Exception:
        return None

def generate_html_dashboard(dashboard_data):
    html_content = f"""<!DOCTYPE html>
<html lang="de" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global VCP Breakout Ranking - Top 12 Elite</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{ 
                    colors: {{ 
                        darkbg: '#0b0f17', 
                        cardbg: '#151d2a',
                        bordercolor: '#222f43'
                    }} 
                }}
            }}
        }}
    </script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    </style>
</head>
<body class="bg-darkbg text-gray-100 min-h-screen p-4 md:p-8">
    <div class="max-w-7xl mx-auto">
        <header class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-bordercolor gap-4">
            <div>
                <div class="flex items-center gap-3">
                    <h1 class="text-2xl md:text-3xl font-extrabold text-emerald-400 tracking-wide">🏆 Global VCP Elite Ranking</h1>
                    <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Top 12</span>
                </div>
                <p class="text-gray-400 text-xs md:text-sm mt-1">Institutionelle Ausbruchs-Muster & Volumendynamik (Klick auf Ticker öffnet TradingView Chart)</p>
            </div>
            <div id="stats-box" class="bg-cardbg px-4 py-2.5 rounded-xl border border-bordercolor text-xs md:text-sm text-gray-300 flex items-center gap-3">
                <span>Lade Daten...</span>
            </div>
        </header>

        <div class="bg-cardbg rounded-xl border border-bordercolor overflow-hidden shadow-2xl">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-900/80 text-gray-400 text-xs uppercase tracking-wider border-b border-bordercolor">
                            <th class="p-4">Rang</th>
                            <th class="p-4">Region</th>
                            <th class="p-4">Ticker (Chart Link)</th>
                            <th class="p-4">Kurs</th>
                            <th class="p-4">VCP Spanne (20D)</th>
                            <th class="p-4">52W-Hoch Abstand</th>
                            <th class="p-4">Volumen-Power</th>
                            <th class="p-4 text-right">Trend (5T)</th>
                        </tr>
                    </thead>
                    <tbody id="stockTableBody" class="divide-y divide-bordercolor text-sm"></tbody>
                </table>
            </div>
        </div>
        <footer class="mt-4 text-center md:text-right text-xs text-gray-500">
            Automatische Aktualisierung via Python & GitHub Actions | Datenquelle: Yahoo Finance
        </footer>
    </div>

    <script>
        const stocksData = {json.dumps(dashboard_data, indent=2)};

        function getTradingViewUrl(ticker, region) {{
            let symbol = ticker;
            if (ticker.endsWith('.DE')) symbol = 'XETR:' + ticker.replace('.DE', '');
            else if (ticker.endsWith('.AS')) symbol = 'AMEX:' + ticker.replace('.AS', '');
            else if (ticker.endsWith('.PA')) symbol = 'EURONEXT:' + ticker.replace('.PA', '');
            else if (ticker.endsWith('.L')) symbol = 'LSE:' + ticker.replace('.L', '');
            else if (ticker.endsWith('.SW')) symbol = 'SIX:' + ticker.replace('.SW', '');
            else if (ticker.endsWith('.HK')) symbol = 'HKEX:' + ticker.replace('.HK', '');
            else if (ticker.endsWith('.T')) symbol = 'TSE:' + ticker.replace('.T', '');
            return `https://www.tradingview.com/chart/?symbol=${{encodeURIComponent(symbol)}}`;
        }}

        function renderTable(data) {{
            const tbody = document.getElementById('stockTableBody');
            const statsBox = document.getElementById('stats-box');
            tbody.innerHTML = '';

            statsBox.innerHTML = `
                <div class="flex items-center gap-2">
                    <span class="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span><strong class="text-emerald-400">${{data.length}}</strong> Elite-Setups aktiv</span>
                </div>
            `;

            if (!data || data.length === 0) {{
                tbody.innerHTML = `<tr><td colspan="8" class="p-8 text-center text-gray-400">Keine Daten im Scan gefunden.</td></tr>`;
                return;
            }}

            data.forEach(stock => {{
                const history = stock.history || [];
                let miniChart = '';
                if (history.length > 1) {{
                    const min = Math.min(...history);
                    const max = Math.max(...history);
                    const range = max - min === 0 ? 1 : max - min;
                    const points = history.map((val, idx) => {{
                        const x = (idx / (history.length - 1)) * 75;
                        const y = 22 - ((val - min) / range) * 18;
                        return `${{x}},${{y}}`;
                    }}).join(' ');
                    miniChart = `<svg width="75" height="25" class="inline-block ml-auto"><polyline fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" points="${{points}}"/></svg>`;
                }}

                let rankBadge = `<span class="font-bold text-gray-400 px-2">#${{stock.rank}}</span>`;
                if (stock.rank === 1) rankBadge = `<span class="px-2.5 py-1 bg-amber-500/20 text-amber-300 font-bold rounded-lg border border-amber-500/40 shadow-sm">🥇 #1</span>`;
                if (stock.rank === 2) rankBadge = `<span class="px-2.5 py-1 bg-slate-300/20 text-slate-200 font-bold rounded-lg border border-slate-300/40 shadow-sm">🥈 #2</span>`;
                if (stock.rank === 3) rankBadge = `<span class="px-2.5 py-1 bg-amber-700/20 text-amber-500 font-bold rounded-lg border border-amber-700/40 shadow-sm">🥉 #3</span>`;

                const vcpTightClass = stock.vcp <= 5.0 ? 'text-emerald-400 font-bold' : 'text-gray-200';

                let volBadge = `<span class="text-gray-400">${{stock.volRatio.toFixed(2)}}x</span>`;
                if (stock.volRatio >= 1.5) {{
                    volBadge = `<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold border border-emerald-500/30">🔥 ${{stock.volRatio.toFixed(2)}}x</span>`;
                }} else if (stock.volRatio >= 1.2) {{
                    volBadge = `<span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 font-semibold">${{stock.volRatio.toFixed(2)}}x</span>`;
                }}

                const tvUrl = getTradingViewUrl(stock.ticker, stock.region);

                const row = `
                    <tr class="hover:bg-slate-800/60 transition duration-150">
                        <td class="p-4">${{rankBadge}}</td>
                        <td class="p-4"><span class="px-2 py-0.5 bg-slate-800 text-xs rounded text-gray-300 border border-slate-700 font-medium">${{stock.region}}</span></td>
                        <td class="p-4 font-bold text-base">
                            <a href="${{tvUrl}}" target="_blank" rel="noopener noreferrer" class="text-emerald-400 hover:text-emerald-300 hover:underline flex items-center gap-1.5 group">
                                <span>${{stock.ticker}}</span>
                                <svg class="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                            </a>
                        </td>
                        <td class="p-4 font-semibold text-gray-100">${{stock.price.toFixed(2)}}</td>
                        <td class="p-4 ${{vcpTightClass}}">${{stock.vcp.toFixed(2)}}%</td>
                        <td class="p-4 ${{stock.highDist >= -2 ? 'text-emerald-400 font-bold' : 'text-gray-300'}}">${{stock.highDist.toFixed(2)}}%</td>
                        <td class="p-4">${{volBadge}}</td>
                        <td class="p-4 text-right">${{miniChart}}</td>
                    </tr>
                `;
                tbody.innerHTML += row;
            }});
        }}

        renderTable(stocksData);
    </script>
</body>
</html>"""
    
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("\n[i] 'dashboard.html' erfolgreich erstellt! Du kannst sie jetzt einfach im Browser öffnen.")

def main():
    print("=== STARTE INSTITUTIONELLEN GLOBALEN VCP-SCANNER ==_\n")
    results = []
    
    us_tickers = get_us_tickers()
    print(f"Scanne {len(us_tickers)} US-Aktien...")
    for ticker in us_tickers:
        res = analyze_stock(ticker, "USA")
        if res: results.append(res)
        time.sleep(0.01)

    global_markets = get_global_tickers()
    for region, tickers in global_markets.items():
        print(f"Scanne Region {region} ({len(tickers)} Aktien)...")
        for ticker in tickers:
            res = analyze_stock(ticker, region)
            if res: results.append(res)
            time.sleep(0.01)

    results = sorted(results, key=lambda x: x['Score'], reverse=True)
    top_highlights = results[:12]

    dashboard_data = []
    for idx, r in enumerate(top_highlights, 1):
        print(f"  #{idx}: {r['Ticker']} ({r['Region']}) | Score: {r['Score']} | VCP: {r['20D_Range_%']}%")
        dashboard_data.append({
            "rank": idx,
            "score": r['Score'],
            "ticker": r['Ticker'],
            "region": r['Region'],
            "price": r['Kurs'],
            "vcp": r['20D_Range_%'],
            "highDist": r['Abstand_52W_Hoch_%'],
            "volRatio": r['Vol_Ratio'],
            "history": r['History']
        })
        
    generate_html_dashboard(dashboard_data)

    if top_highlights:
        msg = "🚨 *Global Breakout Ranking (Top 12 Elite)* 🚨\n\n"
        for idx, r in enumerate(top_highlights, 1):
            msg += f"*{idx}. {r['Ticker']}* ({r['Region']}) | VCP: `{r['20D_Range_%']}%` | Vol: `{r['Vol_Ratio']}x`\n"
        send_telegram_alert(msg)

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()