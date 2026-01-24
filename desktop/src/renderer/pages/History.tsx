import { useEffect, useState } from 'react';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import { FileText, Trash2, BarChart3 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { formatDate } from '../lib/utils';
import { getAnalysisHistory, deleteAnalysis } from '../lib/api';
import { useToast } from '../components/Toast';

export default function History() {
  const { analyses, setAnalyses } = useAnalysisStore();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await getAnalysisHistory(1, 100);
      setAnalyses(res.data ?? []);
    } catch {
      setError('Saved analyses could not be loaded. Check the API connection and retry.');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();

    setDeleting(id);
    try {
      await deleteAnalysis(id);
      setAnalyses(useAnalysisStore.getState().analyses.filter((a) => a.analysisId !== id));
      toast('success', 'Analysis deleted');
    } catch {
      toast('error', 'Analysis could not be deleted. It remains in your history.');
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="page-header">
        <div>
          <h1 className="page-title">Analysis History</h1>
          <p className="text-cascade-sage text-sm mt-1">Saved statement analyses, most recent first. Showing up to 100 records.</p>
        </div>
        {!loading && !error && <span className="text-sm text-cascade-sage bg-cascade-mist/50 px-3 py-1 rounded-full">{analyses.length} saved</span>}
      </div>

      {loading ? <p role="status" className="text-sm text-cascade-sage">Loading saved analyses…</p> : error ? (
        <div role="alert" className="card text-sm">
          <p>{error}</p>
          <button onClick={loadHistory} className="btn-secondary mt-3">Retry history</button>
        </div>
      ) : analyses.length === 0 ? (
        <div className="card text-center py-16">
          <BarChart3 size={48} className="mx-auto text-cascade-mist mb-4" />
          <h3 className="text-base font-semibold mb-2">No history yet</h3>
          <p className="text-sm text-cascade-sage max-w-sm mx-auto">
            Upload a statement to create a saved analysis, or open the SEC filings study.
          </p>
          <Link to="/public-filings" className="btn-secondary inline-flex mt-4">Review public filings</Link>
        </div>
      ) : (
        <div className="space-y-2">
          {analyses.map((item) => (
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
                    {item.companyName || 'Untitled Analysis'}
                  </p>
                  <p className="text-xs text-cascade-sage">{item.period} · {item.fileName}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {item.summary && (
                  <div className="hidden sm:flex gap-2">
                    {(['profitability', 'liquidity', 'leverage', 'efficiency'] as const).map((key) => {
                      const score = item.summary![key];
                      return (
                        <div key={key} className="flex items-center gap-1">
                          <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: score >= 70 ? '#16a34a' : score >= 50 ? '#d97706' : '#dc2626' }} />
                          <span className="text-[11px] text-cascade-sage capitalize">{key.slice(0, 4)}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                <span className="text-xs text-cascade-sage whitespace-nowrap">{formatDate(item.createdAt)}</span>
                <button
                  onClick={(e) => handleDelete(e, item.analysisId)}
                  aria-label={`Delete ${item.companyName || 'analysis'}`}
                  disabled={deleting !== null}
                  className="p-1.5 rounded-lg text-cascade-sage hover:text-semantic-danger hover:bg-semantic-danger/10 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
