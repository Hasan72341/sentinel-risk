import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, Loader2, AlertTriangle, CheckCircle2, XCircle, MinusCircle, FileText } from 'lucide-react';
import { getComplianceFrameworks, runFrameworkCheck, apiErrorMessage } from '../lib/asiaMarketsApi';
import type {
  Framework, FrameworkId, FrameworkComplianceReport, FrameworkCheckResult, CheckStatus, FrameworkReportStatus,
} from '../lib/asiaMarketsApi';
import { COUNTRIES, countryOptions, getCountry, loadSelectedCountry, saveSelectedCountry, formatNumber } from '../lib/region';
import type { CountryCode } from '../lib/region';
import { useToast } from '../components/Toast';

// Used until the API responds, so the selector is never empty.
const FALLBACK_FRAMEWORKS: Pick<Framework, 'id' | 'name' | 'jurisdiction'>[] = [
  { id: 'IFRS', name: 'IFRS Accounting Standards', jurisdiction: 'International' },
  { id: 'IND_AS', name: 'Indian Accounting Standards (Ind AS)', jurisdiction: 'India' },
  { id: 'CAS', name: 'Chinese Accounting Standards for Business Enterprises (CAS)', jurisdiction: 'China' },
  { id: 'JGAAP', name: 'Japanese GAAP (J-GAAP)', jurisdiction: 'Japan' },
  { id: 'KIFRS', name: 'Korean IFRS (K-IFRS)', jurisdiction: 'South Korea' },
];

const FALLBACK_DISCLOSURES = [
  { id: 'basis_of_preparation', label: 'Basis of preparation and the framework applied are stated' },
  { id: 'accounting_policies', label: 'Material accounting policies are disclosed' },
  { id: 'going_concern', label: 'Going concern assessment and any material uncertainties are disclosed' },
  { id: 'related_parties', label: 'Related party relationships and transactions are disclosed' },
  { id: 'segment_information', label: 'Segment information is disclosed (listed entities)' },
  { id: 'earnings_per_share', label: 'Earnings per share is presented (listed entities)' },
  { id: 'contingent_liabilities', label: 'Contingent liabilities and commitments are disclosed' },
  { id: 'subsequent_events', label: 'Events after the reporting period are disclosed' },
  { id: 'financial_risk', label: 'Financial instrument risks (credit, liquidity, market) are disclosed' },
];

const STATEMENTS = [
  { id: 'balance_sheet', label: 'Balance sheet' },
  { id: 'income_statement', label: 'Income statement' },
  { id: 'cash_flow_statement', label: 'Cash flow statement' },
  { id: 'changes_in_equity', label: 'Changes in equity' },
  { id: 'notes', label: 'Notes' },
];

const FIELD_GROUPS: { title: string; fields: { key: string; label: string; hint?: string }[] }[] = [
  {
    title: 'Balance sheet',
    fields: [
      { key: 'total_assets', label: 'Total assets' },
      { key: 'current_assets', label: 'Current assets' },
      { key: 'non_current_assets', label: 'Non-current assets' },
      { key: 'cash', label: 'Cash and cash equivalents' },
      { key: 'receivables', label: 'Trade receivables' },
      { key: 'inventory', label: 'Inventory' },
      { key: 'total_liabilities', label: 'Total liabilities' },
      { key: 'current_liabilities', label: 'Current liabilities' },
      { key: 'non_current_liabilities', label: 'Non-current liabilities' },
      { key: 'total_equity', label: 'Total equity' },
    ],
  },
  {
    title: 'Income statement',
    fields: [
      { key: 'revenue', label: 'Revenue' },
      { key: 'cost_of_sales', label: 'Cost of sales', hint: 'positive' },
      { key: 'gross_profit', label: 'Gross profit' },
      { key: 'profit_before_tax', label: 'Profit before tax' },
      { key: 'tax_expense', label: 'Tax expense', hint: 'positive' },
      { key: 'net_income', label: 'Net income' },
    ],
  },
  {
    title: 'Cash flow and equity',
    fields: [
      { key: 'operating_cash_flow', label: 'Operating cash flow' },
      { key: 'investing_cash_flow', label: 'Investing cash flow' },
      { key: 'financing_cash_flow', label: 'Financing cash flow' },
      { key: 'fx_effect_on_cash', label: 'Exchange rate effect on cash' },
      { key: 'net_change_in_cash', label: 'Net change in cash' },
      { key: 'opening_cash', label: 'Opening cash' },
      { key: 'closing_cash', label: 'Closing cash' },
      { key: 'dividends', label: 'Dividends paid', hint: 'positive' },
      { key: 'other_equity_movements', label: 'Other equity movements' },
    ],
  },
];

