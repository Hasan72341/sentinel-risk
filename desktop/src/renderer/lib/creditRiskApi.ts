import { getApiClient } from './api';

export type CounterpartyType = 'corporate' | 'financial_institution' | 'fund';
export type CountryCode = 'IN' | 'CN' | 'JP' | 'KR';
export type ReviewFrequency = 'annual' | 'semi_annual';

export interface QualitativeInputs {
  business_profile: number;
  management_governance: number;
  sector_outlook: number;
  country: number;
}

export interface SampleCounterparty {
  name: string;
  counterparty_type: CounterpartyType;
  country: CountryCode;
  sector: string;
  financials: Record<string, number>;
  qualitative: QualitativeInputs;
}

export interface ScorecardInputField { key: string; label: string; group: string }

export interface QuantitativeFactorSpec {
  key: string;
  label: string;
  weight: number;
  weak_anchor: number;
  strong_anchor: number;
  format: 'pct' | 'x' | 'days' | 'usd_mn';
  formula: string;
  log_scale: boolean;
}

export interface QualitativeFactorSpec { key: keyof QualitativeInputs; label: string; weight: number; description: string }

export interface RatingScaleRow {
  grade: string;
  min_score: number;
  max_score: number;
  pd_1y: number;
  description: string;
  review_frequency: ReviewFrequency;
  limit_pct_of_base: number;
}

export interface RatingMethodology {
  summary: string;
  disclaimer: string;
  units: string;
  limit_rule: string;
  strength_threshold: number;
  concern_threshold: number;
  rating_scale: RatingScaleRow[];
  countries: { code: CountryCode; name: string; currency: string }[];
  scorecards: Record<CounterpartyType, {
    label: string;
    inputs: ScorecardInputField[];
    quantitative_factors: QuantitativeFactorSpec[];
    qualitative_factors: QualitativeFactorSpec[];
  }>;
}

export interface ScorecardFactor {
  key: string;
  label: string;
  category: 'quantitative' | 'qualitative';
  weight: number;
  value: number | null;
  display_value: string;
  higher_is_better: boolean;
  score: number;
  weighted_score: number;
}

export interface PeerMetric {
  key: string;
  label: string;
  value: number | null;
  display_value: string;
  peer_median: number | null;
  display_peer_median: string;
  peers_outperformed: number | null;
  peer_count: number;
  position: 'stronger' | 'weaker' | 'in line' | 'not comparable';
}

export interface PeerComparison {
  peer_count: number;
  same_sector_peers: number;
  peer_median_score: number;
  rank: number;
  rank_out_of: number;
  metrics: PeerMetric[];
  peers: { name: string; country: string | null; sector: string | null; total_score: number; grade: string }[];
}

export interface ScorecardResult {
  name: string;
  counterparty_type: CounterpartyType;
  counterparty_type_label: string;
  country: CountryCode;
  country_name: string;
  local_currency: string;
  sector: string;
  factors: ScorecardFactor[];
  total_score: number;
  quantitative_score: number;
  qualitative_score: number;
  grade: string;
  grade_description: string;
  pd_1y: number;
  strengths: string[];
  concerns: string[];
  recommendation: string;
  review_frequency: ReviewFrequency;
  limit: {
    capital_base: number;
    capital_base_label: string;
    limit_pct_of_base: number;
    proposed_limit: number;
    currency: string;
  };
  financials: Record<string, number>;
  disclaimer: string;
  peer_comparison: PeerComparison | null;
}

export interface CreditReviewDraft {
  title: string;
  note: string;
  sections: { title: string; body: string }[];
  text: string;
}

export interface ScoreRequest {
  counterparty_type: CounterpartyType;
  name: string;
  country: CountryCode;
  sector?: string;
  financials: Record<string, number>;
  qualitative: QualitativeInputs;
  peers?: Omit<SampleCounterparty, 'counterparty_type'>[];
  use_sample_peers?: boolean;
}

export type DueDiligenceState = 'pending' | 'complete' | 'not_applicable' | 'issue';

export interface DueDiligenceItem { id: string; category: string; text: string; mandatory: boolean }

export interface DueDiligenceChecklist {
  counterparty_type: CounterpartyType;
  country: CountryCode;
  country_name: string;
  states: DueDiligenceState[];
  items: DueDiligenceItem[];
  note: string;
}

