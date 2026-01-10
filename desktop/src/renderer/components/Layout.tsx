import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, BarChart3, FileText, History, Settings,
  ChevronLeft, ChevronRight, Menu, Sparkles, Activity,
  FileSearch, ShieldCheck, Merge, Globe, TrendingUp, Calculator, Target,
  BrainCircuit, Network, MessageSquareHeart, Layers, Scale,
  Waves, Brain, ArrowRightLeft, Sliders, Atom,
  Shield, Award, Users, Gauge, Flame, Radar, AreaChart, Coins,
} from 'lucide-react';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import Header from './Header';
import Titlebar from './Titlebar';
import { getAnalysisHistory, getPreferences } from '../lib/api';

type NavItem = { to: string; icon: React.ElementType; label: string };
type NavSection = { title: string; items: NavItem[] };

const navSections: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    ],
  },
  {
    title: 'Credit Risk',
    items: [
      { to: '/public-filings', icon: FileSearch, label: 'Public Filings' },
      { to: '/analysis', icon: BarChart3, label: 'Statement Analysis' },
      { to: '/credit-rating', icon: Award, label: 'Credit Rating' },
      { to: '/counterparty-monitor', icon: Users, label: 'Counterparty Monitor' },
      { to: '/benchmarking', icon: Scale, label: 'Peer & Sector' },
      { to: '/prediction', icon: Activity, label: 'Distress scores' },
      { to: '/document-intelligence', icon: FileSearch, label: 'Document extraction' },
      { to: '/compliance', icon: ShieldCheck, label: 'Compliance' },
      { to: '/consolidation', icon: Merge, label: 'Consolidation' },
    ],
  },
  {
    title: 'Risk Methodology',
    items: [
      { to: '/var-backtesting', icon: Gauge, label: 'VaR Backtesting' },
      { to: '/stress-testing', icon: Flame, label: 'Stress Testing' },
      { to: '/model-monitoring', icon: Radar, label: 'Model Monitoring' },
      { to: '/financial-engineering', icon: Calculator, label: 'VaR & Pricing' },
      { to: '/time-series', icon: TrendingUp, label: 'Time Series' },
    ],
  },
  {
    title: 'Exposure Management',
    items: [
      { to: '/credit-exposure', icon: Shield, label: 'Exposure Monitoring' },
      { to: '/potential-exposure', icon: AreaChart, label: 'Potential Exposure' },
      { to: '/initial-margin', icon: Coins, label: 'Initial Margin' },
    ],
  },
  {
    title: 'Markets',
    items: [
      { to: '/asia-markets', icon: Globe, label: 'Asia Markets' },
      { to: '/sentiment', icon: MessageSquareHeart, label: 'Sentiment' },
    ],
  },
  {
    title: 'Quant Lab',
    items: [
      { to: '/backtest', icon: Target, label: 'Strategy Backtest' },
      { to: '/factor-analysis', icon: Layers, label: 'Factor Analysis' },
      { to: '/black-litterman', icon: Scale, label: 'Black-Litterman' },
      { to: '/stochastic-calculus', icon: Waves, label: 'Stochastic' },
      { to: '/network-analysis', icon: Network, label: 'Network' },
      { to: '/causal-inference', icon: ArrowRightLeft, label: 'Causal' },
      { to: '/reinforcement-learning', icon: Brain, label: 'Reinforcement learning' },
      { to: '/fuzzy-mcdm', icon: BrainCircuit, label: 'Fuzzy MCDM' },
      { to: '/fuzzy-neural', icon: Atom, label: 'Fuzzy Neural' },
      { to: '/advanced-optimization', icon: Sliders, label: 'Adv. Optimisation' },
    ],
  },
  {
    title: 'Workspace',
    items: [
      { to: '/ai-copilot', icon: Sparkles, label: 'AI Copilot' },
      { to: '/reports', icon: FileText, label: 'Reports' },
      { to: '/history', icon: History, label: 'History' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

// A route is active on an exact match or on a child path ("/analysis/abc"),
// never on a sibling that merely shares a prefix.
function isActivePath(pathname: string, to: string): boolean {
  if (to === '/') return pathname === '/';
  return pathname === to || pathname.startsWith(`${to}/`);
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { sidebarOpen, toggleSidebar, setAnalyses } = useAnalysisStore();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  // Saved history comes only from the API. Example records are never inserted.
  useEffect(() => {
    getAnalysisHistory(1, 100).then((res) => {
      if (res.data) setAnalyses(res.data);
    }).catch(() => {
      // History pages show their own loading errors and retry controls.
    });
    getPreferences().then((res) => {
      if (res.data) useAnalysisStore.getState().setPreferences(res.data);
    });
  }, [setAnalyses]);

  return (
    <div className="flex h-screen overflow-hidden flex-col">
      <Titlebar />
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside
          className={`
            ${sidebarOpen ? 'w-56' : 'w-14'}
            bg-cascade-charcoal text-white
            flex flex-col transition-all duration-300
            shrink-0 hidden md:flex
          `}
        >
          {/* Logo */}
          <div className="h-12 flex items-center px-3 gap-2.5">
            <div className="w-7 h-7 bg-cascade-gold rounded-md flex items-center justify-center text-white font-bold text-xs shrink-0">
              S
            </div>
            {sidebarOpen && (
              <span className="font-bold text-sm tracking-tight whitespace-nowrap">
                Sentinel <span className="text-cascade-gold">Risk</span>
              </span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3">
            {navSections.map((section, index) => (
              <div key={section.title} role="group" aria-label={section.title}>
                {sidebarOpen ? (
                  <p className={`px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/30 ${index === 0 ? 'pt-0' : 'pt-4'}`}>
                    {section.title}
                  </p>
                ) : (
                  index > 0 && <div className="mx-2 my-2 border-t border-white/10" title={section.title} />
                )}
                <div className="space-y-0.5">
                  {section.items.map(({ to, icon: Icon, label }) => (
                    <NavLink
                      key={to}
                      to={to}
                      className={() => {
                        const isActive = isActivePath(location.pathname, to);
                        return `
                          flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium
                          transition-colors duration-150
                          ${isActive
                            ? 'text-cascade-gold bg-cascade-gold/10'
                            : 'text-white/40 hover:text-white hover:bg-white/5'
                          }
                          ${!sidebarOpen ? 'justify-center' : ''}
                        `;
                      }}
                      title={!sidebarOpen ? `${section.title}: ${label}` : undefined}
                    >
                      <Icon size={18} />
                      {sidebarOpen && <span className="whitespace-nowrap">{label}</span>}
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>

          {/* Collapse toggle */}
          <div className="px-2 pb-3">
            <button
              onClick={toggleSidebar}
              aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
              className="w-full p-2 rounded-lg text-white/30 hover:text-white hover:bg-white/5 transition-colors"
            >
              {sidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
            </button>
          </div>
        </aside>

        {/* Mobile menu button */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={mobileMenuOpen}
          className="md:hidden fixed top-10 left-3 z-50 p-2 rounded-lg bg-cascade-charcoal text-white"
        >
          <Menu size={18} />
        </button>

        {/* Mobile overlay */}
        {mobileMenuOpen && (
          <div
            className="md:hidden fixed inset-0 bg-black/50 z-40"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Mobile sidebar */}
        <aside
          className={`
            md:hidden fixed left-0 top-9 bottom-0 w-56 bg-cascade-charcoal text-white
            flex flex-col z-40 transition-transform duration-300
            ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          `}
        >
          <div className="h-12 flex items-center px-3 gap-2.5">
            <div className="w-7 h-7 bg-cascade-gold rounded-md flex items-center justify-center text-white font-bold text-xs">S</div>
            <span className="font-bold text-sm tracking-tight">Sentinel <span className="text-cascade-gold">Risk</span></span>
          </div>
          <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3">
            {navSections.map((section, index) => (
              <div key={section.title} role="group" aria-label={section.title}>
                <p className={`px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/30 ${index === 0 ? 'pt-0' : 'pt-4'}`}>
                  {section.title}
                </p>
                <div className="space-y-0.5">
                  {section.items.map(({ to, icon: Icon, label }) => (
                    <NavLink
                      key={to}
                      to={to}
                      onClick={() => setMobileMenuOpen(false)}
                      className={() => {
                        const isActive = isActivePath(location.pathname, to);
                        return `flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 ${
                          isActive ? 'text-cascade-gold bg-cascade-gold/10' : 'text-white/40 hover:text-white hover:bg-white/5'
                        }`;
                      }}
                    >
                      <Icon size={18} />
                      <span>{label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <div className="flex-1 overflow-y-auto p-6 scrollbar-thin bg-cascade-stone">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
