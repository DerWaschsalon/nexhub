const number = new Intl.NumberFormat('de-DE');
const dateTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });

export const formatNumber = (n: number) => number.format(Math.round(n));
export const formatDate = (ms: number) => dateTime.format(new Date(ms));

/** 1,2 Mio. · 38 Tsd. · 950 */
export function formatCompact(n: number): string {
	if (n >= 1e6) return `${(n / 1e6).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio.`;
	if (n >= 1e4) return `${Math.round(n / 1e3).toLocaleString('de-DE')} Tsd.`;
	return formatNumber(n);
}

/** 5:42 bzw. 1:05:42 */
export function formatDuration(ms: number): string {
	const s = Math.round(ms / 1000);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

export const formatPct = (n: number) => `${n.toLocaleString('de-DE', { maximumFractionDigits: 1 })} %`;
