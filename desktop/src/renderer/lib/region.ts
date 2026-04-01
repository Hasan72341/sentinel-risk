// Regional formatting helpers for India, China, Japan and South Korea.
// All output is English: en-IN for Indian digit grouping, en-US otherwise.

export type CountryCode = 'IN' | 'CN' | 'JP' | 'KR';
export type CurrencyCode = 'INR' | 'CNY' | 'JPY' | 'KRW' | 'USD';

export interface CountryInfo {
  code: CountryCode;
  name: string;
  currency: Exclude<CurrencyCode, 'USD'>;
  locale: 'en-IN' | 'en-US';
  /** Decimal places normally shown for the currency. */
  minorUnits: number;
  timeZone: string;
  framework: string;
  frameworkId: 'IND_AS' | 'CAS' | 'JGAAP' | 'KIFRS';
}

export const COUNTRIES: readonly CountryInfo[] = [
  { code: 'IN', name: 'India', currency: 'INR', locale: 'en-IN', minorUnits: 2, timeZone: 'Asia/Kolkata', framework: 'Ind AS', frameworkId: 'IND_AS' },
  { code: 'CN', name: 'China', currency: 'CNY', locale: 'en-US', minorUnits: 2, timeZone: 'Asia/Shanghai', framework: 'CAS', frameworkId: 'CAS' },
  { code: 'JP', name: 'Japan', currency: 'JPY', locale: 'en-US', minorUnits: 0, timeZone: 'Asia/Tokyo', framework: 'J-GAAP', frameworkId: 'JGAAP' },
  { code: 'KR', name: 'South Korea', currency: 'KRW', locale: 'en-US', minorUnits: 0, timeZone: 'Asia/Seoul', framework: 'K-IFRS', frameworkId: 'KIFRS' },
];

export const REPORTING_CURRENCY: CurrencyCode = 'USD';
export const DEFAULT_COUNTRY: CountryCode = 'IN';
const STORAGE_KEY = 'sentinel-risk.country';

export function isCountryCode(value: unknown): value is CountryCode {
  return typeof value === 'string' && COUNTRIES.some((country) => country.code === value);
}

export function getCountry(code: string | null | undefined): CountryInfo {
  const upper = (code ?? '').toUpperCase();
  return COUNTRIES.find((country) => country.code === upper) ?? COUNTRIES[0];
}

/** Options for a country <select>. */
export function countryOptions(): { value: CountryCode; label: string }[] {
  return COUNTRIES.map((country) => ({ value: country.code, label: `${country.name} (${country.currency})` }));
}

/** Last country chosen on this device, or the default. */
export function loadSelectedCountry(): CountryCode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isCountryCode(stored) ? stored : DEFAULT_COUNTRY;
  } catch {
    return DEFAULT_COUNTRY;
  }
}

export function saveSelectedCountry(code: CountryCode): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // Storage can be unavailable; the selection then lasts for the session only.
  }
}

function localeForCurrency(currency: string): string {
  return currency === 'INR' ? 'en-IN' : 'en-US';
}

function minorUnitsForCurrency(currency: string): number {
  return currency === 'JPY' || currency === 'KRW' ? 0 : 2;
}

const DASH = '-';

function usable(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** Plain number with the country's digit grouping (12,34,567 in India; 1,234,567 elsewhere). */
export function formatNumber(value: number | null | undefined, country: CountryCode = DEFAULT_COUNTRY, decimals = 2): string {
  if (!usable(value)) return DASH;
  return new Intl.NumberFormat(getCountry(country).locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Currency amount, for example INR 1,23,456.00 with the rupee sign, or a yen amount with no decimals. */
export function formatCurrency(
  value: number | null | undefined,
  currency: string,
  options: { decimals?: number; display?: 'symbol' | 'code' } = {},
): string {
  if (!usable(value)) return DASH;
  const decimals = options.decimals ?? minorUnitsForCurrency(currency);
  try {
    return new Intl.NumberFormat(localeForCurrency(currency), {
      style: 'currency',
      currency,
      currencyDisplay: options.display === 'code' ? 'code' : 'narrowSymbol',
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  } catch {
    // Unknown currency code: fall back to a plain number with the code as given.
    return `${currency} ${new Intl.NumberFormat('en-US', { maximumFractionDigits: decimals }).format(value)}`;
  }
}

function trimmed(value: number, locale: string, decimals: number): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 0, maximumFractionDigits: decimals }).format(value);
}

/**
 * Compact amount in words. India uses lakh (1,00,000) and crore (1,00,00,000);
 * the other countries use thousand, million, billion and trillion.
 */
export function formatCompact(value: number | null | undefined, country: CountryCode = DEFAULT_COUNTRY, decimals = 2): string {
  if (!usable(value)) return DASH;
  const info = getCountry(country);
  const size = Math.abs(value);
  const steps: [number, string][] = info.code === 'IN'
    ? [[1e12, 'lakh crore'], [1e7, 'crore'], [1e5, 'lakh']]
    : [[1e12, 'trillion'], [1e9, 'billion'], [1e6, 'million'], [1e3, 'thousand']];
  for (const [unit, label] of steps) {
    if (size >= unit) return `${trimmed(value / unit, info.locale, decimals)} ${label}`;
  }
  return trimmed(value, info.locale, decimals);
}

/** Compact amount with the country's currency sign in front. */
export function formatCompactCurrency(value: number | null | undefined, country: CountryCode = DEFAULT_COUNTRY, decimals = 2): string {
  if (!usable(value)) return DASH;
  const info = getCountry(country);
  const sign = new Intl.NumberFormat(info.locale, { style: 'currency', currency: info.currency, currencyDisplay: 'narrowSymbol' })
    .formatToParts(0)
    .find((part) => part.type === 'currency')?.value ?? info.currency;
  const body = formatCompact(Math.abs(value), info.code, decimals);
  return `${value < 0 ? '-' : ''}${sign}${body}`;
}

/** Percentage from a value already in percent units (1.5 gives +1.50%). */
export function formatPercent(value: number | null | undefined, decimals = 2, signed = false): string {
  if (!usable(value)) return DASH;
  const text = new Intl.NumberFormat('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(value));
  const sign = value < 0 ? '-' : signed && value > 0 ? '+' : '';
  return `${sign}${text}%`;
}

/** Local date and time in a market's time zone, in English. */
export function formatMarketTime(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(date);
  } catch {
    return date.toISOString().slice(0, 16).replace('T', ' ');
  }
}
