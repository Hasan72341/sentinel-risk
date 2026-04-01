// API clients and types for Asia market data, regional reference data,
// framework compliance checks and region-aware benchmarking.
import { getApiClient } from './api';
import type { CountryCode } from './region';

// ---------------------------------------------------------------------------
// Asia markets (live data from an unofficial source; can be unavailable)
// ---------------------------------------------------------------------------

export type LiveStatus = 'live' | 'unavailable';
export type BoardStatus = 'live' | 'partial' | 'unavailable';

interface QuoteFields {
  status: LiveStatus;
  /** Present when status is "unavailable". */
  message?: string;
  error?: string;
  /** Present only when status is "live". */
  price?: number;
  previous_close?: number | null;
  change?: number | null;
  change_pct?: number | null;
  currency?: string | null;
  exchange?: string | null;
  timezone?: string | null;
  day_high?: number | null;
  day_low?: number | null;
  fifty_two_week_high?: number | null;
  fifty_two_week_low?: number | null;
  volume?: number | null;
  as_of?: string | null;
}

export interface IndexRow extends QuoteFields {
  country: CountryCode;
  name: string;
  symbol: string;
  optional: boolean;
  market_name?: string;
  sparkline?: number[];
}

export interface FxRow extends QuoteFields {
  country: CountryCode;
  pair: string;
  symbol: string;
  sparkline?: number[];
}

interface BoardBase {
  status: BoardStatus;
  source: string;
  fetched_at: string;
  live_count: number;
  total_count: number;
  message?: string;
  error?: string;
}

export interface IndexBoard extends BoardBase { indices: IndexRow[] }
export interface FxBoard extends BoardBase { rates: FxRow[] }

