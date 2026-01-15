import axios from 'axios';
import { isDesktop, readFileBuffer, saveFile, writeFile } from './desktop';
import type { AnalysisResult, AnalysisHistoryItem, RatioResult, UserPreferences, LicenseInfo, ApiResponse, AIConfig, EvidenceInspectionResult, DocumentExtractResult, ConsolidatedCompany, ConsolidationResult, ARIMAResult, GARCHResult, VaRResult, MonteCarloResult, BlackScholesResult, PortfolioOptResult, BacktestDemoResult, SingleBacktestResult, PortfolioBacktestResult } from '../../types';
import { adaptAdvOptDemo, adaptCausalDemo, adaptNetworkDemo, adaptStochasticDemo } from './demoAdapters';
import type { AdvOptDemoView, CausalDemoView, NetworkDemoView, StochasticDemoView } from './demoAdapters';

let apiClient: ReturnType<typeof axios.create> | null = null;

export async function getApiClient(): Promise<ReturnType<typeof axios.create>> {
  if (!apiClient) {
    const baseUrl = getLocalApiUrl();
    apiClient = axios.create({
      baseURL: baseUrl,
      timeout: 60000,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  return apiClient;
}

// Paths from the native file picker are read by the desktop shell;
// blob: and http(s): URLs (drag & drop, browser mode) are fetched directly.
function isNativePath(filePath: string): boolean {
  return isDesktop && !/^(blob|https?|data):/i.test(filePath);
}

async function buildUploadFormData(filePath: string, mappingOverrides?: Record<string, string | null>): Promise<FormData> {
  let blob: Blob;
  let fileName: string;

  if (isNativePath(filePath)) {
    const fileInfo = await readFileBuffer(filePath);
    const buffer = Uint8Array.from(atob(fileInfo.buffer), (c) => c.charCodeAt(0));
    blob = new Blob([buffer], { type: fileInfo.mimeType });
    fileName = fileInfo.name;
  } else {
    const response = await fetch(filePath);
    blob = await response.blob();
    fileName = filePath.split(/[\\/]/).pop() || 'statement.csv';
  }

  const formData = new FormData();
  formData.append('file', blob, fileName);
  if (mappingOverrides) formData.append('mapping_overrides', JSON.stringify(mappingOverrides));
  return formData;
}

export async function inspectEvidence(
  filePath: string,
  mappingOverrides?: Record<string, string | null>,
): Promise<ApiResponse<EvidenceInspectionResult>> {
  try {
    const client = await getApiClient();
    const formData = await buildUploadFormData(filePath, mappingOverrides);
    const { data } = await client.post('/evidence/inspect', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return { data };
  } catch (error: any) {
    return { error: { code: 'EVIDENCE_INSPECTION_FAILED', message: error.response?.data?.detail || error.message || 'Evidence inspection failed', details: null } };
  }
}

// The analysis, license and settings endpoints return flat snake_case JSON.
// These mappers convert it to the camelCase shapes the renderer uses.
function apiError(error: any, code: string, fallback: string): ApiResponse<never> {
  const detail = error?.response?.data?.detail;
  return { error: { code, message: (typeof detail === 'string' ? detail : null) || error?.message || fallback, details: null } };
}

function toRatio(raw: any): RatioResult {
  return {
    category: raw.category,
    ratioName: raw.ratio_name,
    value: raw.value,
    unit: raw.unit,
    benchmark: raw.benchmark ?? null,
    status: raw.status,
  };
}

function toAnalysis(raw: any): AnalysisResult {
  return {
    analysisId: raw.analysis_id,
    companyName: raw.company_name ?? '',
    period: raw.period ?? '',
    fileName: raw.file_name ?? '',
    createdAt: raw.created_at,
    ratios: (raw.ratios ?? []).map(toRatio),
  };
}

function toHistoryItem(raw: any): AnalysisHistoryItem {
  const summary = raw.summary ?? {};
  return {
    analysisId: raw.analysis_id,
    companyName: raw.company_name ?? '',
    period: raw.period ?? '',
    fileName: raw.file_name ?? '',
    createdAt: raw.created_at,
    summary: {
      profitability: summary.profitability ?? 0,
      liquidity: summary.liquidity ?? 0,
      leverage: summary.leverage ?? 0,
      efficiency: summary.efficiency ?? 0,
    },
  };
}

function toPreferences(raw: any): UserPreferences {
  return {
    defaultLanguage: 'en',
    chartTheme: raw.chart_theme === 'dark' ? 'dark' : 'light',
    decimalPlaces: raw.decimal_places ?? 2,
    autoSave: raw.auto_save ?? true,
  };
}

export async function uploadAndAnalyze(filePath: string): Promise<ApiResponse<AnalysisResult>> {
  try {
    const client = await getApiClient();
    const formData = await buildUploadFormData(filePath);
    const { data } = await client.post('/analysis/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return { data: toAnalysis(data) };
  } catch (error: any) {
    return apiError(error, 'ANALYSIS_FAILED', 'Analysis failed');
  }
}

export async function getAnalysisHistory(page = 1, perPage = 20): Promise<ApiResponse<AnalysisHistoryItem[]>> {
  const client = await getApiClient();
  const { data } = await client.get('/analysis/history', { params: { page, per_page: perPage } });
  return { data: (Array.isArray(data) ? data : []).map(toHistoryItem) };
}

export async function getAnalysisById(id: string): Promise<ApiResponse<AnalysisResult>> {
  const client = await getApiClient();
  const { data } = await client.get(`/analysis/${id}`);
  return { data: toAnalysis(data) };
}

export async function deleteAnalysis(id: string): Promise<ApiResponse<null>> {
  const client = await getApiClient();
  await client.delete(`/analysis/${id}`);
  return { data: null };
}

export type ReportFormat = 'pdf' | 'xlsx';

// The backend returns the report file itself (PDF or XLSX bytes).
export async function generateReport(analysisId: string, format: ReportFormat): Promise<Blob> {
  const client = await getApiClient();
  const { data } = await client.post('/reports/generate', { analysis_id: analysisId, format }, {
    responseType: 'blob',
  });
  return data;
}

// Desktop: writes to the location chosen in the save dialog and returns that path.
// Browser: triggers a download and returns the file name. Null if the dialog is cancelled.
export async function saveReport(analysisId: string, format: ReportFormat, suggestedName: string): Promise<string | null> {
  const fileName = `${suggestedName}.${format}`;
  if (!isDesktop) {
    const blob = await generateReport(analysisId, format);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    link.click();
    URL.revokeObjectURL(url);
    return fileName;
  }
  const filePath = await saveFile(fileName);
  if (!filePath) return null;
  await writeFile(filePath, await generateReport(analysisId, format));
  return filePath;
}

export async function validateLicense(key: string): Promise<ApiResponse<LicenseInfo>> {
  try {
    const client = await getApiClient();
    const { data } = await client.post('/license/validate', { key });
    return {
      data: {
        valid: Boolean(data.valid),
        tier: data.tier ?? 'free',
        expiresAt: data.expires_at ?? null,
        features: data.features ?? [],
      },
    };
  } catch {
    return { error: { code: 'NETWORK_ERROR', message: 'Cannot connect to license server', details: null } };
  }
}

export async function getPreferences(): Promise<ApiResponse<UserPreferences>> {
  try {
    const client = await getApiClient();
    const { data } = await client.get('/settings/preferences');
    return { data: toPreferences(data) };
  } catch {
    return { data: { defaultLanguage: 'en', chartTheme: 'light', decimalPlaces: 2, autoSave: true } };
  }
}

export async function updatePreferences(prefs: UserPreferences): Promise<ApiResponse<UserPreferences>> {
  const client = await getApiClient();
  const { data } = await client.put('/settings/preferences', {
    default_language: prefs.defaultLanguage,
    chart_theme: prefs.chartTheme,
    decimal_places: prefs.decimalPlaces,
    auto_save: prefs.autoSave,
  });
  return { data: toPreferences(data) };
}

export function getLocalApiUrl(): string {
  return 'http://127.0.0.1:8000/api/v1';
}

export async function getAIConfig(): Promise<AIConfig> {
  const client = await getApiClient();
  const { data } = await client.get('/ai/configure');
  return data;
}

export async function configureAI(apiKey: string, endpoint: string, model: string): Promise<{ status: string; model: string }> {
  const client = await getApiClient();
  const { data } = await client.post('/ai/configure', { api_key: apiKey, api_endpoint: endpoint, model });
  return data;
}

export async function runPrediction(analysisId: string): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/prediction/from-analysis', { analysis_id: analysisId });
  return data;
}

// Document Intelligence
export async function extractFromPDF(file: File | Blob, forceOcr = false): Promise<DocumentExtractResult> {
  const client = await getApiClient();
  const formData = new FormData();
  formData.append('file', file);
  formData.append('force_ocr', String(forceOcr));
  const { data } = await client.post('/document-intelligence/extract-pdf', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function extractFromImage(file: File | Blob): Promise<DocumentExtractResult> {
  const client = await getApiClient();
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post('/document-intelligence/extract-image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function extractFromExcel(file: File | Blob): Promise<DocumentExtractResult> {
  const client = await getApiClient();
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await client.post('/document-intelligence/extract-excel', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function extractFromText(text: string): Promise<DocumentExtractResult> {
  const client = await getApiClient();
  const { data } = await client.post('/document-intelligence/extract-text', { text });
  return data;
}

// Consolidation
export async function consolidateCompanies(companies: ConsolidatedCompany[]): Promise<ConsolidationResult> {
  const client = await getApiClient();
  const { data } = await client.post('/consolidation/consolidate', { companies });
  // The backend names the field ratio_name; the shared RatioResult type uses ratioName.
  const ratios = (data.ratios ?? []).map((ratio: Record<string, unknown>) => ({
    ...ratio,
    ratioName: ratio.ratioName ?? ratio.ratio_name ?? '',
  }));
  return { ...data, ratios };
}

// Time Series
export async function runTimeSeriesFull(prices: number[], forecastSteps = 30): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/time-series/full', { prices, forecast_steps: forecastSteps });
  return data;
}

export async function runARIMA(prices: number[], forecastSteps = 30): Promise<ARIMAResult> {
  const client = await getApiClient();
  const { data } = await client.post('/time-series/arima', { prices, forecast_steps: forecastSteps });
  return data;
}

export async function runGARCH(prices: number[]): Promise<GARCHResult> {
  const client = await getApiClient();
  const { data } = await client.post('/time-series/garch', { prices });
  return data;
}

// Financial Engineering
export async function calculateVaR(prices: number[], confidence = 0.95, method = 'historical', positionValue = 1000000): Promise<VaRResult> {
  const client = await getApiClient();
  const { data } = await client.post('/financial-engineering/var', { prices, confidence, method, position_value: positionValue });
  return data;
}

export async function runMonteCarlo(s0: number, mu: number, sigma: number, days = 252, simulations = 10000): Promise<MonteCarloResult> {
  const client = await getApiClient();
  const { data } = await client.post('/financial-engineering/monte-carlo', { s0, mu, sigma, days, simulations });
  return data;
}

export async function runBlackScholes(spot: number, strike: number, time: number, rate: number, volatility: number, optionType = 'call'): Promise<BlackScholesResult> {
  const client = await getApiClient();
  const { data } = await client.post('/financial-engineering/black-scholes', { spot, strike, time, rate, volatility, option_type: optionType });
  return data;
}

export async function optimizePortfolio(expectedReturns: number[], covMatrix: number[][], riskFreeRate = 0): Promise<PortfolioOptResult> {
  const client = await getApiClient();
  const { data } = await client.post('/financial-engineering/portfolio-optimize', { expected_returns: expectedReturns, cov_matrix: covMatrix, risk_free_rate: riskFreeRate });
  return data;
}

// Backtesting
export async function runBacktestStrategy(
  prices: number[],
  signals?: number[],
  initialCapital = 1000000,
  commission = 0.001,
  slippage = 0.0005,
  benchmarkPrices?: number[],
  strategyName = 'Strategy',
): Promise<SingleBacktestResult> {
  const client = await getApiClient();
  const { data } = await client.post('/backtest/strategy', {
    prices, signals, initial_capital: initialCapital,
    commission, slippage, benchmark_prices: benchmarkPrices, strategy_name: strategyName,
  });
  return data;
}

export async function runBacktestPortfolio(
  assetPrices: number[][],
  weights?: number[],
  rebalanceDays = 21,
  initialCapital = 10000000,
  benchmarkPrices?: number[],
  assetNames?: string[],
): Promise<PortfolioBacktestResult> {
  const client = await getApiClient();
  const { data } = await client.post('/backtest/portfolio', {
    asset_prices: assetPrices, weights, rebalance_days: rebalanceDays,
    initial_capital: initialCapital, benchmark_prices: benchmarkPrices, asset_names: assetNames,
  });
  return data;
}

export async function getBacktestDemo(): Promise<BacktestDemoResult> {
  const client = await getApiClient();
  const { data } = await client.get('/backtest/demo');
  return data;
}

// Fuzzy MCDM
export async function runFuzzyAHP(criteriaMatrix: number[][], criteriaNames: string[]): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/fuzzy-mcdm/ahp', { criteria_matrix: criteriaMatrix, criteria_names: criteriaNames });
  return data;
}

export async function runFuzzyTOPSIS(
  decisionMatrix: number[][], criteriaNames: string[], alternativeNames: string[],
  criteriaWeights: number[], benefitCriteria?: boolean[],
): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/fuzzy-mcdm/topsis', {
    decision_matrix: decisionMatrix, criteria_names: criteriaNames,
    alternative_names: alternativeNames, criteria_weights: criteriaWeights, benefit_criteria: benefitCriteria,
  });
  return data;
}

export async function getFuzzyMCDDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/fuzzy-mcdm/demo');
  return data;
}

// Factor Analysis
export async function runPCA(returnsMatrix: number[][], assetNames?: string[], nComponents?: number): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/factor-analysis/pca', { returns_matrix: returnsMatrix, asset_names: assetNames, n_components: nComponents });
  return data;
}

export async function runFamaFrench(
  returnsMatrix: number[][], marketReturns: number[],
  assetNames?: string[], marketCap?: number[], bookToMarket?: number[],
): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/factor-analysis/fama-french', {
    returns_matrix: returnsMatrix, market_returns: marketReturns,
    asset_names: assetNames, market_cap: marketCap, book_to_market: bookToMarket,
  });
  return data;
}

