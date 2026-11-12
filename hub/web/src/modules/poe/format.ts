// Preise und Änderungen für Path of Exile, in der gewählten Sprache (lib/format.ts).
import { i18n } from '#lib/i18n.svelte.ts';

/** Preis ohne Einheit: große Preise ganz, kleine mit höchstens zwei Stellen, die etwas aussagen
 *  (412 · 3.5 · 0.005), sonst stünde bei Splittern nur „0“. */
export function formatAmount(n: number): string {
	if (n >= 100) return n.toLocaleString(i18n.locale, { maximumFractionDigits: 0 });
	if (n >= 1) return n.toLocaleString(i18n.locale, { maximumFractionDigits: 2 });
	return n.toLocaleString(i18n.locale, { maximumSignificantDigits: 2 });
}

/** "412 divine" */
export const formatPrice = (n: number, unit: string | null): string =>
	unit ? `${formatAmount(n)} ${unit}` : formatAmount(n);

/** "+6 %" / "-3 %"; ohne Vergleichswert "–" */
export function formatChange(pct: number | null): string {
	if (pct === null) return '–';
	const rounded = Math.round(pct);
	return `${rounded > 0 ? '+' : ''}${rounded} %`;
}

/** Farbe einer Änderung für style:color: steigend grün, fallend rot, sonst normal */
export function changeColor(pct: number | null): string | undefined {
	if (pct === null || Math.round(pct) === 0) return undefined;
	return pct > 0 ? 'var(--ok)' : 'var(--danger)';
}
