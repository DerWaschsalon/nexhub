// Fähigkeiten eines Spielers in einem Kampf, aufgebaut wie bei Warcraft Logs/AbyssLogs: eine Zeile je
// Fähigkeit, aufklappbar, wenn es mehr zu zeigen gibt (Spezialisierungen, Mehrfachtreffer).
import { Fragment, useState } from 'react';
import type { FightPlayer, FightSkill } from '../lib/api.ts';
import { castsOf } from '../lib/casts.ts';
import { classColor } from '../lib/classes.ts';
import { useI18n } from '../lib/i18n.tsx';
import type { GameNames } from '../lib/names.ts';
import { SkillIcon } from './SkillIcon.tsx';

const ROMAN = ['I', 'II', 'III', 'IV', 'V'];

export function SkillTable({ player, boss, names }: { player: FightPlayer; boss: string; names: GameNames }) {
	const { t, num, compact, pct } = useI18n();
	const [open, setOpen] = useState<Set<number>>(new Set());
	const color = classColor(player.cls);
	const max = player.skills[0]?.damage || 1;
	const hits = player.skills.reduce((n, s) => n + s.hits, 0);
	const rate = (v: number) => (v ? pct(v) : '–');
	const count = (v: number, hitsOf: number) => (v ? num(Math.round((v * hitsOf) / 100)) : '–');
	const expandable = (s: FightSkill) => s.specs.length > 0 || s.multi_hits > 0;
	const toggle = (i: number) => setOpen((o) => {
		const n = new Set(o);
		if (n.has(i)) n.delete(i);
		else n.add(i);
		return n;
	});

	return (
		<>
			<header className="skills-head">
				<h2>{t('skills.against', { boss })}</h2>
				<span className="dim">{t('skills.summary', { n: player.skills.length, c: num(castsOf(player).length), h: num(hits) })}</span>
			</header>
			<div className="table-wrap">
				<table className="table skills">
					<thead>
						<tr>
							<th>{t('skills.col.skill')}</th>
							<th className="right">{t('skills.col.damage')}</th>
							<th>{t('skills.col.pct')}</th>
							<th className="right">{t('skills.col.hits')}</th>
							<th className="right">{t('skills.col.crit')}</th>
							<th className="right">{t('skills.col.min')}</th>
							<th className="right">{t('skills.col.max')}</th>
							<th className="right">{t('skills.col.avg')}</th>
							<th className="right">{t('skills.col.back')}</th>
							<th className="right">{t('skills.col.parry')}</th>
							<th className="right">{t('skills.col.perfect')}</th>
							<th className="right">{t('skills.col.double')}</th>
							<th className="right">{t('skills.col.multi')}</th>
						</tr>
					</thead>
					<tbody>
						{player.skills.map((s, i) => {
							const name = names.skill(s.code, s.name);
							const canOpen = expandable(s);
							const isOpen = open.has(i);
							return (
								<Fragment key={`${s.code}-${i}`}>
									<tr className={isOpen ? 'open' : undefined}>
										<td>
											<span className="skill">
												{canOpen ? (
													<button type="button" className="caret" aria-expanded={isOpen}
														aria-label={t('skills.expand', { name })} onClick={() => toggle(i)}>›</button>
												) : (
													<span className="caret" aria-hidden />
												)}
												<SkillIcon code={s.code} />
												<span className="skill-name">
													{name}
													{s.dot && <span className="chip">DoT</span>}
													{s.specs.length > 0 && <span className="specs">{t('skills.specs', { n: s.specs.length })}</span>}
												</span>
											</span>
										</td>
										<td className="right num" title={num(s.damage)}>{compact(s.damage)}</td>
										<td>
											<span className="share">
												<span className="bar thin" aria-hidden><span style={{ width: `${(100 * s.damage) / max}%`, background: color }} /></span>
												<span className="num">{pct(s.share)}</span>
											</span>
										</td>
										<td className="right num">{num(s.hits)}</td>
										<td className="right num">{rate(s.crit)}</td>
										<td className="right num">{s.min ? compact(s.min) : '–'}</td>
										<td className="right num">{s.max ? compact(s.max) : '–'}</td>
										<td className="right num">{s.avg ? compact(s.avg) : '–'}</td>
										<td className="right num">{count(s.back, s.hits)}</td>
										<td className="right num">{count(s.parry, s.hits)}</td>
										<td className="right num">{count(s.perfect, s.hits)}</td>
										<td className="right num">{count(s.double, s.hits)}</td>
										<td className="right num">{s.multi_hits ? `${s.multi_hits}× (${compact(s.multi_damage)})` : '–'}</td>
									</tr>
									{isOpen && (
										<tr className="detail">
											<td colSpan={13}>
												<div className="detail-body">
													<div>
														<span className="dim">{t('skills.specsActive')}</span>
														{s.specs.length ? (
															<span className="spec-slots">
																{ROMAN.map((r, k) => (
																	<span key={r} className={s.specs.includes(k + 1) ? 'on' : undefined}>{r}</span>
																))}
															</span>
														) : (
															<span>{t('skills.noSpecs')}</span>
														)}
													</div>
													{s.multi_hits > 0 && (
														<div className="dim">{t('skills.multiDetail', { n: num(s.multi_hits), d: num(s.multi_damage) })}</div>
													)}
												</div>
											</td>
										</tr>
									)}
								</Fragment>
							);
						})}
					</tbody>
				</table>
			</div>
		</>
	);
}
