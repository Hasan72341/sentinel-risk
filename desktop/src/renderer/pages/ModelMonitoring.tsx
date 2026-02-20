import { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Activity, AlertTriangle, CheckCircle2, ClipboardCopy, Loader2, XCircle } from 'lucide-react';
import { useToast } from '../components/Toast';
import { apiErrorMessage, formatAmount, runModelMonitoring } from '../lib/riskMethodologyApi';
import type { ModelMonitoringReport, MonitoringStatus, VarMethod } from '../lib/riskMethodologyApi';

const STATUS_STYLE: Record<MonitoringStatus, { box: string; text: string; label: string; color: string }> = {
  green: { box: 'bg-green-50 border-green-200', text: 'text-green-800', label: 'Green: performing as expected', color: '#16a34a' },
  amber: { box: 'bg-amber-50 border-amber-200', text: 'text-amber-800', label: 'Amber: review required', color: '#d97706' },
  red: { box: 'bg-red-50 border-red-200', text: 'text-red-800', label: 'Red: not performing adequately', color: '#dc2626' },
};

function pValue(value: number): string {
  return value < 0.001 ? '<0.001' : value.toFixed(3);
}

function StatusIcon({ status }: { status: MonitoringStatus }) {
  if (status === 'green') return <CheckCircle2 className="text-green-600 shrink-0" size={28} />;
  if (status === 'amber') return <AlertTriangle className="text-amber-600 shrink-0" size={28} />;
  return <XCircle className="text-red-600 shrink-0" size={28} />;
}