export interface DueDiligenceAssessment {
  total_items: number;
  completed_items: number;
  completeness_pct: number;
  mandatory_total: number;
  mandatory_outstanding: string[];
  issues: string[];
  status: 'ready' | 'incomplete' | 'blocked';
  status_label: string;
  items: (DueDiligenceItem & { state: DueDiligenceState })[];
}

export interface PortfolioCounterparty {
  name: string;
  counterparty_type: CounterpartyType;
  country: CountryCode;
  rating: string;
  previous_rating?: string | null;
  review_frequency: ReviewFrequency;
  last_review_date: string;
  limit: number;
  utilisation: number;
}

export interface SamplePortfolio {
  as_of: string;
  currency: string;
  note: string;
  counterparties: PortfolioCounterparty[];
}

export interface MonitoredCounterparty {
  name: string;
  counterparty_type: CounterpartyType;
  counterparty_type_label: string;
  country: CountryCode;
  country_name: string;
  rating: string;
  previous_rating: string;
  migration_notches: number;
  migration: 'upgrade' | 'downgrade' | 'stable';
  review_frequency: ReviewFrequency;
  last_review_date: string;
  next_review_date: string;
  days_to_review: number;
  review_status: 'overdue' | 'due_soon' | 'current';
  limit: number;
  utilisation: number;
  utilisation_pct: number;
  headroom: number;
  limit_breach: number;
  watchlist: boolean;
  watchlist_flags: string[];
  priority_score: number;
  priority: 'High' | 'Medium' | 'Low' | 'None';
  actions: string[];
}

export interface PortfolioBreakdown { key: string; label: string; count: number; limit: number; utilisation: number }

export interface PortfolioReview {
  as_of: string;
  summary: {
    counterparties: number;
    total_limit: number;
    total_utilisation: number;
    utilisation_pct: number;
    reviews_overdue: number;
    reviews_due_soon: number;
    upgrades: number;
    downgrades: number;
    limit_breaches: number;
    watchlist: number;
    by_country: PortfolioBreakdown[];
    by_type: PortfolioBreakdown[];
  };
  counterparties: MonitoredCounterparty[];
  reviews_due: MonitoredCounterparty[];
  migrations: MonitoredCounterparty[];
  watchlist: MonitoredCounterparty[];
  actions: { name: string; priority: MonitoredCounterparty['priority']; priority_score: number; action: string }[];
  disclaimer: string;
}

export async function getRatingMethodology(): Promise<RatingMethodology> {
  const client = await getApiClient();
  const { data } = await client.get('/credit-rating/methodology');
  return data;
}

export async function getRatingSamples(): Promise<{ note: string; samples: Record<CounterpartyType, SampleCounterparty[]> }> {
  const client = await getApiClient();
  const { data } = await client.get('/credit-rating/samples');
  return data;
}

export async function scoreCounterparty(request: ScoreRequest): Promise<ScorecardResult> {
  const client = await getApiClient();
  const { data } = await client.post('/credit-rating/score', request);
  return data;
}

export async function generateCreditReview(request: ScoreRequest): Promise<{ scorecard: ScorecardResult; review: CreditReviewDraft }> {
  const client = await getApiClient();
  const { data } = await client.post('/credit-rating/review', request);
  return data;
}

export async function getDueDiligenceChecklist(counterpartyType: CounterpartyType, country: CountryCode): Promise<DueDiligenceChecklist> {
  const client = await getApiClient();
  const { data } = await client.get('/credit-rating/due-diligence', { params: { counterparty_type: counterpartyType, country } });
  return data;
}

export async function assessDueDiligence(
  counterpartyType: CounterpartyType,
  country: CountryCode,
  states: Record<string, DueDiligenceState>,
): Promise<DueDiligenceAssessment> {
  const client = await getApiClient();
  const { data } = await client.post('/credit-rating/due-diligence/assess', { counterparty_type: counterpartyType, country, states });
  return data;
}

export async function getSamplePortfolio(asOf?: string): Promise<SamplePortfolio> {
  const client = await getApiClient();
  const { data } = await client.get('/counterparty-monitor/sample', { params: asOf ? { as_of: asOf } : undefined });
  return data;
}

export async function reviewCounterpartyPortfolio(counterparties: PortfolioCounterparty[], asOf?: string): Promise<PortfolioReview> {
  const client = await getApiClient();
  const { data } = await client.post('/counterparty-monitor/review', { counterparties, as_of: asOf || null });
  return data;
}

export function apiErrorMessage(cause: any, fallback: string): string {
  const detail = cause?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item: any) => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('; ');
  }
  return cause?.message || fallback;
}
