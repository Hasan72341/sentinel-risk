import { getApiClient } from './api';

// Risk Methodology desk: VaR backtesting, stress testing, economic capital
// and model performance monitoring. All models are simplified, for analysis
// and learning; they are not regulatory calculations.

export type VarMethod = 'historical' | 'parametric';
export type RiskType = 'equity' | 'rates' | 'credit' | 'fx';
export type Market = 'India' | 'China' | 'Japan' | 'South Korea';
export type TrafficLightZone = 'green' | 'yellow' | 'red';
export type MonitoringStatus = 'green' | 'amber' | 'red';

export interface RiskFactor {
  id: string;
  label: string;
  risk_type: RiskType;
  market: Market;
  unit: '%' | 'bp';
  liquidity_horizon: number;
}

export interface FactorPosition {
  factor_id: string;
  sensitivity: number;
}

export interface TestResult {
  statistic: number;
  p_value: number;
}

export interface KupiecResult extends TestResult {
  observed_rate: number;
  expected_rate: number;
}

export interface IndependenceResult extends TestResult {
  pi01: number;
  pi11: number;
  n00: number;
  n01: number;
  n10: number;
  n11: number;
}

export interface TrafficLight {
  zone: TrafficLightZone;
  n_exceptions: number;
  n_obs: number;
  confidence: number;
  cumulative_probability: number;
  plus_factor: number | null;
  standard_setting: boolean;
}

export interface ExpectedShortfallBucket {
  liquidity_horizon_days: number;
  factors: string[];
  es_base_horizon: number;
}

export interface ExpectedShortfallSummary {
  confidence: number;
  method: VarMethod;
  n_obs: number;
  var_1d: number;
  es_1d: number;
  es_base_horizon: number;
  base_horizon_days: number;
  liquidity_adjusted_es: number | null;
  buckets: ExpectedShortfallBucket[];
  note: string;
}

export interface BacktestPoint {
  date: string;
  pnl: number;
  var: number;
  es: number;
  exception: boolean;
}

export interface BacktestException {
  date: string;
  index: number;
  pnl: number;
  var: number;
  excess: number;
  loss_to_var: number | null;
}

export interface SamplePortfolioInfo {
  name: string;
  currency: string;
  seed: number;
  disclaimer: string;
}

export interface BacktestSummary {
  method: VarMethod;
  confidence: number;
  window: number;
  n_obs: number;
  n_exceptions: number;
  expected_exceptions: number;
  exception_rate: number;
  kupiec: KupiecResult;
  independence: IndependenceResult;
  conditional_coverage: TestResult;
  traffic_light: TrafficLight;
}

export interface BacktestResult extends BacktestSummary {
  expected_shortfall: ExpectedShortfallSummary;
  series: BacktestPoint[];
  exceptions: BacktestException[];
  disclaimer: string;
  portfolio?: SamplePortfolioInfo;
}

export interface BacktestRequest {
  pnl?: number[];
  dates?: string[];
  factor_pnl?: Record<string, number[]>;
  confidence?: number;
  window?: number;
  method?: VarMethod;
  es_confidence?: number;
  seed?: number;
  days?: number;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  shocks: Record<string, number>;
  illustrative?: boolean;
}

export interface ScenarioLibrary {
  factors: RiskFactor[];
  scenarios: Scenario[];
  sample_portfolio: { name: string; currency: string; positions: FactorPosition[]; disclaimer: string };
  disclaimer: string;
}

export interface FactorPnl {
  factor_id: string;
  label: string;
  risk_type: RiskType;
  market: Market;
  unit: '%' | 'bp';
  shock: number;
  sensitivity: number;
  pnl: number;
}

export interface ScenarioOutcome {
  total_pnl: number;
  by_risk_type: Record<RiskType, number>;
  by_market: Record<Market, number>;
  by_factor: FactorPnl[];
}

export interface ScenarioResult extends ScenarioOutcome {
  id: string;
  name: string;
  description: string;
  source: 'library' | 'custom';
  shocks: Record<string, number>;
}

export interface StressResult {
  results: ScenarioResult[];
  worst_scenario: { id: string; name: string; total_pnl: number };
  using_sample_portfolio: boolean;
  disclaimer: string;
}

export interface CustomScenario {
  name: string;
  description?: string;
  shocks: Record<string, number>;
}

export interface ReverseStressResult {
  reachable: boolean;
  loss_threshold: number;
  base_pnl: number;
  multiplier: number | null;
  scaled_shocks: Record<string, number>;
  scaled: ScenarioOutcome | null;
  finding: string;
}

export interface CreditExposureInput {
  name: string;
  market?: string;
  ead: number;
  pd: number;
  lgd: number;
}

export interface EconomicCapitalRequest {
  market_annual_vol?: number;
  credit_exposures?: CreditExposureInput[];
  asset_correlation?: number;
  operational_expected_loss?: number;
  operational_sigma?: number;
  correlations?: Record<string, number>;
  confidence?: number;
  simulations?: number;
  seed?: number;
}