export interface PriceBar {
  date: string;
  timestamp: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

export type QuoteRange = '5d' | '1mo' | '3mo' | '6mo' | '1y' | '2y' | '5y';
export const QUOTE_RANGES: QuoteRange[] = ['1mo', '3mo', '6mo', '1y', '2y', '5y'];

export interface TickerQuote extends QuoteFields {
  symbol: string;
  range: QuoteRange;
  interval: string;
  source: string;
  name?: string | null;
  instrument_type?: string | null;
  history?: PriceBar[];
}

export async function getAsiaIndices(): Promise<IndexBoard> {
  const client = await getApiClient();
  const { data } = await client.get('/asia-markets/indices');
  return data;
}

export async function getAsiaFx(): Promise<FxBoard> {
  const client = await getApiClient();
  const { data } = await client.get('/asia-markets/fx');
  return data;
}

export async function getAsiaQuote(symbol: string, range: QuoteRange = '6mo'): Promise<TickerQuote> {
  const client = await getApiClient();
  const { data } = await client.get('/asia-markets/quote', { params: { symbol, range } });
  return data;
}

// ---------------------------------------------------------------------------
// Regional reference data
// ---------------------------------------------------------------------------

export interface RegionalCountry {
  code: CountryCode;
  name: string;
  currency: { code: string; name: string; symbol: string; minor_units: number };
  locale: string;
  number_grouping: { style: string; description: string; units: { name: string; value: number }[] };
  fiscal_year: { start_month: number; end_month: number; description: string };
  accounting: { primary_framework: string; framework_id: string; description: string; alternatives: string[] };
  regulators: { short_name: string; name: string; role: string }[];
  exchanges: { short_name: string; name: string; yahoo_suffix: string }[];
  indices: { name: string; symbol: string }[];
  fx_symbol: string;
  market: { timezone: string; timezone_label: string; sessions: [string, string][]; lunch_break: boolean };
}

export interface MarketStatus {
  country: CountryCode;
  name: string;
  related_index?: string;
  status: 'open' | 'break' | 'closed';
  is_open: boolean;
  reason: string;
  local_time: string;
  weekday: string;
  timezone: string;
  timezone_label: string;
  sessions: [string, string][];
  note: string;
}

export async function getRegionalCountries(): Promise<{ reporting_currency: string; countries: RegionalCountry[] }> {
  const client = await getApiClient();
  const { data } = await client.get('/regional/countries');
  return data;
}

export async function getMarketStatus(): Promise<{ markets: MarketStatus[] }> {
  const client = await getApiClient();
  const { data } = await client.get('/regional/market-status');
  return data;
}

// ---------------------------------------------------------------------------
// Compliance (presentation and consistency checks)
// ---------------------------------------------------------------------------

export type FrameworkId = 'IFRS' | 'IND_AS' | 'CAS' | 'JGAAP' | 'KIFRS';
export type CheckStatus = 'pass' | 'fail' | 'not_applicable';
export type CheckSeverity = 'blocking' | 'warning' | 'info';
export type FrameworkReportStatus = 'compliant' | 'needs_attention' | 'non_compliant' | 'insufficient_data';

export interface Framework {
  id: FrameworkId;
  name: string;
  jurisdiction: string;
  issuer: string;
  equity_statement: string;
  notes: string[];
}

export interface FrameworkCheck {
  check_id: string;
  category: string;
  standard: string;
  severity: CheckSeverity;
  rule: string;
}

export interface FrameworkCheckResult extends FrameworkCheck {
  status: CheckStatus;
  message: string;
  remediation?: string;
}

export interface FrameworkComplianceReport {
  framework: Framework;
  framework_notes: string[];
  compliance_score: number;
  total_checks: number;
  passed: number;
  failed: number;
  not_applicable: number;
  critical_issues: string[];
  warnings: string[];
  info_items: string[];
  status: FrameworkReportStatus;
  results: FrameworkCheckResult[];
  recommendations: { priority: 'critical' | 'high' | 'medium'; title: string; description: string }[];
  tolerance_pct: number;
  simplified: boolean;
  disclaimer: string;
}

export interface FrameworkCatalogue {
  frameworks: Framework[];
  checks: FrameworkCheck[];
  disclosure_items: { id: string; label: string }[];
  disclaimer: string;
}

export interface FrameworkCheckRequest {
  framework: FrameworkId;
  financial_data: Record<string, number>;
  prior_period?: Record<string, number>;
  disclosures?: Record<string, boolean>;
  statements_present?: string[];
  tolerance_pct?: number;
}

export async function getComplianceFrameworks(): Promise<FrameworkCatalogue> {
  const client = await getApiClient();
  const { data } = await client.get('/compliance/frameworks');
  return data;
}

export async function runFrameworkCheck(request: FrameworkCheckRequest): Promise<FrameworkComplianceReport> {
  const client = await getApiClient();
  const { data } = await client.post('/compliance/check', request);
  return data;
}

// ---------------------------------------------------------------------------
// Benchmarking (illustrative sector profiles)
// ---------------------------------------------------------------------------

export type BenchmarkRank = 'excellent' | 'above_average' | 'below_average' | 'poor';

export interface SectorOption { id: string; name: string; ratio_count: number }
export interface BenchmarkRegion { id: CountryCode; name: string; tilt_rationale: string }

export interface SectorCatalogue {
  industries: SectorOption[];
  regions: BenchmarkRegion[];
  illustrative: boolean;
  disclaimer: string;
}

export interface SectorRatioInput { ratio_name: string; value: number; unit?: string }

export interface SectorComparison {
  ratio_name: string;
  label: string;
  unit: 'fraction' | 'x';
  lower_is_better: boolean;
  company_value: number;
  industry_median: number;
  industry_p25: number;
  industry_p75: number;
  percentile: number;
  rank: BenchmarkRank;
  deviation_pct: number;
}

export interface SectorBenchmarkResult {
  industry_id: string;
  industry_name: string;
  region: CountryCode;
  region_name: string;
  overall_score: number;
  overall_rank: BenchmarkRank | 'not_scored';
  ratios_compared: number;
  comparisons: SectorComparison[];
  strengths: string[];
  weaknesses: string[];
  unmatched_ratios: string[];
  tilt_rationale: string;
  illustrative: boolean;
  disclaimer: string;
}

export interface SectorProfile {
  sector_id: string;
  sector_name: string;
  region: CountryCode;
  region_name: string;
  ratios: Record<string, { label: string; unit: 'fraction' | 'x'; lower_is_better: boolean; p25: number; median: number; p75: number }>;
  tilt_rationale: string;
  illustrative: boolean;
  disclaimer: string;
}

export async function getSectorCatalogue(): Promise<SectorCatalogue> {
  const client = await getApiClient();
  const { data } = await client.get('/benchmarking/industries');
  return data;
}

export async function getSectorProfile(sectorId: string, region: CountryCode): Promise<SectorProfile> {
  const client = await getApiClient();
  const { data } = await client.get('/benchmarking/profile', { params: { industry_id: sectorId, region } });
  return data;
}

export async function compareSectorBenchmark(
  companyName: string,
  ratios: SectorRatioInput[],
  sectorId: string,
  region: CountryCode,
): Promise<SectorBenchmarkResult> {
  const client = await getApiClient();
  const { data } = await client.post('/benchmarking/compare', {
    company_name: companyName, ratios, industry_id: sectorId, region,
  });
  return data;
}

/** Error text from an API failure, preferring the server's detail message. */
export function apiErrorMessage(cause: unknown, fallback: string): string {
  const error = cause as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return error?.message || fallback;
}
