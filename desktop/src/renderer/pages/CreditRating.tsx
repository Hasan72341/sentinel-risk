import { useEffect, useMemo, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, ReferenceLine } from 'recharts';
import { Award, Loader2, AlertTriangle, Copy, ClipboardCheck, FileText, BookOpen, ListChecks } from 'lucide-react';
import { useToast } from '../components/Toast';
import {
  apiErrorMessage, assessDueDiligence, generateCreditReview, getDueDiligenceChecklist,
  getRatingMethodology, getRatingSamples,
} from '../lib/creditRiskApi';
import type {
  CounterpartyType, CountryCode, CreditReviewDraft, DueDiligenceAssessment, DueDiligenceChecklist,
  DueDiligenceState, QualitativeInputs, RatingMethodology, SampleCounterparty, ScorecardResult,
} from '../lib/creditRiskApi';

type Tab = 'scorecard' | 'review' | 'diligence' | 'methodology';

const TYPES: { id: CounterpartyType; label: string }[] = [
  { id: 'corporate', label: 'Corporate' },
  { id: 'financial_institution', label: 'Financial institution' },
  { id: 'fund', label: 'Fund' },
];

const STATE_LABELS: Record<DueDiligenceState, string> = {
  pending: 'Pending', complete: 'Complete', not_applicable: 'Not applicable', issue: 'Issue',
};

const QUALITATIVE_LEVELS = ['1 - Weak', '2 - Below average', '3 - Average', '4 - Good', '5 - Strong'];
const DEFAULT_QUALITATIVE: QualitativeInputs = { business_profile: 3, management_governance: 3, sector_outlook: 3, country: 3 };

function scoreColour(score: number, strength: number, concern: number): string {
  if (score >= strength) return '#16a34a';
  if (score <= concern) return '#dc2626';
  return '#92761f';
}

function positionClass(position: string): string {
  if (position === 'stronger') return 'text-green-700';
  if (position === 'weaker') return 'text-red-700';
  return 'text-gray-600';
}