export interface EconomicCapitalRow {
  risk_type: 'market' | 'credit' | 'operational';
  expected_loss: number;
  loss_quantile: number;
  unexpected_loss: number;
  share_of_undiversified_pct: number;
  allocated_capital: number;
}

export interface EconomicCapitalResult {
  confidence: number;
  simulations: number;
  seed: number;
  horizon: string;
  currency: string;
  inputs: {
    market_annual_vol: number;
    asset_correlation: number;
    operational_expected_loss: number;
    operational_sigma: number;
    correlations: Record<string, number>;
    credit_exposures: CreditExposureInput[];
    using_sample_exposures: boolean;
  };
  breakdown: EconomicCapitalRow[];
  total: { expected_loss: number; loss_quantile: number; unexpected_loss: number };
  economic_capital: number;
  diversification: { undiversified: number; diversified: number; benefit: number; benefit_pct: number };
  histogram: { loss: number; count: number }[];
  disclaimer: string;
}

export interface ExceptionDriver {
  factor_id: string;
  label: string;
  risk_type: string;
  market: string;
  pnl: number;
  share_of_loss_pct: number | null;
}

export interface MonitoredException extends BacktestException {
  drivers: ExceptionDriver[];
}

export interface StabilityPeriod {
  start: string;
  end: string;
  n_obs: number;
  n_exceptions: number;
  exception_rate: number;
  mean_var: number;
}

export interface ModelMonitoringReport {
  status: MonitoringStatus;
  status_reasons: string[];
  findings: string[];
  summary: BacktestSummary;
  clustering: {
    consecutive_pairs: number;
    max_in_window: number;
    cluster_window_days: number;
    mean_gap_days: number | null;
    min_gap_days: number | null;
  };
  largest_breaches: MonitoredException[];
  exceptions: MonitoredException[];
  drivers: { available: boolean; top_risk_type_counts: Record<string, number> };
  mean_loss_to_var: number | null;
  stability: {
    mean_var: number;
    min_var: number;
    max_var: number;
    var_coefficient_of_variation: number | null;
    max_daily_var_change_pct: number | null;
    sub_periods: StabilityPeriod[];
  };
  series: BacktestPoint[];
  disclaimer: string;
  portfolio?: SamplePortfolioInfo;
}

const BASE = '/risk-methodology';

/** Readable message from an API failure (FastAPI puts it in `detail`). */
export function apiErrorMessage(cause: any, fallback: string): string {
  const detail = cause?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return cause?.message || fallback;
}

/** Omit `pnl` to backtest the bundled synthetic sample book. */
export async function runVarBacktest(request: BacktestRequest = {}): Promise<BacktestResult> {
  const client = await getApiClient();
  const { data } = await client.post(`${BASE}/var-backtest`, request);
  return data;
}

/** Omit `pnl` to report on the bundled synthetic sample book. */
export async function runModelMonitoring(request: BacktestRequest = {}): Promise<ModelMonitoringReport> {
  const client = await getApiClient();
  const { data } = await client.post(`${BASE}/model-monitoring`, request);
  return data;
}

export async function getScenarioLibrary(): Promise<ScenarioLibrary> {
  const client = await getApiClient();
  const { data } = await client.get(`${BASE}/stress/scenarios`);
  return data;
}

/** Omit `positions` to use the sample book; omit `scenarioIds` to run the whole library. */
export async function runStressTest(
  positions?: FactorPosition[],
  scenarioIds?: string[],
  customScenarios: CustomScenario[] = [],
): Promise<StressResult> {
  const client = await getApiClient();
  const { data } = await client.post(`${BASE}/stress/run`, {
    positions, scenario_ids: scenarioIds, custom_scenarios: customScenarios,
  });
  return data;
}

export async function runReverseStress(
  shocks: Record<string, number>,
  lossThreshold: number,
  positions?: FactorPosition[],
): Promise<ReverseStressResult> {
  const client = await getApiClient();
  const { data } = await client.post(`${BASE}/stress/reverse`, {
    positions, shocks, loss_threshold: lossThreshold,
  });
  return data;
}

export async function runEconomicCapital(request: EconomicCapitalRequest = {}): Promise<EconomicCapitalResult> {
  const client = await getApiClient();
  const { data } = await client.post(`${BASE}/economic-capital`, request);
  return data;
}

/** Compact amount formatting for cards, axes and tables, e.g. -$1.25m. */
export function formatAmount(value: number, digits = 2, symbol = '$'): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}${symbol}${(abs / 1e9).toFixed(digits)}bn`;
  if (abs >= 1e6) return `${sign}${symbol}${(abs / 1e6).toFixed(digits)}m`;
  if (abs >= 1e4) return `${sign}${symbol}${(abs / 1e3).toFixed(0)}k`;
  return `${sign}${symbol}${abs.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
}