export async function getFactorAnalysisDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/factor-analysis/demo');
  return data;
}

// Black-Litterman
export async function runBlackLitterman(
  marketCapWeights: number[], covarianceMatrix: number[][],
  riskAversion = 2.5, tau = 0.05, views?: { assets: number[]; value: number; confidence: number }[],
  riskFreeRate = 0,
): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/black-litterman/optimize', {
    market_cap_weights: marketCapWeights, covariance_matrix: covarianceMatrix,
    risk_aversion: riskAversion, tau, views, risk_free_rate: riskFreeRate,
  });
  return data;
}

export async function getBlackLittermanDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/black-litterman/demo');
  return data;
}

// Sentiment Analysis
export async function analyzeSentiment(texts: string[], labels?: string[], weights?: number[]): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/sentiment/analyze', { texts, labels, weights });
  return data;
}

export async function analyzeStockSentiment(symbol: string, newsTexts: string[], socialTexts?: string[]): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.post('/sentiment/stock', { symbol, news_texts: newsTexts, social_texts: socialTexts });
  return data;
}

export async function getSentimentDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/sentiment/demo');
  return data;
}

// Stochastic Calculus
export async function getStochasticDemo(): Promise<StochasticDemoView> {
  const client = await getApiClient();
  const { data } = await client.get('/stochastic-calculus/demo');
  return adaptStochasticDemo(data);
}

// Network Analysis
export async function getNetworkDemo(): Promise<NetworkDemoView> {
  const client = await getApiClient();
  const { data } = await client.get('/network-analysis/demo');
  return adaptNetworkDemo(data);
}

// Causal Inference
export async function getCausalDemo(): Promise<CausalDemoView> {
  const client = await getApiClient();
  const { data } = await client.get('/causal-inference/demo');
  return adaptCausalDemo(data);
}

// Reinforcement Learning
export async function getRLDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/reinforcement-learning/demo');
  return data;
}

// Fuzzy Neural
export async function getFuzzyNeuralDemo(): Promise<any> {
  const client = await getApiClient();
  const { data } = await client.get('/fuzzy-neural/demo');
  return data;
}

// Advanced Optimization
export async function getAdvOptDemo(): Promise<AdvOptDemoView> {
  const client = await getApiClient();
  const { data } = await client.get('/advanced-optimization/demo');
  return adaptAdvOptDemo(data);
}
