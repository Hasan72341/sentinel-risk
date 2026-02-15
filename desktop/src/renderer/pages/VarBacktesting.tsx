import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, Info, Loader2, ShieldCheck } from 'lucide-react';
import { useToast } from '../components/Toast';
import { apiErrorMessage, formatAmount, runVarBacktest } from '../lib/riskMethodologyApi';
import type { BacktestResult, TrafficLightZone, VarMethod } from '../lib/riskMethodologyApi';

type Source = 'sample' | 'own';

const METHOD_LABEL: Record<VarMethod, string> = {
  historical: 'Historical simulation',
  parametric: 'Parametric (normal)',
};

const ZONE_STYLE: Record<TrafficLightZone, string> = {
  green: 'bg-green-100 text-green-800 border-green-200',
  yellow: 'bg-amber-100 text-amber-800 border-amber-200',
  red: 'bg-red-100 text-red-800 border-red-200',
};

function pnlInputExample(today = new Date()): string {
  const date = new Date(today);
  const dates: string[] = [];
  while (dates.length < 2) {
    date.setDate(date.getDate() - 1);
    if (date.getDay() === 0 || date.getDay() === 6) continue;
    dates.unshift([
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0'),
    ].join('-'));
  }
  return `date,pnl\n${dates[0]},12500\n${dates[1]},-8300`;
}

/** One P&L per line, or "date,pnl" per line. A header row is skipped. */
function parseSeries(raw: string): { pnl: number[]; dates?: string[] } {
  const lines = raw.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const pnl: number[] = [];
  const dates: string[] = [];
  lines.forEach((line, index) => {
    const cells = line.split(/[,;\t]/).map(cell => cell.trim());
    const value = Number(cells[cells.length - 1]);
    if (cells[cells.length - 1] === '' || !Number.isFinite(value)) {
      if (index === 0) return; // header row
      throw new Error(`Line ${index + 1}: "${line}" is not a number`);
    }
    pnl.push(value);
    if (cells.length > 1) dates.push(cells[0]);
  });
  return { pnl, dates: dates.length === pnl.length ? dates : undefined };
}

function pValue(value: number): string {
  return value < 0.001 ? '<0.001' : value.toFixed(3);
}

