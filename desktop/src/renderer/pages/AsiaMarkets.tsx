import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Globe, RefreshCw, Search, Loader2, AlertTriangle, Clock } from 'lucide-react';
import {
  getAsiaIndices, getAsiaFx, getAsiaQuote, getMarketStatus, apiErrorMessage, QUOTE_RANGES,
} from '../lib/asiaMarketsApi';
import type {
  IndexBoard, FxBoard, TickerQuote, MarketStatus, BoardStatus, QuoteRange, IndexRow,
} from '../lib/asiaMarketsApi';
import { COUNTRIES, formatNumber, formatPercent, formatMarketTime, getCountry } from '../lib/region';
import type { CountryCode } from '../lib/region';
import { useToast } from '../components/Toast';

const SUFFIX_HINTS: { country: string; examples: string }[] = [
  { country: 'India', examples: '.NS (NSE), .BO (BSE)' },
  { country: 'China', examples: '.SS (Shanghai), .SZ (Shenzhen)' },
  { country: 'Japan', examples: '.T (Tokyo)' },
  { country: 'South Korea', examples: '.KS (KOSPI), .KQ (KOSDAQ)' },
];

const BOARD_BADGE: Record<BoardStatus, { label: string; className: string; dot: string }> = {
  live: { label: 'Quotes available', className: 'bg-green-50 text-green-700 border-green-200', dot: 'bg-green-500' },
  partial: { label: 'Partly available', className: 'bg-amber-50 text-amber-700 border-amber-200', dot: 'bg-amber-500' },
  unavailable: { label: 'Quotes unavailable', className: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-500' },
};

const MARKET_BADGE: Record<MarketStatus['status'], { label: string; className: string }> = {
  open: { label: 'Open', className: 'bg-green-50 text-green-700' },
  break: { label: 'Midday break', className: 'bg-amber-50 text-amber-700' },
  closed: { label: 'Closed', className: 'bg-gray-100 text-gray-600' },
};

function changeColor(value: number | null | undefined): string {
  if (value == null || value === 0) return 'text-gray-600';
  return value > 0 ? 'text-green-700' : 'text-red-700';
}

function StatusBadge({ status }: { status: BoardStatus }) {
  const badge = BOARD_BADGE[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${badge.className}`}>
      <span className={`w-2 h-2 rounded-full ${badge.dot}`} /> {badge.label}
    </span>
  );
}

function Unavailable({ error }: { error?: string }) {
  return <span className="text-xs text-red-700" title={error}>Unavailable{error ? `: ${error}` : ''}</span>;
}

export default function AsiaMarkets() {
  const { toast } = useToast();
  const [indices, setIndices] = useState<IndexBoard | null>(null);
  const [fx, setFx] = useState<FxBoard | null>(null);
  const [markets, setMarkets] = useState<MarketStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [boardError, setBoardError] = useState('');

  const [ticker, setTicker] = useState('');
  const [range, setRange] = useState<QuoteRange>('6mo');
  const [quote, setQuote] = useState<TickerQuote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState('');

  const loadBoards = useCallback(async (announce: boolean) => {
    setLoading(true); setBoardError('');
    const [indexResult, fxResult, statusResult] = await Promise.allSettled([getAsiaIndices(), getAsiaFx(), getMarketStatus()]);
    setIndices(indexResult.status === 'fulfilled' ? indexResult.value : null);
    setFx(fxResult.status === 'fulfilled' ? fxResult.value : null);
    if (statusResult.status === 'fulfilled') setMarkets(statusResult.value.markets);
    const failed = [indexResult, fxResult].find((result) => result.status === 'rejected') as PromiseRejectedResult | undefined;
    if (failed) {
      const message = apiErrorMessage(failed.reason, 'Could not reach the Sentinel Risk API');
      setBoardError(message);
      if (announce) toast('error', message);
    } else if (announce) {
      const allLive = indexResult.status === 'fulfilled' && indexResult.value.status === 'live'
        && fxResult.status === 'fulfilled' && fxResult.value.status === 'live';
      toast(allLive ? 'success' : 'warning', allLive ? 'Market data refreshed.' : 'Some quotes are unavailable.');
    }
    setLoading(false);
  }, [toast]);

  useEffect(() => { loadBoards(false); }, []);

  async function lookup(event?: FormEvent, nextRange: QuoteRange = range) {
    event?.preventDefault();
    const symbol = ticker.trim();
    if (!symbol) { setQuoteError('Enter a ticker with its exchange suffix. Supported suffixes are listed below.'); return; }
    setQuoteLoading(true); setQuoteError('');
    try {
      setQuote(await getAsiaQuote(symbol, nextRange));
    } catch (cause) {
      setQuote(null);
      setQuoteError(apiErrorMessage(cause, 'Lookup failed'));
    } finally { setQuoteLoading(false); }
  }

  function changeRange(next: QuoteRange) {
    setRange(next);
    if (quote) lookup(undefined, next);
  }

  const overall: BoardStatus | null = indices && fx
    ? (indices.status === 'live' && fx.status === 'live' ? 'live'
      : indices.status === 'unavailable' && fx.status === 'unavailable' ? 'unavailable' : 'partial')
    : null;
  const statusFor = (code: CountryCode) => markets.find((market) => market.country === code && !market.related_index);
  const hongKong = markets.find((market) => market.related_index);
  const history = quote?.history ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
            <Globe className="text-cascade-gold" size={20} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-cascade-charcoal">Asia Markets</h1>
            <p className="text-sm text-gray-500">Benchmark indices, USD rates and ticker lookup for India, China, Japan and South Korea</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {overall && <StatusBadge status={overall} />}
          <button onClick={() => loadBoards(true)} disabled={loading}
            className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />} Refresh
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Prices come from Yahoo Finance's public chart endpoint and may be delayed, rate limited or unavailable.
        Check the source timestamp for each quote. This unofficial feed is unsuitable for trade execution or valuation.
      </p>

      {boardError && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{boardError}</p>
        </div>
      )}

      {/* Market hours */}
      {markets.length > 0 && (
        <div className="bg-white rounded-xl border p-5">
          <h2 className="text-sm font-semibold text-cascade-charcoal mb-3 flex items-center gap-2"><Clock size={15} /> Market hours</h2>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {markets.map((market) => (
              <div key={market.name} className="border rounded-lg p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-cascade-charcoal">{market.name}</p>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${MARKET_BADGE[market.status].className}`}>
                    {MARKET_BADGE[market.status].label}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{market.weekday} {market.local_time.slice(11)} {market.timezone_label}</p>
                <p className="text-xs text-gray-400">{market.sessions.map(([start, end]) => `${start} to ${end}`).join(', ')}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-3">{markets[0].note}</p>
        </div>
      )}

      {/* Index board */}
      <div className="bg-white rounded-xl border p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-cascade-charcoal">Benchmark indices</h2>
          {indices && <StatusBadge status={indices.status} />}
        </div>
        {!indices && loading && <p className="text-sm text-gray-500 flex items-center gap-2"><Loader2 className="animate-spin" size={14} /> Loading indices</p>}
        {!indices && !loading && <p className="text-sm text-gray-500">No index data loaded.</p>}
        {indices && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {COUNTRIES.map((country) => {
              const rows = indices.indices.filter((row) => row.country === country.code);
              const status = statusFor(country.code);
              return (
                <div key={country.code} className="border rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between bg-gray-50 px-3 py-2">
                    <p className="text-sm font-semibold text-cascade-charcoal">{country.name}</p>
                    {status && <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${MARKET_BADGE[status.status].className}`}>{MARKET_BADGE[status.status].label}</span>}
                  </div>
                  <table className="w-full text-sm">
                    <tbody>
                      {rows.map((row: IndexRow) => (
                        <tr key={row.symbol} className="border-t">
                          <td className="px-3 py-2">
                            <p className="font-medium text-cascade-charcoal">{row.name}</p>
                            <p className="text-xs text-gray-400">
                              {row.symbol}{row.market_name ? ` / ${row.market_name}` : ''}
                              {row.optional && hongKong ? ` / ${MARKET_BADGE[hongKong.status].label}` : ''}
                            </p>
                          </td>
                          {row.status === 'live' ? (
                            <>
                              <td className="px-3 py-2 text-right font-semibold">{formatNumber(row.price, country.code)}</td>
                              <td className={`px-3 py-2 text-right whitespace-nowrap ${changeColor(row.change)}`}>
                                <p>{formatPercent(row.change_pct, 2, true)}</p>
                                <p className="text-xs">{row.change != null && row.change > 0 ? '+' : ''}{formatNumber(row.change, country.code)}</p>
                              </td>
                              <td className="px-3 py-2 text-right text-xs text-gray-400 whitespace-nowrap">
                                {formatMarketTime(row.as_of, row.timezone || country.timeZone)}
                              </td>
                            </>
                          ) : (
                            <td colSpan={3} className="px-3 py-2 text-right"><Unavailable error={row.error} /></td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}
        {indices && <p className="text-xs text-gray-400 mt-3">Change is against the previous session close. Times are local exchange time. Source: {indices.source}.</p>}
      </div>

      {/* FX board */}
      <div className="bg-white rounded-xl border p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-cascade-charcoal">USD exchange rates</h2>
          {fx && <StatusBadge status={fx.status} />}
        </div>
        {!fx && loading && <p className="text-sm text-gray-500 flex items-center gap-2"><Loader2 className="animate-spin" size={14} /> Loading rates</p>}
        {!fx && !loading && <p className="text-sm text-gray-500">No rate data loaded.</p>}
        {fx && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {fx.rates.map((rate) => (
              <div key={rate.symbol} className="border rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">{rate.pair} <span className="text-gray-400">({getCountry(rate.country).name})</span></p>
                {rate.status === 'live' ? (
                  <>
                    <p className="text-xl font-bold text-cascade-charcoal">{formatNumber(rate.price, rate.country, rate.price != null && rate.price < 20 ? 4 : 2)}</p>
                    <p className={`text-xs ${changeColor(rate.change)}`}>{formatPercent(rate.change_pct, 2, true)} vs previous close</p>
                    <p className="text-xs text-gray-400 mt-1" title={rate.as_of || 'Source timestamp unavailable'}>As of {formatMarketTime(rate.as_of, rate.timezone || 'UTC')} ({rate.timezone || 'UTC'})</p>
                  </>
                ) : <Unavailable error={rate.error} />}
              </div>
            ))}
          </div>
        )}
        <p className="text-xs text-gray-400 mt-3">Quoted as local currency units per 1 US dollar. A rising rate means the local currency has weakened against the dollar.</p>
      </div>

      {/* Ticker lookup */}
      <div className="bg-white rounded-xl border p-5 space-y-4">
        <h2 className="text-sm font-semibold text-cascade-charcoal">Ticker lookup</h2>
        <form onSubmit={lookup} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="asia-ticker" className="block text-xs text-gray-500 mb-1">Ticker with exchange suffix</label>
            <input id="asia-ticker" value={ticker} onChange={(event) => setTicker(event.target.value)} maxLength={20}
              placeholder="Symbol with exchange suffix" spellCheck={false} autoCapitalize="characters"
              className="border rounded-lg px-3 py-2 text-sm font-mono w-56 uppercase" />
          </div>
          <div>
            <label htmlFor="asia-range" className="block text-xs text-gray-500 mb-1">History</label>
            <select id="asia-range" value={range} onChange={(event) => changeRange(event.target.value as QuoteRange)}
              className="border rounded-lg px-3 py-2 text-sm bg-white">
              {QUOTE_RANGES.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </div>
          <button type="submit" disabled={quoteLoading}
            className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {quoteLoading ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />} Look up
          </button>
        </form>
        <p className="text-xs text-gray-500">
          Suffixes: {SUFFIX_HINTS.map((hint) => `${hint.country} ${hint.examples}`).join('; ')}.
        </p>

        {quoteError && <p role="alert" className="text-sm text-red-700">{quoteError}</p>}

        {quote && quote.status === 'unavailable' && (
          <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
            <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
            <div>
              <p className="text-sm font-medium text-red-700">Quote unavailable for {quote.symbol}</p>
              <p className="text-sm text-red-700">{quote.error}</p>
            </div>
          </div>
        )}

        {quote && quote.status === 'live' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <p className="text-lg font-bold text-cascade-charcoal">{quote.name || quote.symbol}</p>
              <p className="text-xs text-gray-400">{quote.symbol}{quote.exchange ? ` / ${quote.exchange}` : ''}{quote.currency ? ` / ${quote.currency}` : ''}</p>
              <StatusBadge status="live" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="border rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">Last available price</p>
                <p className="text-xl font-bold text-cascade-charcoal">{formatNumber(quote.price, quote.currency === 'INR' ? 'IN' : 'JP')}</p>
                <p className={`text-xs ${changeColor(quote.change)}`}>{formatPercent(quote.change_pct, 2, true)} vs previous close</p>
              </div>
              <div className="border rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">Day range</p>
                <p className="text-sm font-semibold">{formatNumber(quote.day_low, 'JP')} to {formatNumber(quote.day_high, 'JP')}</p>
              </div>
              <div className="border rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">52-week range</p>
                <p className="text-sm font-semibold">{formatNumber(quote.fifty_two_week_low, 'JP')} to {formatNumber(quote.fifty_two_week_high, 'JP')}</p>
              </div>
              <div className="border rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">As of (exchange time)</p>
                <p className="text-sm font-semibold">{formatMarketTime(quote.as_of, quote.timezone || 'UTC')}</p>
              </div>
            </div>
            {history.length > 1 ? (
              <div>
                <p className="text-xs text-gray-500 mb-2">Closing price, {quote.range} ({quote.interval} bars, {history.length} points)</p>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={history}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                    <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} width={70}
                      tickFormatter={(value: number) => formatNumber(value, 'JP', value < 100 ? 2 : 0)} />
                    <Tooltip formatter={(value: number) => [formatNumber(value, 'JP'), 'Close']} />
                    <Line type="monotone" dataKey="close" stroke="#92761f" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-gray-500">No price history returned for this range.</p>}
            <p className="text-xs text-gray-400">Source: {quote.source}.</p>
          </div>
        )}
      </div>
    </div>
  );
}
