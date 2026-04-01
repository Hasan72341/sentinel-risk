"""Asia market data tests. The HTTP layer is mocked; nothing hits the network."""

import asyncio
import unittest
from unittest import mock

import httpx

from app.services import asia_markets
from app.services.asia_markets import MarketDataError, normalize_symbol, parse_chart


def chart_payload(symbol="^NSEI", currency="INR", price=22421.95,
                  closes=(22780.25, 22716.2, 22620.45, 22421.95, None)):
    """Same shape as a real chart response, including the trailing empty bar
    the endpoint adds for a session that has not traded yet."""
    start = 1790567100
    return {"chart": {"result": [{
        "meta": {
            "currency": currency, "symbol": symbol, "exchangeName": "NSI",
            "fullExchangeName": "NSE", "instrumentType": "INDEX",
            "regularMarketTime": 1790848872, "exchangeTimezoneName": "Asia/Kolkata",
            "regularMarketPrice": price, "fiftyTwoWeekHigh": 26373.2,
            "fiftyTwoWeekLow": 22182.55, "regularMarketDayHigh": 22610.6,
            "regularMarketDayLow": 22217.3, "regularMarketVolume": 0,
            "longName": "NIFTY 50", "chartPreviousClose": 22780.25,
        },
        "timestamp": [start + 86400 * i for i in range(len(closes))],
        "indicators": {"quote": [{
            "open": list(closes), "high": list(closes), "low": list(closes),
            "close": list(closes), "volume": [100 if c is not None else None for c in closes],
        }]},
    }], "error": None}}


NOT_FOUND = {"chart": {"result": None, "error": {
    "code": "Not Found", "description": "No data found, symbol may be delisted"}}}


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


class ParseChartTests(unittest.TestCase):
    def test_quote_uses_last_completed_bar_as_previous_close(self):
        quote = parse_chart(chart_payload())
        self.assertEqual(quote["symbol"], "^NSEI")
        self.assertEqual(quote["name"], "NIFTY 50")
        self.assertEqual(quote["currency"], "INR")
        self.assertEqual(quote["price"], 22421.95)
        # Previous close is 22620.45 (the bar before the latest), not the
        # range-start chartPreviousClose of 22780.25.
        self.assertEqual(quote["previous_close"], 22620.45)
        self.assertAlmostEqual(quote["change"], -198.5, places=6)
        # -198.5 / 22620.45 * 100 = -0.8775%
        self.assertAlmostEqual(quote["change_pct"], -0.8775, places=4)
        self.assertEqual(quote["as_of"], "2026-10-01T10:01:12Z")  # 15:31 in Mumbai

    def test_null_bars_are_dropped_from_history(self):
        history = parse_chart(chart_payload())["history"]
        self.assertEqual(len(history), 4)
        self.assertEqual([bar["close"] for bar in history], [22780.25, 22716.2, 22620.45, 22421.95])
        self.assertEqual(history[0]["date"], "2026-09-28")

    def test_single_bar_falls_back_to_chart_previous_close(self):
        quote = parse_chart(chart_payload(price=110.0, closes=(110.0,)))  # one bar only
        self.assertEqual(quote["previous_close"], 22780.25)

    def test_source_error_and_bad_shapes_raise(self):
        with self.assertRaisesRegex(MarketDataError, "delisted"):
            parse_chart(NOT_FOUND)
        for bad in ({}, {"chart": {"result": [], "error": None}}, "text", None):
            with self.assertRaises(MarketDataError):
                parse_chart(bad)

    def test_symbol_validation(self):
        self.assertEqual(normalize_symbol(" reliance.ns "), "RELIANCE.NS")
        self.assertEqual(normalize_symbol("^n225"), "^N225")
        for bad in ("", "AAA/../x", "a b", "x" * 21, "7203.T?range=1d"):
            with self.assertRaises(ValueError):
                normalize_symbol(bad)


