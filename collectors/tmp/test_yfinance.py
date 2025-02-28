import yfinance as yf
from datetime import datetime, timedelta

def calculate_bagger_years(daily_quotes, buy_date, buy_price, n_times):
    """Calculate years to achieve N-bagger."""
    bagger_obj = next((row for row in daily_quotes if row['Close'] >= buy_price * n_times), None)
    if bagger_obj:
        bagger_date = datetime.strptime(bagger_obj['Date'], '%Y-%m-%d')
        delta_years = (bagger_date - buy_date).days / 365.0
        return round(delta_years, 2)
    return "None"

def get_n_bagger_info(code, start_date='1900-01-01'):
    """Calculate bagger information using yfinance."""
    # Fetch stock data
    stock = yf.Ticker(code)
    hist = stock.history(start=start_date)
    hist.reset_index(inplace=True)
    hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')

    if hist.empty:
        return None

    # Find minimum price in the first year
    hist_first_year = hist[hist['Date'] <= (datetime.strptime(hist['Date'].iloc[0], '%Y-%m-%d') + timedelta(days=365)).strftime('%Y-%m-%d')]
    min_price_row = hist_first_year.loc[hist_first_year['Close'].idxmin()]
    buy_price = min_price_row['Close']
    buy_date = datetime.strptime(min_price_row['Date'], '%Y-%m-%d')

    # Calculate N-bagger years
    five_bagger_years = calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 5)
    seven_bagger_years = calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 7)
    ten_bagger_years = calculate_bagger_years(hist.to_dict('records'), buy_date, buy_price, 10)

    # Calculate max N-bagger and current N-bagger
    max_price_row = hist.loc[hist['Close'].idxmax()]
    max_n_bagger = round(max_price_row['Close'] / buy_price, 1)
    max_n_bagger_date = max_price_row['Date']
    max_bagger_years = round((datetime.strptime(max_n_bagger_date, '%Y-%m-%d') - buy_date).days / 365.0, 2)

    current_n_bagger = round(hist['Close'].iloc[-1] / buy_price, 1)

    return {
        "Current N-Bagger": current_n_bagger,
        "Max N-Bagger": max_n_bagger,
        "Years to 5-Bagger": five_bagger_years,
        "Years to 7-Bagger": seven_bagger_years,
        "Years to 10-Bagger": ten_bagger_years,
        "Max Bagger Years": max_bagger_years
    }

# Example usage
code = "3496.T"
result = get_n_bagger_info(code)
print(result)
