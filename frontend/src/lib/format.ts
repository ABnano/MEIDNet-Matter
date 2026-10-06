/** Numbers as the report prints them: three significant figures, thousands separated above 1000. */
export function fmt(v: number | null | undefined, unit = ''): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const s = Math.abs(v) >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : Number(v.toPrecision(3)).toString();
  return unit ? `${s} ${unit}` : s;
}
export const signed = (v: number | null | undefined, unit = '') => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${fmt(v, unit)}`);
export const pct = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? '—' : `${(100 * v).toFixed(digits)} %`);
export const int = (v: number | null | undefined) => (v === null || v === undefined ? '—' : v.toLocaleString('en-US'));
export const seconds = (s: number) => (s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`);
export const shortLabel = (label: string) => (/gap/i.test(label) ? 'Eg' : /formation|enthalp/i.test(label) ? 'ΔHf' : label);
export const statusWord: Record<string, string> = { ok: 'Good', caution: 'Fair', not_ok: 'Weak', info: 'Measured', not_computed: 'Not computed' };
export const statusClass: Record<string, string> = { ok: 'badge-ok', caution: 'badge-warn', not_ok: 'badge-bad', info: 'badge-info', not_computed: 'badge-neutral' };
export const domainClass: Record<string, string> = { in_distribution: 'badge-ok', near_boundary: 'badge-warn', extrapolating: 'badge-bad', far_outside: 'badge-bad' };