// Illustrative figures for a fictional company. Not real data.
const SAMPLE_NAME = 'Lotus Peak Components (fictional)';
const SAMPLE_CURRENT: Record<string, string> = {
  total_assets: '1000', current_assets: '400', non_current_assets: '600', cash: '100', receivables: '150',
  inventory: '120', total_liabilities: '600', current_liabilities: '250', non_current_liabilities: '350',
  total_equity: '400', revenue: '1200', cost_of_sales: '800', gross_profit: '400', profit_before_tax: '100',
  tax_expense: '25', net_income: '75', operating_cash_flow: '90', investing_cash_flow: '-50',
  financing_cash_flow: '-20', net_change_in_cash: '20', opening_cash: '80', closing_cash: '100', dividends: '15',
};
const SAMPLE_PRIOR: Record<string, string> = {
  total_assets: '950', total_liabilities: '610', total_equity: '340', revenue: '1100', net_income: '60',
};

const STATUS_STYLE: Record<FrameworkReportStatus, { label: string; className: string }> = {
  compliant: { label: 'No major issues found', className: 'bg-green-50 text-green-700 border-green-200' },
  needs_attention: { label: 'Needs attention', className: 'bg-amber-50 text-amber-700 border-amber-200' },
  non_compliant: { label: 'Significant issues', className: 'bg-red-50 text-red-700 border-red-200' },
  insufficient_data: { label: 'Not enough data', className: 'bg-gray-50 text-gray-600 border-gray-200' },
};

const CHECK_ICON: Record<CheckStatus, { icon: typeof CheckCircle2; className: string; label: string }> = {
  pass: { icon: CheckCircle2, className: 'text-green-600', label: 'Pass' },
  fail: { icon: XCircle, className: 'text-red-600', label: 'Fail' },
  not_applicable: { icon: MinusCircle, className: 'text-gray-400', label: 'Manual review' },
};

type Answer = '' | 'yes' | 'no';

function toNumbers(values: Record<string, string>): { numbers: Record<string, number>; invalid: string[] } {
  const numbers: Record<string, number> = {};
  const invalid: string[] = [];
  Object.entries(values).forEach(([key, raw]) => {
    const text = raw.replace(/,/g, '').trim();
    if (!text) return;
    const value = Number(text);
    if (Number.isFinite(value)) numbers[key] = value; else invalid.push(key);
  });
  return { numbers, invalid };
}

