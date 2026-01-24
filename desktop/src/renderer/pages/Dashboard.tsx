import { useEffect, useState } from 'react';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import {
  BarChart3, FileText, Shield, Globe, Award, Gauge, ArrowRight, Sparkles, MessageSquareHeart,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { formatDate } from '../lib/utils';
import { getAnalysisHistory } from '../lib/api';

type DeskLink = { to: string; label: string };

type Desk = {
  title: string;
  summary: string;
  icon: React.ElementType;
  primary: DeskLink;
  links: DeskLink[];
};

const desks: Desk[] = [
  {
    title: 'Credit Risk',
    summary:
      'Review SEC filings or uploaded statements, compare financial ratios and inspect credit scorecard assumptions.',
    icon: Award,
    primary: { to: '/public-filings', label: 'Open Public Filings' },
    links: [
      { to: '/credit-rating', label: 'Illustrative Credit Rating' },
      { to: '/analysis', label: 'Statement Analysis' },
      { to: '/counterparty-monitor', label: 'Counterparty Monitor' },
      { to: '/benchmarking', label: 'Peer & Sector' },
      { to: '/prediction', label: 'Distress scores' },
      { to: '/compliance', label: 'Compliance' },
    ],
  },
  {
    title: 'Risk Methodology',
    summary:
      'Backtest VaR, compare stress scenarios and inspect model exceptions using uploaded inputs or labelled examples.',
    icon: Gauge,
    primary: { to: '/var-backtesting', label: 'Open VaR Backtesting' },
    links: [
      { to: '/stress-testing', label: 'Stress Testing & Capital' },
      { to: '/model-monitoring', label: 'Model Monitoring' },
      { to: '/financial-engineering', label: 'VaR & Pricing' },
      { to: '/time-series', label: 'Time Series' },
    ],
  },
  {
    title: 'Exposure Management',
    summary:
      'Inspect exposure and collateral, compare usage with assumed limits, and simulate potential exposure and initial margin.',
    icon: Shield,
    primary: { to: '/credit-exposure', label: 'Open Exposure Monitoring' },
    links: [
      { to: '/potential-exposure', label: 'Potential Exposure' },
      { to: '/initial-margin', label: 'Initial Margin' },
    ],
  },
];

const markets = [
  { code: 'IN', name: 'India', currency: 'INR' },
  { code: 'CN', name: 'China', currency: 'CNY' },
  { code: 'JP', name: 'Japan', currency: 'JPY' },
  { code: 'KR', name: 'South Korea', currency: 'KRW' },
];

export default function Dashboard() {
  const { analyses, setAnalyses } = useAnalysisStore();
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');

  // Load history on mount
  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setHistoryError('');
    try {
      const res = await getAnalysisHistory();
      setAnalyses(res.data ?? []);
    } catch {
      setHistoryError('Saved analyses could not be loaded. Check the API connection and retry.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Risk Workbench</h1>
          <p className="text-cascade-sage text-sm mt-1">
            Financial statements, exposure calculations and model diagnostics.
          </p>
        </div>
      </div>

      <Link to="/public-filings" className="card block border-l-4 border-cascade-gold hover:shadow-md transition-shadow">
        <p className="text-xs uppercase tracking-wide text-cascade-sage">Start with reported financials</p>
        <h2 className="text-lg font-semibold mt-2">Coca-Cola, PepsiCo and Keurig Dr Pepper</h2>
        <p className="text-sm mt-2">Nine annual statements · FY2022–2024 · ratios, peer comparisons and credit reviews linked to SEC filings. Information cutoff April 1, 2025.</p>
        <span className="text-sm font-semibold mt-3 inline-flex items-center gap-2">Review public filings <ArrowRight size={15} /></span>
      </Link>

      {/* Desk cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {desks.map(({ title, summary, icon: Icon, primary, links }) => (
          <section key={title} aria-label={title} className="card flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-cascade-gold/10 flex items-center justify-center shrink-0">
                <Icon size={20} className="text-cascade-gold" />
              </div>
              <h2 className="text-lg font-semibold">{title}</h2>
            </div>
            <p className="text-sm text-cascade-sage">{summary}</p>
            <ul className="space-y-1.5 flex-1">
              {links.map((link) => (
                <li key={link.to}>
                  <Link to={link.to} className="text-sm font-medium text-cascade-charcoal hover:text-cascade-gold transition-colors inline-flex items-center gap-1.5">
                    <ArrowRight size={12} className="text-cascade-gold" />
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
            <Link to={primary.to} className="btn-primary text-center">{primary.label}</Link>
          </section>
        ))}
      </div>

      {/* Markets shortcut */}
      <div className="card flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-cascade-gold/10 flex items-center justify-center shrink-0">
            <Globe size={20} className="text-cascade-gold" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Markets</h2>
            <p className="text-sm text-cascade-sage mt-1">
              Index and FX quotes for India, China, Japan and South Korea. Quote timestamps and provider availability are shown on the market board.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {markets.map((m) => (
                <span key={m.code} className="rounded-full bg-cascade-mist/60 px-2.5 py-1 text-xs font-medium text-cascade-charcoal">
                  {m.name} <span className="text-cascade-sage">{m.currency}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4 shrink-0">
          <Link to="/sentiment" className="text-sm font-semibold text-cascade-gold hover:text-cascade-gold-hover inline-flex items-center gap-1.5">
            <MessageSquareHeart size={14} /> News sentiment
          </Link>
          <Link to="/ai-copilot" className="text-sm font-semibold text-cascade-gold hover:text-cascade-gold-hover inline-flex items-center gap-1.5">
            <Sparkles size={14} /> AI Copilot
          </Link>
          <Link to="/asia-markets" className="btn-primary whitespace-nowrap">Open Asia Markets</Link>
        </div>
      </div>

      {/* Evidence-first entry point */}
      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Statement review</h2>
            <p className="mt-1 text-sm text-cascade-sage">Inspect source documents, resolve findings, then continue to statement analysis.</p>
          </div>
          <Link to="/analysis" className="btn-primary">Start evidence review</Link>
        </div>
        <div className="card flex items-start gap-3 border-cascade-gold/30 bg-cascade-gold/5 p-5">
          <Shield size={20} className="mt-0.5 shrink-0 text-cascade-gold" />
          <p className="text-sm text-cascade-sage">
            Review extracted PDF facts and source citations, or map columns from CSV and Excel statements before calculating ratios.
          </p>
        </div>
      </div>

      {/* Recent Analyses */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Recent Statement Analyses</h2>
          <Link to="/history" className="text-sm text-cascade-gold hover:text-cascade-gold-hover font-medium">
            View all
          </Link>
        </div>

        {loading ? <p role="status" className="text-sm text-cascade-sage">Loading saved analyses…</p> : historyError ? (
          <div role="alert" className="card text-sm">
            <p>{historyError}</p>
            <button onClick={loadHistory} className="btn-secondary mt-3">Retry history</button>
          </div>
        ) : analyses.length === 0 ? (
          <div className="card text-center py-12">
            <BarChart3 size={48} className="mx-auto text-cascade-mist mb-4" />
            <h3 className="text-base font-semibold mb-2">No analyses yet</h3>
            <p className="text-sm text-cascade-sage max-w-sm mx-auto">
              Upload a CSV, Excel or PDF financial statement to see your first analysis here.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {analyses.slice(0, 5).map((item) => (
              <Link
                key={item.analysisId}
                to={`/analysis/${item.analysisId}`}
                className="card flex items-center justify-between hover:shadow-elevated transition-shadow group py-4"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-cascade-gold/10 flex items-center justify-center shrink-0">
                    <FileText size={16} className="text-cascade-gold" />
                  </div>
                  <div>
                    <p className="font-medium text-sm group-hover:text-cascade-gold transition-colors">
                      {item.companyName || 'Unnamed Analysis'}
                    </p>
                    <p className="text-xs text-cascade-sage">{item.period}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-xs text-cascade-sage whitespace-nowrap">{formatDate(item.createdAt)}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
