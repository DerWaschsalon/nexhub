/** Kampfzeit als 5:42 bzw. 1:05:42; vor dem Pull negativ. */
export function formatDuration(ms: number): string {
	const sign = ms < 0 ? '-' : '';
	const s = Math.round(Math.abs(ms) / 1000);
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = String(s % 60).padStart(2, '0');
	return sign + (h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`);
}

/** Achsenmarken: runde Schritte, höchstens `max` Stück. */
export function timeTicks(durationMs: number, max = 8): number[] {
	const step = [5, 10, 15, 30, 60, 120, 300, 600].map((s) => s * 1000).find((s) => durationMs / s <= max) ?? 600_000;
	const out = [];
	for (let t = 0; t <= durationMs; t += step) out.push(t);
	return out;
}
