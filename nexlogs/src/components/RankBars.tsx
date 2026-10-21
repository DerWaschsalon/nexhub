import type { Player } from '../lib/api.ts';
import { classColor } from '../lib/classes.ts';
import { formatCompact, formatNumber } from '../lib/format.ts';
import { PlayerName } from './ClassBadge.tsx';

/** Rangliste: Balken in Klassenfarbe, längster Balken = meister Schaden. */
export function RankBars({ players, selected, onSelect }: {
	players: Player[];
	selected?: string | null;
	onSelect?: (name: string) => void;
}) {
	const max = players[0]?.damage || 1;
	const total = players.reduce((s, p) => s + p.damage, 0) || 1;
	return (
		<ol className="ranks">
			{players.map((p, i) => {
				const color = classColor(p.cls);
				const body = (
					<>
						<span className="rank num">{i + 1}</span>
						<PlayerName name={p.name} cls={p.cls} />
						<span className="bar" aria-hidden>
							<span style={{ width: `${(100 * p.damage) / max}%`, background: color, boxShadow: `0 0 18px -4px ${color}` }} />
						</span>
						<span className="value num" title={`${formatNumber(p.damage)} Schaden`}>
							{formatCompact(p.damage)}
							<small>{Math.round((100 * p.damage) / total)} %</small>
						</span>
						<span className="dps num">{formatNumber(p.dps)}<small>/s</small></span>
					</>
				);
				return (
					<li key={p.name} className={selected === p.name ? 'selected' : undefined}>
						{onSelect ? (
							<button type="button" onClick={() => onSelect(p.name)} aria-pressed={selected === p.name}>{body}</button>
						) : (
							<div>{body}</div>
						)}
					</li>
				);
			})}
		</ol>
	);
}
