// API client and types for the Credit Risk Exposure Management desk:
// daily exposure monitoring, potential future exposure and initial margin.
import { getApiClient } from './api';

// ---------------------------------------------------------------------------
// Daily exposure monitoring
// ---------------------------------------------------------------------------

export interface ExposurePosition {
  counterparty: string;
  current_mtm: number;
  previous_mtm: number;
  collateral: number;
  previous_collateral: number;
  credit_limit: number;
  required_margin: number;
  previous_required_margin?: number | null;
  currency?: string | null;
  country?: string | null;
  client_type?: string | null;
}

export type LimitBreachStatus = 'none' | 'opened' | 'ongoing' | 'closed';
export type MarginStatus = 'none' | 'call_triggered' | 'deficit_outstanding' | 'cured';

export interface ExposureRow {
  counterparty: string;
  country: string | null;
  client_type: string | null;
  currency: string | null;
  current_mtm: number;
  exposure: number;
  collateral: number;
  net_exposure: number;
  previous_net_exposure: number;
  day_change: number;
  mtm_change: number;
  collateral_change: number;
  credit_limit: number;
  limit_utilization_pct: number;
  limit_breach: number;
  limit_breach_flag: boolean;
  limit_breach_status: LimitBreachStatus;
  margin_requirement: number;
  margin_excess: number;
  margin_shortfall: number;
  margin_call_flag: boolean;
  margin_status: MarginStatus;
  net_exposure_reporting: number;
  day_change_reporting: number;
  commentary: string;
}

export interface ExposureCountryBucket {
  country: string;
  clients: number;
  net_exposure: number;
  day_change: number;
}

export interface ExposureSummary {
  reporting_currency: string | null;
  clients: number;
  gross_exposure: number;
  collateral: number;
  net_exposure: number;
  previous_net_exposure: number;
  day_change: number;
  margin_requirement: number;
  margin_deficit: number;
  limit_breach_amount: number;
  limit_breach_count: number;
  limit_breaches_opened: number;
  limit_breaches_closed: number;
  margin_call_count: number;
  margin_calls_triggered: number;
  largest_mover: string | null;
  by_country: ExposureCountryBucket[];
  commentary: string;
}

export type BreachSeverity = 'critical' | 'high' | 'medium' | 'watch';

export interface BreachItem {
  counterparty: string;
  country: string | null;
  currency: string | null;
  reporting_currency: string | null;
  type: 'limit_breach' | 'margin_deficit' | 'limit_watch';
  severity: BreachSeverity;
  status: 'new' | 'ongoing' | 'watch';
  amount: number;
  amount_reporting: number;
  pct: number;
  detail: string;
  action: string;
}

export interface ExposureBookReview {
  results: ExposureRow[];
  summary: ExposureSummary;
  breaches: BreachItem[];
}

export interface SampleExposureBook {
  positions: ExposurePosition[];
  fx_rates: Record<string, number>;
  reporting_currency: string;
  unit: string;
  disclaimer: string;
}

export async function reviewExposureBook(
  positions: ExposurePosition[],
  reportingCurrency?: string,
  fxRates?: Record<string, number>,
): Promise<ExposureBookReview> {
  const client = await getApiClient();
  const { data } = await client.post('/credit-exposure/review', {
    positions,
    reporting_currency: reportingCurrency || null,
    fx_rates: fxRates ?? null,
  });
  return data;
}

export async function getSampleExposureBook(): Promise<SampleExposureBook> {
  const client = await getApiClient();
  const { data } = await client.get('/credit-exposure/sample-book');
  return data;
}

// ---------------------------------------------------------------------------
// Shared margin-model types
// ---------------------------------------------------------------------------

export type RiskProduct = 'equity' | 'bond' | 'irs' | 'cds' | 'equity_option' | 'fx';

export const PRODUCT_LABELS: Record<RiskProduct, string> = {
  equity: 'Equity',
  bond: 'Bond',
  irs: 'Interest rate swap',
  cds: 'Credit default swap',
  equity_option: 'Equity option',
  fx: 'FX',
};

