import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { Radar, Loader2, AlertTriangle, RefreshCw } from 'lucide-react';
import { useToast } from '../components/Toast';
import { apiErrorMessage, getSamplePortfolio, reviewCounterpartyPortfolio } from '../lib/creditRiskApi';
import type { CounterpartyType, CountryCode, MonitoredCounterparty, PortfolioCounterparty, PortfolioReview, ReviewFrequency } from '../lib/creditRiskApi';

type Tab = 'portfolio' | 'reviews' | 'migrations' | 'watchlist' | 'actions';

const columns = ['name', 'counterparty_type', 'country', 'rating', 'previous_rating', 'review_frequency', 'last_review_date', 'limit', 'utilisation'] as const;

function toCsv(rows: PortfolioCounterparty[]): string {
  return [columns.join(','), ...rows.map(row => columns.map(column => row[column] ?? '').join(','))].join('\n');
}

function parseCsv(raw: string): PortfolioCounterparty[] {
  const lines = raw.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2 || lines[0].trim() !== columns.join(',')) {
    throw new Error(`First row must be: ${columns.join(',')}`);
  }
  return lines.slice(1).map((line, index) => {
    const cells = line.split(',').map(cell => cell.trim());
    if (cells.length !== columns.length || !cells[0]) throw new Error(`Row ${index + 2}: expected ${columns.length} columns`);
    const limit = Number(cells[7]);
    const utilisation = Number(cells[8]);
    if (cells[7] === '' || cells[8] === '' || !Number.isFinite(limit) || !Number.isFinite(utilisation)) {
      throw new Error(`Row ${index + 2}: limit and utilisation must be numbers`);
    }
    return {
      name: cells[0], counterparty_type: cells[1] as CounterpartyType, country: cells[2] as CountryCode,
      rating: cells[3], previous_rating: cells[4] || null, review_frequency: cells[5] as ReviewFrequency,
      last_review_date: cells[6], limit, utilisation,
    };
  });
}

const priorityClass: Record<MonitoredCounterparty['priority'], string> = {
  High: 'bg-red-50 text-red-700 border-red-200',
  Medium: 'bg-amber-50 text-amber-700 border-amber-200',
  Low: 'bg-blue-50 text-blue-700 border-blue-200',
  None: 'bg-gray-50 text-gray-500 border-gray-200',
};

function PriorityBadge({ priority }: { priority: MonitoredCounterparty['priority'] }) {
  return <span className={`inline-block px-2 py-0.5 rounded-full border text-xs font-medium ${priorityClass[priority]}`}>{priority}</span>;
}

function reviewLabel(row: MonitoredCounterparty): string {
  if (row.review_status === 'overdue') return `Overdue by ${-row.days_to_review} days`;
  if (row.review_status === 'due_soon') return `Due in ${row.days_to_review} days`;
  return `In ${row.days_to_review} days`;
}

function reviewClass(status: MonitoredCounterparty['review_status']): string {
  return status === 'overdue' ? 'text-red-700 font-semibold' : status === 'due_soon' ? 'text-amber-700 font-semibold' : '';
}

