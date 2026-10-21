// Zahlen, Zeiten und Daten in der gewählten Sprache (lib/i18n.svelte.ts). In Vorlagen aufgerufen
// sind sie reaktiv: Wechselt die Sprache, formatiert die Seite neu.
import { i18n } from '#lib/i18n.svelte.ts';

const one = (n: number) => n.toLocaleString(i18n.locale, { maximumFractionDigits: 1 });

/** "Oct 21, 2026, 10:12 AM" / "21.10.2026, 10:12" aus einem ISO-Zeitstempel der API. */
export function formatDateTime(iso: string): string {
	return formatMs(new Date(iso).getTime());
}

/** Wie formatDateTime, aus Unix-Millisekunden. */
export function formatMs(ms: number): string {
	return new Intl.DateTimeFormat(i18n.locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(ms));
}

/** Große Zahlen mit Tausendertrennern: 1,234,567 / 1.234.567 */
export const formatNumber = (n: number): string => Math.round(n).toLocaleString(i18n.locale);

/** Kurz für schmale Spalten und Achsen: 1.2M · 38.4K · 950 (deutsch mit Komma) */
export function formatCompact(n: number): string {
	if (n >= 1e6) return `${one(n / 1e6)}M`;
	if (n >= 1e4) return `${one(n / 1e3)}K`;
	return formatNumber(n);
}

/** Prozent mit einer Nachkommastelle: 12.5% */
export const formatPct = (n: number): string => `${one(n)}%`;

/** Dauer als "5:42" bzw. "1:05:42"; vor dem Pull negativ ("-0:03"). */
export function formatDuration(ms: number): string {
	const sign = ms < 0 ? '-' : '';
	const s = Math.round(Math.abs(ms) / 1000);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return sign + (h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`);
}

/** Achsenmarken für Zeitachsen: runde Schritte, höchstens `max` Stück. */
export function timeTicks(durationMs: number, max = 8): number[] {
	const step = [5, 10, 15, 30, 60, 120, 300, 600].map((s) => s * 1000).find((s) => durationMs / s <= max) ?? 600_000;
	const out = [];
	for (let t = 0; t <= durationMs; t += step) out.push(t);
	return out;
}