export const PRODUCT_SIDES: Record<RiskProduct, { value: string; label: string }[]> = {
  equity: [{ value: 'long', label: 'Long' }, { value: 'short', label: 'Short' }],
  fx: [{ value: 'long', label: 'Long foreign currency' }, { value: 'short', label: 'Short foreign currency' }],
  bond: [{ value: 'long', label: 'Long' }, { value: 'short', label: 'Short' }],
  equity_option: [{ value: 'long', label: 'Bought' }, { value: 'short', label: 'Sold' }],
  irs: [{ value: 'pay_fixed', label: 'Pay fixed' }, { value: 'receive_fixed', label: 'Receive fixed' }],
  cds: [{ value: 'buy_protection', label: 'Buy protection' }, { value: 'sell_protection', label: 'Sell protection' }],
};

/** What the historical series must contain for each product. */
export const PRODUCT_SERIES_HINT: Record<RiskProduct, string> = {
  equity: 'price or index levels',
  equity_option: 'prices of the underlying',
  fx: 'exchange rate levels',
  bond: 'yields in percent (7.10 = 7.10%)',
  irs: 'swap rates in percent (6.50 = 6.50%)',
  cds: 'spreads in basis points',
};

export interface MarginPosition {
  product: RiskProduct;
  side?: string;
  notional: number;
  label?: string;
  duration?: number;
  strike?: number;
  expiry_years?: number;
  volatility?: number;
  rate?: number;
  option_type?: 'call' | 'put';
}

export interface SampleSeriesInfo {
  name: string;
  label: string;
  product: RiskProduct;
  kind: 'price' | 'rate';
}

export interface SampleSeries extends SampleSeriesInfo {
  series: number[];
  stressed_episode: { start_index: number; end_index: number };
  disclaimer: string;
}

export async function listSampleSeries(): Promise<SampleSeriesInfo[]> {
  const client = await getApiClient();
  const { data } = await client.get('/margin-models/sample-series');
  return data.series;
}

export async function getSampleSeries(name: string, observations = 750): Promise<SampleSeries> {
  const client = await getApiClient();
  const { data } = await client.get(`/margin-models/sample-series/${encodeURIComponent(name)}`, { params: { observations } });
  return data;
}

// ---------------------------------------------------------------------------
// Historical market data analysis
// ---------------------------------------------------------------------------

export interface WorstMove {
  horizon_days: number;
  observations: number;
  worst_down: number;
  worst_down_start_index: number;
  worst_down_end_index: number;
  worst_up: number;
  worst_up_start_index: number;
  worst_up_end_index: number;
  quantile_1pct: number;
  quantile_99pct: number;
}

export interface MarketDataAnalysis {
  kind: 'price' | 'rate';
  unit: string;
  observations: number;
  first: number;
  last: number;
  minimum: number;
  maximum: number;
  mean_daily_move: number;
  daily_volatility: number;
  annualised_volatility: number;
  window: number;
  returns: number[];
  rolling_volatility: (number | null)[];
  worst_moves: WorstMove[];
}

export async function analyzeMarketData(series: number[], kind: 'price' | 'rate', window = 20): Promise<MarketDataAnalysis> {
  const client = await getApiClient();
  const { data } = await client.post('/margin-models/market-data/analyze', { series, kind, window });
  return data;
}

// ---------------------------------------------------------------------------
// Initial margin
// ---------------------------------------------------------------------------

export interface InitialMarginPositionResult {
  label: string;
  product: RiskProduct;
  side: string;
  notional: number;
  reference_level: number;
  observations: number;
  scenarios: number;
  daily_volatility: number;
  volatility_unit: string;
  sensitivity: number;
  historical_im: number;
  parametric_im: number;
  worst_scenario_pnl: number;
}

export interface InitialMarginResult {
  mpor_days: number;
  confidence: number;
  lookback: number | null;
  positions: InitialMarginPositionResult[];
  portfolio: {
    scenarios: number;
    historical_im: number;
    parametric_im: number;
    standalone_historical_im: number;
    standalone_parametric_im: number;
    historical_diversification_benefit: number;
    parametric_diversification_benefit: number;
    worst_scenario_pnl: number;
  };
  method_note: string;
}

export interface CalibrationRow {
  label: string;
  calibration: 'lookback' | 'full' | 'ewma' | 'stressed';
  start_index: number;
  end_index: number;
  daily_moves: number;
  daily_volatility: number;
  annualised_volatility: number;
  parametric_im: number;
  historical_im: number | null;
}

export interface CalibrationResult {
  product: RiskProduct;
  side: string;
  notional: number;
  mpor_days: number;
  confidence: number;
  reference_level: number;
  sensitivity: number;
  volatility_unit: string;
  rows: CalibrationRow[];
  method_note: string;
}

