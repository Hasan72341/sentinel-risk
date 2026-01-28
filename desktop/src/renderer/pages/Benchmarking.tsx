import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { BarChart3, Loader2, AlertTriangle, Info } from 'lucide-react';
import { getSectorCatalogue, compareSectorBenchmark, apiErrorMessage } from '../lib/asiaMarketsApi';
import type {
  SectorOption, BenchmarkRegion, SectorBenchmarkResult, SectorComparison, BenchmarkRank, SectorRatioInput,
} from '../lib/asiaMarketsApi';
import { countryOptions, getCountry, loadSelectedCountry, saveSelectedCountry, formatNumber, formatPercent } from '../lib/region';
import type { CountryCode } from '../lib/region';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import { useToast } from '../components/Toast';

const ILLUSTRATIVE_NOTE =
  'Benchmark ranges are illustrative. They are hand-set for analysis and learning, not computed from a market data set, and must not be quoted as observed peer statistics.';

// Ratios the sector profiles cover. Percent ratios are entered in percent.
const RATIO_FIELDS: { key: string; label: string; unit: '%' | 'x' }[] = [
  { key: 'gross_profit_margin', label: 'Gross profit margin', unit: '%' },
  { key: 'operating_margin', label: 'Operating margin', unit: '%' },
  { key: 'net_profit_margin', label: 'Net profit margin', unit: '%' },
  { key: 'return_on_assets', label: 'Return on assets', unit: '%' },
  { key: 'return_on_equity', label: 'Return on equity', unit: '%' },
  { key: 'debt_to_assets', label: 'Debt to assets', unit: '%' },
  { key: 'current_ratio', label: 'Current ratio', unit: 'x' },
  { key: 'quick_ratio', label: 'Quick ratio', unit: 'x' },
  { key: 'debt_to_equity', label: 'Debt to equity', unit: 'x' },
  { key: 'interest_coverage', label: 'Interest coverage', unit: 'x' },
  { key: 'asset_turnover', label: 'Asset turnover', unit: 'x' },
  { key: 'inventory_turnover', label: 'Inventory turnover', unit: 'x' },
  { key: 'receivables_turnover', label: 'Receivables turnover', unit: 'x' },
];

// Illustrative ratios for a fictional company. Not real data.
const SAMPLE_COMPANY = 'Lotus Peak Components (fictional)';
const SAMPLE_SECTOR = 'automobiles';
const SAMPLE_RATIOS: Record<string, string> = {
  gross_profit_margin: '19.5', operating_margin: '6.8', net_profit_margin: '4.4', return_on_assets: '4.6',
  return_on_equity: '12', debt_to_assets: '31', current_ratio: '1.8', quick_ratio: '0.85', debt_to_equity: '1.5',
  interest_coverage: '6.2', asset_turnover: '1.05', inventory_turnover: '7.4', receivables_turnover: '8.1',
};

const RANK_STYLE: Record<BenchmarkRank | 'not_scored', { label: string; className: string; color: string }> = {
  excellent: { label: 'Top quartile', className: 'bg-green-50 text-green-700', color: '#16a34a' },
  above_average: { label: 'Above median', className: 'bg-emerald-50 text-emerald-700', color: '#65a30d' },
  below_average: { label: 'Below median', className: 'bg-amber-50 text-amber-700', color: '#d97706' },
  poor: { label: 'Bottom quartile', className: 'bg-red-50 text-red-700', color: '#dc2626' },
  not_scored: { label: 'Not scored', className: 'bg-gray-100 text-gray-600', color: '#9ca3af' },
};

function showValue(value: number, unit: SectorComparison['unit'], country: CountryCode): string {
  return unit === 'fraction' ? formatPercent(value * 100, 1) : `${formatNumber(value, country, 2)}x`;
}

