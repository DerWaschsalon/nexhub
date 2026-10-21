// Buff-Zeitleiste: je Buff eine Spur mit den Zeiten, in denen er aktiv war, dazu die Laufzeit.
// Erst die Buffs auf dem gewählten Spieler, dann die Debuffs auf dem Boss (wie im Meter).
import type { Buff } from '../lib/api.ts';
import { useI18n } from '../lib/i18n.tsx';
import type { GameNames } from '../lib/names.ts';
import { formatDuration, timeTicks } from '../lib/time.ts';

function Lanes({ buffs, durationMs, names }: { buffs: Buff[]; durationMs: number; names: GameNames }) {
	const { t } = useI18n();
	const pct = (ms: number) => (100 * Math.min(durationMs, Math.max(0, ms))) / durationMs;
	// Gleiche Buffs von mehreren Quellen zusammen auf eine Spur
	const byId = new Map<number, Buff[]>();
	for (const b of buffs) byId.set(b.id, [...(byId.get(b.id) ?? []), b]);
	const rows = [...byId.entries()]
		.map(([id, list]) => ({ id, segs: list.flatMap((b) => b.segments), up: Math.max(...list.map((b) => b.up)) }))
		.sort((a, b) => b.up - a.up);
	if (!rows.length) return <p className="dim">{t('buffs.none')}</p>;
	return (
		<div className="lanes buff-lanes">
			<div className="lane axis-lane" aria-hidden>
				<span />
				<div className="track">
					{timeTicks(durationMs).map((ms) => (
						<span key={ms} className="tick" style={{ left: `${pct(ms)}%` }}>{formatDuration(ms)}</span>
					))}
				</div>
				<span />
			</div>
			{rows.map((r) => {
				const icon = names.buffIcon(r.id);
				const uptime = Math.min(100, (100 * r.up) / durationMs);
				return (
					<div className="lane" key={r.id}>
						<span className="lane-name">
							{icon ? <img className="skill-icon" src={icon} width={22} height={22} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="skill-icon fallback" style={{ width: 22, height: 22 }} />}
							{names.buff(r.id)}
						</span>
						<div className="track">
							{r.segs.map(([start, end, stacks], i) => {
								const left = pct(start);
								const width = pct(end) - left;
								if (width <= 0) return null;
								return (
									<span key={i} className="seg" style={{ left: `${left}%`, width: `${width}%`, opacity: 0.55 + Math.min(stacks, 5) * 0.09 }}
										title={`${formatDuration(start)}–${formatDuration(end)}${stacks > 1 ? ` · ${t('buffs.stacks', { n: stacks })}` : ''}`} />
								);
							})}
						</div>
						<span className="uptime num" title={t('buffs.uptime')}>{uptime > 0 && uptime < 1 ? '<1%' : `${Math.round(uptime)}%`}</span>
					</div>
				);
			})}
		</div>
	);
}

export function BuffTimeline({ buffs, actor, target, playerName, boss, durationMs, names }: {
	buffs: Buff[];
	actor: number;
	target: number | null;
	playerName: string;
	boss: string;
	durationMs: number;
	names: GameNames;
}) {
	const { t } = useI18n();
	return (
		<>
			<h3>{t('buffs.onPlayer', { name: playerName })}</h3>
			<Lanes buffs={buffs.filter((b) => b.actor === actor)} durationMs={durationMs} names={names} />
			{target != null && (
				<>
					<h3>{t('buffs.onTarget', { boss })}</h3>
					<Lanes buffs={buffs.filter((b) => b.actor === target)} durationMs={durationMs} names={names} />
				</>
			)}
		</>
	);
}
