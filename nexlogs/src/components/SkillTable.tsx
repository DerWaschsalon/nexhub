import type { FightPlayer } from '../lib/api.ts';
import { classColor } from '../lib/classes.ts';
import { formatCompact, formatNumber, formatPct } from '../lib/format.ts';
import { SkillIcon } from './SkillIcon.tsx';

export function SkillTable({ player }: { player: FightPlayer }) {
	const color = classColor(player.cls);
	const max = player.skills[0]?.damage || 1;
	return (
		<div className="table-wrap">
			<table className="table skills">
				<thead>
					<tr>
						<th>Fähigkeit</th>
						<th>Anteil</th>
						<th className="right">Schaden</th>
						<th className="right">Treffer</th>
						<th className="right">Krit</th>
						<th className="right">Rücken</th>
						<th className="right">Perfekt</th>
						<th className="right">Doppelt</th>
					</tr>
				</thead>
				<tbody>
					{player.skills.map((s, i) => (
						<tr key={`${s.code}-${s.name}-${i}`}>
							<td>
								<span className="skill">
									<SkillIcon code={s.code} />
									<span>{s.name}{s.dot && <span className="chip">DoT</span>}</span>
								</span>
							</td>
							<td>
								<span className="share">
									<span className="bar thin" aria-hidden><span style={{ width: `${(100 * s.damage) / max}%`, background: color }} /></span>
									<span className="num">{formatPct(s.share)}</span>
								</span>
							</td>
							<td className="right num" title={formatNumber(s.damage)}>{formatCompact(s.damage)}</td>
							<td className="right num">{formatNumber(s.hits)}</td>
							<td className="right num">{formatPct(s.crit)}</td>
							<td className="right num">{formatPct(s.back)}</td>
							<td className="right num">{formatPct(s.perfect)}</td>
							<td className="right num">{formatPct(s.double)}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
