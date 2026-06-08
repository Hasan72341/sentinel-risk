import { useEffect, useState } from 'react';
import { Download, ExternalLink, FileCheck2 } from 'lucide-react';
import { save } from '@tauri-apps/plugin-dialog';
import { getApiClient } from '../lib/api';
import { isDesktop, writeFile } from '../lib/desktop';

type Fact = { kind: string; concept?: string; formula?: string; reason?: string; accn?: string; filed?: string; source_sha256?: string };
type Annual = { year: number; period_start: string; period_end: string; filed: string; accession: string; filing_url: string;
  values: Record<string, number | null>; ratios: Record<string, number | null>; evidence: Record<string, Fact>;
  quality: { missing_fields: string[]; balance_sheet_residual_usd: number | null } };
type Issuer = { ticker: string; name: string; years: Annual[]; context: { profile: string; event: string; source: string; section: string };
  monitoring: { area: string; rule: string; status: string; basis: string }[]; review: string };
type CaseStudy = { title: string; as_of: string; data_status: string; selection_policy: string; limitations: string[];
  issuers: Issuer[]; peer_metrics: Record<string, { label: string; formula: string; unit: string; median: number | null; n: number }>;
  sources: { ticker: string; url: string; sha256: string; retrieved_at: string }[] };

function money(value: number | null) { return value === null ? 'Unavailable' : (value / 1e6).toLocaleString('en-US', { maximumFractionDigits: 1 }); }
function ratio(value: number | null, unit: string) { return value === null ? 'Unavailable' : unit === '%' ? `${(value * 100).toFixed(2)}%` : `${value.toFixed(2)}x`; }
function label(key: string) { return key === 'interest_expense' ? 'Gross interest expense' : key.replace(/_/g, ' '); }

