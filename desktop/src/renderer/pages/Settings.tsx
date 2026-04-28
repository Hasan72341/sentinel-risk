import { useState, useEffect } from 'react';
import { useAnalysisStore } from '../hooks/useAnalysisStore';
import { useAppVersion } from '../hooks/useAppVersion';
import { Globe, Palette, Save, RotateCcw, Monitor, Settings2, Eye, EyeOff, CheckCircle, Circle } from 'lucide-react';
import { updatePreferences, getAIConfig, configureAI } from '../lib/api';
import { isDesktop } from '../lib/desktop';
import { useToast } from '../components/Toast';

const PROVIDERS = [
  { name: 'OpenAI', endpoint: 'https://api.openai.com/v1' },
  { name: 'DeepSeek', endpoint: 'https://api.deepseek.com/v1' },
  { name: 'OpenRouter', endpoint: 'https://openrouter.ai/api/v1' },
];

export default function Settings() {
  const { preferences, setPreferences } = useAnalysisStore();
  const { toast } = useToast();
  const version = useAppVersion();
  const [saved, setSaved] = useState(false);
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiProvider, setAiProvider] = useState(PROVIDERS[0].endpoint);
  const [customEndpoint, setCustomEndpoint] = useState('');
  const [aiModel, setAiModel] = useState('');
  const [aiConfigured, setAiConfigured] = useState(false);
  const [aiLoaded, setAiLoaded] = useState(false);
  const [aiLoadError, setAiLoadError] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [savingAI, setSavingAI] = useState(false);
  const endpoint = aiProvider === 'custom' ? customEndpoint.trim() : aiProvider;

  useEffect(() => {
    let active = true;
    getAIConfig().then((config) => {
      if (!active) return;
      setAiConfigured(config.configured);
      setAiModel(config.model || '');
      if (config.endpoint) {
        const known = PROVIDERS.some((provider) => provider.endpoint === config.endpoint);
        setAiProvider(known ? config.endpoint : 'custom');
        if (!known) setCustomEndpoint(config.endpoint);
      }
    }).catch(() => {
      if (active) setAiLoadError(true);
    }).finally(() => {
      if (active) setAiLoaded(true);
    });
    return () => { active = false; };
  }, []);

  const handleSave = async () => {
    try {
      await updatePreferences(preferences);
      setSaved(true);
      toast('success', 'Preferences saved');
      setTimeout(() => setSaved(false), 2000);
    } catch {
      toast('error', 'Could not save preferences. Check the API connection.');
    }
  };

  const handleReset = () => {
    setPreferences({ defaultLanguage: 'en', chartTheme: 'light', decimalPlaces: 2, autoSave: true });
    setSaved(false);
    toast('info', 'Defaults selected. Save to apply them.');
  };

  const handleSaveAI = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!aiApiKey.trim() || !aiModel.trim()) {
      toast('error', 'Enter the provider API key and model ID.');
      return;
    }
    try {
      const url = new URL(endpoint);
      if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error();
    } catch {
      toast('error', 'Enter an HTTP or HTTPS API base URL without credentials, a query or a fragment.');
      return;
    }
    setSavingAI(true);
    try {
      await configureAI(aiApiKey.trim(), endpoint, aiModel.trim());
      setAiConfigured(true);
      setAiLoadError(false);
      setAiApiKey('');
      setShowApiKey(false);
      toast('success', 'Provider settings saved');
    } catch {
      toast('error', 'Could not save provider settings. Check the fields and API connection.');
    } finally {
      setSavingAI(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="text-cascade-sage text-sm mt-1">Display preferences and optional model provider.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleReset} className="btn-secondary flex items-center gap-2 text-xs">
            <RotateCcw size={14} /> Reset
          </button>
          <button onClick={handleSave} className="btn-primary flex items-center gap-2">
            <Save size={16} /> {saved ? 'Saved' : 'Save preferences'}
          </button>
        </div>
      </div>

      <SettingsCard icon={Palette} title="Display" desc="Chart appearance and saved-analysis preferences.">
        <div className="space-y-4">
          <SettingRow label="Chart theme" htmlFor="chart-theme">
            <select id="chart-theme" value={preferences.chartTheme}
              onChange={(event) => setPreferences({ chartTheme: event.target.value as 'light' | 'dark' })} className="input-field w-40">
              <option value="light">Light</option><option value="dark">Dark</option>
            </select>
          </SettingRow>
          <SettingRow label="Decimal places" htmlFor="decimal-places">
            <select id="decimal-places" value={preferences.decimalPlaces}
              onChange={(event) => setPreferences({ decimalPlaces: parseInt(event.target.value, 10) })} className="input-field w-40">
              {[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </SettingRow>
          <SettingRow label="Auto-save analyses" htmlFor="auto-save">
            <button id="auto-save" type="button" role="switch" aria-checked={preferences.autoSave}
              onClick={() => setPreferences({ autoSave: !preferences.autoSave })}
              className={`relative w-10 h-[22px] rounded-full transition-colors ${preferences.autoSave ? 'bg-cascade-gold' : 'bg-cascade-mist'}`}>
              <span className={`absolute top-[3px] left-[3px] w-4 h-4 bg-white rounded-full shadow transition-transform ${preferences.autoSave ? 'translate-x-[18px]' : ''}`} />
            </button>
          </SettingRow>
        </div>
      </SettingsCard>

      <SettingsCard icon={Globe} title="Language" desc="The interface and generated analysis use English.">
        <p className="text-sm text-cascade-charcoal">English</p>
      </SettingsCard>

      <SettingsCard icon={Settings2} title="Model provider" desc="Optional provider for the AI Copilot. Financial calculations run in the local API.">
        <form onSubmit={handleSaveAI} className="space-y-4">
          <p className="flex items-center gap-1.5 text-xs text-cascade-sage" role={aiLoadError ? 'alert' : 'status'}>
            {aiConfigured ? <CheckCircle size={14} /> : <Circle size={14} />}
            {!aiLoaded ? 'Loading provider settings…' : aiLoadError ? 'Provider settings unavailable. Check the API connection.' : aiConfigured ? 'Provider configured' : 'Local rule-based analysis'}
          </p>
          <SettingRow label="Provider" htmlFor="ai-provider">
            <select id="ai-provider" value={aiProvider} onChange={(event) => setAiProvider(event.target.value)} className="input-field w-full sm:w-72 text-sm">
              {PROVIDERS.map((provider) => <option key={provider.endpoint} value={provider.endpoint}>{provider.name}</option>)}
              <option value="custom">Custom compatible endpoint</option>
            </select>
          </SettingRow>
          {aiProvider === 'custom' && (
            <SettingRow label="API base URL" htmlFor="ai-endpoint">
              <input id="ai-endpoint" type="url" required value={customEndpoint} onChange={(event) => setCustomEndpoint(event.target.value)}
                placeholder="Full API base URL, including its version path" spellCheck={false}
                className="input-field w-full sm:w-72 text-xs font-mono" />
            </SettingRow>
          )}
          <SettingRow label="Model ID" htmlFor="ai-model">
            <input id="ai-model" type="text" required value={aiModel} onChange={(event) => setAiModel(event.target.value)}
              placeholder="Model identifier from your provider" spellCheck={false} className="input-field w-full sm:w-72 text-xs font-mono" />
          </SettingRow>
          <SettingRow label="API key" htmlFor="ai-key">
            <div className="relative w-full sm:w-72">
              <input id="ai-key" type={showApiKey ? 'text' : 'password'} required value={aiApiKey}
                onChange={(event) => setAiApiKey(event.target.value)} autoComplete="off" spellCheck={false}
                placeholder={aiConfigured ? 'Enter a key to replace this configuration' : 'Provider API key'}
                className="input-field w-full pr-10 font-mono text-xs" />
              <button type="button" onClick={() => setShowApiKey(!showApiKey)} aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-cascade-sage hover:text-cascade-charcoal">
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </SettingRow>
          <p className="text-xs text-cascade-sage leading-relaxed">
            Use a model ID supported by your provider. Settings are stored in the local API database.
            Copilot requests send the conversation and selected analysis to the configured endpoint.
          </p>
          <div className="flex justify-end">
            <button type="submit" disabled={!aiLoaded || savingAI || !aiApiKey.trim() || !aiModel.trim() || !endpoint}
              className="btn-primary flex items-center gap-2 text-xs">
              <Save size={14} /> {savingAI ? 'Saving…' : 'Save provider settings'}
            </button>
          </div>
        </form>
      </SettingsCard>

      <SettingsCard icon={Monitor} title="Application" desc="Installed build and runtime.">
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-cascade-sage">Version</dt><dd className="font-medium">{version}</dd></div>
          <div className="flex justify-between"><dt className="text-cascade-sage">Interface</dt><dd className="font-medium">{isDesktop ? 'Desktop' : 'Browser'}</dd></div>
          <div className="flex justify-between"><dt className="text-cascade-sage">Storage</dt><dd className="font-medium">Local SQLite database</dd></div>
        </dl>
      </SettingsCard>
    </div>
  );
}

function SettingsCard({ icon: Icon, title, desc, children }: {
  icon: React.ElementType; title: string; desc: string; children: React.ReactNode;
}) {
  return <section className="card">
    <div className="flex items-center gap-3 mb-5">
      <div className="w-9 h-9 rounded-xl bg-cascade-mist flex items-center justify-center shrink-0"><Icon size={18} className="text-cascade-sage" /></div>
      <div><h2 className="font-semibold text-sm">{title}</h2><p className="text-xs text-cascade-sage">{desc}</p></div>
    </div>
    {children}
  </section>;
}

function SettingRow({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
    <label htmlFor={htmlFor} className="text-sm font-medium">{label}</label>{children}
  </div>;
}
