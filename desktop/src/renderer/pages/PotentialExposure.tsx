import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import { AlertTriangle, Loader2, TrendingUp } from 'lucide-react';
import { useToast } from '../components/Toast';
import { PRODUCT_LABELS, PRODUCT_SIDES, apiErrorMessage, formatAmount, simulatePFE } from '../lib/exposureApi';
import type { PFEResult, RiskProduct } from '../lib/exposureApi';

interface Field { key: string; label: string; value: string; optional?: string }

// Illustrative starting values; they mirror the backend defaults and are not market data.
const productFields: Record<RiskProduct, Field[]> = {
  equity: [
    { key: 'spot', label: 'Spot price', value: '100' },
    { key: 'quantity', label: 'Quantity (shares)', value: '10000' },
    { key: 'volatility', label: 'Volatility (decimal)', value: '0.25' },
    { key: 'drift', label: 'Drift (decimal)', value: '0' },
  ],
  fx: [
    { key: 'spot', label: 'Spot (domestic per foreign)', value: '83' },
    { key: 'notional_foreign', label: 'Foreign notional', value: '1000000' },
    { key: 'strike', label: 'Forward strike', value: '', optional: 'Model forward if blank' },
    { key: 'domestic_rate', label: 'Domestic rate (decimal)', value: '0.065' },
    { key: 'foreign_rate', label: 'Foreign rate (decimal)', value: '0.045' },
    { key: 'volatility', label: 'Volatility (decimal)', value: '0.06' },
    { key: 'maturity_years', label: 'Maturity (years)', value: '1' },
  ],
  bond: [
    { key: 'notional', label: 'Face value', value: '10000000' },
    { key: 'coupon_rate', label: 'Coupon (decimal)', value: '0.07' },
    { key: 'yield_rate', label: 'Yield (decimal)', value: '0.07' },
    { key: 'maturity_years', label: 'Maturity (years)', value: '5' },
    { key: 'yield_vol_bp', label: 'Yield volatility (bp per year)', value: '90' },
  ],
  irs: [
    { key: 'notional', label: 'Notional', value: '10000000' },
    { key: 'swap_rate', label: 'Market swap rate (decimal)', value: '0.065' },
    { key: 'fixed_rate', label: 'Fixed rate (decimal)', value: '', optional: 'Swap rate if blank' },
    { key: 'maturity_years', label: 'Maturity (years)', value: '5' },
    { key: 'payments_per_year', label: 'Fixed payments per year', value: '1' },
    { key: 'rate_vol_bp', label: 'Rate volatility (bp per year)', value: '90' },
  ],
  cds: [
    { key: 'notional', label: 'Notional', value: '10000000' },
    { key: 'spread_bp', label: 'Market spread (bp)', value: '120' },
    { key: 'contract_spread_bp', label: 'Contract spread (bp)', value: '', optional: 'Market spread if blank' },
    { key: 'spread_volatility', label: 'Spread volatility (decimal)', value: '0.6' },
    { key: 'recovery', label: 'Recovery rate (decimal)', value: '0.4' },
    { key: 'rate', label: 'Discount rate (decimal)', value: '0.05' },
    { key: 'maturity_years', label: 'Maturity (years)', value: '5' },
  ],
  equity_option: [
    { key: 'spot', label: 'Spot price', value: '100' },
    { key: 'strike', label: 'Strike', value: '100' },
    { key: 'quantity', label: 'Quantity (shares)', value: '10000' },
    { key: 'volatility', label: 'Volatility (decimal)', value: '0.25' },
    { key: 'rate', label: 'Risk-free rate (decimal)', value: '0.05' },
    { key: 'expiry_years', label: 'Expiry (years)', value: '1' },
  ],
};

const initialInputs = Object.fromEntries(
  (Object.keys(productFields) as RiskProduct[]).map(product => [
    product, Object.fromEntries(productFields[product].map(field => [field.key, field.value])),
  ]),
) as Record<RiskProduct, Record<string, string>>;

const initialSides = Object.fromEntries(
  (Object.keys(PRODUCT_SIDES) as RiskProduct[]).map(product => [product, PRODUCT_SIDES[product][0].value]),
) as Record<RiskProduct, string>;

function numberOrThrow(raw: string, label: string): number {
  const value = Number(raw);
  if (raw.trim() === '' || !Number.isFinite(value)) throw new Error(`${label} must be a number`);
  return value;
}