export default function Compliance() {
  const { toast } = useToast();
  const [country, setCountry] = useState<CountryCode>(() => loadSelectedCountry());
  const [frameworks, setFrameworks] = useState<Pick<Framework, 'id' | 'name' | 'jurisdiction'>[]>(FALLBACK_FRAMEWORKS);
  const [disclosureItems, setDisclosureItems] = useState(FALLBACK_DISCLOSURES);
  const [framework, setFramework] = useState<FrameworkId>(() => getCountry(loadSelectedCountry()).frameworkId);
  const [current, setCurrent] = useState<Record<string, string>>({});
  const [prior, setPrior] = useState<Record<string, string>>({});
  const [statements, setStatements] = useState<Set<string>>(new Set());
  const [statementsReviewed, setStatementsReviewed] = useState(false);
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [usingSample, setUsingSample] = useState(false);
  const [report, setReport] = useState<FrameworkComplianceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    getComplianceFrameworks()
      .then((catalogue) => {
        if (cancelled) return;
        if (catalogue.frameworks?.length) setFrameworks(catalogue.frameworks);
        if (catalogue.disclosure_items?.length) setDisclosureItems(catalogue.disclosure_items);
      })
      .catch(() => { /* the built-in list above is used */ });
    return () => { cancelled = true; };
  }, []);

  function chooseCountry(code: CountryCode) {
    setCountry(code);
    saveSelectedCountry(code);
    setFramework(getCountry(code).frameworkId);
  }

  function loadSample() {
    setCurrent(SAMPLE_CURRENT);
    setPrior(SAMPLE_PRIOR);
    setStatements(new Set(STATEMENTS.map((statement) => statement.id)));
    setStatementsReviewed(true);
    setUsingSample(true);
    setReport(null);
  }

  function clearAll() {
    setCurrent({}); setPrior({}); setStatements(new Set()); setStatementsReviewed(false);
    setAnswers({}); setUsingSample(false); setReport(null); setError('');
  }

  function toggleStatement(id: string) {
    setStatementsReviewed(true);
    setStatements((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function runCheck() {
    setError('');
    const currentValues = toNumbers(current);
    const priorValues = toNumbers(prior);
    const invalid = [...currentValues.invalid, ...priorValues.invalid];
    if (invalid.length) { setError(`These fields are not numbers: ${invalid.join(', ')}`); return; }
    if (!Object.keys(currentValues.numbers).length) { setError('Enter at least one current-period figure, or load the sample.'); return; }

    const disclosures: Record<string, boolean> = {};
    Object.entries(answers).forEach(([key, answer]) => { if (answer) disclosures[key] = answer === 'yes'; });

    setLoading(true); setReport(null);
    try {
      const result = await runFrameworkCheck({
        framework,
        financial_data: currentValues.numbers,
        prior_period: Object.keys(priorValues.numbers).length ? priorValues.numbers : undefined,
        disclosures: Object.keys(disclosures).length ? disclosures : undefined,
        statements_present: statementsReviewed ? Array.from(statements) : undefined,
      });
      setReport(result);
      toast(result.failed ? 'warning' : 'success', `${result.passed} passed, ${result.failed} failed, ${result.not_applicable} for manual review.`);
    } catch (cause) {
      const message = apiErrorMessage(cause, 'Compliance check failed');
      setError(message);
      toast('error', message);
    } finally { setLoading(false); }
  }

  const grouped = useMemo(() => {
    const groups = new Map<string, FrameworkCheckResult[]>();
    (report?.results ?? []).forEach((result) => {
      groups.set(result.standard, [...(groups.get(result.standard) ?? []), result]);
    });
    return Array.from(groups.entries());
  }, [report]);

  const selectedFramework = frameworks.find((item) => item.id === framework);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <ShieldCheck className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Compliance checks</h1>
          <p className="text-sm text-gray-500">Presentation and consistency checks under IFRS, Ind AS, CAS, J-GAAP or K-IFRS</p>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Simplified checks on summary figures, for analysis and learning. This is not an audit and not a complete
        compliance review under any framework.
      </p>

      {/* Framework */}
      <div className="bg-white rounded-xl border p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor="compliance-country" className="block text-sm font-semibold mb-1">Country</label>
          <select id="compliance-country" value={country} onChange={(event) => chooseCountry(event.target.value as CountryCode)}
            className="w-full border rounded-lg px-3 py-2 text-sm bg-white">
            {countryOptions().map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <p className="text-xs text-gray-500 mt-1">Selecting a country picks its usual framework: {COUNTRIES.map((item) => `${item.name} ${item.framework}`).join(', ')}.</p>
        </div>
        <div>
          <label htmlFor="compliance-framework" className="block text-sm font-semibold mb-1">Accounting framework</label>
          <select id="compliance-framework" value={framework} onChange={(event) => setFramework(event.target.value as FrameworkId)}
            className="w-full border rounded-lg px-3 py-2 text-sm bg-white">
            {frameworks.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {selectedFramework && <p className="text-xs text-gray-500 mt-1">Jurisdiction: {selectedFramework.jurisdiction}</p>}
        </div>
      </div>

      {/* Figures */}
      <div className="bg-white rounded-xl border p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-cascade-charcoal">Summary figures</h2>
            <p className="text-xs text-gray-500">One currency and unit throughout. Leave a field blank if you do not have it; the related check is then skipped.</p>
          </div>
          <div className="flex gap-2">
            <button onClick={loadSample} className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Load sample</button>
            <button onClick={clearAll} className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50">Clear</button>
          </div>
        </div>
        {usingSample && (
          <p className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-3 py-2">
            Illustrative sample data for {SAMPLE_NAME}. The figures are invented for demonstration.
          </p>
        )}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          {FIELD_GROUPS.map((group) => (
            <div key={group.title}>
              <div className="grid grid-cols-[1fr_6.5rem_6.5rem] gap-2 text-xs text-gray-500 mb-1">
                <span className="font-semibold text-cascade-charcoal">{group.title}</span><span>Current</span><span>Prior</span>
              </div>
              {group.fields.map((field) => (
                <div key={field.key} className="grid grid-cols-[1fr_6.5rem_6.5rem] gap-2 items-center mb-1.5">
                  <label htmlFor={`cur-${field.key}`} className="text-xs text-gray-700">
                    {field.label}{field.hint && <span className="text-gray-400"> ({field.hint})</span>}
                  </label>
                  <input id={`cur-${field.key}`} inputMode="decimal" value={current[field.key] ?? ''}
                    onChange={(event) => { setUsingSample(false); setCurrent({ ...current, [field.key]: event.target.value }); }}
                    className="border rounded px-2 py-1 text-xs text-right font-mono" />
                  <input aria-label={`${field.label}, prior period`} inputMode="decimal" value={prior[field.key] ?? ''}
                    onChange={(event) => { setUsingSample(false); setPrior({ ...prior, [field.key]: event.target.value }); }}
                    className="border rounded px-2 py-1 text-xs text-right font-mono" />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Statements and disclosures */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border p-5">
          <h2 className="text-sm font-semibold text-cascade-charcoal mb-1">Statements held</h2>
          <p className="text-xs text-gray-500 mb-3">Tick what the set of accounts contains. If you tick nothing, presence is inferred from the figures.</p>
          {STATEMENTS.map((statement) => (
            <label key={statement.id} className="flex items-center gap-2 text-sm py-1">
              <input type="checkbox" checked={statements.has(statement.id)} onChange={() => toggleStatement(statement.id)} />
              {statement.label}
            </label>
          ))}
        </div>
        <div className="bg-white rounded-xl border p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold text-cascade-charcoal mb-1">Disclosure checklist</h2>
          <p className="text-xs text-gray-500 mb-3">Answer from your reading of the notes. Unanswered items are listed for manual review and do not affect the score.</p>
          {disclosureItems.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-3 py-1 border-t first:border-t-0">
              <label htmlFor={`disc-${item.id}`} className="text-xs text-gray-700">{item.label}</label>
              <select id={`disc-${item.id}`} value={answers[item.id] ?? ''}
                onChange={(event) => setAnswers({ ...answers, [item.id]: event.target.value as Answer })}
                className="border rounded px-2 py-1 text-xs bg-white shrink-0">
                <option value="">Not reviewed</option>
                <option value="yes">Disclosed</option>
                <option value="no">Not disclosed</option>
              </select>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={runCheck} disabled={loading}
          className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
          {loading ? <Loader2 className="animate-spin" size={16} /> : <ShieldCheck size={16} />} Run checks
        </button>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      </div>

      {/* Report */}
      {report && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-white rounded-xl border p-4 col-span-2 md:col-span-1">
              <p className="text-xs text-gray-500 mb-1">Checks passed</p>
              <p className="text-xl font-bold text-cascade-charcoal">{report.compliance_score}%</p>
              <p className="text-xs text-gray-400">of {report.passed + report.failed} assessed</p>
            </div>
            <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Passed</p><p className="text-xl font-bold text-green-700">{report.passed}</p></div>
            <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Failed</p><p className="text-xl font-bold text-red-700">{report.failed}</p></div>
            <div className="bg-white rounded-xl border p-4"><p className="text-xs text-gray-500 mb-1">Manual review</p><p className="text-xl font-bold text-gray-600">{report.not_applicable}</p></div>
            <div className={`rounded-xl border p-4 ${STATUS_STYLE[report.status].className}`}>
              <p className="text-xs mb-1 opacity-80">Outcome</p>
              <p className="text-sm font-bold">{STATUS_STYLE[report.status].label}</p>
            </div>
          </div>

          <div className="bg-white rounded-xl border p-5">
            <h2 className="text-sm font-semibold text-cascade-charcoal flex items-center gap-2"><FileText size={15} /> {report.framework.name}</h2>
            <p className="text-xs text-gray-500 mt-1">Issued by: {report.framework.issuer}. Rounding tolerance: {formatNumber(report.tolerance_pct, country, 1)}% of the larger amount.</p>
            <ul className="list-disc pl-5 mt-2 space-y-0.5">
              {report.framework_notes.map((note) => <li key={note} className="text-xs text-gray-600">{note}</li>)}
            </ul>
          </div>

          {report.critical_issues.length > 0 && (
            <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
              <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
              <div className="space-y-1">{report.critical_issues.map((issue) => <p key={issue} className="text-sm text-red-700">{issue}</p>)}</div>
            </div>
          )}

          {grouped.map(([standard, results]) => (
            <div key={standard} className="bg-white rounded-xl border overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-cascade-charcoal">{standard}</h3>
                <p className="text-xs text-gray-500">{results.filter((result) => result.status === 'pass').length} of {results.length} passed</p>
              </div>
              {results.map((result) => {
                const style = CHECK_ICON[result.status];
                const Icon = style.icon;
                return (
                  <div key={result.check_id} className="border-t px-4 py-3 flex items-start gap-3">
                    <Icon className={`${style.className} shrink-0 mt-0.5`} size={16} aria-label={style.label} />
                    <div className="min-w-0">
                      <p className="text-sm text-cascade-charcoal">{result.rule}
                        {result.severity === 'blocking' && <span className="ml-2 text-xs text-red-700 font-medium">Blocking</span>}
                      </p>
                      <p className="text-xs text-gray-600 mt-0.5">{result.message}</p>
                      {result.status === 'fail' && result.remediation && <p className="text-xs text-amber-700 mt-0.5">{result.remediation}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}

          {report.recommendations.length > 0 && (
            <div className="bg-white rounded-xl border p-5">
              <h2 className="text-sm font-semibold text-cascade-charcoal mb-2">Follow-up</h2>
              <div className="space-y-2">
                {report.recommendations.map((item) => (
                  <div key={item.title} className="text-sm">
                    <span className={`text-xs font-medium uppercase mr-2 ${item.priority === 'critical' ? 'text-red-700' : item.priority === 'high' ? 'text-amber-700' : 'text-gray-500'}`}>{item.priority}</span>
                    <span className="font-medium text-cascade-charcoal">{item.title}</span>
                    <p className="text-xs text-gray-600">{item.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-gray-400">{report.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
