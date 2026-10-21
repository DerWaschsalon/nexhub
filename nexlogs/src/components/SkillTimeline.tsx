// Fähigkeiten-Zeitleiste: der Opener als Reihe, darunter je Fähigkeit eine Spur mit jedem Zauber.
// Rechts lassen sich Fähigkeiten ein- und ausblenden.
import { useMemo, useState } from 'react';
import type { FightPlayer } from '../lib/api.ts';
import { castsOf } from '../lib/casts.ts';
import { classColor } from '../lib/classes.ts';
import { useI18n } from '../lib/i18n.tsx';
import type { GameNames } from '../lib/names.ts';
import { formatDuration, timeTicks } from '../lib/time.ts';
import { SkillIcon } from './SkillIcon.tsx';

const OPENER = 24; // so viele Zauber zeigt der Opener

export function SkillTimeline({ player, durationMs, boss, names }: {
	player: FightPlayer;
	durationMs: number;
	boss: string;
	names: GameNames;
}) {
	const { t } = useI18n();
	const casts = useMemo(() => castsOf(player), [player]);
	// Fähigkeiten in der Reihenfolge ihres ersten Einsatzes
	const skills = useMemo(() => {
		const seen = new Map<string, { code: number | null; name: string; times: number[] }>();
		for (const c of casts) {
			const key = `${c.code}|${c.name}`;
			if (!seen.has(key)) seen.set(key, { code: c.code, name: c.name, times: [] });
			seen.get(key)!.times.push(c.t);
		}
		return [...seen.entries()].map(([key, v]) => ({ key, ...v }));
	}, [casts]);
	const [hidden, setHidden] = useState<Set<string>>(new Set());
	const color = classColor(player.cls);

	if (!casts.length) return <p className="dim">{t('timeline.noCasts')}</p>;

	const shown = skills.filter((s) => !hidden.has(s.key));
	const pos = (ms: number) => `${Math.min(100, Math.max(0, (100 * ms) / durationMs))}%`;
	const toggle = (key: string) => setHidden((h) => {
		const n = new Set(h);
		if (n.has(key)) n.delete(key);
		else n.add(key);
		return n;
	});

	return (
		<div className="timeline-layout">
			<div className="timeline-main">
				<h3>{t('timeline.opener')}</h3>
				<ol className="opener">
					{casts.slice(0, OPENER).map((c, i) => (
						<li key={i} title={`${formatDuration(c.t)} · ${names.skill(c.code, c.name)}`}>
							<SkillIcon code={c.code} size={30} />
							<span>{names.skill(c.code, c.name)}</span>
						</li>
					))}
				</ol>

				<h3>{t('timeline.skills')}</h3>
				<div className="lanes" style={{ ['--lane-color' as string]: color }}>
					<div className="lane axis-lane" aria-hidden>
						<span />
						<div className="track">
							{timeTicks(durationMs).map((ms) => (
								<span key={ms} className="tick" style={{ left: pos(ms) }}>{formatDuration(ms)}</span>
							))}
						</div>
					</div>
					{shown.map((s) => (
						<div className="lane" key={s.key}>
							<span className="lane-name"><SkillIcon code={s.code} size={22} />{names.skill(s.code, s.name)}</span>
							<div className="track">
								{s.times.map((ms, i) => (
									<span key={i} className="cast" style={{ left: pos(ms) }} title={formatDuration(ms)} />
								))}
							</div>
						</div>
					))}
				</div>
			</div>

			<aside className="timeline-filter">
				<div className="filter-head">
					<strong>{t('filter.skills')} <span className="dim">{shown.length}</span></strong>
					<button type="button" className="link" onClick={() => setHidden(hidden.size === skills.length ? new Set() : new Set(skills.map((s) => s.key)))}>
						{hidden.size === skills.length ? t('filter.all') : t('filter.none')}
					</button>
				</div>
				<ul>
					{skills.map((s) => (
						<li key={s.key}>
							<label>
								<input type="checkbox" checked={!hidden.has(s.key)} onChange={() => toggle(s.key)} />
								<SkillIcon code={s.code} size={20} />
								<span>{names.skill(s.code, s.name)}</span>
							</label>
						</li>
					))}
				</ul>
				<div className="filter-head">
					<strong>{t('filter.target')}</strong>
				</div>
				<p className="target">{boss}</p>
			</aside>
		</div>
	);
}
