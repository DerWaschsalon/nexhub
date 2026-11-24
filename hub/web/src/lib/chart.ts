// Rechnen für Liniendiagramme (lib/components/LineChart.svelte): Wertebereich, Skala, nächster Punkt.
// Ohne DOM, damit es sich einzeln prüfen lässt.

/** Bildet einen Wert aus dem Wertebereich auf Pixel ab. */
export type Scale = (value: number) => number;

/** Luft über und unter den Werten, als Anteil ihrer Spanne */
const PADDING = 0.15;

/** Wertebereich einer Achse: ab 0 bis zum größten Wert, oder eng um die Werte mit etwas Luft
 *  (Werte, die sich nur um wenige Prozent ändern, wären ab 0 eine flache Linie). */
export function domain(values: number[], fromZero: boolean): [number, number] {
	const hi = Math.max(...values);
	if (fromZero) return [0, Math.max(1, hi)];
	const lo = Math.min(...values);
	const span = hi - lo || Math.max(1, hi * 0.02);
	return [lo - span * PADDING, hi + span * PADDING];
}

/** Lineare Skala. Ein einzelner Wert (from = to) landet in der Mitte. */
export function linear([from, to]: [number, number], [start, end]: [number, number]): Scale {
	if (from === to) return () => (start + end) / 2;
	return (value) => start + ((value - from) / (to - from)) * (end - start);
}

/** Index des Werts in `xs` (aufsteigend), der `x` am nächsten liegt. */
export function nearest(xs: number[], x: number): number {
	let best = 0;
	for (let i = 1; i < xs.length; i++) {
		if (Math.abs(xs[i] - x) < Math.abs(xs[best] - x)) best = i;
	}
	return best;
}

/** Höchstens `steps + 1` gleichmäßig verteilte Indizes von 0 bis n − 1, für Achsenmarken. */
export function spread(n: number, steps: number): number[] {
	if (n <= 1) return n ? [0] : [];
	const count = Math.min(n - 1, steps);
	return [...new Set(Array.from({ length: count + 1 }, (_, k) => Math.round((k / count) * (n - 1))))];
}
