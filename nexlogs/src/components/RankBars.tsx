import type { Player } from '../lib/api.ts';
import { classColor } from '../lib/classes.ts';
import { useI18n } from '../lib/i18n.tsx';
import { PlayerName } from './ClassBadge.tsx';

/** Rangliste: Balken in Klassenfarbe, längster Balken = meister Schaden. */
export function RankBars({ players, selected, onSelect }: {
	players: Player[];
	selected?: string | null;
	onSelect?: (name: string) => void;
}) {
	const { num, compact, t } = useI18n();
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
						<span className="value num" title={`${num(p.damage)} ${t('skills.col.damage')}`}>
							{compact(p.damage)}
							<small>{Math.round((100 * p.damage) / total)} %</small>
						</span>
						<span className="dps num">{num(p.dps)}<small>/s</small></span>
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
