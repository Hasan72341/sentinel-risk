import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Legend } from 'recharts';
import { AlertTriangle, BarChart3, Calculator, Database, History, Loader2, Plus, SlidersHorizontal, Trash2 } from 'lucide-react';
import { useToast } from '../components/Toast';
import {
  PRODUCT_LABELS, PRODUCT_SERIES_HINT, PRODUCT_SIDES, analyzeMarketData, apiErrorMessage, backtestInitialMargin,
  calculateInitialMargin, compareMarginCalibrations, formatAmount, getSampleSeries, listSampleSeries, parseSeries,
} from '../lib/exposureApi';
import type {
  CalibrationResult, InitialMarginResult, MarginBacktestResult, MarginPosition, MarketDataAnalysis, RiskProduct, SampleSeriesInfo,
} from '../lib/exposureApi';

type Tab = 'calculator' | 'calibration' | 'backtest' | 'market';

interface PositionDraft {
  id: number;
  label: string;
  product: RiskProduct;
  side: string;
  notional: string;
  duration: string;
  strike: string;
  expiryYears: string;
  volatility: string;
  rate: string;
  optionType: 'call' | 'put';
  seriesText: string;
  synthetic: boolean;
}

// Illustrative starting portfolio; each position is paired with a synthetic series on load.
const starterPositions: { sample: string; draft: Omit<PositionDraft, 'id' | 'seriesText' | 'synthetic'> }[] = [
  { sample: 'equity_index', draft: { label: 'Long equity basket', product: 'equity', side: 'long', notional: '1000000', duration: '', strike: '', expiryYears: '', volatility: '', rate: '', optionType: 'call' } },
  { sample: 'swap_rate', draft: { label: 'Pay-fixed 5y swap', product: 'irs', side: 'pay_fixed', notional: '10000000', duration: '4.3', strike: '', expiryYears: '', volatility: '', rate: '', optionType: 'call' } },
  { sample: 'fx_usdjpy', draft: { label: 'Short USD/JPY', product: 'fx', side: 'short', notional: '2000000', duration: '', strike: '', expiryYears: '', volatility: '', rate: '', optionType: 'call' } },
];

function requireNumber(raw: string, label: string): number {
  const value = Number(raw);
  if (raw.trim() === '' || !Number.isFinite(value)) throw new Error(`${label} must be a number`);
  return value;
}

function toPosition(draft: PositionDraft): MarginPosition {
  const name = draft.label || PRODUCT_LABELS[draft.product];
  const position: MarginPosition = {
    product: draft.product, side: draft.side, label: name,
    notional: requireNumber(draft.notional, `${name}: notional`),
  };
  if (draft.product === 'bond' || draft.product === 'irs' || draft.product === 'cds') {
    position.duration = requireNumber(draft.duration, `${name}: duration`);
  }
  if (draft.product === 'equity_option') {
    position.strike = requireNumber(draft.strike, `${name}: strike`);
    position.expiry_years = requireNumber(draft.expiryYears, `${name}: expiry`);
    position.volatility = requireNumber(draft.volatility, `${name}: implied volatility`);
    position.rate = draft.rate.trim() === '' ? 0 : requireNumber(draft.rate, `${name}: rate`);
    position.option_type = draft.optionType;
  }
  return position;
}

function seriesOf(draft: PositionDraft): number[] {
  const series = parseSeries(draft.seriesText);
  if (series.length < 3) throw new Error(`${draft.label || PRODUCT_LABELS[draft.product]}: paste a historical series first`);
  return series;
}

const inputClass = 'w-full mt-1 px-3 py-2 border rounded-lg text-sm';
const buttonClass = 'px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium';