class FetchTests(unittest.TestCase):
    def setUp(self):
        asia_markets.clear_cache()

    def run_with(self, handler, coroutine_factory):
        with mock.patch.object(asia_markets, "_new_client", mock_client(handler)):
            return asyncio.run(coroutine_factory())

    def test_quote_live_and_request_shape(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=chart_payload("7203.T", "JPY", 3000.0, (2900.0, 3000.0)))

        result = self.run_with(handler, lambda: asia_markets.get_quote("7203.t", "1mo"))
        self.assertEqual(result["status"], "live")
        self.assertEqual(result["symbol"], "7203.T")
        self.assertEqual(result["currency"], "JPY")
        self.assertEqual(result["change"], 100.0)
        self.assertAlmostEqual(result["change_pct"], 3.4483, places=4)  # 100 / 2900
        self.assertEqual(len(result["history"]), 2)
        self.assertEqual(seen[0].url.host, "query1.finance.yahoo.com")
        self.assertEqual(seen[0].url.path, "/v8/finance/chart/7203.T")
        self.assertEqual(seen[0].url.params["range"], "1mo")
        self.assertEqual(seen[0].url.params["interval"], "1d")

    def test_index_symbol_is_percent_encoded(self):
        paths = []

        def handler(request):
            paths.append(request.url.raw_path.decode())
            return httpx.Response(200, json=chart_payload())

        self.run_with(handler, lambda: asia_markets.get_quote("^NSEI", "5d"))
        self.assertTrue(paths[0].startswith("/v8/finance/chart/%5ENSEI?"))

    def test_rate_limit_returns_unavailable_without_prices(self):
        calls = []

        def handler(request):
            calls.append(request.url.host)
            return httpx.Response(429, text="Too Many Requests")

        result = self.run_with(handler, lambda: asia_markets.get_quote("INFY.NS"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["message"], "Live data unavailable")
        self.assertIn("429", result["error"])
        self.assertNotIn("price", result)
        self.assertNotIn("history", result)
        # Both hosts are tried once.
        self.assertEqual(calls, ["query1.finance.yahoo.com", "query2.finance.yahoo.com"])

    def test_second_host_is_used_when_first_fails(self):
        def handler(request):
            if request.url.host.startswith("query1"):
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(200, json=chart_payload())

        result = self.run_with(handler, lambda: asia_markets.get_quote("^NSEI"))
        self.assertEqual(result["status"], "live")

    def test_timeout_network_error_and_html_are_unavailable(self):
        def timeout(request):
            raise httpx.ReadTimeout("slow", request=request)

        def refused(request):
            raise httpx.ConnectError("refused", request=request)

        def html(request):
            return httpx.Response(200, text="<html>consent</html>")

        for handler, expected in ((timeout, "timed out"), (refused, "Network error"), (html, "Unreadable")):
            asia_markets.clear_cache()
            result = self.run_with(handler, lambda: asia_markets.get_quote("005930.KS"))
            self.assertEqual(result["status"], "unavailable")
            self.assertIn(expected, result["error"])
            self.assertNotIn("price", result)

    def test_unknown_symbol_is_unavailable_and_not_retried(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(404, json=NOT_FOUND)

        result = self.run_with(handler, lambda: asia_markets.get_quote("NOPE123.XX"))
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("delisted", result["error"])
        self.assertEqual(len(calls), 1)

    def test_invalid_inputs_raise_before_any_request(self):
        def handler(request):
            raise AssertionError("no request expected")

        with self.assertRaises(ValueError):
            self.run_with(handler, lambda: asia_markets.get_quote("bad symbol"))
        with self.assertRaises(ValueError):
            self.run_with(handler, lambda: asia_markets.get_quote("7203.T", "10y"))

    def test_cache_avoids_second_request(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(200, json=chart_payload())

        async def twice():
            await asia_markets.get_quote("^NSEI", "5d")
            return await asia_markets.get_quote("^NSEI", "5d")

        result = self.run_with(handler, twice)
        self.assertEqual(result["status"], "live")
        self.assertEqual(len(calls), 1)

    def test_index_board_reports_partial_availability(self):
        def handler(request):
            if "N225" in request.url.path or "BSESN" in request.url.path:
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(200, json=chart_payload())

        board = self.run_with(handler, asia_markets.get_index_board)
        self.assertEqual(board["status"], "partial")
        self.assertEqual(board["total_count"], 8)
        self.assertEqual(board["live_count"], 6)
        rows = {row["symbol"]: row for row in board["indices"]}
        self.assertEqual(set(rows), {"^NSEI", "^BSESN", "000001.SS", "000300.SS", "^HSI",
                                     "^N225", "^KS11", "^KQ11"})
        self.assertEqual(rows["^N225"]["status"], "unavailable")
        self.assertNotIn("price", rows["^N225"])
        self.assertEqual(rows["^KS11"]["status"], "live")
        self.assertEqual(rows["^KS11"]["country"], "KR")
        self.assertEqual(rows["^KS11"]["name"], "KOSPI")
        self.assertEqual(rows["^KS11"]["sparkline"], [22780.25, 22716.2, 22620.45, 22421.95])
        self.assertTrue(rows["^HSI"]["optional"])

    def test_fx_board_all_unavailable(self):
        board = self.run_with(lambda request: httpx.Response(503, text="down"), asia_markets.get_fx_board)
        self.assertEqual(board["status"], "unavailable")
        self.assertEqual(board["live_count"], 0)
        self.assertEqual(board["message"], "Live data unavailable")
        self.assertEqual([row["pair"] for row in board["rates"]],
                         ["USD/INR", "USD/CNY", "USD/JPY", "USD/KRW"])
        self.assertTrue(all("price" not in row for row in board["rates"]))

    def test_fx_board_live(self):
        def handler(request):
            return httpx.Response(200, json=chart_payload("INR=X", "INR", 88.5, (88.0, 88.5)))

        board = self.run_with(handler, asia_markets.get_fx_board)
        self.assertEqual(board["status"], "live")
        self.assertEqual(board["rates"][0]["symbol"], "INR=X")
        self.assertEqual(board["rates"][0]["price"], 88.5)
        self.assertNotIn("error", board)


if __name__ == "__main__":
    unittest.main()