export default function PublicFilings() {
  const [data, setData] = useState<CaseStudy | null>(null);
  const [ticker, setTicker] = useState('KO');
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [saved, setSaved] = useState('');
  useEffect(() => {
    let active = true;
    getApiClient().then(client => client.get<CaseStudy>('/public-filings/case'))
      .then(response => { if (active) setData(response.data); })
      .catch(cause => { if (active) setError(cause.response?.data?.detail || 'Unable to load the bundled filings. Start the local API and reload this page.'); });
    return () => { active = false; };
  }, []);

  const download = async () => {
    setExporting(true); setError(''); setSaved('');
    try {
      const client = await getApiClient();
      const response = await client.get('/public-filings/export', { responseType: 'blob' });
      const filename = 'public-filings-credit-case.zip';
      if (isDesktop) {
        const path = await save({ defaultPath: filename, filters: [{ name: 'Credit case archive', extensions: ['zip'] }] });
        if (path) { await writeFile(path, response.data); setSaved(`Saved ${path}`); }
      } else {
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000); setSaved('Credit case downloaded.');
      }
    } catch { setError('Export failed. Confirm the API is running and retry.'); }
    finally { setExporting(false); }
  };

  if (!data) return <div role={error ? 'alert' : 'status'} className="card">{error || 'Loading verified SEC filing cache…'}</div>;
  const issuer = data.issuers.find(item => item.ticker === ticker) || data.issuers[0];
  const latest = issuer.years[issuer.years.length - 1];
  const alertCount = data.issuers.flatMap(item => item.monitoring).filter(item => item.status === 'review').length;
  return <div className="space-y-6">
    <div className="page-header flex-wrap gap-3">
      <div><h1 className="page-title">Public Filings Credit Review</h1>
        <p className="text-sm text-cascade-sage mt-1">Reported SEC financials · FY2022–2024 · information cutoff {data.as_of}</p></div>
      <button className="btn-primary flex items-center gap-2" onClick={download} disabled={exporting}><Download size={16} />{exporting ? 'Preparing export…' : 'Export evidence pack'}</button>
    </div>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {saved && <p role="status" className="text-green-800">{saved}</p>}
    <div className="card border-l-4 border-cascade-gold text-sm space-y-2">
      <p className="font-semibold flex gap-2 items-center"><FileCheck2 size={18} />Annual filings and source references</p>
      <p>Reported financials and labelled calculations for three US-listed companies. Monitoring screens use research thresholds; credit reviews are analytical drafts.</p>
      <p className="text-cascade-sage">The study includes filings available by {data.as_of}. Sample portfolios and scorecards elsewhere in the app use illustrative assumptions.</p>
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {[['Issuers', data.issuers.length], ['Annual statements', data.issuers.reduce((count, item) => count + item.years.length, 0)], ['Research screens triggered', alertCount]].map(([name, value]) =>
        <div key={name} className="card"><p className="text-sm text-cascade-sage">{name}</p><p className="text-3xl font-semibold mt-2">{value}</p></div>)}
    </div>
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Company and filing context</h2>
        <label className="text-sm">Issuer <select aria-label="Issuer" value={ticker} onChange={event => setTicker(event.target.value)} className="ml-2 border rounded p-2 bg-white">{data.issuers.map(item => <option key={item.ticker} value={item.ticker}>{item.ticker} — {item.name}</option>)}</select></label></div>
      <h3 className="font-semibold">{issuer.name}</h3><p className="text-sm">{issuer.context.profile}</p>
      <p className="text-sm">{issuer.context.event}</p>
      <a className="text-sm text-blue-700 underline inline-flex gap-1" href={issuer.context.source} target="_blank" rel="noreferrer">Read company disclosure: {issuer.context.section}<ExternalLink size={14} /></a>
    </section>
    <section className="card space-y-3"><h2 className="text-lg font-semibold">Financial statements</h2>
      <p className="text-sm text-cascade-sage">USD millions for display; exports retain USD. Select a filing below to inspect its original source. Missing facts stay unavailable.</p>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-3">Reported / derived field</th>{issuer.years.map(row => <th className="text-right p-3" key={row.year}>{row.year}<br /><a href={row.filing_url} target="_blank" rel="noreferrer" className="font-normal text-blue-700 underline">{row.period_end}</a></th>)}</tr></thead>
        <tbody>{Object.keys(latest.values).map(key => <tr className="border-b border-cascade-mist" key={key}><th className="py-2 text-left font-normal capitalize">{label(key)}</th>{issuer.years.map(row => <td key={row.year} className="text-right p-2 tabular-nums" title={row.evidence[key].formula || row.evidence[key].concept || row.evidence[key].reason}>{money(row.values[key])}{row.evidence[key].kind === 'derived' && <span className="text-xs text-cascade-sage"> *</span>}</td>)}</tr>)}</tbody></table></div>
      <p className="text-xs text-cascade-sage">* Derived from cited facts. Consolidated equity includes noncontrolling interests; shareholder equity does not. Interest expense definitions differ, so no gross interest coverage comparison is presented.</p>
    </section>
    <section className="card space-y-3"><h2 className="text-lg font-semibold">Ratios and selected peers</h2>
      <p className="text-sm text-cascade-sage">FY2024 median includes this issuer. Three selected companies are a comparison set, not a sector benchmark. Ratios use reported GAAP figures.</p>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b"><th className="text-left py-3">Metric</th>{issuer.years.map(row => <th className="text-right p-3" key={row.year}>{row.year}</th>)}<th className="text-right p-3">Peer median (n)</th></tr></thead>
        <tbody>{Object.entries(data.peer_metrics).map(([key, metric]) => <tr className="border-b border-cascade-mist" key={key}><th className="py-2 text-left font-normal">{metric.label}<div className="text-xs text-cascade-sage">{metric.formula}</div></th>{issuer.years.map(row => <td className="text-right p-2 tabular-nums" key={row.year}>{ratio(row.ratios[key], metric.unit)}</td>)}<td className="text-right p-2 tabular-nums">{ratio(metric.median, metric.unit)} ({metric.n})</td></tr>)}</tbody></table></div>
    </section>
    <section className="card space-y-3"><h2 className="text-lg font-semibold">Annual monitoring</h2>
      <p className="text-sm text-cascade-sage">Review flags identify changes in liquidity, margin or cash flow. Thresholds are research assumptions; contractual covenants are not available.</p>
      {issuer.monitoring.map(check => <div key={check.area} className="flex flex-wrap justify-between gap-2 border-b border-cascade-mist py-2 text-sm"><span>{check.area}: {check.rule}</span><strong className={check.status === 'review' ? 'text-amber-800' : 'text-cascade-sage'}>{label(check.status)}</strong></div>)}
    </section>
    <section className="card space-y-3"><h2 className="text-lg font-semibold">Credit review draft</h2><pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{issuer.review}</pre></section>
    <section className="card space-y-3"><h2 className="text-lg font-semibold">Evidence and limitations</h2><p className="text-sm">{data.selection_policy}</p>
      {issuer.years.map(row => <details key={row.year} className="border rounded p-3"><summary className="cursor-pointer text-sm">{row.year} field provenance · filed {row.filed} · {row.quality.missing_fields.length} unavailable</summary><pre className="text-xs overflow-auto mt-3 max-h-96">{JSON.stringify(row.evidence, null, 2)}</pre></details>)}
      {data.sources.map(source => <div className="text-xs break-all" key={source.ticker}><a className="text-blue-700 underline" href={source.url} target="_blank" rel="noreferrer">{source.ticker}: SEC companyfacts</a><p>Retrieved {source.retrieved_at}; SHA256 {source.sha256}</p></div>)}
      <ul className="list-disc pl-5 text-sm space-y-2">{data.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </section>
  </div>;
}
