import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Activity, AlertTriangle, ClipboardCopy, Database, Loader2 } from 'lucide-react';
import { useToast } from '../components/Toast';
import { apiErrorMessage, formatAmount, getSampleExposureBook, reviewExposureBook } from '../lib/exposureApi';
import type { BreachItem, BreachSeverity, ExposureBookReview, ExposurePosition, ExposureRow, SampleExposureBook } from '../lib/exposureApi';

const requiredColumns = ['counterparty', 'current_mtm', 'previous_mtm', 'collateral', 'previous_collateral', 'credit_limit', 'required_margin'] as const;
const textColumns = ['country', 'client_type', 'currency'] as const;
const optionalNumberColumns = ['previous_required_margin'] as const;
const allColumns = ['counterparty', ...textColumns, ...requiredColumns.slice(1), ...optionalNumberColumns];
const reportingCurrencies = ['USD', 'INR', 'CNY', 'JPY', 'KRW'];

const severityStyle: Record<BreachSeverity, string> = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  high: 'bg-orange-100 text-orange-800 border-orange-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  watch: 'bg-gray-100 text-gray-700 border-gray-200',
};
const breachTypeLabel: Record<BreachItem['type'], string> = {
  limit_breach: 'Credit limit breach',
  margin_deficit: 'Margin deficit',
  limit_watch: 'Limit watch',
};

function toCsv(positions: ExposurePosition[]): string {
  const lines = positions.map(position => allColumns.map(column => (position as any)[column] ?? '').join(','));
  return [allColumns.join(','), ...lines].join('\n');
}

function parseRows(raw: string): ExposurePosition[] {
  const lines = raw.trim().split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) throw new Error('Paste a header row followed by at least one position');
  const header = lines[0].split(',').map(cell => cell.trim().toLowerCase());
  const missing = requiredColumns.filter(column => !header.includes(column));
  if (missing.length) throw new Error(`Header is missing: ${missing.join(', ')}`);
  const unknown = header.filter(column => !allColumns.includes(column));
  if (unknown.length) throw new Error(`Unknown column: ${unknown.join(', ')}`);

  return lines.slice(1).map((line, index) => {
    const cells = line.split(',').map(cell => cell.trim());
    if (cells.length !== header.length) throw new Error(`Row ${index + 2}: expected ${header.length} columns, found ${cells.length}`);
    const cell = (column: string) => cells[header.indexOf(column)] ?? '';
    const amount = (column: string) => {
      const value = Number(cell(column));
      if (cell(column) === '' || !Number.isFinite(value)) throw new Error(`Row ${index + 2}: ${column} must be a number`);
      return value;
    };
    if (!cell('counterparty')) throw new Error(`Row ${index + 2}: counterparty is required`);
    return {
      counterparty: cell('counterparty'),
      current_mtm: amount('current_mtm'), previous_mtm: amount('previous_mtm'),
      collateral: amount('collateral'), previous_collateral: amount('previous_collateral'),
      credit_limit: amount('credit_limit'), required_margin: amount('required_margin'),
      previous_required_margin: header.includes('previous_required_margin') && cell('previous_required_margin') !== '' ? amount('previous_required_margin') : null,
      country: header.includes('country') ? cell('country') || null : null,
      client_type: header.includes('client_type') ? cell('client_type') || null : null,
      currency: header.includes('currency') ? cell('currency').toUpperCase() || null : null,
    };
  });
}

function parseFxRates(raw: string): Record<string, number> {
  const rates: Record<string, number> = {};
  raw.split(/[,\n]+/).map(part => part.trim()).filter(Boolean).forEach(part => {
    const [code, value] = part.split('=').map(piece => piece.trim());
    const rate = Number(value);
    if (!code || !value || !Number.isFinite(rate) || rate <= 0) throw new Error(`Conversion rate "${part}" must use CURRENCY=rate, with a positive numeric rate`);
    rates[code.toUpperCase()] = rate;
  });
  return rates;
}