export default function Benchmarking() {
  const { currentAnalysis } = useAnalysisStore();
  const { toast } = useToast();

  const [region, setRegion] = useState<CountryCode>(() => loadSelectedCountry());
  const [sectors, setSectors] = useState<SectorOption[]>([]);
  const [regions, setRegions] = useState<BenchmarkRegion[]>([]);
  const [sectorId, setSectorId] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [dataSource, setDataSource] = useState<'manual' | 'sample' | 'analysis'>('manual');
  const [result, setResult] = useState<SectorBenchmarkResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [catalogueError, setCatalogueError] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    getSectorCatalogue()
      .then((catalogue) => {
        if (cancelled) return;
        setSectors(catalogue.industries);
        setRegions(catalogue.regions);
      })
      .catch((cause) => { if (!cancelled) setCatalogueError(apiErrorMessage(cause, 'Could not load sector profiles')); });
    return () => { cancelled = true; };
  }, []);

  function chooseRegion(code: CountryCode) {
    setRegion(code);
    saveSelectedCountry(code);
    setResult(null);
  }

  function loadSample() {
    setCompanyName(SAMPLE_COMPANY);
    setValues(SAMPLE_RATIOS);
    setSectorId(SAMPLE_SECTOR);
    setDataSource('sample');
    setResult(null);
  }

  function loadFromAnalysis() {
    if (!currentAnalysis) return;
    const next: Record<string, string> = {};
    currentAnalysis.ratios.forEach((ratio) => {
      const field = RATIO_FIELDS.find((item) => item.key === ratio.ratioName);
      if (!field || !Number.isFinite(ratio.value)) return;
      // The statement analysis stores percent ratios as fractions (0.12 for 12%).
      const value = field.unit === '%' ? ratio.value * 100 : ratio.value;
      next[field.key] = String(Math.round(value * 10000) / 10000);
    });
    setValues(next);
    setCompanyName(currentAnalysis.companyName);
    setDataSource('analysis');
    setResult(null);
    toast('info', `Loaded ${Object.keys(next).length} ratios from ${currentAnalysis.companyName}.`);
  }

  async function compare() {
    setError('');
    if (!sectorId) { setError('Select a sector.'); return; }
    const ratios: SectorRatioInput[] = [];
    const invalid: string[] = [];
    RATIO_FIELDS.forEach((field) => {
      const text = (values[field.key] ?? '').replace(/,/g, '').trim();
      if (!text) return;
      const value = Number(text);
      if (Number.isFinite(value)) ratios.push({ ratio_name: field.key, value, unit: field.unit === '%' ? 'percent' : 'x' });
      else invalid.push(field.label);
    });
    if (invalid.length) { setError(`These ratios are not numbers: ${invalid.join(', ')}`); return; }
    if (!ratios.length) { setError('Enter at least one ratio, or load the sample.'); return; }

    setLoading(true); setResult(null);
    try {
      setResult(await compareSectorBenchmark(companyName.trim(), ratios, sectorId, region));
    } catch (cause) {
      const message = apiErrorMessage(cause, 'Benchmark comparison failed');
      setError(message);
      toast('error', message);
    } finally { setLoading(false); }
  }

  const tilt = regions.find((item) => item.id === region)?.tilt_rationale;
  const chartData = (result?.comparisons ?? []).map((row) => ({ name: row.label, score: row.percentile, rank: row.rank }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <BarChart3 className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Sector benchmarking</h1>
          <p className="text-sm text-gray-500">Compare a company's ratios with a sector profile for India, China, Japan or South Korea</p>
        </div>
      </div>

      <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
        <Info className="text-amber-600 shrink-0 mt-0.5" size={18} />
        <p className="text-sm text-amber-800">{ILLUSTRATIVE_NOTE}</p>
      </div>

      {catalogueError && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{catalogueError}</p>
        </div>
      )}

      {/* Selection */}
      <div className="bg-white rounded-xl border p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label htmlFor="bench-region" className="block text-sm font-semibold mb-1">Region</label>
          <select id="bench-region" value={region} onChange={(event) => chooseRegion(event.target.value as CountryCode)}
            className="w-full border rounded-lg px-3 py-2 text-sm bg-white">
            {countryOptions().map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          {tilt && <p className="text-xs text-gray-500 mt-1">Regional assumption: {tilt}</p>}
        </div>
        <div>
          <label htmlFor="bench-sector" className="block text-sm font-semibold mb-1">Sector</label>
          <select id="bench-sector" value={sectorId} onChange={(event) => { setSectorId(event.target.value); setResult(null); }}
            className="w-full border rounded-lg px-3 py-2 text-sm bg-white">
            <option value="">Select a sector</option>
            {sectors.map((sector) => <option key={sector.id} value={sector.id}>{sector.name}</option>)}
          </select>
          <p className="text-xs text-gray-500 mt-1">Profiles cover non-financial sectors. Banks, insurers and funds need different ratios.</p>
        </div>
        <div>
          <label htmlFor="bench-company" className="block text-sm font-semibold mb-1">Company name</label>
          <input id="bench-company" value={companyName} onChange={(event) => setCompanyName(event.target.value)}
            className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Optional" />
        </div>
      </div>

      {/* Ratios */}
      <div className="bg-white rounded-xl border p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-cascade-charcoal">Company ratios</h2>
            <p className="text-xs text-gray-500">Enter margins and returns in percent (12 for 12%). Blank ratios are left out.</p>
          </div>
          <div className="flex gap-2">
            {currentAnalysis && (
              <button onClick={loadFromAnalysis} className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Use current analysis</button>
            )}
            <button onClick={loadSample} className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Load sample</button>
            <button onClick={() => { setValues({}); setDataSource('manual'); setResult(null); }} className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Clear</button>
          </div>
        </div>
        {dataSource === 'sample' && (
          <p className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
            Illustrative sample data for {SAMPLE_COMPANY}. The ratios are invented for demonstration.
          </p>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {RATIO_FIELDS.map((field) => (
            <div key={field.key}>
              <label htmlFor={`ratio-${field.key}`} className="block text-xs text-gray-600 mb-1">{field.label} ({field.unit})</label>
              <input id={`ratio-${field.key}`} inputMode="decimal" value={values[field.key] ?? ''}
                onChange={(event) => { setDataSource('manual'); setValues({ ...values, [field.key]: event.target.value }); }}
                className="w-full border rounded-lg px-3 py-1.5 text-sm text-right font-mono" />
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={compare} disabled={loading}
            className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <BarChart3 size={16} />} Compare
          </button>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Overall score</p>
              <p className="text-xl font-bold text-cascade-charcoal">{result.ratios_compared ? result.overall_score : '-'}<span className="text-sm text-gray-400"> / 100</span></p>
              <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-medium ${RANK_STYLE[result.overall_rank].className}`}>{RANK_STYLE[result.overall_rank].label}</span>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Profile</p>
              <p className="text-sm font-semibold text-cascade-charcoal">{result.industry_name}</p>
              <p className="text-xs text-gray-400">{result.region_name} ({getCountry(result.region).currency}), illustrative</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Top quartile</p>
              <p className="text-sm text-green-700">{result.strengths.length ? result.strengths.join(', ') : 'None'}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Bottom quartile</p>
              <p className="text-sm text-red-700">{result.weaknesses.length ? result.weaknesses.join(', ') : 'None'}</p>
            </div>
          </div>

          {result.ratios_compared === 0 ? (
            <p className="text-sm text-gray-500">None of the ratios entered are covered by this sector profile.</p>
          ) : (
            <>
              <div className="bg-white rounded-xl border overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>{['Ratio', 'Company', 'Lower quartile', 'Median', 'Upper quartile', 'vs median', 'Band'].map((label) => <th key={label} className="p-3 whitespace-nowrap font-medium">{label}</th>)}</tr>
                  </thead>
                  <tbody>
                    {result.comparisons.map((row) => (
                      <tr key={row.ratio_name} className="border-t">
                        <td className="p-3 font-medium">{row.label}{row.lower_is_better && <span className="text-xs text-gray-400"> (lower is better)</span>}</td>
                        <td className="p-3 font-semibold">{showValue(row.company_value, row.unit, result.region)}</td>
                        <td className="p-3 text-gray-600">{showValue(row.industry_p25, row.unit, result.region)}</td>
                        <td className="p-3 text-gray-600">{showValue(row.industry_median, row.unit, result.region)}</td>
                        <td className="p-3 text-gray-600">{showValue(row.industry_p75, row.unit, result.region)}</td>
                        <td className="p-3 text-gray-600">{formatPercent(row.deviation_pct, 1, true)}</td>
                        <td className="p-3"><span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${RANK_STYLE[row.rank].className}`}>{RANK_STYLE[row.rank].label}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="bg-white rounded-xl border p-5">
                <h2 className="text-sm font-semibold text-cascade-charcoal mb-1">Band score by ratio</h2>
                <p className="text-xs text-gray-500 mb-3">Each ratio scores 90, 65, 35 or 10 by quartile band; leverage ratios score higher when lower. The overall score is the average.</p>
                <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 30)}>
                  <BarChart data={chartData} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={140} />
                    <Tooltip formatter={(value: number) => [value, 'Band score']} />
                    <Bar dataKey="score" isAnimationActive={false}>
                      {chartData.map((entry) => <Cell key={entry.name} fill={RANK_STYLE[entry.rank].color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}

          {result.unmatched_ratios.length > 0 && (
            <p className="text-xs text-gray-500">Not in this profile, so not compared: {result.unmatched_ratios.join(', ')}.</p>
          )}
          <p className="text-xs text-gray-400">{result.disclaimer} Regional assumption: {result.tilt_rationale}</p>
        </div>
      )}
    </div>
  );
}
