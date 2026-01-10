import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { useAppVersion } from '../hooks/useAppVersion';
import { getLocalApiUrl } from '../lib/api';

export default function Header() {
  const version = useAppVersion();

  return (
    <header className="h-12 bg-cascade-soft-white border-b border-cascade-mist flex items-center justify-between px-4">
      <div />
      <div className="flex items-center gap-3">
        {/* API Status indicator */}
        <ApiStatusIndicator />

        {/* Version */}
        <span className="text-[11px] text-cascade-sage/60">v{version}</span>
      </div>
    </header>
  );
}

function ApiStatusIndicator() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${getLocalApiUrl()}/health`, {
          signal: AbortSignal.timeout(3000),
        });
        setStatus(res.ok ? 'online' : 'offline');
      } catch {
        setStatus('offline');
      }
    };
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  if (status === 'checking') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-cascade-sage">
        <RefreshCw size={12} className="animate-spin" />
        <span className="hidden sm:inline">Connecting...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 text-[11px]" role="status" title={getLocalApiUrl()}>
      <span className={`w-2 h-2 rounded-full ${status === 'online' ? 'bg-semantic-success' : 'bg-semantic-danger'} animate-pulse`} />
      <span className={`hidden sm:inline ${status === 'online' ? 'text-semantic-success' : 'text-semantic-danger'}`}>
        {status === 'online' ? 'API connected' : 'API unavailable'}
      </span>
    </div>
  );
}