function statusBadge(row: ExposureRow) {
  const badges: { label: string; style: string }[] = [];
  if (row.limit_breach_status === 'opened') badges.push({ label: 'Breach opened', style: 'bg-red-100 text-red-800' });
  if (row.limit_breach_status === 'ongoing') badges.push({ label: 'Breach ongoing', style: 'bg-red-100 text-red-800' });
  if (row.limit_breach_status === 'closed') badges.push({ label: 'Breach closed', style: 'bg-green-100 text-green-800' });
  if (row.margin_status === 'call_triggered') badges.push({ label: 'Margin call', style: 'bg-amber-100 text-amber-800' });
  if (row.margin_status === 'deficit_outstanding') badges.push({ label: 'Deficit outstanding', style: 'bg-amber-100 text-amber-800' });
  if (row.margin_status === 'cured') badges.push({ label: 'Deficit cured', style: 'bg-green-100 text-green-800' });
  if (!badges.length) return <span className="text-xs text-gray-400">Within limits</span>;
  return <div className="flex flex-wrap gap-1">{badges.map(badge => (
    <span key={badge.label} className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${badge.style}`}>{badge.label}</span>
  ))}</div>;
}

export default function CreditExposure() {
  const { toast } = useToast();
  const [input, setInput] = useState(allColumns.join(','));
  const [fxInput, setFxInput] = useState('');
  const [reportingCurrency, setReportingCurrency] = useState('USD');
  const [sample, setSample] = useState<SampleExposureBook | null>(null);
  const [usingSample, setUsingSample] = useState(false);
  const [review, setReview] = useState<ExposureBookReview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function loadSample() {
    try {
      const book = sample ?? await getSampleExposureBook();
      setSample(book);
      setInput(toCsv(book.positions));
      setFxInput(Object.entries(book.fx_rates).map(([code, rate]) => `${code}=${rate}`).join(', '));
      setReportingCurrency(book.reporting_currency);
      setUsingSample(true);
      setReview(null);
    } catch (cause: any) {
      toast('error', apiErrorMessage(cause, 'Could not load the sample book'));
    }
  }

  useEffect(() => { loadSample(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function runReview() {
    setError(''); setLoading(true);
    try {
      const result = await reviewExposureBook(parseRows(input), reportingCurrency, parseFxRates(fxInput));
      setReview(result);
      const { limit_breach_count: breaches, margin_call_count: calls } = result.summary;
      toast(breaches || calls ? 'info' : 'success', `Reviewed ${result.summary.clients} clients: ${breaches} limit breach(es), ${calls} margin deficit(s)`);
    } catch (cause: any) {
      setReview(null);
      setError(apiErrorMessage(cause, 'Exposure review failed'));
    } finally { setLoading(false); }
  }

  async function copyCommentary() {
    if (!review) return;
    const text = [review.summary.commentary, '', ...review.results.map(row => `${row.counterparty}: ${row.commentary}`)].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast('success', 'Commentary copied');
    } catch {
      toast('error', 'Could not copy to the clipboard');
    }
  }

  const summary = review?.summary;
  const ccy = summary?.reporting_currency ?? '';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Activity className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Daily Exposure Monitoring</h1>
          <p className="text-sm text-gray-500">Credit exposure, collateral, margin and limits per client, with day-on-day commentary</p>
        </div>
      </div>

      {usingSample && sample && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
          <Database className="text-amber-600 shrink-0 mt-0.5" size={16} />
          <p className="text-xs text-amber-800"><strong>Sample data.</strong> {sample.disclaimer} Amounts are in {sample.unit}.</p>
        </div>
      )}

      <div className="bg-white border rounded-xl p-5 space-y-3">
        <label htmlFor="exposure-input" className="block text-sm font-semibold text-cascade-charcoal">Daily positions (CSV)</label>
        <textarea id="exposure-input" value={input} onChange={event => { setInput(event.target.value); setUsingSample(false); }} rows={9}
          placeholder={allColumns.join(',')} className="w-full font-mono text-xs border rounded-lg p-3" spellCheck={false} />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label htmlFor="reporting-currency" className="text-xs text-gray-500">Reporting currency</label>
            <select id="reporting-currency" value={reportingCurrency} onChange={event => setReportingCurrency(event.target.value)} className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
              {reportingCurrencies.map(code => <option key={code} value={code}>{code}</option>)}
            </select>
          </div>
          <div className="md:col-span-3">
            <label htmlFor="fx-rates" className="text-xs text-gray-500">Conversion rates (value of one unit of each currency, all quoted in the same currency)</label>
            <input id="fx-rates" value={fxInput} onChange={event => { setFxInput(event.target.value); setUsingSample(false); }}
              placeholder="CURRENCY=rate, CURRENCY=rate" aria-describedby="fx-rates-hint" className="w-full mt-1 px-3 py-2 border rounded-lg text-sm font-mono" />
            <p id="fx-rates-hint" className="text-xs text-gray-500 mt-1">Enter positive rates from the same valuation date and quote currency, including {reportingCurrency}. Rates are supplied manually.</p>
          </div>
        </div>
        <p className="text-xs text-gray-500">
          Required columns: {requiredColumns.join(', ')}. Optional: {[...textColumns, ...optionalNumberColumns].join(', ')}. Each row is reviewed in its own currency;
          totals are converted with the rates you enter. Commas inside names are unsupported. Results use a simplified exposure model.
        </p>
        <div className="flex flex-wrap gap-2">
          <button onClick={runReview} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Activity size={16} />} Review exposures
          </button>
          <button onClick={loadSample} disabled={loading} className="px-4 py-2 border rounded-lg text-sm font-medium text-cascade-charcoal hover:bg-gray-50 flex items-center gap-2">
            <Database size={16} /> Load sample book
          </button>
        </div>
        {error && (
          <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
            <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={16} />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
      </div>

      {review && summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Net exposure ({ccy})</p>
              <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(summary.net_exposure, 2)}</p>
              <p className={`text-xs ${summary.day_change > 0 ? 'text-red-600' : summary.day_change < 0 ? 'text-green-600' : 'text-gray-400'}`}>
                {summary.day_change > 0 ? '+' : ''}{formatAmount(summary.day_change, 2)} day on day
              </p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Collateral held ({ccy})</p>
              <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(summary.collateral, 2)}</p>
              <p className="text-xs text-gray-400">against gross exposure {formatAmount(summary.gross_exposure, 2)}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Limit breaches</p>
              <p className={`text-xl font-bold ${summary.limit_breach_count ? 'text-red-600' : 'text-green-600'}`}>{summary.limit_breach_count}</p>
              <p className="text-xs text-gray-400">{summary.limit_breaches_opened} opened, {summary.limit_breaches_closed} closed today</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Margin deficit ({ccy})</p>
              <p className={`text-xl font-bold ${summary.margin_call_count ? 'text-amber-600' : 'text-green-600'}`}>{formatAmount(summary.margin_deficit, 2)}</p>
              <p className="text-xs text-gray-400">{summary.margin_call_count} client(s), {summary.margin_calls_triggered} new call(s)</p>
            </div>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
            <p className="text-sm text-blue-800">{summary.commentary}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border p-5">
              <h3 className="font-semibold text-cascade-charcoal mb-1">Breach investigation list</h3>
              <p className="text-xs text-gray-500 mb-3">Ordered by severity, then by amount in {ccy || 'the book currency'}.</p>
              {review.breaches.length === 0 && <p className="text-sm text-gray-500">No breaches or watch items today.</p>}
              <ol className="space-y-3">
                {review.breaches.map((item, index) => (
                  <li key={`${item.counterparty}-${item.type}`} className="border rounded-lg p-3">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="text-xs text-gray-400">{index + 1}.</span>
                      <span className={`px-2 py-0.5 rounded-full border text-xs font-semibold uppercase ${severityStyle[item.severity]}`}>{item.severity}</span>
                      <span className="text-sm font-medium text-cascade-charcoal">{item.counterparty}</span>
                      <span className="text-xs text-gray-500">{breachTypeLabel[item.type]}{item.status !== 'watch' ? ` (${item.status})` : ''}</span>
                      {item.type !== 'limit_watch' && (
                        <span className="ml-auto text-sm font-semibold text-cascade-charcoal">{formatAmount(item.amount_reporting, 2)} {ccy}</span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700">{item.detail}</p>
                    <p className="text-xs text-gray-500 mt-1">Next step: {item.action}</p>
                  </li>
                ))}
              </ol>
            </div>

            <div className="bg-white rounded-xl border p-5">
              <h3 className="font-semibold text-cascade-charcoal mb-4">Net exposure by country ({ccy})</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={summary.by_country}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                  <XAxis dataKey="country" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value: number) => formatAmount(value, 2)} />
                  <Bar dataKey="net_exposure" name="Net exposure" fill="#92761f" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white border rounded-xl overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-600">
                <tr>{['Client', 'Ccy', 'Exposure', 'Collateral', 'Net exposure', 'Day change', 'Margin req.', 'Margin excess / (deficit)', 'Limit used', 'Flags'].map(label => (
                  <th key={label} className="p-3 whitespace-nowrap font-medium">{label}</th>
                ))}</tr>
              </thead>
              <tbody>
                {review.results.map(row => (
                  <tr key={row.counterparty} className="border-t align-top">
                    <td className="p-3">
                      <p className="font-medium text-cascade-charcoal">{row.counterparty}</p>
                      <p className="text-xs text-gray-500">{[row.country, row.client_type].filter(Boolean).join(' / ')}</p>
                    </td>
                    <td className="p-3">{row.currency ?? '-'}</td>
                    <td className="p-3">{formatAmount(row.exposure, 2)}</td>
                    <td className="p-3">{formatAmount(row.collateral, 2)}</td>
                    <td className="p-3 font-medium">{formatAmount(row.net_exposure, 2)}</td>
                    <td className={`p-3 ${row.day_change > 0 ? 'text-red-700' : row.day_change < 0 ? 'text-green-700' : ''}`}>{row.day_change > 0 ? '+' : ''}{formatAmount(row.day_change, 2)}</td>
                    <td className="p-3">{formatAmount(row.margin_requirement, 2)}</td>
                    <td className={`p-3 ${row.margin_excess < 0 ? 'text-amber-700 font-semibold' : ''}`}>{row.margin_excess < 0 ? `(${formatAmount(-row.margin_excess, 2)})` : formatAmount(row.margin_excess, 2)}</td>
                    <td className={`p-3 ${row.limit_breach_flag ? 'text-red-700 font-semibold' : ''}`}>{row.limit_utilization_pct.toFixed(1)}%</td>
                    <td className="p-3">{statusBadge(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-white border rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-cascade-charcoal">Day-on-day commentary</h3>
              <button onClick={copyCommentary} className="px-3 py-1.5 border rounded-lg text-xs font-medium text-cascade-charcoal hover:bg-gray-50 flex items-center gap-2">
                <ClipboardCopy size={14} /> Copy
              </button>
            </div>
            <p className="text-xs text-gray-500">Written automatically from the figures above; review before sending.</p>
            {review.results.map(row => (
              <p key={row.counterparty} className="text-sm text-gray-700"><strong>{row.counterparty}:</strong> {row.commentary}</p>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