export default function ModelMonitoring() {
  const { toast } = useToast();
  const [method, setMethod] = useState<VarMethod>('historical');
  const [confidence, setConfidence] = useState(0.99);
  const [windowDays, setWindowDays] = useState(250);
  const [report, setReport] = useState<ModelMonitoringReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function run() {
    setLoading(true); setError('');
    try {
      const result = await runModelMonitoring({ method, confidence, window: windowDays });
      setReport(result);
      toast(result.status === 'green' ? 'success' : result.status === 'amber' ? 'warning' : 'error', `Model status: ${result.status}`);
    } catch (cause: any) {
      const message = apiErrorMessage(cause, 'Model monitoring failed');
      setError(message);
      toast('error', message);
    } finally { setLoading(false); }
  }

  useEffect(() => { void run(); }, []);

  const chartData = useMemo(() => (report?.series ?? []).map(point => ({
    date: point.date, pnl: point.pnl, varLine: -point.var, exception: point.exception ? point.pnl : null,
  })), [report]);

  async function copyFindings() {
    if (!report) return;
    const text = [`Model status: ${report.status}`, ...report.findings.map(finding => `- ${finding}`), '', report.disclaimer].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast('success', 'Findings copied to the clipboard');
    } catch {
      toast('error', 'Could not copy to the clipboard');
    }
  }

  const style = report ? STATUS_STYLE[report.status] : null;
  const summary = report?.summary;
  const expectedRate = summary ? (1 - summary.confidence) * 100 : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Activity className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Model performance monitoring</h1>
          <p className="text-sm text-gray-500">Exception analysis, stability metrics and written findings for a rolling VaR model.</p>
        </div>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-3">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">Model</span>
            <select value={method} onChange={event => setMethod(event.target.value as VarMethod)} className="border rounded-lg px-3 py-2 text-sm">
              <option value="historical">Historical simulation VaR</option>
              <option value="parametric">Parametric (normal) VaR</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">Confidence</span>
            <select value={confidence} onChange={event => setConfidence(Number(event.target.value))} className="border rounded-lg px-3 py-2 text-sm">
              <option value={0.95}>95%</option>
              <option value={0.975}>97.5%</option>
              <option value={0.99}>99%</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="block text-xs text-gray-500 mb-1">Rolling window (days)</span>
            <input type="number" min={20} max={600} value={windowDays} onChange={event => setWindowDays(Number(event.target.value))}
              className="border rounded-lg px-3 py-2 text-sm w-28" />
          </label>
          <button onClick={run} disabled={loading}
            className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Activity size={16} />} Build report
          </button>
        </div>
        <p className="text-xs text-gray-500">
          Runs on the illustrative Asia multi-asset sample book. Its history is synthetic, generated from a fixed random seed; it is sample data, not market data.
        </p>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {report && style && summary && (
        <>
          <div className={`border rounded-xl p-5 flex items-start gap-4 ${style.box}`}>
            <StatusIcon status={report.status} />
            <div>
              <p className={`text-lg font-bold ${style.text}`}>{style.label}</p>
              <ul className={`text-sm mt-1 list-disc list-inside ${style.text}`}>
                {report.status_reasons.map(reason => <li key={reason}>{reason}</li>)}
              </ul>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Exceptions</p>
              <p className="text-xl font-bold text-cascade-charcoal">{summary.n_exceptions} <span className="text-sm font-normal text-gray-500">vs {summary.expected_exceptions.toFixed(1)}</span></p>
              <p className="text-xs text-gray-400">{summary.n_obs} days, traffic light {summary.traffic_light.zone}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Coverage (Kupiec)</p>
              <p className={`text-xl font-bold ${summary.kupiec.p_value < 0.05 ? 'text-red-600' : 'text-cascade-charcoal'}`}>p = {pValue(summary.kupiec.p_value)}</p>
              <p className="text-xs text-gray-400">LR {summary.kupiec.statistic.toFixed(3)}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Independence (Christoffersen)</p>
              <p className={`text-xl font-bold ${summary.independence.p_value < 0.05 ? 'text-red-600' : 'text-cascade-charcoal'}`}>p = {pValue(summary.independence.p_value)}</p>
              <p className="text-xs text-gray-400">LR {summary.independence.statistic.toFixed(3)}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Conditional coverage</p>
              <p className={`text-xl font-bold ${summary.conditional_coverage.p_value < 0.05 ? 'text-red-600' : 'text-cascade-charcoal'}`}>p = {pValue(summary.conditional_coverage.p_value)}</p>
              <p className="text-xs text-gray-400">LR {summary.conditional_coverage.statistic.toFixed(3)}</p>
            </div>
          </div>

          <div className="bg-white rounded-xl border p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-cascade-charcoal">Findings</h3>
              <button onClick={copyFindings} className="px-3 py-1.5 border rounded-lg text-xs flex items-center gap-2 hover:bg-gray-50"><ClipboardCopy size={14} /> Copy for the model document</button>
            </div>
            <ol className="list-decimal list-inside space-y-2 text-sm text-gray-700">
              {report.findings.map(finding => <li key={finding}>{finding}</li>)}
            </ol>
          </div>

          <div className="bg-white rounded-xl border p-5">
            <h3 className="font-semibold text-cascade-charcoal mb-1">Daily P&amp;L against VaR</h3>
            <p className="text-xs text-gray-500 mb-4">Red dots mark exceptions. Synthetic sample data, USD.</p>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={60} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value, 1)} width={70} />
                <Tooltip formatter={(value: any, name: any) => [formatAmount(Number(value)), name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line name="Daily P&L" type="linear" dataKey="pnl" stroke="#78716c" strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line name={`VaR ${(summary.confidence * 100).toFixed(1)}%`} type="stepAfter" dataKey="varLine" stroke="#92761f" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Scatter name="Exception" dataKey="exception" fill="#dc2626" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border p-5">
              <h3 className="font-semibold text-cascade-charcoal mb-1">Exception rate by sub-period</h3>
              <p className="text-xs text-gray-500 mb-4">Dashed line is the target rate of {expectedRate.toFixed(1)}%.</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={report.stability.sub_periods.map(period => ({ name: `${period.start} to ${period.end}`, rate: period.exception_rate * 100, count: period.n_exceptions }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip formatter={(value: any, _name: any, item: any) => [`${Number(value).toFixed(2)}% (${item.payload.count} exceptions)`, 'Exception rate']} />
                  <ReferenceLine y={expectedRate} stroke="#1a1a19" strokeDasharray="4 3" />
                  <Bar dataKey="rate" isAnimationActive={false}>
                    {report.stability.sub_periods.map(period => (
                      <Cell key={period.start} fill={period.exception_rate * 100 > 2 * expectedRate ? '#dc2626' : '#92761f'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-white rounded-xl border p-5">
              <h3 className="font-semibold text-cascade-charcoal mb-3">Clustering and stability</h3>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <div><dt className="text-xs text-gray-500">Back-to-back exceptions</dt><dd className="font-semibold">{report.clustering.consecutive_pairs}</dd></div>
                <div><dt className="text-xs text-gray-500">Most in any {report.clustering.cluster_window_days} days</dt><dd className="font-semibold">{report.clustering.max_in_window}</dd></div>
                <div><dt className="text-xs text-gray-500">Mean gap between exceptions</dt><dd className="font-semibold">{report.clustering.mean_gap_days === null ? 'n/a' : `${report.clustering.mean_gap_days.toFixed(1)} days`}</dd></div>
                <div><dt className="text-xs text-gray-500">Mean loss / VaR on exceptions</dt><dd className="font-semibold">{report.mean_loss_to_var === null ? 'n/a' : `${report.mean_loss_to_var.toFixed(2)}x`}</dd></div>
                <div><dt className="text-xs text-gray-500">VaR range</dt><dd className="font-semibold">{formatAmount(report.stability.min_var)} to {formatAmount(report.stability.max_var)}</dd></div>
                <div><dt className="text-xs text-gray-500">Mean VaR</dt><dd className="font-semibold">{formatAmount(report.stability.mean_var)}</dd></div>
                <div><dt className="text-xs text-gray-500">VaR coefficient of variation</dt><dd className="font-semibold">{report.stability.var_coefficient_of_variation === null ? 'n/a' : report.stability.var_coefficient_of_variation.toFixed(3)}</dd></div>
                <div><dt className="text-xs text-gray-500">Largest one-day VaR change</dt><dd className="font-semibold">{report.stability.max_daily_var_change_pct === null ? 'n/a' : `${report.stability.max_daily_var_change_pct.toFixed(1)}%`}</dd></div>
              </dl>
              {Object.keys(report.drivers.top_risk_type_counts).length > 0 && (
                <p className="text-xs text-gray-500 mt-4">
                  Largest loss driver on exception days: {Object.entries(report.drivers.top_risk_type_counts).map(([riskType, count]) => `${riskType} (${count})`).join(', ')}.
                </p>
              )}
            </div>
          </div>

          <div className="bg-white rounded-xl border overflow-x-auto">
            <h3 className="font-semibold text-cascade-charcoal p-5 pb-3">Largest breaches and their drivers</h3>
            {report.largest_breaches.length === 0 ? <p className="px-5 pb-5 text-sm text-gray-500">No exceptions in the backtest window.</p> : (
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-600"><tr>{['Date', 'Loss', 'VaR', 'Loss beyond VaR', 'Loss / VaR', "Main risk factor drivers (share of that day's loss)"].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                <tbody>{report.largest_breaches.map(row => (
                  <tr key={row.index} className="border-t align-top">
                    <td className="p-3 whitespace-nowrap">{row.date}</td>
                    <td className="p-3 text-red-700">{formatAmount(-row.pnl)}</td>
                    <td className="p-3">{formatAmount(row.var)}</td>
                    <td className="p-3">{formatAmount(row.excess)}</td>
                    <td className="p-3">{row.loss_to_var === null ? 'n/a' : `${row.loss_to_var.toFixed(2)}x`}</td>
                    <td className="p-3 text-gray-600">
                      {row.drivers.length === 0 ? 'No factor breakdown' : row.drivers.map(driver => `${driver.label} ${formatAmount(driver.pnl)}${driver.share_of_loss_pct === null ? '' : ` (${driver.share_of_loss_pct.toFixed(0)}%)`}`).join('; ')}
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>

          <p className="text-xs text-gray-500">{report.disclaimer}{report.portfolio && ` ${report.portfolio.name}: ${report.portfolio.disclaimer}`}</p>
        </>
      )}
    </div>
  );
}
