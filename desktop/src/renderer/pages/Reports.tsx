import { useEffect, useState } from 'react';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import { FileText, Download, Plus, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getAnalysisHistory, saveReport } from '../lib/api';
import { useToast } from '../components/Toast';
import { isSampleAnalysis } from '../lib/utils';

export default function Reports() {
  const { analyses, setAnalyses } = useAnalysisStore();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState<string | null>(null);
  const savedAnalyses = analyses.filter(item => !isSampleAnalysis(item.analysisId));

  const loadReports = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await getAnalysisHistory(1, 100);
      setAnalyses(response.data ?? []);
    } catch {
      setError('Saved analyses could not be loaded. Check the API connection and retry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadReports(); }, []);

  const handleExport = async (analysisId: string, companyName: string, period: string, format: 'pdf' | 'xlsx') => {
    if (isSampleAnalysis(analysisId)) {
      toast('warning', 'This is sample data. Upload a statement to export a report.');
      return;
    }
    setExporting(`${analysisId}:${format}`);
    try {
      const name = `${companyName.replace(/\s+/g, '_')}_${period}`;
      const filePath = await saveReport(analysisId, format, name);
      if (filePath) {
        toast('success', `${format.toUpperCase()} report saved successfully`);
      }
    } catch {
      toast('error', `Failed to generate ${format.toUpperCase()} report`);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="text-cascade-sage text-sm mt-1">Download the SEC filings study or export a saved statement analysis.</p>
        </div>
        <Link to="/analysis" className="btn-primary flex items-center gap-2">
          <Plus size={16} /> New Analysis
        </Link>
      </div>

      <Link to="/public-filings" className="card block border-l-4 border-cascade-gold hover:shadow-md transition-shadow">
        <h2 className="text-lg font-semibold">SEC filings study</h2>
        <p className="text-sm text-cascade-sage mt-2">Coca-Cola, PepsiCo and Keurig Dr Pepper · FY2022–2024 · information cutoff April 1, 2025.</p>
        <p className="text-sm mt-2">Financial statements, ratios, credit reviews and an Excel workbook with source references.</p>
        <span className="text-sm font-semibold mt-3 inline-flex items-center gap-2">Open filings and export <ArrowRight size={15} /></span>
      </Link>

      <h2 className="text-lg font-semibold">Saved analysis reports</h2>
      {loading ? <p role="status" className="text-sm text-cascade-sage">Loading saved analyses…</p> : error ? (
        <div role="alert" className="card text-sm">
          <p>{error}</p>
          <button onClick={loadReports} className="btn-secondary mt-3">Retry reports</button>
        </div>
      ) : savedAnalyses.length === 0 ? (
        <div className="card text-center py-16">
          <FileText size={48} className="mx-auto text-cascade-mist mb-4" />
          <h3 className="text-base font-semibold mb-2">No saved statement analyses</h3>
          <p className="text-sm text-cascade-sage max-w-sm mx-auto mb-6">
            Complete a financial analysis first, then export a report in PDF or Excel format.
          </p>
          <Link to="/analysis" className="btn-primary inline-flex items-center gap-2">
            <Plus size={16} /> Start Analysis
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {savedAnalyses.map((item) => (
            <div key={item.analysisId} className="card flex items-center justify-between py-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-cascade-gold/10 flex items-center justify-center shrink-0">
                  <FileText size={16} className="text-cascade-gold" />
                </div>
                <div>
                  <p className="font-medium text-sm">
                    {item.companyName || 'Untitled Report'}
                  </p>
                  <p className="text-xs text-cascade-sage">{item.period}</p>
                </div>
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => handleExport(item.analysisId, item.companyName, item.period, 'pdf')}
                  disabled={exporting !== null}
                  aria-label={`Export ${item.companyName || 'analysis'} as PDF`}
                  className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
                >
                  <Download size={12} /> {exporting === `${item.analysisId}:pdf` ? 'Exporting…' : 'PDF'}
                </button>
                <button
                  onClick={() => handleExport(item.analysisId, item.companyName, item.period, 'xlsx')}
                  disabled={exporting !== null}
                  aria-label={`Export ${item.companyName || 'analysis'} as XLSX`}
                  className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5"
                >
                  <Download size={12} /> {exporting === `${item.analysisId}:xlsx` ? 'Exporting…' : 'XLSX'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