export default function CreditRating() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('scorecard');
  const [methodology, setMethodology] = useState<RatingMethodology | null>(null);
  const [samples, setSamples] = useState<Record<CounterpartyType, SampleCounterparty[]> | null>(null);
  const [type, setType] = useState<CounterpartyType>('corporate');
  const [sampleIndex, setSampleIndex] = useState(0);
  const [name, setName] = useState('');
  const [country, setCountry] = useState<CountryCode>('IN');
  const [sector, setSector] = useState('');
  const [financials, setFinancials] = useState<Record<string, string>>({});
  const [qualitative, setQualitative] = useState<QualitativeInputs>(DEFAULT_QUALITATIVE);
  const [useSamplePeers, setUseSamplePeers] = useState(true);
  const [result, setResult] = useState<ScorecardResult | null>(null);
  const [review, setReview] = useState<CreditReviewDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [checklist, setChecklist] = useState<DueDiligenceChecklist | null>(null);
  const [itemStates, setItemStates] = useState<Record<string, DueDiligenceState>>({});
  const [assessment, setAssessment] = useState<DueDiligenceAssessment | null>(null);

  function loadSample(sample: SampleCounterparty) {
    setName(sample.name);
    setCountry(sample.country);
    setSector(sample.sector);
    setFinancials(Object.fromEntries(Object.entries(sample.financials).map(([key, value]) => [key, String(value)])));
    setQualitative(sample.qualitative);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([getRatingMethodology(), getRatingSamples()])
      .then(([doc, sampleData]) => {
        if (cancelled) return;
        setMethodology(doc);
        setSamples(sampleData.samples);
        loadSample(sampleData.samples.corporate[0]);
      })
      .catch(cause => { if (!cancelled) setError(apiErrorMessage(cause, 'Could not load the rating methodology. Is the local API running?')); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setChecklist(null); setAssessment(null); setItemStates({});
    getDueDiligenceChecklist(type, country)
      .then(data => { if (!cancelled) setChecklist(data); })
      .catch(() => { /* surfaced by the main loader when the API is down */ });
    return () => { cancelled = true; };
  }, [type, country]);

  const scorecardSpec = methodology?.scorecards[type];
  const inputGroups = useMemo(() => {
    const groups: Record<string, { key: string; label: string }[]> = {};
    (scorecardSpec?.inputs || []).forEach(field => { (groups[field.group] ||= []).push(field); });
    return Object.entries(groups);
  }, [scorecardSpec]);

  function changeType(next: CounterpartyType) {
    setType(next); setResult(null); setReview(null); setError('');
    if (samples) { setSampleIndex(0); loadSample(samples[next][0]); }
  }

  function changeSample(index: number) {
    setSampleIndex(index); setResult(null); setReview(null);
    if (index >= 0 && samples) {
      loadSample(samples[type][index]);
    } else {
      setName(''); setSector(''); setFinancials({}); setQualitative(DEFAULT_QUALITATIVE);
    }
  }

  async function runScorecard() {
    setError('');
    if (!scorecardSpec) return;
    if (!name.trim()) { setError('Enter a counterparty name.'); return; }
    const values: Record<string, number> = {};
    for (const field of scorecardSpec.inputs) {
      const raw = (financials[field.key] ?? '').trim();
      const value = Number(raw);
      if (raw === '' || !Number.isFinite(value)) { setError(`Enter a number for "${field.label}".`); return; }
      values[field.key] = value;
    }
    setLoading(true);
    try {
      const data = await generateCreditReview({
        counterparty_type: type, name: name.trim(), country, sector: sector.trim(),
        financials: values, qualitative, use_sample_peers: useSamplePeers,
      });
      setResult(data.scorecard);
      setReview(data.review);
      toast('success', `Scorecard complete: ${data.scorecard.grade}`);
    } catch (cause) {
      setResult(null); setReview(null);
      setError(apiErrorMessage(cause, 'Scorecard failed'));
    } finally { setLoading(false); }
  }

  async function copyReview() {
    if (!review) return;
    try {
      await navigator.clipboard.writeText(review.text);
      toast('success', 'Credit review copied to clipboard');
    } catch {
      toast('error', 'Could not copy to clipboard');
    }
  }

  async function changeItemState(id: string, state: DueDiligenceState) {
    const next = { ...itemStates, [id]: state };
    setItemStates(next);
    try {
      setAssessment(await assessDueDiligence(type, country, next));
    } catch (cause) {
      toast('error', apiErrorMessage(cause, 'Could not assess the checklist'));
    }
  }

  const tabs: { id: Tab; label: string; icon: typeof Award }[] = [
    { id: 'scorecard', label: 'Scorecard', icon: Award },
    { id: 'review', label: 'Credit review', icon: FileText },
    { id: 'diligence', label: 'Due diligence', icon: ListChecks },
    { id: 'methodology', label: 'Methodology', icon: BookOpen },
  ];

  const strength = methodology?.strength_threshold ?? 75;
  const concern = methodology?.concern_threshold ?? 35;
  const chartData = (result?.factors || []).map(factor => ({
    label: `${factor.label} (${factor.weight}%)`, score: factor.score, display: factor.display_value,
  }));
  const checklistGroups = useMemo(() => {
    const groups: Record<string, DueDiligenceChecklist['items']> = {};
    (checklist?.items || []).forEach(item => { (groups[item.category] ||= []).push(item); });
    return Object.entries(groups);
  }, [checklist]);
  const statusClass = assessment?.status === 'ready' ? 'bg-green-50 border-green-200 text-green-800'
    : assessment?.status === 'blocked' ? 'bg-red-50 border-red-200 text-red-800'
    : 'bg-amber-50 border-amber-200 text-amber-800';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <Award className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Internal Credit Rating</h1>
          <p className="text-sm text-gray-500">Scorecards, peer comparison, credit review drafts and onboarding due diligence</p>
        </div>
      </div>

      <p className="text-xs text-gray-500 bg-cascade-stone border border-cascade-mist rounded-lg px-3 py-2">
        Simplified scorecard for analysis and learning; not a regulatory calculation. Bundled counterparties are fictional and their figures are invented sample data.
      </p>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={18} />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Inputs */}
      <div className="bg-white border rounded-xl p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <label className="block text-sm">
            <span className="font-semibold text-gray-700">Counterparty type</span>
            <select value={type} onChange={event => changeType(event.target.value as CounterpartyType)} className="mt-1 w-full border rounded-lg px-3 py-2 text-sm">
              {TYPES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-semibold text-gray-700">Sample or custom</span>
            <select value={sampleIndex} onChange={event => changeSample(Number(event.target.value))} className="mt-1 w-full border rounded-lg px-3 py-2 text-sm">
              {(samples?.[type] || []).map((sample, index) => <option key={sample.name} value={index}>{sample.name}</option>)}
              <option value={-1}>Custom (enter financials)</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-semibold text-gray-700">Country</span>
            <select value={country} onChange={event => setCountry(event.target.value as CountryCode)} className="mt-1 w-full border rounded-lg px-3 py-2 text-sm">
              {(methodology?.countries || []).map(item => <option key={item.code} value={item.code}>{item.name} ({item.currency})</option>)}
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-semibold text-gray-700">Sector</span>
            <input value={sector} onChange={event => setSector(event.target.value)} className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" />
          </label>
        </div>
        <label className="block text-sm">
          <span className="font-semibold text-gray-700">Counterparty name</span>
          <input value={name} onChange={event => setName(event.target.value)} className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" />
        </label>

        {inputGroups.map(([group, fields]) => (
          <div key={group}>
            <h2 className="text-sm font-semibold text-cascade-charcoal mb-2">{group}</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {fields.map(field => (
                <label key={field.key} className="block text-xs text-gray-600">
                  {field.label}
                  <input
                    type="number" step="any" value={financials[field.key] ?? ''}
                    onChange={event => setFinancials(current => ({ ...current, [field.key]: event.target.value }))}
                    className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm text-gray-900"
                  />
                </label>
              ))}
            </div>
          </div>
        ))}
        {methodology && <p className="text-xs text-gray-500">{methodology.units}</p>}

        <div>
          <h2 className="text-sm font-semibold text-cascade-charcoal mb-2">Qualitative assessment</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {(scorecardSpec?.qualitative_factors || []).map(factor => (
              <label key={factor.key} className="block text-xs text-gray-600" title={factor.description}>
                {factor.label}
                <select
                  value={qualitative[factor.key]}
                  onChange={event => setQualitative(current => ({ ...current, [factor.key]: Number(event.target.value) }))}
                  className="mt-1 w-full border rounded-lg px-2 py-1.5 text-sm text-gray-900"
                >
                  {QUALITATIVE_LEVELS.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
                </select>
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <button onClick={runScorecard} disabled={loading || !methodology} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Award size={16} />} Run scorecard
          </button>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={useSamplePeers} onChange={event => setUseSamplePeers(event.target.checked)} />
            Compare with the bundled sample peer set
          </label>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
        {tabs.map(item => (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
              tab === item.id ? 'bg-white text-cascade-charcoal shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <item.icon size={15} /> {item.label}
          </button>
        ))}
      </div>

      {/* Scorecard */}
      {tab === 'scorecard' && !result && (
        <p className="text-sm text-gray-500">Run the scorecard to see the rating, factor breakdown and peer comparison.</p>
      )}
      {tab === 'scorecard' && result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Internal grade</p>
              <p className="text-xl font-bold text-cascade-charcoal">{result.grade}</p>
              <p className="text-xs text-gray-400">{result.grade_description}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Total score</p>
              <p className="text-xl font-bold text-cascade-charcoal">{result.total_score.toFixed(1)} / 100</p>
              <p className="text-xs text-gray-400">Quantitative {result.quantitative_score.toFixed(1)}, qualitative {result.qualitative_score.toFixed(1)}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Indicative 1-year PD</p>
              <p className="text-xl font-bold text-cascade-charcoal">{(result.pd_1y * 100).toFixed(2)}%</p>
              <p className="text-xs text-gray-400">Mapped from grade; not calibrated</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Indicative limit</p>
              <p className="text-xl font-bold text-cascade-charcoal">USD {result.limit.proposed_limit.toLocaleString()} mn</p>
              <p className="text-xs text-gray-400">Review {result.review_frequency === 'annual' ? 'annually' : 'semi-annually'}</p>
            </div>
          </div>

          <div className="bg-white rounded-xl border p-4">
            <p className="text-sm"><span className="font-semibold">Recommendation:</span> {result.recommendation}</p>
          </div>

          <div className="bg-white rounded-xl border p-5">
            <h3 className="text-sm font-semibold text-gray-700 mb-1">Factor scores (0-100, weight in brackets)</h3>
            <p className="text-xs text-gray-500 mb-3">Green: strength (score {strength} or more). Red: concern (score {concern} or less). The dashed line marks the midpoint.</p>
            <ResponsiveContainer width="100%" height={chartData.length * 30 + 40}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" width={230} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value: number, _name, item: any) => [`${value.toFixed(0)} (${item.payload.display})`, 'Score']} />
                <ReferenceLine x={50} stroke="#78716c" strokeDasharray="4 4" />
                <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                  {chartData.map(entry => <Cell key={entry.label} fill={scoreColour(entry.score, strength, concern)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border rounded-xl overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-600"><tr>{['Factor', 'Type', 'Value', 'Score', 'Weight', 'Contribution'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
              <tbody>{result.factors.map(factor => (
                <tr key={factor.key} className="border-t">
                  <td className="p-3 font-medium">{factor.label}</td>
                  <td className="p-3 capitalize text-gray-600">{factor.category}</td>
                  <td className="p-3">{factor.display_value}</td>
                  <td className="p-3">{factor.score.toFixed(1)}</td>
                  <td className="p-3">{factor.weight}%</td>
                  <td className="p-3">{factor.weighted_score.toFixed(2)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border p-5">
              <h3 className="text-sm font-semibold text-green-700 mb-2">Key strengths</h3>
              {result.strengths.length ? <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">{result.strengths.map(item => <li key={item}>{item}</li>)}</ul>
                : <p className="text-sm text-gray-500">No factor at or above the strength threshold.</p>}
            </div>
            <div className="bg-white rounded-xl border p-5">
              <h3 className="text-sm font-semibold text-red-700 mb-2">Key concerns</h3>
              {result.concerns.length ? <ul className="list-disc pl-5 text-sm text-gray-700 space-y-1">{result.concerns.map(item => <li key={item}>{item}</li>)}</ul>
                : <p className="text-sm text-gray-500">No factor at or below the concern threshold.</p>}
            </div>
          </div>

          {result.peer_comparison ? (
            <div className="bg-white border rounded-xl overflow-x-auto">
              <div className="p-4 border-b">
                <h3 className="text-sm font-semibold text-gray-700">Peer and sector comparison</h3>
                <p className="text-xs text-gray-500 mt-1">
                  Rank {result.peer_comparison.rank} of {result.peer_comparison.rank_out_of} by total score; peer median score {result.peer_comparison.peer_median_score.toFixed(1)}.
                  {' '}{result.peer_comparison.same_sector_peers} of {result.peer_comparison.peer_count} peers are in the same sector. Bundled peers are fictional sample data.
                </p>
              </div>
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-600"><tr>{['Metric', 'Counterparty', 'Peer median', 'Peers outperformed', 'Position'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                <tbody>{result.peer_comparison.metrics.map(metric => (
                  <tr key={metric.key} className="border-t">
                    <td className="p-3 font-medium">{metric.label}</td>
                    <td className="p-3">{metric.display_value}</td>
                    <td className="p-3">{metric.display_peer_median}</td>
                    <td className="p-3">{metric.peers_outperformed === null ? 'n/a' : `${metric.peers_outperformed} of ${metric.peer_count}`}</td>
                    <td className={`p-3 capitalize font-medium ${positionClass(metric.position)}`}>{metric.position}</td>
                  </tr>
                ))}</tbody>
              </table>
              <table className="w-full text-sm text-left border-t">
                <thead className="bg-gray-50 text-gray-600"><tr>{['Peer', 'Country', 'Sector', 'Score', 'Grade'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
                <tbody>{result.peer_comparison.peers.map(peer => (
                  <tr key={peer.name} className="border-t">
                    <td className="p-3 font-medium">{peer.name}</td>
                    <td className="p-3">{peer.country || ''}</td>
                    <td className="p-3">{peer.sector || ''}</td>
                    <td className="p-3">{peer.total_score.toFixed(1)}</td>
                    <td className="p-3">{peer.grade}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p className="text-sm text-gray-500">No peer set was used for this run.</p>}
        </div>
      )}

      {/* Credit review */}
      {tab === 'review' && !review && <p className="text-sm text-gray-500">Run the scorecard to generate a credit review draft.</p>}
      {tab === 'review' && review && (
        <div className="bg-white border rounded-xl p-5 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-semibold text-cascade-charcoal">{review.title}</h3>
              <p className="text-xs text-gray-500 mt-1">{review.note} Generated by fixed templates from the scorecard numbers.</p>
            </div>
            <button onClick={copyReview} className="px-3 py-2 border rounded-lg text-sm font-medium flex items-center gap-2 hover:bg-gray-50 shrink-0">
              <Copy size={15} /> Copy
            </button>
          </div>
          {review.sections.map(section => (
            <div key={section.title}>
              <h4 className="text-sm font-semibold text-gray-700">{section.title}</h4>
              <p className="text-sm text-gray-700 mt-1 leading-relaxed">{section.body}</p>
            </div>
          ))}
        </div>
      )}

      {/* Due diligence */}
      {tab === 'diligence' && !checklist && <p className="text-sm text-gray-500">Loading checklist...</p>}
      {tab === 'diligence' && checklist && (
        <div className="space-y-4">
          <div className={`border rounded-xl p-4 flex items-center gap-3 ${assessment ? statusClass : 'bg-white text-gray-600'}`}>
            <ClipboardCheck size={18} className="shrink-0" />
            <div className="text-sm">
              {assessment ? (
                <>
                  <p className="font-semibold">{assessment.status_label}</p>
                  <p>{assessment.completed_items} of {assessment.total_items} items closed ({assessment.completeness_pct}%); {assessment.mandatory_outstanding.length} of {assessment.mandatory_total} mandatory items outstanding; {assessment.issues.length} open issue(s).</p>
                </>
              ) : <p>Onboarding checklist for a {TYPES.find(item => item.id === type)?.label.toLowerCase()} in {checklist.country_name}. Set item states to see approval readiness.</p>}
            </div>
          </div>
          {checklistGroups.map(([category, items]) => (
            <div key={category} className="bg-white border rounded-xl">
              <h3 className="text-sm font-semibold text-gray-700 p-4 border-b">{category}</h3>
              {items.map(item => (
                <div key={item.id} className="flex items-start justify-between gap-4 p-4 border-b last:border-b-0">
                  <p className="text-sm text-gray-700">
                    {item.text}
                    {item.mandatory && <span className="ml-2 text-xs font-medium text-cascade-gold">Mandatory</span>}
                  </p>
                  <select
                    aria-label={`State: ${item.text}`}
                    value={itemStates[item.id] || 'pending'}
                    onChange={event => changeItemState(item.id, event.target.value as DueDiligenceState)}
                    className="border rounded-lg px-2 py-1.5 text-sm shrink-0"
                  >
                    {checklist.states.map(state => <option key={state} value={state}>{STATE_LABELS[state]}</option>)}
                  </select>
                </div>
              ))}
            </div>
          ))}
          <p className="text-xs text-gray-500">{checklist.note} A mandatory item must be complete; it cannot be marked not applicable.</p>
        </div>
      )}

      {/* Methodology */}
      {tab === 'methodology' && methodology && scorecardSpec && (
        <div className="space-y-4">
          <div className="bg-white border rounded-xl p-5 space-y-2 text-sm text-gray-700">
            <p>{methodology.summary}</p>
            <p>{methodology.limit_rule}</p>
            <p className="text-xs text-gray-500">{methodology.disclaimer}</p>
          </div>
          <div className="bg-white border rounded-xl overflow-x-auto">
            <h3 className="text-sm font-semibold text-gray-700 p-4 border-b">Internal rating scale</h3>
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-600"><tr>{['Grade', 'Description', 'Score band', 'Indicative 1-year PD', 'Review', 'Limit % of base'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
              <tbody>{methodology.rating_scale.map((row, index) => (
                <tr key={row.grade} className="border-t">
                  <td className="p-3 font-medium">{row.grade}</td>
                  <td className="p-3">{row.description}</td>
                  <td className="p-3">{index === 0 ? `${row.min_score} to ${row.max_score}` : `${row.min_score} to below ${row.max_score}`}</td>
                  <td className="p-3">{(row.pd_1y * 100).toFixed(2)}%</td>
                  <td className="p-3">{row.review_frequency === 'annual' ? 'Annual' : 'Semi-annual'}</td>
                  <td className="p-3">{(row.limit_pct_of_base * 100).toFixed(0)}%</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="bg-white border rounded-xl overflow-x-auto">
            <h3 className="text-sm font-semibold text-gray-700 p-4 border-b">{scorecardSpec.label} scorecard factors</h3>
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-50 text-gray-600"><tr>{['Factor', 'Weight', 'Formula or basis', 'Weak anchor (score 0)', 'Strong anchor (score 100)'].map(label => <th key={label} className="p-3 whitespace-nowrap">{label}</th>)}</tr></thead>
              <tbody>
                {scorecardSpec.quantitative_factors.map(factor => (
                  <tr key={factor.key} className="border-t align-top">
                    <td className="p-3 font-medium">{factor.label}</td>
                    <td className="p-3">{factor.weight}%</td>
                    <td className="p-3 font-mono text-xs">{factor.formula}</td>
                    <td className="p-3">{factor.weak_anchor}</td>
                    <td className="p-3">{factor.strong_anchor}</td>
                  </tr>
                ))}
                {scorecardSpec.qualitative_factors.map(factor => (
                  <tr key={factor.key} className="border-t align-top">
                    <td className="p-3 font-medium">{factor.label}</td>
                    <td className="p-3">{factor.weight}%</td>
                    <td className="p-3 text-xs">{factor.description}</td>
                    <td className="p-3">1</td>
                    <td className="p-3">5</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