export default function InitialMargin() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('calculator');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [positions, setPositions] = useState<PositionDraft[]>([]);
  const [activeId, setActiveId] = useState(1);
  const [nextId, setNextId] = useState(1);
  const [samples, setSamples] = useState<SampleSeriesInfo[]>([]);

  const [mpor, setMpor] = useState('10');
  const [confidence, setConfidence] = useState('0.99');
  const [lookback, setLookback] = useState('');
  const [lookbacks, setLookbacks] = useState('125, 250, 500');
  const [ewmaLambda, setEwmaLambda] = useState('0.94');
  const [stressWindow, setStressWindow] = useState('250');
  const [backtestLookback, setBacktestLookback] = useState('250');
  const [backtestMethod, setBacktestMethod] = useState<'historical' | 'parametric'>('historical');
  const [nonOverlapping, setNonOverlapping] = useState(false);
  const [volWindow, setVolWindow] = useState('20');

  const [imResult, setImResult] = useState<InitialMarginResult | null>(null);
  const [calibration, setCalibration] = useState<CalibrationResult | null>(null);
  const [backtest, setBacktest] = useState<MarginBacktestResult | null>(null);
  const [market, setMarket] = useState<MarketDataAnalysis | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [list, ...series] = await Promise.all([
          listSampleSeries(), ...starterPositions.map(starter => getSampleSeries(starter.sample)),
        ]);
        if (cancelled) return;
        setSamples(list);
        setPositions(starterPositions.map((starter, i) => ({ ...starter.draft, id: i + 1, seriesText: series[i].series.join(', '), synthetic: true })));
        setNextId(starterPositions.length + 1);
      } catch (cause: any) {
        if (cancelled) return;
        setPositions(starterPositions.map((starter, i) => ({ ...starter.draft, id: i + 1, seriesText: '', synthetic: false })));
        setNextId(starterPositions.length + 1);
        toast('error', apiErrorMessage(cause, 'Could not load the synthetic sample series'));
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const active = positions.find(position => position.id === activeId) ?? positions[0];
  const anySynthetic = positions.some(position => position.synthetic);

  function clearResults() { setImResult(null); setCalibration(null); setBacktest(null); setMarket(null); }

  function update(id: number, patch: Partial<PositionDraft>) {
    setPositions(current => current.map(position => (position.id === id ? { ...position, ...patch } : position)));
    clearResults();
  }

  function addPosition() {
    setPositions(current => [...current, {
      id: nextId, label: '', product: 'equity', side: 'long', notional: '1000000', duration: '', strike: '', expiryYears: '',
      volatility: '', rate: '', optionType: 'call', seriesText: '', synthetic: false,
    }]);
    setActiveId(nextId);
    setNextId(nextId + 1);
    clearResults();
  }

  function removePosition(id: number) {
    setPositions(current => current.filter(position => position.id !== id));
    clearResults();
  }

  async function loadSample(id: number, name: string) {
    if (!name) return;
    try {
      const sample = await getSampleSeries(name);
      update(id, { seriesText: sample.series.join(', '), synthetic: true });
      toast('info', `${sample.label} loaded (synthetic, not market data)`);
    } catch (cause: any) {
      toast('error', apiErrorMessage(cause, 'Could not load the sample series'));
    }
  }

  function settings() {
    return { mporDays: requireNumber(mpor, 'Margin period of risk'), confidence: requireNumber(confidence, 'Confidence') };
  }

  async function run<T>(task: () => Promise<T>, apply: (value: T) => void, done: (value: T) => string, fallback: string) {
    setLoading(true); setError('');
    try {
      const value = await task();
      apply(value);
      toast('success', done(value));
    } catch (cause: any) {
      setError(apiErrorMessage(cause, fallback));
    } finally { setLoading(false); }
  }

  const runCalculator = () => run(
    async () => {
      if (!positions.length) throw new Error('Add at least one position');
      return calculateInitialMargin(
        positions.map(draft => ({ ...toPosition(draft), series: seriesOf(draft) })), settings(),
        lookback.trim() === '' ? null : requireNumber(lookback, 'Look-back'),
      );
    },
    setImResult, value => `Portfolio initial margin ${formatAmount(value.portfolio.historical_im)} (historical)`, 'Initial margin calculation failed',
  );

  const requireActive = () => { if (!active) throw new Error('Add a position first'); return active; };

  const runCalibration = () => run(
    async () => {
      const draft = requireActive();
      return compareMarginCalibrations(toPosition(draft), seriesOf(draft), settings(), {
        lookbacks: parseSeries(lookbacks), ewmaLambda: requireNumber(ewmaLambda, 'EWMA lambda'), stressWindow: requireNumber(stressWindow, 'Stress window'),
      });
    },
    setCalibration, value => `Compared ${value.rows.length} calibrations`, 'Calibration comparison failed',
  );

  const runBacktest = () => run(
    async () => {
      const draft = requireActive();
      return backtestInitialMargin(toPosition(draft), seriesOf(draft), settings(), {
        lookback: requireNumber(backtestLookback, 'Look-back'), method: backtestMethod, nonOverlapping,
      });
    },
    setBacktest, value => `${value.exceptions} exception(s) in ${value.observations} test days`, 'Backtest failed',
  );

  const runMarket = () => run(
    async () => {
      const draft = requireActive();
      const kind = ['bond', 'irs', 'cds'].includes(draft.product) ? 'rate' : 'price';
      return analyzeMarketData(seriesOf(draft), kind, requireNumber(volWindow, 'Volatility window'));
    },
    setMarket, value => `Analysed ${value.observations} observations`, 'Market data analysis failed',
  );

  const tabs: { id: Tab; label: string; icon: typeof Calculator }[] = [
    { id: 'calculator', label: 'Calculator', icon: Calculator },
    { id: 'calibration', label: 'Calibration', icon: SlidersHorizontal },
    { id: 'backtest', label: 'Backtest', icon: History },
    { id: 'market', label: 'Market data', icon: BarChart3 },
  ];

  const activeName = active ? (active.label || PRODUCT_LABELS[active.product]) : 'none';
  const marketUnit = market?.kind === 'price' ? '%' : '';
  const backtestData = backtest?.points.map(point => ({ ...point, loss: -point.realised_pnl }));
  const marketData = market?.returns.map((move, i) => ({ index: i + 1, move, vol: market.rolling_volatility[i] }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Calculator className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Initial Margin</h1>
          <p className="text-sm text-gray-500">Historical-simulation and parametric margin, calibration from market history, and backtesting</p>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
        <Database className="text-amber-600 shrink-0 mt-0.5" size={16} />
        <p className="text-xs text-amber-800">
          <strong>Simplified, for analysis and learning; not a regulatory calculation.</strong>{' '}
          {anySynthetic
            ? 'The starting positions are illustrative and their series are synthetic (generated from a fixed random seed); they are not market data. Paste your own history to analyse a real instrument.'
            : 'Results depend entirely on the history you paste.'}
        </p>
      </div>

      {/* Positions */}
      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-44">
            <label htmlFor="im-mpor" className="text-xs text-gray-500">Margin period of risk (days)</label>
            <input id="im-mpor" type="number" step="1" value={mpor} onChange={event => { setMpor(event.target.value); clearResults(); }} className={inputClass} />
          </div>
          <div className="w-44">
            <label htmlFor="im-confidence" className="text-xs text-gray-500">Confidence (decimal)</label>
            <input id="im-confidence" type="number" step="any" value={confidence} onChange={event => { setConfidence(event.target.value); clearResults(); }} className={inputClass} />
          </div>
          <button onClick={addPosition} className="ml-auto px-3 py-2 border rounded-lg text-sm font-medium text-cascade-charcoal hover:bg-gray-50 flex items-center gap-2">
            <Plus size={16} /> Add position
          </button>
        </div>

        {positions.map(position => (
          <div key={position.id} className={`border rounded-lg p-4 space-y-3 ${position.id === active?.id ? 'border-cascade-gold' : ''}`}>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-gray-500">
                <input type="radio" name="active-position" checked={position.id === active?.id} onChange={() => { setActiveId(position.id); setCalibration(null); setBacktest(null); setMarket(null); }} />
                Use for calibration, backtest and market data
              </label>
              <button onClick={() => removePosition(position.id)} aria-label="Remove position" className="ml-auto text-gray-400 hover:text-red-600"><Trash2 size={16} /></button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div>
                <label className="text-xs text-gray-500">Label</label>
                <input value={position.label} placeholder="Position name" onChange={event => update(position.id, { label: event.target.value })} className={inputClass} />
              </div>
              <div>
                <label className="text-xs text-gray-500">Product</label>
                <select value={position.product} className={inputClass}
                  onChange={event => { const product = event.target.value as RiskProduct; update(position.id, { product, side: PRODUCT_SIDES[product][0].value }); }}>
                  {(Object.keys(PRODUCT_LABELS) as RiskProduct[]).map(key => <option key={key} value={key}>{PRODUCT_LABELS[key]}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">Side</label>
                <select value={position.side} onChange={event => update(position.id, { side: event.target.value })} className={inputClass}>
                  {PRODUCT_SIDES[position.product].map(side => <option key={side.value} value={side.value}>{side.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">{position.product === 'equity_option' ? 'Quantity (underlying units)' : position.product === 'equity' || position.product === 'fx' ? 'Market value' : 'Notional'}</label>
                <input type="number" step="any" value={position.notional} onChange={event => update(position.id, { notional: event.target.value })} className={inputClass} />
              </div>
              {(position.product === 'bond' || position.product === 'irs' || position.product === 'cds') && (
                <div>
                  <label className="text-xs text-gray-500">{position.product === 'cds' ? 'Risky duration (years)' : 'Duration (years)'}</label>
                  <input type="number" step="any" value={position.duration} onChange={event => update(position.id, { duration: event.target.value })} className={inputClass} />
                </div>
              )}
              {position.product === 'equity_option' && (
                <>
                  <div>
                    <label className="text-xs text-gray-500">Type</label>
                    <select value={position.optionType} onChange={event => update(position.id, { optionType: event.target.value as 'call' | 'put' })} className={inputClass}>
                      <option value="call">Call</option>
                      <option value="put">Put</option>
                    </select>
                  </div>
                  {([['strike', 'Strike'], ['expiryYears', 'Expiry (years)'], ['volatility', 'Implied vol (decimal)'], ['rate', 'Rate (decimal)']] as const).map(([key, label]) => (
                    <div key={key}>
                      <label className="text-xs text-gray-500">{label}</label>
                      <input type="number" step="any" value={position[key]} onChange={event => update(position.id, { [key]: event.target.value })} className={inputClass} />
                    </div>
                  ))}
                </>
              )}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <label className="text-xs text-gray-500">Historical series, oldest first: {PRODUCT_SERIES_HINT[position.product]}</label>
                <select value="" onChange={event => loadSample(position.id, event.target.value)} className="ml-auto px-2 py-1 border rounded-lg text-xs">
                  <option value="">Select a synthetic series</option>
                  {samples.map(sample => <option key={sample.name} value={sample.name}>{sample.label}</option>)}
                </select>
              </div>
              <textarea value={position.seriesText} rows={2} spellCheck={false}
                onChange={event => update(position.id, { seriesText: event.target.value, synthetic: false })}
                placeholder={`Paste ${PRODUCT_SERIES_HINT[position.product]}; separate values with commas, spaces or new lines`}
                aria-label={`${position.label || PRODUCT_LABELS[position.product]} historical series`}
                className="w-full mt-1 font-mono text-xs border rounded-lg p-2" />
              <p className="text-xs text-gray-500">Numbers only, without dates or headers. Use the same observation dates across positions.</p>
              {position.synthetic && <p className="text-xs text-amber-700">Synthetic sample series, not market data.</p>}
            </div>
          </div>
        ))}
        {positions.length === 0 && <p className="text-sm text-gray-500">No positions. Add one to start.</p>}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
        {tabs.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); setError(''); }}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === t.id ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Calculator Tab */}
      {tab === 'calculator' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56">
              <label htmlFor="im-lookback" className="text-xs text-gray-500">Look-back (daily moves, blank = all history)</label>
              <input id="im-lookback" type="number" step="1" value={lookback} onChange={event => setLookback(event.target.value)} className={inputClass} />
            </div>
            <button onClick={runCalculator} disabled={loading} className={buttonClass}>
              {loading ? <Loader2 className="animate-spin" size={16} /> : <Calculator size={16} />} Calculate initial margin
            </button>
          </div>
          {imResult && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Portfolio IM, historical</p>
                  <p className="text-xl font-bold text-cascade-gold">{formatAmount(imResult.portfolio.historical_im)}</p>
                  <p className="text-xs text-gray-400">{imResult.portfolio.scenarios} scenarios</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Portfolio IM, parametric</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(imResult.portfolio.parametric_im)}</p>
                  <p className="text-xs text-gray-400">normal, square root of time</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Netting benefit, historical</p>
                  <p className="text-xl font-bold text-green-600">{formatAmount(imResult.portfolio.historical_diversification_benefit)}</p>
                  <p className="text-xs text-gray-400">versus {formatAmount(imResult.portfolio.standalone_historical_im)} standalone</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Worst {imResult.mpor_days}-day scenario</p>
                  <p className="text-xl font-bold text-red-600">{formatAmount(imResult.portfolio.worst_scenario_pnl)}</p>
                  <p className="text-xs text-gray-400">{(imResult.confidence * 100).toFixed(1)}% confidence used for IM</p>
                </div>
              </div>
              <div className="bg-white border rounded-xl overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>{['Position', 'Product', 'Daily volatility', 'Scenarios', 'Historical IM', 'Parametric IM', 'Worst scenario'].map(label => <th key={label} className="p-3 whitespace-nowrap font-medium">{label}</th>)}</tr>
                  </thead>
                  <tbody>
                    {imResult.positions.map((row, i) => (
                      <tr key={i} className="border-t">
                        <td className="p-3 font-medium text-cascade-charcoal">{row.label}</td>
                        <td className="p-3">{PRODUCT_LABELS[row.product]} ({row.side.replace('_', ' ')})</td>
                        <td className="p-3">{row.daily_volatility.toFixed(3)} {row.volatility_unit}</td>
                        <td className="p-3">{row.scenarios}</td>
                        <td className="p-3 font-semibold">{formatAmount(row.historical_im)}</td>
                        <td className="p-3">{formatAmount(row.parametric_im)}</td>
                        <td className="p-3 text-red-700">{formatAmount(row.worst_scenario_pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-4">Standalone and portfolio margin</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={[
                    ...imResult.positions.map(row => ({ name: row.label, historical: row.historical_im, parametric: row.parametric_im })),
                    { name: 'Portfolio', historical: imResult.portfolio.historical_im, parametric: imResult.portfolio.parametric_im },
                  ]}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value)} width={90} />
                    <Tooltip formatter={(value: number) => formatAmount(value)} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="historical" name="Historical IM" fill="#92761f" radius={[6, 6, 0, 0]} />
                    <Bar dataKey="parametric" name="Parametric IM" fill="#4e4732" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4"><p className="text-sm text-blue-800">{imResult.method_note}</p></div>
            </>
          )}
        </div>
      )}

      {/* Calibration Tab */}
      {tab === 'calibration' && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Position: <strong>{activeName}</strong>. The same position is margined on different slices of its history to show how calibration choices move the number.</p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56">
              <label htmlFor="im-lookbacks" className="text-xs text-gray-500">Look-back windows (days)</label>
              <input id="im-lookbacks" value={lookbacks} onChange={event => setLookbacks(event.target.value)} className={inputClass} />
            </div>
            <div className="w-40">
              <label htmlFor="im-lambda" className="text-xs text-gray-500">EWMA lambda</label>
              <input id="im-lambda" type="number" step="any" value={ewmaLambda} onChange={event => setEwmaLambda(event.target.value)} className={inputClass} />
            </div>
            <div className="w-48">
              <label htmlFor="im-stress" className="text-xs text-gray-500">Stressed period length (days)</label>
              <input id="im-stress" type="number" step="1" value={stressWindow} onChange={event => setStressWindow(event.target.value)} className={inputClass} />
            </div>
            <button onClick={runCalibration} disabled={loading} className={buttonClass}>
              {loading ? <Loader2 className="animate-spin" size={16} /> : <SlidersHorizontal size={16} />} Compare calibrations
            </button>
          </div>
          {calibration && (
            <>
              <div className="bg-white border rounded-xl overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>{['Calibration', 'Daily moves', `Daily volatility (${calibration.volatility_unit})`, 'Annualised', 'Parametric IM', 'Historical IM'].map(label => <th key={label} className="p-3 whitespace-nowrap font-medium">{label}</th>)}</tr>
                  </thead>
                  <tbody>
                    {calibration.rows.map(row => (
                      <tr key={row.label} className={`border-t ${row.calibration === 'stressed' ? 'bg-red-50' : ''}`}>
                        <td className="p-3 font-medium text-cascade-charcoal">{row.label}</td>
                        <td className="p-3">{row.daily_moves}</td>
                        <td className="p-3">{row.daily_volatility.toFixed(3)}</td>
                        <td className="p-3">{row.annualised_volatility.toFixed(2)}</td>
                        <td className="p-3">{formatAmount(row.parametric_im)}</td>
                        <td className="p-3">{row.historical_im === null ? 'n/a' : formatAmount(row.historical_im)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-4">Initial margin by calibration</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={calibration.rows.map(row => ({ name: row.label.replace(/ \(.*\)/, ''), historical: row.historical_im, parametric: row.parametric_im }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value)} width={90} />
                    <Tooltip formatter={(value: number) => formatAmount(value)} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="historical" name="Historical IM" fill="#92761f" radius={[6, 6, 0, 0]} />
                    <Bar dataKey="parametric" name="Parametric IM" fill="#4e4732" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4"><p className="text-sm text-blue-800">{calibration.method_note}</p></div>
            </>
          )}
        </div>
      )}

      {/* Backtest Tab */}
      {tab === 'backtest' && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Position: <strong>{activeName}</strong>. Each test day the margin is calibrated on the preceding look-back window and compared with the loss realised over the following margin period of risk.</p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-44">
              <label htmlFor="bt-lookback" className="text-xs text-gray-500">Look-back (days)</label>
              <input id="bt-lookback" type="number" step="1" value={backtestLookback} onChange={event => setBacktestLookback(event.target.value)} className={inputClass} />
            </div>
            <div className="w-44">
              <label htmlFor="bt-method" className="text-xs text-gray-500">Margin method</label>
              <select id="bt-method" value={backtestMethod} onChange={event => setBacktestMethod(event.target.value as 'historical' | 'parametric')} className={inputClass}>
                <option value="historical">Historical simulation</option>
                <option value="parametric">Parametric</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-500 pb-2">
              <input type="checkbox" checked={nonOverlapping} onChange={event => setNonOverlapping(event.target.checked)} />
              Non-overlapping test windows
            </label>
            <button onClick={runBacktest} disabled={loading} className={buttonClass}>
              {loading ? <Loader2 className="animate-spin" size={16} /> : <History size={16} />} Run backtest
            </button>
          </div>
          {backtest && backtestData && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Exceptions</p>
                  <p className={`text-xl font-bold ${backtest.exceptions > Math.ceil(backtest.expected_exceptions) ? 'text-red-600' : 'text-green-600'}`}>{backtest.exceptions}</p>
                  <p className="text-xs text-gray-400">expected {backtest.expected_exceptions} in {backtest.observations} test days</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Exception rate</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{(backtest.exception_rate * 100).toFixed(2)}%</p>
                  <p className="text-xs text-gray-400">target {(backtest.expected_rate * 100).toFixed(2)}%</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Average IM</p>
                  <p className="text-xl font-bold text-cascade-gold">{formatAmount(backtest.average_im)}</p>
                  <p className="text-xs text-gray-400">maximum {formatAmount(backtest.max_im)}</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Worst loss beyond IM</p>
                  <p className="text-xl font-bold text-red-600">{formatAmount(backtest.worst_excess_loss)}</p>
                  <p className="text-xs text-gray-400">{backtest.binomial_p_value === null ? 'binomial test needs non-overlapping windows' : `binomial tail probability ${backtest.binomial_p_value.toFixed(3)}`}</p>
                </div>
              </div>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-1">Margin against realised {backtest.mpor_days}-day loss</h3>
                <p className="text-xs text-gray-500 mb-4">Losses are shown as positive numbers; red dots mark exceptions. The horizontal axis is the observation number in the series.</p>
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={backtestData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="index" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value)} width={90} />
                    <Tooltip formatter={(value: number) => formatAmount(value)} labelFormatter={(value: number) => `Observation ${value}`} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="stepAfter" dataKey="im" name="Initial margin" stroke="#92761f" strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="loss" name="Realised loss (gain if negative)" stroke="#78716c" strokeWidth={1} isAnimationActive={false}
                      dot={(props: any) => (props.payload.exception
                        ? <circle key={props.index} cx={props.cx} cy={props.cy} r={3.5} fill="#dc2626" stroke="#ffffff" strokeWidth={1} />
                        : <g key={props.index} />)} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-1">
                <p className="text-sm text-blue-800 font-medium">{backtest.verdict}</p>
                <p className="text-sm text-blue-800">{backtest.method_note}</p>
              </div>
            </>
          )}
        </div>
      )}

      {/* Market Data Tab */}
      {tab === 'market' && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Series of: <strong>{activeName}</strong>. Price series use relative returns; yield, rate and spread series use absolute changes.</p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-56">
              <label htmlFor="md-window" className="text-xs text-gray-500">Rolling volatility window (days)</label>
              <input id="md-window" type="number" step="1" value={volWindow} onChange={event => setVolWindow(event.target.value)} className={inputClass} />
            </div>
            <button onClick={runMarket} disabled={loading} className={buttonClass}>
              {loading ? <Loader2 className="animate-spin" size={16} /> : <BarChart3 size={16} />} Analyse series
            </button>
          </div>
          {market && marketData && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Observations</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{market.observations}</p>
                  <p className="text-xs text-gray-400">{formatAmount(market.first, 2)} to {formatAmount(market.last, 2)}</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Daily volatility</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{market.daily_volatility.toFixed(3)}{marketUnit}</p>
                  <p className="text-xs text-gray-400">{market.unit}</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Annualised volatility</p>
                  <p className="text-xl font-bold text-cascade-gold">{market.annualised_volatility.toFixed(2)}{marketUnit}</p>
                  <p className="text-xs text-gray-400">daily x square root of 252</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Range</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(market.minimum, 2)} - {formatAmount(market.maximum, 2)}</p>
                  <p className="text-xs text-gray-400">minimum and maximum level</p>
                </div>
              </div>
              <div className="bg-white border rounded-xl overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>{['Horizon', 'Worst down move', 'Observations (from - to)', 'Worst up move', 'Observations (from - to)', '1st percentile', '99th percentile'].map((label, i) => <th key={i} className="p-3 whitespace-nowrap font-medium">{label}</th>)}</tr>
                  </thead>
                  <tbody>
                    {market.worst_moves.map(move => (
                      <tr key={move.horizon_days} className="border-t">
                        <td className="p-3 font-medium text-cascade-charcoal">{move.horizon_days}-day</td>
                        <td className="p-3 text-red-700">{move.worst_down.toFixed(3)}{marketUnit}</td>
                        <td className="p-3 text-gray-500">{move.worst_down_start_index} - {move.worst_down_end_index}</td>
                        <td className="p-3 text-green-700">{move.worst_up.toFixed(3)}{marketUnit}</td>
                        <td className="p-3 text-gray-500">{move.worst_up_start_index} - {move.worst_up_end_index}</td>
                        <td className="p-3">{move.quantile_1pct.toFixed(3)}{marketUnit}</td>
                        <td className="p-3">{move.quantile_99pct.toFixed(3)}{marketUnit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-4">Rolling {market.window}-day volatility, annualised</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={marketData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="index" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value: number) => Number(value).toFixed(3)} labelFormatter={(value: number) => `Observation ${value}`} />
                    <Line type="monotone" dataKey="vol" name="Rolling volatility" stroke="#92761f" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-4">Daily moves</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={marketData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                    <XAxis dataKey="index" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value: number) => Number(value).toFixed(3)} labelFormatter={(value: number) => `Observation ${value}`} />
                    <Line type="monotone" dataKey="move" name="Daily move" stroke="#1a1a19" strokeWidth={1} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
