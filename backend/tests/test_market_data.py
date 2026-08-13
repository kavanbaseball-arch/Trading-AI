from app.market_data import series_from_stooq_csv, series_from_yahoo_chart


def test_yahoo_chart_parser():
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704067200, 1704153600, 1704240000],
                    "indicators": {
                        "quote": [{"close": [100.0, 101.5, 99.0]}],
                        "adjclose": [{"adjclose": [100.0, 101.5, 99.0]}],
                    },
                }
            ]
        }
    }
    series = series_from_yahoo_chart(payload, "AAPL")
    assert list(series.values) == [100.0, 101.5, 99.0]
    assert series.name == "AAPL"


def test_stooq_rejects_js_challenge():
    html = "<!DOCTYPE html><html><body>This site requires JavaScript to verify your browser.</body></html>"
    try:
        series_from_stooq_csv(html, "AAPL")
        assert False, "should have raised"
    except RuntimeError as exc:
        assert "browser-challenge" in str(exc)


def test_stooq_english_and_polish_headers():
    english = "Date,Open,High,Low,Close,Volume\n2024-01-02,1,1,1,10,1\n2024-01-03,1,1,1,11,1\n"
    series = series_from_stooq_csv(english, "MSFT")
    assert list(series.values) == [10.0, 11.0]
    polish = "Data,Otwarcie,Najwyzszy,Najnizszy,Zamkniecie,Wolumen\n2024-01-02,1,1,1,20,1\n"
    series = series_from_stooq_csv(polish, "MSFT")
    assert list(series.values) == [20.0]
