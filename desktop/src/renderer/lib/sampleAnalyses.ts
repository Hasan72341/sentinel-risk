import type { AnalysisHistoryItem, AnalysisResult, RatioResult } from '../../types';

// Illustrative sample analyses with invented figures for fictional companies.
// Retained for explicit legacy /analysis/demo-* links only, never saved history.
// Their fixed dates describe the examples, not current company results.
export const SAMPLE_ANALYSES: AnalysisHistoryItem[] = [
  {
    analysisId: 'demo-001',
    companyName: 'Acme Corporation (sample)',
    period: 'FY 2024',
    fileName: 'acme_income_2024.xlsx',
    createdAt: '2024-12-15T10:30:00Z',
    summary: { profitability: 78, liquidity: 85, leverage: 62, efficiency: 71 },
  },
  {
    analysisId: 'demo-002',
    companyName: 'Globex Example Industries (sample)',
    period: 'Q3 2024',
    fileName: 'globex_q3_2024.csv',
    createdAt: '2024-11-28T14:20:00Z',
    summary: { profitability: 65, liquidity: 72, leverage: 45, efficiency: 88 },
  },
  {
    analysisId: 'demo-003',
    companyName: 'Pinnacle Example Holdings (sample)',
    period: 'FY 2023',
    fileName: 'pinnacle_annual_2023.xlsx',
    createdAt: '2024-10-05T09:15:00Z',
    summary: { profitability: 42, liquidity: 58, leverage: 80, efficiency: 55 },
  },
];

const SAMPLE_RATIOS: RatioResult[] = [
  { category: 'profitability', ratioName: 'Gross Profit Margin', value: 0.42, unit: '%', benchmark: 0.38, status: 'good' },
  { category: 'profitability', ratioName: 'Net Profit Margin', value: 0.18, unit: '%', benchmark: 0.12, status: 'good' },
  { category: 'profitability', ratioName: 'Return on Assets', value: 0.14, unit: '%', benchmark: 0.10, status: 'good' },
  { category: 'profitability', ratioName: 'Return on Equity', value: 0.22, unit: '%', benchmark: 0.18, status: 'good' },
  { category: 'liquidity', ratioName: 'Current Ratio', value: 2.4, unit: 'x', benchmark: 2.0, status: 'good' },
  { category: 'liquidity', ratioName: 'Quick Ratio', value: 1.8, unit: 'x', benchmark: 1.5, status: 'good' },
  { category: 'liquidity', ratioName: 'Cash Ratio', value: 0.6, unit: 'x', benchmark: 0.5, status: 'good' },
  { category: 'leverage', ratioName: 'Debt to Equity', value: 1.8, unit: 'x', benchmark: 1.5, status: 'warning' },
  { category: 'leverage', ratioName: 'Debt to Assets', value: 0.65, unit: '%', benchmark: 0.50, status: 'critical' },
  { category: 'leverage', ratioName: 'Interest Coverage', value: 4.2, unit: 'x', benchmark: 3.0, status: 'good' },
  { category: 'efficiency', ratioName: 'Asset Turnover', value: 0.85, unit: 'x', benchmark: 0.80, status: 'good' },
  { category: 'efficiency', ratioName: 'Inventory Turnover', value: 6.3, unit: 'x', benchmark: 5.5, status: 'good' },
];

// Detail view for a sample analysis: every sample shares one illustrative ratio set.
export function sampleAnalysisDetail(analysisId: string): AnalysisResult | null {
  const item = SAMPLE_ANALYSES.find((sample) => sample.analysisId === analysisId);
  if (!item) return null;
  return {
    analysisId: item.analysisId,
    companyName: item.companyName,
    period: item.period,
    fileName: item.fileName,
    createdAt: item.createdAt,
    ratios: SAMPLE_RATIOS,
  };
}