export interface BacktestPoint {
  index: number;
  im: number;
  realised_pnl: number;
  exception: boolean;
}

export interface MarginBacktestResult {
  product: RiskProduct;
  method: 'historical' | 'parametric';
  mpor_days: number;
  confidence: number;
  lookback: number;
  non_overlapping: boolean;
  observations: number;
  exceptions: number;
  exception_rate: number;
  expected_rate: number;
  expected_exceptions: number;
  average_im: number;
  max_im: number;
  worst_excess_loss: number;
  binomial_p_value: number | null;
  verdict: string;
  points: BacktestPoint[];
  method_note: string;
}

export interface MarginSettings {
  mporDays: number;
  confidence: number;
}

export async function calculateInitialMargin(
  positions: (MarginPosition & { series: number[] })[],
  settings: MarginSettings,
  lookback?: number | null,
): Promise<InitialMarginResult> {
  const client = await getApiClient();
  const { data } = await client.post('/margin-models/initial-margin', {
    positions, mpor_days: settings.mporDays, confidence: settings.confidence, lookback: lookback ?? null,
  });
  return data;
}

export async function compareMarginCalibrations(
  position: MarginPosition,
  series: number[],
  settings: MarginSettings,
  options: { lookbacks?: number[]; ewmaLambda?: number; stressWindow?: number } = {},
): Promise<CalibrationResult> {
  const client = await getApiClient();
  const { data } = await client.post('/margin-models/initial-margin/calibration', {
    position, series, mpor_days: settings.mporDays, confidence: settings.confidence,
    lookbacks: options.lookbacks ?? [125, 250, 500],
    ewma_lambda: options.ewmaLambda ?? 0.94,
    stress_window: options.stressWindow ?? 250,
  });
  return data;
}

export async function backtestInitialMargin(
  position: MarginPosition,
  series: number[],
  settings: MarginSettings,
  options: { lookback?: number; method?: 'historical' | 'parametric'; nonOverlapping?: boolean } = {},
): Promise<MarginBacktestResult> {
  const client = await getApiClient();
  const { data } = await client.post('/margin-models/initial-margin/backtest', {
    position, series, mpor_days: settings.mporDays, confidence: settings.confidence,
    lookback: options.lookback ?? 250,
    method: options.method ?? 'historical',
    non_overlapping: options.nonOverlapping ?? false,
  });
  return data;
}

// ---------------------------------------------------------------------------
// Potential future exposure
// ---------------------------------------------------------------------------

export interface ExposureProfile {
  expected_exposure: number[];
  pfe: number[];
  peak_pfe: number;
  peak_pfe_time: number;
  epe: number;
  max_expected_exposure: number;
}

export interface PFEResult {
  product: RiskProduct;
  parameters: Record<string, number | string | null>;
  quantile: number;
  paths: number;
  seed: number | null;
  mpor_days: number;
  threshold: number;
  initial_margin: number;
  horizon_years: number;
  grid_step_years: number;
  times: number[];
  initial_value: number;
  expected_mtm: number[];
  uncollateralised: ExposureProfile;
  collateralised: ExposureProfile;
  model: string;
  simplifications: string[];
}

export interface PFERequest {
  product: RiskProduct;
  params: Record<string, number | string | null>;
  horizon_years?: number | null;
  quantile: number;
  paths: number;
  seed?: number | null;
  mpor_days: number;
  threshold: number;
  initial_margin: number;
}

export async function simulatePFE(request: PFERequest): Promise<PFEResult> {
  const client = await getApiClient();
  const { data } = await client.post('/margin-models/pfe', request);
  return data;
}

// ---------------------------------------------------------------------------
// Small shared helpers for the desk pages
// ---------------------------------------------------------------------------

/** Parse numbers separated by commas, whitespace or new lines. */
export function parseSeries(raw: string): number[] {
  const tokens = raw.split(/[\s,;]+/).filter(Boolean);
  const values = tokens.map(Number);
  const bad = tokens.find((_, i) => !Number.isFinite(values[i]));
  if (bad !== undefined) throw new Error(`"${bad}" is not a number`);
  return values;
}

export function formatAmount(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function apiErrorMessage(cause: any, fallback: string): string {
  const detail = cause?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item: any) => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`).join('; ');
  }
  return cause?.message || fallback;
}