export default function VarBacktesting() {
  const { toast } = useToast();
  const [source, setSource] = useState<Source>('sample');
  const [ownInput, setOwnInput] = useState('');
  const [confidence, setConfidence] = useState(0.99);
  const [windowDays, setWindowDays] = useState(250);
  const [shown, setShown] = useState<VarMethod>('historical');
  const [results, setResults] = useState<Record<VarMethod, BacktestResult> | null>(null);
  const [usedSource, setUsedSource] = useState<Source>('sample');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const ownPlaceholder = pnlInputExample();

  async function run(nextSource: Source = source) {
    setLoading(true); setError('');
    try {
      const series: { pnl?: number[]; dates?: string[] } = nextSource === 'own' ? parseSeries(ownInput) : {};
      if (nextSource === 'own' && (series.pnl?.length ?? 0) <= windowDays) {
        throw new Error(`Provide more than ${windowDays} observations (the rolling window), or choose a shorter window.`);
      }
      const base = { ...series, confidence, window: windowDays, es_confidence: 0.975 };
      const [historical, parametric] = await Promise.all([
        runVarBacktest({ ...base, method: 'historical' }),
        runVarBacktest({ ...base, method: 'parametric' }),
      ]);
      setResults({ historical, parametric });
      setUsedSource(nextSource);
      toast('success', `Backtest complete: ${historical.n_obs} days, ${historical.n_exceptions} historical and ${parametric.n_exceptions} parametric exceptions`);
    } catch (cause: any) {
      const message = apiErrorMessage(cause, 'VaR backtest failed');
      setError(message);
      toast('error', message);
    } finally { setLoading(false); }
  }

  useEffect(() => { void run('sample'); }, []);

  const result = results?.[shown] ?? null;
  const symbol = usedSource === 'sample' ? '$' : '';
  const chartData = useMemo(() => (result?.series ?? []).map(point => ({
    date: point.date,
    pnl: point.pnl,
    varLine: -point.var,
    esLine: -point.es,
    exception: point.exception ? point.pnl : null,
  })), [result]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <ShieldCheck className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">VaR backtesting</h1>
          <p className="text-sm text-gray-500">Rolling one-day VaR against realised P&amp;L, with coverage tests and expected shortfall.</p>
        </div>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1 max-w-md">
          {([['sample', 'Sample Asia book'], ['own', 'My P&L series']] as const).map(([id, label]) => (
            <button key={id} onClick={() => setSource(id)}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${source === id ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              {label}
            </button>
          ))}
        </div>

        {source === 'sample' ? (
          <p className="text-xs text-gray-500">
            Illustrative multi-asset book with equity, rates, credit spread and FX sensitivities across India, China, Japan and South Korea.
            Its history is synthetic, generated from a fixed random seed. It is sample data, not market data.
          </p>
        ) : (
          <div>
            <label htmlFor="own-pnl" className="block text-sm font-semibold mb-1">Daily P&amp;L (oldest first)</label>
            <textarea id="own-pnl" value={ownInput} onChange={event => setOwnInput(event.target.value)} rows={6}
              placeholder={ownPlaceholder} aria-describedby="own-pnl-hint" spellCheck={false} className="w-full font-mono text-xs border rounded-lg p-3" />
            <p id="own-pnl-hint" className="text-xs text-gray-500 mt-1">One value per line, or YYYY-MM-DD,pnl. Provide at least {windowDays + 1} observations for the selected window. Losses are negative; use one currency. The example amounts show format only.</p>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">VaR confidence</span>
            <select value={confidence} onChange={event => setConfidence(Number(event.target.value))} className="border rounded-lg px-3 py-2 text-sm">
              <option value={0.95}>95%</option>
              <option value={0.975}>97.5%</option>
              <option value={0.99}>99%</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">Rolling window (days)</span>
            <input type="number" min={20} max={2000} value={windowDays} onChange={event => setWindowDays(Number(event.target.value))}
              className="border rounded-lg px-3 py-2 text-sm w-28" />
          </label>
          <button onClick={() => run()} disabled={loading}
            className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <ShieldCheck size={16} />} Run backtest
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {results && result && (
        <>
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1 max-w-md">
            {(Object.keys(METHOD_LABEL) as VarMethod[]).map(method => (
              <button key={method} onClick={() => setShown(method)}
                className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${shown === method ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
                {METHOD_LABEL[method]}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Exceptions</p>
              <p className="text-xl font-bold text-cascade-charcoal">{result.n_exceptions} <span className="text-sm font-normal text-gray-500">vs {result.expected_exceptions.toFixed(1)} expected</span></p>
              <p className="text-xs text-gray-400">{result.n_obs} backtest days, rate {(result.exception_rate * 100).toFixed(2)}%</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Basel traffic light</p>
              <span className={`inline-block px-3 py-1 rounded-full border text-sm font-semibold capitalize ${ZONE_STYLE[result.traffic_light.zone]}`}>{result.traffic_light.zone} zone</span>
              <p className="text-xs text-gray-400 mt-1">
                {result.traffic_light.n_exceptions} in last {result.traffic_light.n_obs} days
                {result.traffic_light.plus_factor !== null && `, add-on ${result.traffic_light.plus_factor.toFixed(2)}`}
              </p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Latest VaR ({(result.confidence * 100).toFixed(1)}%, 1 day)</p>
              <p className="text-xl font-bold text-red-600">{formatAmount(result.series[result.series.length - 1].var, 2, symbol)}</p>
              <p className="text-xs text-gray-400">{METHOD_LABEL[result.method]}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Expected shortfall (97.5%, 1 day)</p>
              <p className="text-xl font-bold text-red-700">{formatAmount(result.expected_shortfall.es_1d, 2, symbol)}</p>
              <p className="text-xs text-gray-400">Latest {result.expected_shortfall.n_obs}-day window</p>
            </div>
          </div>

          {!result.traffic_light.standard_setting && (
            <p className="text-xs text-gray-500 flex items-start gap-2"><Info size={14} className="shrink-0 mt-0.5" />
              The traffic-light zones are defined for a 99% VaR over 250 days. For this setting the zone is derived from the same cumulative binomial probability thresholds (95% and 99.99%) and is indicative only.
            </p>
          )}

          <div className="bg-white rounded-xl border p-5">
            <h3 className="font-semibold text-cascade-charcoal mb-1">Daily P&amp;L against VaR</h3>
            <p className="text-xs text-gray-500 mb-4">
              Red dots mark exceptions: days where the loss exceeded that day&apos;s VaR.
              {usedSource === 'sample' && ' Synthetic sample data, USD.'}
            </p>
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={60} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value, 1, symbol)} width={70} />
                <Tooltip formatter={(value: any, name: any) => [formatAmount(Number(value), 2, symbol), name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line name="Daily P&L" type="linear" dataKey="pnl" stroke="#78716c" strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line name={`VaR ${(result.confidence * 100).toFixed(1)}%`} type="stepAfter" dataKey="varLine" stroke="#92761f" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line name="ES 97.5%" type="stepAfter" dataKey="esLine" stroke="#1a1a19" strokeWidth={1} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
                <Scatter name="Exception" dataKey="exception" fill="#dc2626" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border overflow-x-auto">
            <div className="p-5 pb-3">
              <h3 className="font-semibold text-cascade-charcoal">Coverage tests</h3>
              <p className="text-xs text-gray-500">A p-value below 0.05 rejects the hypothesis at the 5% level.</p>
            </div>
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="p-3">Test</th>
                  <th className="p-3">What it checks</th>
                  {(Object.keys(METHOD_LABEL) as VarMethod[]).map(method => <th key={method} className="p-3 whitespace-nowrap" colSpan={2}>{METHOD_LABEL[method]}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr className="border-t">
                  <td className="p-3 font-medium">Exceptions</td>
                  <td className="p-3 text-gray-600">Observed against expected count</td>
                  {(Object.keys(METHOD_LABEL) as VarMethod[]).map(method => (
                    <td key={method} className="p-3" colSpan={2}>{results[method].n_exceptions} / {results[method].expected_exceptions.toFixed(1)}
                      <span className={`ml-2 px-2 py-0.5 rounded-full border text-xs capitalize ${ZONE_STYLE[results[method].traffic_light.zone]}`}>{results[method].traffic_light.zone}</span>
                    </td>
                  ))}
                </tr>
                {([
                  ['Kupiec proportion of failures', 'Exception rate equals the target rate', 'kupiec'],
                  ['Christoffersen independence', 'Exceptions do not cluster from one day to the next', 'independence'],
                  ['Christoffersen conditional coverage', 'Correct rate and independence jointly', 'conditional_coverage'],
                ] as const).map(([label, checks, key]) => (
                  <tr key={key} className="border-t">
                    <td className="p-3 font-medium">{label}</td>
                    <td className="p-3 text-gray-600">{checks}</td>
                    {(Object.keys(METHOD_LABEL) as VarMethod[]).map(method => {
                      const test = results[method][key];
                      return [
                        <td key={`${method}-stat`} className="p-3 whitespace-nowrap">LR {test.statistic.toFixed(3)}</td>,
                        <td key={`${method}-p`} className={`p-3 whitespace-nowrap ${test.p_value < 0.05 ? 'text-red-700 font-semibold' : ''}`}>p = {pValue(test.p_value)}</td>,
                      ];
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-white rounded-xl border p-5 space-y-3">
            <h3 className="font-semibold text-cascade-charcoal">Expected shortfall at 97.5% with liquidity horizons</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div><p className="text-xs text-gray-500">VaR 97.5%, 1 day</p><p className="font-semibold">{formatAmount(result.expected_shortfall.var_1d, 2, symbol)}</p></div>
              <div><p className="text-xs text-gray-500">ES 97.5%, 1 day</p><p className="font-semibold">{formatAmount(result.expected_shortfall.es_1d, 2, symbol)}</p></div>
              <div><p className="text-xs text-gray-500">ES scaled to {result.expected_shortfall.base_horizon_days} days</p><p className="font-semibold">{formatAmount(result.expected_shortfall.es_base_horizon, 2, symbol)}</p></div>
              <div><p className="text-xs text-gray-500">Liquidity-adjusted ES</p><p className="font-semibold">{result.expected_shortfall.liquidity_adjusted_es === null ? 'Needs a factor breakdown' : formatAmount(result.expected_shortfall.liquidity_adjusted_es, 2, symbol)}</p></div>
            </div>
            {result.expected_shortfall.buckets.length > 0 && (
              <table className="w-full text-sm text-left">
                <thead className="text-gray-600"><tr><th className="py-2 pr-3">Liquidity horizon</th><th className="py-2 pr-3">Risk factors at or beyond it</th><th className="py-2 text-right">10-day ES</th></tr></thead>
                <tbody>{result.expected_shortfall.buckets.map(bucket => (
                  <tr key={bucket.liquidity_horizon_days} className="border-t align-top">
                    <td className="py-2 pr-3 whitespace-nowrap">{bucket.liquidity_horizon_days} days</td>
                    <td className="py-2 pr-3 text-gray-600 text-xs">{bucket.factors.join(', ')}</td>
                    <td className="py-2 text-right whitespace-nowrap">{formatAmount(bucket.es_base_horizon, 2, symbol)}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900">{result.expected_shortfall.note} Liquidity horizons per factor are illustrative.</div>
          </div>

          <div className="bg-white rounded-xl border overflow-x-auto">
            <h3 className="font-semibold text-cascade-charcoal p-5 pb-3">Exceptions ({METHOD_LABEL[result.method]})</h3>
            {result.exceptions.length === 0 ? <p className="px-5 pb-5 text-sm text-gray-500">No exceptions in the backtest window.</p> : (
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-600"><tr>{['Date', 'P&L', 'VaR', 'Loss beyond VaR', 'Loss / VaR'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                <tbody>{result.exceptions.map(row => (
                  <tr key={row.index} className="border-t">
                    <td className="p-3">{row.date}</td>
                    <td className="p-3 text-red-700">{formatAmount(row.pnl, 2, symbol)}</td>
                    <td className="p-3">{formatAmount(row.var, 2, symbol)}</td>
                    <td className="p-3">{formatAmount(row.excess, 2, symbol)}</td>
                    <td className="p-3">{row.loss_to_var === null ? 'n/a' : `${row.loss_to_var.toFixed(2)}x`}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>

          <p className="text-xs text-gray-500">{result.disclaimer}{result.portfolio && ` ${result.portfolio.name}: ${result.portfolio.disclaimer}`}</p>
        </>
      )}
    </div>
  );
}