function Table({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <div className="bg-white border rounded-xl overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-50 text-gray-600"><tr>{headers.map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export default function CounterpartyMonitor() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('portfolio');
  const [input, setInput] = useState('');
  const [asOf, setAsOf] = useState('');
  const [isSample, setIsSample] = useState(true);
  const [note, setNote] = useState('');
  const [review, setReview] = useState<PortfolioReview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadSample() {
    setError(''); setLoading(true);
    try {
      const sample = await getSamplePortfolio(asOf || undefined);
      setInput(toCsv(sample.counterparties));
      setAsOf(sample.as_of);
      setNote(sample.note);
      setIsSample(true);
      setReview(await reviewCounterpartyPortfolio(sample.counterparties, sample.as_of));
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Could not load the sample portfolio. Is the local API running?'));
    } finally { setLoading(false); }
  }

  useEffect(() => { loadSample(); }, []);

  async function runReview() {
    setError(''); setLoading(true);
    try {
      const result = await reviewCounterpartyPortfolio(parseCsv(input), asOf || undefined);
      setReview(result);
      toast('success', `Reviewed ${result.summary.counterparties} counterparties`);
    } catch (cause) {
      setReview(null);
      setError(apiErrorMessage(cause, 'Portfolio review failed'));
    } finally { setLoading(false); }
  }

  const summary = review?.summary;
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'portfolio', label: 'Portfolio', count: summary?.counterparties },
    { id: 'reviews', label: 'Reviews due', count: review?.reviews_due.length },
    { id: 'migrations', label: 'Migrations', count: review?.migrations.length },
    { id: 'watchlist', label: 'Watchlist', count: summary?.watchlist },
    { id: 'actions', label: 'Action list', count: review?.actions.length },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Radar className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Counterparty Monitor</h1>
          <p className="text-sm text-gray-500">Reviews due, rating migrations, limit utilisation, watchlist and prioritised actions</p>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <div className="bg-white border rounded-xl p-5 space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <label htmlFor="portfolio-input" className="block text-sm font-semibold">Counterparty portfolio (CSV)</label>
          <label className="text-sm text-gray-600 flex items-center gap-2">
            As-of date
            <input type="date" value={asOf} onChange={event => setAsOf(event.target.value)} className="border rounded-lg px-2 py-1.5 text-sm" />
          </label>
        </div>
        <textarea id="portfolio-input" value={input} onChange={event => { setInput(event.target.value); setIsSample(false); }} rows={8}
          className="w-full font-mono text-xs border rounded-lg p-3" spellCheck={false} />
        <p className="text-xs text-gray-500">
          {isSample && note ? `${note} ` : ''}
          Types: corporate, financial_institution, fund. Countries: IN, CN, JP, KR. Ratings: IR1 (strongest) to IR10. Review frequency: annual or semi_annual.
          Use one currency for limit and utilisation (the sample uses USD millions). Commas inside names are unsupported.
          Simplified monitoring rules for analysis and learning; not a regulatory calculation.
        </p>
        <div className="flex flex-wrap gap-3">
          <button onClick={runReview} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Radar size={16} />} Review portfolio
          </button>
          <button onClick={loadSample} disabled={loading} className="px-4 py-2 border rounded-lg text-sm font-medium flex items-center gap-2 hover:bg-gray-50 disabled:opacity-50">
            <RefreshCw size={15} /> Load sample portfolio
          </button>
        </div>
      </div>

      {review && summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Utilisation / limit</p>
              <p className="text-xl font-bold text-cascade-charcoal">{summary.utilisation_pct}%</p>
              <p className="text-xs text-gray-400">{summary.total_utilisation.toLocaleString()} of {summary.total_limit.toLocaleString()}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Reviews overdue</p>
              <p className={`text-xl font-bold ${summary.reviews_overdue ? 'text-red-600' : 'text-cascade-charcoal'}`}>{summary.reviews_overdue}</p>
              <p className="text-xs text-gray-400">{summary.reviews_due_soon} due within 30 days</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Limit breaches</p>
              <p className={`text-xl font-bold ${summary.limit_breaches ? 'text-red-600' : 'text-cascade-charcoal'}`}>{summary.limit_breaches}</p>
              <p className="text-xs text-gray-400">Utilisation above limit</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Rating migrations</p>
              <p className="text-xl font-bold text-cascade-charcoal">{summary.downgrades} down / {summary.upgrades} up</p>
              <p className="text-xs text-gray-400">Against previous rating</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Watchlist</p>
              <p className="text-xl font-bold text-cascade-charcoal">{summary.watchlist}</p>
              <p className="text-xs text-gray-400">of {summary.counterparties} counterparties, as of {review.as_of}</p>
            </div>
          </div>

          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {tabs.map(item => (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  tab === item.id ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {item.label}{item.count !== undefined ? ` (${item.count})` : ''}
              </button>
            ))}
          </div>

          {tab === 'portfolio' && (
            <div className="space-y-4">
              <Table headers={['Counterparty', 'Type', 'Country', 'Rating', 'Limit', 'Utilisation', 'Used', 'Next review', 'Priority']}>
                {review.counterparties.map(row => (
                  <tr key={row.name} className="border-t">
                    <td className="p-3 font-medium">{row.name}</td>
                    <td className="p-3">{row.counterparty_type_label}</td>
                    <td className="p-3">{row.country_name}</td>
                    <td className="p-3">{row.rating}</td>
                    <td className="p-3">{row.limit.toLocaleString()}</td>
                    <td className="p-3">{row.utilisation.toLocaleString()}</td>
                    <td className={`p-3 ${row.limit_breach ? 'text-red-700 font-semibold' : row.utilisation_pct >= 90 ? 'text-amber-700 font-semibold' : ''}`}>{row.utilisation_pct}%</td>
                    <td className={`p-3 whitespace-nowrap ${reviewClass(row.review_status)}`}>{row.next_review_date}</td>
                    <td className="p-3"><PriorityBadge priority={row.priority} /></td>
                  </tr>
                ))}
              </Table>
              <div className="bg-white rounded-xl border p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Limit and utilisation by country</h3>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={summary.by_country}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value: number) => value.toLocaleString()} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="limit" name="Limit" fill="#e7e5e4" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="utilisation" name="Utilisation" fill="#92761f" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {tab === 'reviews' && (review.reviews_due.length ? (
            <Table headers={['Counterparty', 'Rating', 'Frequency', 'Last review', 'Next review', 'Status']}>
              {review.reviews_due.map(row => (
                <tr key={row.name} className="border-t">
                  <td className="p-3 font-medium">{row.name}</td>
                  <td className="p-3">{row.rating}</td>
                  <td className="p-3">{row.review_frequency === 'annual' ? 'Annual' : 'Semi-annual'}</td>
                  <td className="p-3 whitespace-nowrap">{row.last_review_date}</td>
                  <td className="p-3 whitespace-nowrap">{row.next_review_date}</td>
                  <td className={`p-3 ${reviewClass(row.review_status)}`}>{reviewLabel(row)}</td>
                </tr>
              ))}
            </Table>
          ) : <p className="text-sm text-gray-500">No reviews are overdue or due within 30 days.</p>)}

          {tab === 'migrations' && (review.migrations.length ? (
            <Table headers={['Counterparty', 'Previous rating', 'Current rating', 'Notches', 'Direction']}>
              {review.migrations.map(row => (
                <tr key={row.name} className="border-t">
                  <td className="p-3 font-medium">{row.name}</td>
                  <td className="p-3">{row.previous_rating}</td>
                  <td className="p-3">{row.rating}</td>
                  <td className="p-3">{Math.abs(row.migration_notches)}</td>
                  <td className={`p-3 capitalize font-medium ${row.migration === 'downgrade' ? 'text-red-700' : 'text-green-700'}`}>{row.migration}</td>
                </tr>
              ))}
            </Table>
          ) : <p className="text-sm text-gray-500">No rating changes against the previous rating.</p>)}

          {tab === 'watchlist' && (review.watchlist.length ? (
            <Table headers={['Counterparty', 'Rating', 'Used', 'Flags', 'Priority']}>
              {review.watchlist.map(row => (
                <tr key={row.name} className="border-t align-top">
                  <td className="p-3 font-medium">{row.name}</td>
                  <td className="p-3">{row.rating}</td>
                  <td className="p-3">{row.utilisation_pct}%</td>
                  <td className="p-3">{row.watchlist_flags.join('; ')}</td>
                  <td className="p-3"><PriorityBadge priority={row.priority} /></td>
                </tr>
              ))}
            </Table>
          ) : <p className="text-sm text-gray-500">No counterparties are flagged for the watchlist.</p>)}

          {tab === 'actions' && (review.actions.length ? (
            <Table headers={['Priority', 'Counterparty', 'Action']}>
              {review.actions.map((item, index) => (
                <tr key={`${item.name}-${index}`} className="border-t align-top">
                  <td className="p-3"><PriorityBadge priority={item.priority} /></td>
                  <td className="p-3 font-medium">{item.name}</td>
                  <td className="p-3 text-gray-700">{item.action}</td>
                </tr>
              ))}
            </Table>
          ) : <p className="text-sm text-gray-500">No actions are required.</p>)}
        </>
      )}
    </div>
  );
}
