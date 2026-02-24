import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertTriangle, Flame, Landmark, Loader2, Plus, RotateCcw, Trash2, Undo2 } from 'lucide-react';
import { useToast } from '../components/Toast';
import {
  apiErrorMessage, formatAmount, getScenarioLibrary, runEconomicCapital, runReverseStress, runStressTest,
} from '../lib/riskMethodologyApi';
import type {
  CustomScenario, EconomicCapitalResult, ReverseStressResult, RiskFactor, RiskType,
  ScenarioLibrary, StressResult,
} from '../lib/riskMethodologyApi';

type Tab = 'scenarios' | 'reverse' | 'capital';

const RISK_TYPE_LABEL: Record<RiskType, string> = { equity: 'Equity', rates: 'Rates', credit: 'Credit spread', fx: 'FX' };
const RISK_TYPES = Object.keys(RISK_TYPE_LABEL) as RiskType[];
const LOSS = '#dc2626';
const GAIN = '#16a34a';

function unitHint(factor: RiskFactor): string {
  return factor.unit === '%' ? 'USD per +1%' : 'USD per +1bp';
}

function PnlBars({ data, height = 240 }: { data: { name: string; pnl: number }[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value, 1)} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={190} />
        <Tooltip formatter={(value: any) => [formatAmount(Number(value)), 'P&L']} />
        <ReferenceLine x={0} stroke="#1a1a19" />
        <Bar dataKey="pnl" isAnimationActive={false}>
          {data.map(row => <Cell key={row.name} fill={row.pnl < 0 ? LOSS : GAIN} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function StressTesting() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('scenarios');
  const [library, setLibrary] = useState<ScenarioLibrary | null>(null);
  const [sensitivities, setSensitivities] = useState<Record<string, number>>({});
  const [customScenarios, setCustomScenarios] = useState<CustomScenario[]>([]);
  const [draftName, setDraftName] = useState('');
  const [draftShocks, setDraftShocks] = useState<Record<string, string>>({});
  const [stress, setStress] = useState<StressResult | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [reverseScenario, setReverseScenario] = useState('');
  const [threshold, setThreshold] = useState(50_000_000);
  const [reverse, setReverse] = useState<ReverseStressResult | null>(null);
  const [capital, setCapital] = useState<EconomicCapitalResult | null>(null);
  const [capitalInputs, setCapitalInputs] = useState({ confidence: 0.999, asset_correlation: 0.2, operational_expected_loss: 2_000_000, market_credit: 0.5 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const factors = library?.factors ?? [];
  const isSampleBook = useMemo(() => !!library && library.sample_portfolio.positions.every(
    position => sensitivities[position.factor_id] === position.sensitivity,
  ), [library, sensitivities]);
  const positions = useMemo(
    () => factors.map(factor => ({ factor_id: factor.id, sensitivity: sensitivities[factor.id] ?? 0 })),
    [factors, sensitivities],
  );
  const allScenarios = useMemo(() => [
    ...(library?.scenarios ?? []).map(scenario => ({ id: scenario.id, name: scenario.name, shocks: scenario.shocks })),
    ...customScenarios.map((scenario, index) => ({ id: `custom_${index + 1}`, name: scenario.name, shocks: scenario.shocks })),
  ], [library, customScenarios]);

  function fail(cause: any, fallback: string) {
    const message = apiErrorMessage(cause, fallback);
    setError(message);
    toast('error', message);
  }

  function resetBook(source: ScenarioLibrary | null = library) {
    if (!source) return;
    setSensitivities(Object.fromEntries(source.sample_portfolio.positions.map(p => [p.factor_id, p.sensitivity])));
  }

  async function runScenarios(book = positions, custom = customScenarios) {
    setLoading(true); setError('');
    try {
      // Passing the library ids keeps the library scenarios alongside any user-defined ones.
      const full = await runStressTest(book.length ? book : undefined, library?.scenarios.map(s => s.id), custom);
      setStress(full);
      setSelectedId(current => (full.results.some(row => row.id === current) ? current : full.worst_scenario.id));
      toast('success', `Worst scenario: ${full.worst_scenario.name} (${formatAmount(full.worst_scenario.total_pnl)})`);
    } catch (cause: any) { fail(cause, 'Stress test failed'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const loaded = await getScenarioLibrary();
        setLibrary(loaded);
        resetBook(loaded);
        setReverseScenario(loaded.scenarios[0]?.id ?? '');
        const result = await runStressTest();
        setStress(result);
        setSelectedId(result.worst_scenario.id);
      } catch (cause: any) { fail(cause, 'Could not load the scenario library'); }
      finally { setLoading(false); }
    })();
  }, []);

  function addCustomScenario() {
    const shocks: Record<string, number> = {};
    for (const [factorId, raw] of Object.entries(draftShocks)) {
      if (raw.trim() === '') continue;
      const value = Number(raw);
      if (!Number.isFinite(value)) { setError(`Shock for ${factorId} is not a number`); return; }
      if (value !== 0) shocks[factorId] = value;
    }
    if (!draftName.trim()) { setError('Give the scenario a name'); return; }
    if (Object.keys(shocks).length === 0) { setError('Enter at least one non-zero shock'); return; }
    const next = [...customScenarios, { name: draftName.trim(), description: 'User-defined scenario.', shocks }];
    setCustomScenarios(next); setDraftName(''); setDraftShocks({}); setError('');
    void runScenarios(positions, next);
  }

  function removeCustomScenario(index: number) {
    const next = customScenarios.filter((_, i) => i !== index);
    setCustomScenarios(next);
    void runScenarios(positions, next);
  }

  async function runReverse() {
    const scenario = allScenarios.find(item => item.id === reverseScenario);
    if (!scenario) { setError('Choose a scenario to scale'); return; }
    setLoading(true); setError('');
    try {
      setReverse(await runReverseStress(scenario.shocks, threshold, positions));
    } catch (cause: any) { fail(cause, 'Reverse stress test failed'); }
    finally { setLoading(false); }
  }

  async function runCapital() {
    setLoading(true); setError('');
    try {
      const result = await runEconomicCapital({
        confidence: capitalInputs.confidence,
        asset_correlation: capitalInputs.asset_correlation,
        operational_expected_loss: capitalInputs.operational_expected_loss,
        correlations: { market_credit: capitalInputs.market_credit },
      });
      setCapital(result);
      toast('success', `Economic capital: ${formatAmount(result.economic_capital)}`);
    } catch (cause: any) { fail(cause, 'Economic capital simulation failed'); }
    finally { setLoading(false); }
  }

  const selected = stress?.results.find(row => row.id === selectedId) ?? null;
  const tabs: { id: Tab; label: string; icon: typeof Flame }[] = [
    { id: 'scenarios', label: 'Scenarios', icon: Flame },
    { id: 'reverse', label: 'Reverse stress', icon: Undo2 },
    { id: 'capital', label: 'Economic capital', icon: Landmark },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Flame className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Stress testing and capital</h1>
          <p className="text-sm text-gray-500">Scenario P&amp;L across equity, rates, credit spread and FX for India, China, Japan and South Korea.</p>
        </div>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
        {tabs.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); setError(''); }}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${tab === t.id ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
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

      {tab !== 'capital' && library && (
        <details className="bg-white border rounded-xl p-5" open={false}>
          <summary className="cursor-pointer text-sm font-semibold text-cascade-charcoal">
            Portfolio sensitivities {isSampleBook ? `(${library.sample_portfolio.name})` : '(edited)'}
          </summary>
          <p className="text-xs text-gray-500 mt-2">
            USD P&amp;L for a +1 unit move in each risk factor. FX is the move of the local currency against USD.
            {' '}The sample book is illustrative, not a real portfolio.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mt-3">
            {RISK_TYPES.map(riskType => (
              <div key={riskType} className="space-y-2">
                <p className="text-xs font-semibold text-gray-600">{RISK_TYPE_LABEL[riskType]}</p>
                {factors.filter(factor => factor.risk_type === riskType).map(factor => (
                  <label key={factor.id} className="block text-xs text-gray-500">
                    {factor.label} <span className="text-gray-400">({unitHint(factor)})</span>
                    <input type="number" value={sensitivities[factor.id] ?? 0} step={1000}
                      onChange={event => setSensitivities({ ...sensitivities, [factor.id]: Number(event.target.value) })}
                      className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm text-cascade-charcoal" />
                  </label>
                ))}
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-4">
            <button onClick={() => runScenarios()} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 text-sm font-medium">Apply and rerun scenarios</button>
            <button onClick={() => resetBook()} className="px-4 py-2 border rounded-lg text-sm flex items-center gap-2"><RotateCcw size={14} /> Reset to sample book</button>
          </div>
        </details>
      )}

      {tab === 'scenarios' && (
        <div className="space-y-4">
          {loading && !stress && <p className="text-sm text-gray-500 flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> Running scenarios</p>}
          {stress && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white rounded-xl border p-4 md:col-span-2">
                  <p className="text-xs text-gray-500 mb-1">Worst scenario</p>
                  <p className="text-lg font-bold text-cascade-charcoal">{stress.worst_scenario.name}</p>
                  <p className="text-xl font-bold text-red-600">{formatAmount(stress.worst_scenario.total_pnl)}</p>
                </div>
                <div className="bg-white rounded-xl border p-4">
                  <p className="text-xs text-gray-500 mb-1">Scenarios run</p>
                  <p className="text-xl font-bold text-cascade-charcoal">{stress.results.length}</p>
                  <p className="text-xs text-gray-400">{stress.results.filter(row => row.source === 'custom').length} user-defined</p>
                </div>
              </div>

              <div className="bg-white rounded-xl border p-5">
                <h3 className="font-semibold text-cascade-charcoal mb-1">Scenario P&amp;L</h3>
                <p className="text-xs text-gray-500 mb-4">Illustrative shock sizes applied to linear sensitivities, USD.</p>
                <PnlBars data={stress.results.map(row => ({ name: row.name, pnl: row.total_pnl }))} height={Math.max(240, stress.results.length * 36)} />
              </div>

              <div className="bg-white rounded-xl border p-5 space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="font-semibold text-cascade-charcoal">Breakdown</h3>
                  <select value={selectedId} onChange={event => setSelectedId(event.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                    {stress.results.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </div>
                {selected && (
                  <>
                    <p className="text-sm text-gray-600">{selected.description} Total P&amp;L <strong className={selected.total_pnl < 0 ? 'text-red-700' : 'text-green-700'}>{formatAmount(selected.total_pnl)}</strong>.</p>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs font-semibold text-gray-600 mb-2">By risk factor type</p>
                        <PnlBars data={RISK_TYPES.map(riskType => ({ name: RISK_TYPE_LABEL[riskType], pnl: selected.by_risk_type[riskType] }))} height={200} />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-gray-600 mb-2">By market</p>
                        <PnlBars data={Object.entries(selected.by_market).map(([name, pnl]) => ({ name, pnl }))} height={200} />
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead className="bg-gray-50 text-gray-600"><tr>{['Risk factor', 'Market', 'Shock', 'Sensitivity', 'P&L'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                        <tbody>{selected.by_factor.map(row => (
                          <tr key={row.factor_id} className="border-t">
                            <td className="p-3 font-medium">{row.label}</td>
                            <td className="p-3">{row.market}</td>
                            <td className="p-3 whitespace-nowrap">{row.shock > 0 ? '+' : ''}{row.shock}{row.unit === '%' ? '%' : ' bp'}</td>
                            <td className="p-3">{row.sensitivity.toLocaleString('en-US')}</td>
                            <td className={`p-3 ${row.pnl < 0 ? 'text-red-700' : row.pnl > 0 ? 'text-green-700' : ''}`}>{formatAmount(row.pnl)}</td>
                          </tr>
                        ))}</tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </>
          )}

          <div className="bg-white rounded-xl border p-5 space-y-3">
            <h3 className="font-semibold text-cascade-charcoal">Define a scenario</h3>
            <p className="text-xs text-gray-500">Equity and FX shocks in percent, rates and credit spread shocks in basis points. Leave a field empty for no shock.</p>
            <input value={draftName} onChange={event => setDraftName(event.target.value)} placeholder="Scenario name" maxLength={80}
              className="border rounded-lg px-3 py-2 text-sm w-full max-w-md" />
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {RISK_TYPES.map(riskType => (
                <div key={riskType} className="space-y-2">
                  <p className="text-xs font-semibold text-gray-600">{RISK_TYPE_LABEL[riskType]}</p>
                  {factors.filter(factor => factor.risk_type === riskType).map(factor => (
                    <label key={factor.id} className="block text-xs text-gray-500">
                      {factor.label} ({factor.unit})
                      <input type="number" value={draftShocks[factor.id] ?? ''}
                        onChange={event => setDraftShocks({ ...draftShocks, [factor.id]: event.target.value })}
                        className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm text-cascade-charcoal" />
                    </label>
                  ))}
                </div>
              ))}
            </div>
            <button onClick={addCustomScenario} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
              <Plus size={16} /> Add and run
            </button>
            {customScenarios.length > 0 && (
              <ul className="text-sm divide-y border rounded-lg">
                {customScenarios.map((scenario, index) => (
                  <li key={`${scenario.name}-${index}`} className="flex items-center justify-between px-3 py-2">
                    <span>{scenario.name} <span className="text-xs text-gray-400">({Object.keys(scenario.shocks).length} shocks)</span></span>
                    <button onClick={() => removeCustomScenario(index)} aria-label={`Remove ${scenario.name}`} className="text-gray-400 hover:text-red-600"><Trash2 size={15} /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {stress && <p className="text-xs text-gray-500">{stress.disclaimer}</p>}
        </div>
      )}

      {tab === 'reverse' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border p-5 space-y-3">
            <h3 className="font-semibold text-cascade-charcoal">Reverse stress test</h3>
            <p className="text-xs text-gray-500">Scales every shock in the chosen scenario by the same multiplier until the portfolio loss reaches the threshold.</p>
            <div className="flex flex-wrap items-end gap-4">
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Scenario to scale</span>
                <select value={reverseScenario} onChange={event => setReverseScenario(event.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                  {allScenarios.map(scenario => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
                </select>
              </label>
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Loss threshold (USD)</span>
                <input type="number" min={1} step={1_000_000} value={threshold} onChange={event => setThreshold(Number(event.target.value))}
                  className="border rounded-lg px-3 py-2 text-sm w-44" />
              </label>
              <button onClick={runReverse} disabled={loading || !library} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <Undo2 size={16} />} Find breaking point
              </button>
            </div>
          </div>
          {reverse && (
            <div className="bg-white rounded-xl border p-5 space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div><p className="text-xs text-gray-500">Multiplier</p><p className="text-xl font-bold text-cascade-charcoal">{reverse.multiplier === null ? 'Not reachable' : `${reverse.multiplier.toFixed(2)}x`}</p></div>
                <div><p className="text-xs text-gray-500">P&amp;L at 1x</p><p className={`text-xl font-bold ${reverse.base_pnl < 0 ? 'text-red-600' : 'text-green-600'}`}>{formatAmount(reverse.base_pnl)}</p></div>
                <div><p className="text-xs text-gray-500">Loss threshold</p><p className="text-xl font-bold text-cascade-charcoal">{formatAmount(reverse.loss_threshold)}</p></div>
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4"><p className="text-sm text-blue-800">{reverse.finding}</p></div>
              {reverse.scaled && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 text-gray-600"><tr>{['Risk factor', 'Market', 'Scaled shock', 'P&L'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                    <tbody>{reverse.scaled.by_factor.filter(row => row.shock !== 0).map(row => (
                      <tr key={row.factor_id} className="border-t">
                        <td className="p-3 font-medium">{row.label}</td>
                        <td className="p-3">{row.market}</td>
                        <td className="p-3 whitespace-nowrap">{row.shock > 0 ? '+' : ''}{row.shock.toFixed(1)}{row.unit === '%' ? '%' : ' bp'}</td>
                        <td className={`p-3 ${row.pnl < 0 ? 'text-red-700' : row.pnl > 0 ? 'text-green-700' : ''}`}>{formatAmount(row.pnl)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              <p className="text-xs text-gray-500">Linear sensitivities only: large multipliers overstate what a linear approximation can describe. Simplified, for analysis and learning; not a regulatory calculation.</p>
            </div>
          )}
        </div>
      )}

      {tab === 'capital' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border p-5 space-y-3">
            <h3 className="font-semibold text-cascade-charcoal">Economic capital (simplified)</h3>
            <p className="text-xs text-gray-500">
              One-year unexpected loss from a simulated loss distribution: market risk from the sample book&apos;s volatility,
              credit risk from a one-factor default model on a sample set of fictional counterparties, and a lognormal operational loss.
            </p>
            <div className="flex flex-wrap items-end gap-4">
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Confidence</span>
                <select value={capitalInputs.confidence} onChange={event => setCapitalInputs({ ...capitalInputs, confidence: Number(event.target.value) })} className="border rounded-lg px-3 py-2 text-sm">
                  <option value={0.99}>99%</option>
                  <option value={0.995}>99.5%</option>
                  <option value={0.999}>99.9%</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Credit asset correlation</span>
                <input type="number" min={0} max={0.95} step={0.05} value={capitalInputs.asset_correlation}
                  onChange={event => setCapitalInputs({ ...capitalInputs, asset_correlation: Number(event.target.value) })} className="border rounded-lg px-3 py-2 text-sm w-28" />
              </label>
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Market / credit correlation</span>
                <input type="number" min={-0.9} max={0.9} step={0.1} value={capitalInputs.market_credit}
                  onChange={event => setCapitalInputs({ ...capitalInputs, market_credit: Number(event.target.value) })} className="border rounded-lg px-3 py-2 text-sm w-28" />
              </label>
              <label className="text-sm">
                <span className="block text-xs text-gray-500 mb-1">Operational expected loss (USD)</span>
                <input type="number" min={0} step={500_000} value={capitalInputs.operational_expected_loss}
                  onChange={event => setCapitalInputs({ ...capitalInputs, operational_expected_loss: Number(event.target.value) })} className="border rounded-lg px-3 py-2 text-sm w-40" />
              </label>
              <button onClick={runCapital} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
                {loading ? <Loader2 className="animate-spin" size={16} /> : <Landmark size={16} />} Simulate
              </button>
            </div>
          </div>
          {capital && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Economic capital ({(capital.confidence * 100).toFixed(1)}%)</p><p className="text-xl font-bold text-cascade-charcoal">{formatAmount(capital.economic_capital)}</p><p className="text-xs text-gray-400">{capital.horizon}, {capital.simulations.toLocaleString('en-US')} simulations</p></div>
                <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Sum of standalone capital</p><p className="text-xl font-bold text-cascade-charcoal">{formatAmount(capital.diversification.undiversified)}</p></div>
                <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Diversification benefit</p><p className="text-xl font-bold text-green-600">{formatAmount(capital.diversification.benefit)}</p><p className="text-xs text-gray-400">{capital.diversification.benefit_pct.toFixed(1)}% of standalone</p></div>
                <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Expected loss</p><p className="text-xl font-bold text-cascade-charcoal">{formatAmount(capital.total.expected_loss)}</p></div>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-white rounded-xl border p-5">
                  <h3 className="font-semibold text-cascade-charcoal mb-4">Capital by risk type</h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={capital.breakdown.map(row => ({ name: row.risk_type, standalone: row.unexpected_loss, allocated: row.allocated_capital }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value, 0)} width={70} />
                      <Tooltip formatter={(value: any, name: any) => [formatAmount(Number(value)), name]} />
                      <Bar name="Standalone" dataKey="standalone" fill="#78716c" isAnimationActive={false} />
                      <Bar name="After diversification" dataKey="allocated" fill="#92761f" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="bg-white rounded-xl border p-5">
                  <h3 className="font-semibold text-cascade-charcoal mb-4">Simulated one-year loss distribution</h3>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={capital.histogram}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                      <XAxis dataKey="loss" tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value, 0)} minTickGap={40} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value: any) => [Number(value).toLocaleString('en-US'), 'Simulations']} labelFormatter={(value: any) => `Loss near ${formatAmount(Number(value))}`} />
                      <Bar dataKey="count" fill="#1a1a19" isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="bg-white rounded-xl border overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-gray-600"><tr>{['Risk type', 'Expected loss', `Loss at ${(capital.confidence * 100).toFixed(1)}%`, 'Unexpected loss', 'Share', 'Allocated capital'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                  <tbody>
                    {capital.breakdown.map(row => (
                      <tr key={row.risk_type} className="border-t">
                        <td className="p-3 font-medium capitalize">{row.risk_type}</td>
                        <td className="p-3">{formatAmount(row.expected_loss)}</td>
                        <td className="p-3">{formatAmount(row.loss_quantile)}</td>
                        <td className="p-3">{formatAmount(row.unexpected_loss)}</td>
                        <td className="p-3">{row.share_of_undiversified_pct.toFixed(1)}%</td>
                        <td className="p-3">{formatAmount(row.allocated_capital)}</td>
                      </tr>
                    ))}
                    <tr className="border-t font-semibold">
                      <td className="p-3">Total (diversified)</td>
                      <td className="p-3">{formatAmount(capital.total.expected_loss)}</td>
                      <td className="p-3">{formatAmount(capital.total.loss_quantile)}</td>
                      <td className="p-3">{formatAmount(capital.total.unexpected_loss)}</td>
                      <td className="p-3" />
                      <td className="p-3">{formatAmount(capital.economic_capital)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <details className="bg-white rounded-xl border p-5">
                <summary className="cursor-pointer text-sm font-semibold text-cascade-charcoal">Sample credit exposures (fictional counterparties, illustrative figures)</summary>
                <table className="w-full text-sm text-left mt-3">
                  <thead className="text-gray-600"><tr>{['Counterparty', 'Market', 'Exposure at default', 'PD', 'LGD'].map(label => <th key={label} className="py-2 pr-3">{label}</th>)}</tr></thead>
                  <tbody>{capital.inputs.credit_exposures.map(exposure => (
                    <tr key={exposure.name} className="border-t">
                      <td className="py-2 pr-3">{exposure.name}</td>
                      <td className="py-2 pr-3">{exposure.market ?? 'n/a'}</td>
                      <td className="py-2 pr-3">{formatAmount(exposure.ead)}</td>
                      <td className="py-2 pr-3">{(exposure.pd * 100).toFixed(1)}%</td>
                      <td className="py-2 pr-3">{(exposure.lgd * 100).toFixed(0)}%</td>
                    </tr>
                  ))}</tbody>
                </table>
              </details>
              <p className="text-xs text-gray-500">{capital.disclaimer}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
