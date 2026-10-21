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