export default function PotentialExposure() {
  const { toast } = useToast();
  const [product, setProduct] = useState<RiskProduct>('irs');
  const [inputs, setInputs] = useState(initialInputs);
  const [sides, setSides] = useState(initialSides);
  const [optionType, setOptionType] = useState<'call' | 'put'>('call');
  const [settings, setSettings] = useState({ horizon: '', quantile: '0.95', paths: '5000', mpor: '10', threshold: '0', initialMargin: '0', seed: '42' });
  const [fixedSeed, setFixedSeed] = useState(true);
  const [result, setResult] = useState<PFEResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function run() {
    setError(''); setLoading(true);
    try {
      const params: Record<string, number | string | null> = { side: sides[product] };
      productFields[product].forEach(field => {
        const raw = inputs[product][field.key];
        params[field.key] = field.optional && raw.trim() === '' ? null : numberOrThrow(raw, field.label);
      });
      if (product === 'equity_option') params.option_type = optionType;
      const data = await simulatePFE({
        product, params,
        horizon_years: settings.horizon.trim() === '' ? null : numberOrThrow(settings.horizon, 'Horizon'),
        quantile: numberOrThrow(settings.quantile, 'Quantile'),
        paths: numberOrThrow(settings.paths, 'Paths'),
        seed: fixedSeed ? numberOrThrow(settings.seed, 'Seed') : null,
        mpor_days: numberOrThrow(settings.mpor, 'Margin period of risk'),
        threshold: numberOrThrow(settings.threshold, 'Threshold'),
        initial_margin: numberOrThrow(settings.initialMargin, 'Initial margin'),
      });
      setResult(data);
      toast('success', `Simulated ${data.paths.toLocaleString('en-US')} paths over ${data.times.length - 1} steps`);
    } catch (cause: any) {
      setResult(null);
      setError(apiErrorMessage(cause, 'Simulation failed'));
    } finally { setLoading(false); }
  }

  const chartData = result?.times.map((time, i) => ({
    time,
    pfe: result.uncollateralised.pfe[i],
    ee: result.uncollateralised.expected_exposure[i],
    pfeCollateralised: result.collateralised.pfe[i],
    eeCollateralised: result.collateralised.expected_exposure[i],
  }));
  const quantileLabel = result ? `${(result.quantile * 100).toFixed(result.quantile * 100 % 1 ? 1 : 0)}%` : '';

  const settingFields: { key: keyof typeof settings; label: string; placeholder?: string }[] = [
    { key: 'horizon', label: 'Horizon (years)', placeholder: `Default: ${inputs[product].maturity_years || inputs[product].expiry_years || '1'}y` },
    { key: 'quantile', label: 'PFE quantile (decimal)', placeholder: '0.5 to below 1' },
    { key: 'paths', label: 'Paths', placeholder: '100 to 50,000' },
    { key: 'mpor', label: 'Margin period of risk (days)' },
    { key: 'threshold', label: 'Collateral threshold' },
    { key: 'initialMargin', label: 'Initial margin held' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-cascade-gold/10 rounded-xl flex items-center justify-center">
          <TrendingUp className="text-cascade-gold" size={20} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cascade-charcoal">Potential Future Exposure</h1>
          <p className="text-sm text-gray-500">Simulated exposure profile per trade, with and without collateral</p>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl">
        <p className="text-xs text-amber-800">
          <strong>Illustrative scenario.</strong> Starting values are model assumptions, not observed market quotes.
          Enter your trade terms and calibrated inputs. Each model uses one risk factor per trade.
        </p>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label htmlFor="pfe-product" className="text-xs text-gray-500">Product</label>
            <select id="pfe-product" value={product} onChange={event => { setProduct(event.target.value as RiskProduct); setResult(null); }} className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
              {(Object.keys(PRODUCT_LABELS) as RiskProduct[]).map(key => <option key={key} value={key}>{key === 'fx' ? 'FX forward' : PRODUCT_LABELS[key]}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pfe-side" className="text-xs text-gray-500">Our side</label>
            <select id="pfe-side" value={sides[product]} onChange={event => setSides({ ...sides, [product]: event.target.value })} className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
              {PRODUCT_SIDES[product].map(side => <option key={side.value} value={side.value}>{side.label}</option>)}
            </select>
          </div>
          {product === 'equity_option' && (
            <div>
              <label htmlFor="pfe-option-type" className="text-xs text-gray-500">Option type</label>
              <select id="pfe-option-type" value={optionType} onChange={event => setOptionType(event.target.value as 'call' | 'put')} className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
                <option value="call">Call</option>
                <option value="put">Put</option>
              </select>
            </div>
          )}
        </div>

        <div>
          <h3 className="text-sm font-semibold text-cascade-charcoal mb-2">Trade and model inputs</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {productFields[product].map(field => (
              <div key={field.key}>
                <label htmlFor={`pfe-input-${field.key}`} className="text-xs text-gray-500">{field.label}</label>
                <input id={`pfe-input-${field.key}`} type="number" step="any" value={inputs[product][field.key]} placeholder={field.optional}
                  onChange={event => setInputs({ ...inputs, [product]: { ...inputs[product], [field.key]: event.target.value } })}
                  className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-2">Decimal rates use 0.05 for 5%; 100 basis points equal 1 percentage point. Amounts must use consistent currency units.</p>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-cascade-charcoal mb-2">Simulation and collateral</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {settingFields.map(field => (
              <div key={field.key}>
                <label htmlFor={`pfe-setting-${field.key}`} className="text-xs text-gray-500">{field.label}</label>
                <input id={`pfe-setting-${field.key}`} type="number" step="any" value={settings[field.key]} placeholder={field.placeholder}
                  onChange={event => setSettings({ ...settings, [field.key]: event.target.value })}
                  className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
              </div>
            ))}
            <div>
              <label className="text-xs text-gray-500 flex items-center gap-2">
                <input type="checkbox" checked={fixedSeed} onChange={event => setFixedSeed(event.target.checked)} />
                Fixed random seed (reproducible)
              </label>
              <input type="number" step="1" value={settings.seed} disabled={!fixedSeed}
                onChange={event => setSettings({ ...settings, seed: event.target.value })}
                className="w-full mt-1 px-3 py-2 border rounded-lg text-sm disabled:bg-gray-50 disabled:text-gray-400" />
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2">The time grid steps in units of the margin period of risk, so collateral always lags the trade value by exactly one step.</p>
        </div>

        <button onClick={run} disabled={loading} className="px-4 py-2 bg-cascade-gold text-white rounded-lg hover:bg-cascade-gold/90 disabled:opacity-50 flex items-center gap-2 text-sm font-medium">
          {loading ? <Loader2 className="animate-spin" size={16} /> : <TrendingUp size={16} />} Simulate exposure
        </button>
        {error && (
          <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
            <AlertTriangle className="text-red-500 shrink-0 mt-0.5" size={16} />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}
      </div>

      {result && chartData && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Peak PFE ({quantileLabel}), no collateral</p>
              <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(result.uncollateralised.peak_pfe)}</p>
              <p className="text-xs text-gray-400">at {result.uncollateralised.peak_pfe_time.toFixed(2)} years</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Peak PFE ({quantileLabel}), collateralised</p>
              <p className="text-xl font-bold text-blue-700">{formatAmount(result.collateralised.peak_pfe)}</p>
              <p className="text-xs text-gray-400">at {result.collateralised.peak_pfe_time.toFixed(2)} years</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Expected positive exposure, no collateral</p>
              <p className="text-xl font-bold text-cascade-gold">{formatAmount(result.uncollateralised.epe)}</p>
              <p className="text-xs text-gray-400">time average over {result.horizon_years.toFixed(2)} years</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-xs text-gray-500 mb-1">Expected positive exposure, collateralised</p>
              <p className="text-xl font-bold text-cascade-charcoal">{formatAmount(result.collateralised.epe)}</p>
              <p className="text-xs text-gray-400">{result.mpor_days}-day margin period of risk</p>
            </div>
          </div>

          <div className="bg-white rounded-xl border p-5">
            <h3 className="font-semibold text-cascade-charcoal mb-1">Exposure profile</h3>
            <p className="text-xs text-gray-500 mb-4">
              Simulated output from the inputs above ({result.paths.toLocaleString('en-US')} paths{result.seed !== null ? `, seed ${result.seed}` : ', random seed'}). Value at inception: {formatAmount(result.initial_value)}.
            </p>
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="time" type="number" domain={[0, result.horizon_years]} tick={{ fontSize: 11 }} tickFormatter={(value: number) => value.toFixed(1)}
                  label={{ value: 'Years', position: 'insideBottomRight', offset: -4, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => formatAmount(value)} width={90} />
                <Tooltip formatter={(value: number) => formatAmount(value)} labelFormatter={(value: number) => `${Number(value).toFixed(2)} years`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="pfe" name={`PFE ${quantileLabel}`} stroke="#1a1a19" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="ee" name="Expected exposure" stroke="#92761f" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="pfeCollateralised" name={`PFE ${quantileLabel}, collateralised`} stroke="#2563eb" strokeWidth={1.5} strokeDasharray="5 3" dot={false} />
                <Line type="monotone" dataKey="eeCollateralised" name="Expected exposure, collateralised" stroke="#78716c" strokeWidth={1.5} strokeDasharray="5 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-2">
            <p className="text-sm text-blue-800"><strong>Model.</strong> {result.model}</p>
            <ul className="list-disc pl-5 text-sm text-blue-800 space-y-1">
              {result.simplifications.map(note => <li key={note}>{note}</li>)}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
