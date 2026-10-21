const dateTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });

/** "21.10.2026, 10:12" aus einem ISO-Zeitstempel der API. */
export function formatDateTime(iso: string): string {
	return dateTime.format(new Date(iso));
}

/** "21.10.2026, 10:12" aus Unix-Millisekunden. */
export function formatMs(ms: number): string {
	return dateTime.format(new Date(ms));
}

/** Dauer als "5:42" bzw. "1:05:42". */
export function formatDuration(ms: number): string {
	const s = Math.round(ms / 1000);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

const number = new Intl.NumberFormat('de-DE');
/** Große Zahlen mit Tausenderpunkten: 1.234.567 */
export const formatNumber = (n: number): string => number.format(n);

/** Achsenbeschriftung: 950 · 38 Tsd. · 1,2 Mio. */
export function formatCompact(n: number): string {
	if (n >= 1e6) return `${(n / 1e6).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio.`;
	if (n >= 1e3) return `${Math.round(n / 1e3).toLocaleString('de-DE')} Tsd.`;
	return String(Math.round(n));
}
