import { useEffect, useMemo, useRef, useState } from 'react';
import type { Fight } from '../lib/api.ts';
import { classColor } from '../lib/classes.ts';
import { useI18n } from '../lib/i18n.tsx';
import { formatDuration } from '../lib/time.ts';

// Breite = echte Breite des Containers, damit die Schrift auf dem Handy nicht mitschrumpft
const H = 260;
const PAD = { l: 56, r: 12, t: 12, b: 28 };
const SMOOTH_S = 5; // gleitender Mittelwert über 5 Sekunden, sonst zackt jeder Treffer

/** DPS-Verlauf je Spieler in Klassenfarbe. Zwei Spieler derselben Klasse: der zweite gestrichelt. */
export function DpsChart({ fight, highlight }: { fight: Fight; highlight: string | null }) {
	const { t, num, compact } = useI18n();
	const [hover, setHover] = useState<number | null>(null);
	const box = useRef<HTMLElement>(null);
	const [W, setW] = useState(900);
	useEffect(() => {
		if (!box.current) return;
		const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
		ro.observe(box.current);
		return () => ro.disconnect();
	}, []);
	const series = useMemo(() => {
		if (!fight.timeline) return [];
		const seen = new Map<string, number>();
		return fight.timeline.players.map((s) => {
			const p = fight.players.find((x) => x.actor === s.actor);
			const cls = p?.cls ?? null;
			const nth = seen.get(cls ?? '') ?? 0;
			seen.set(cls ?? '', nth + 1);
			const perSec = s.damage.map((d) => (d * 1000) / fight.timeline!.bucket_ms);
			const smooth = perSec.map((_, i) => {
				const from = Math.max(0, i - SMOOTH_S + 1);
				const win = perSec.slice(from, i + 1);
				return win.reduce((a, b) => a + b, 0) / win.length;
			});
			return { name: p?.name ?? `#${s.actor}`, color: classColor(cls), dashed: nth > 0, values: smooth };
		});
	}, [fight]);

	if (!series.length) return <p className="dim">{t('chart.none')}</p>;

	const n = Math.max(...series.map((s) => s.values.length));
	const max = Math.max(1, ...series.flatMap((s) => s.values));
	const x = (i: number) => PAD.l + (i / Math.max(1, n - 1)) * (W - PAD.l - PAD.r);
	const y = (v: number) => H - PAD.b - (v / max) * (H - PAD.t - PAD.b);
	const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
	const secs = (fight.timeline!.bucket_ms / 1000) * (n - 1);
	const steps = W < 520 ? 3 : 5;
	const xTicks = Array.from({ length: steps + 1 }, (_, k) => Math.round((k / steps) * (n - 1)));

	function move(e: React.PointerEvent<SVGSVGElement>) {
		const box = e.currentTarget.getBoundingClientRect();
		const px = ((e.clientX - box.left) / box.width) * W;
		const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
		setHover(i >= 0 && i < n ? i : null);
	}

	const hoverRows = hover === null ? [] : [...series].map((s) => ({ ...s, v: s.values[hover] ?? 0 })).sort((a, b) => b.v - a.v);

	return (
		<figure className="chart" ref={box}>
			<svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('chart.label', { d: formatDuration(secs * 1000) })}
				onPointerMove={move} onPointerLeave={() => setHover(null)}>
				{ticks.map((v) => (
					<g key={v}>
						<line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="grid" />
						<text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" className="axis">{compact(v)}</text>
					</g>
				))}
				{xTicks.map((i) => (
					<text key={i} x={x(i)} y={H - 8} textAnchor="middle" className="axis">
						{formatDuration(i * fight.timeline!.bucket_ms)}
					</text>
				))}
				{series.map((s) => (
					<polyline key={s.name} fill="none" stroke={s.color} strokeWidth={highlight === s.name ? 3 : 1.8}
						strokeDasharray={s.dashed ? '6 4' : undefined} strokeLinejoin="round"
						opacity={highlight && highlight !== s.name ? 0.25 : 1}
						points={s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} />
				))}
				{hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} className="cursor" />}
			</svg>
			{hover !== null && (
				<div className="tip glass" style={{ left: `${(x(hover) / W) * 100}%` }}>
					<strong>{formatDuration(hover * fight.timeline!.bucket_ms)}</strong>
					{hoverRows.map((r) => (
						<span key={r.name}><i style={{ background: r.color }} />{r.name}<b className="num">{num(r.v)}</b></span>
					))}
				</div>
			)}
			<figcaption className="legend">
				{series.map((s) => (
					<span key={s.name}><i style={{ background: s.dashed ? 'none' : s.color, borderColor: s.color }} className={s.dashed ? 'dashed' : undefined} />{s.name}</span>
				))}
			</figcaption>
		</figure>
	);
}
