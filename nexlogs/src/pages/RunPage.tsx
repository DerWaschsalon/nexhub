import { useState } from 'react';
import { fightUrl, runUrl, type Fight, type Run, type Source } from '../lib/api.ts';
import { useI18n } from '../lib/i18n.tsx';
import { useGameNames } from '../lib/names.ts';
import { href, navigate } from '../lib/router.ts';
import { formatDuration } from '../lib/time.ts';
import { useApi } from '../lib/useApi.ts';
import { BuffTimeline } from '../components/BuffTimeline.tsx';
import { PlayerName } from '../components/ClassBadge.tsx';
import { DpsChart } from '../components/DpsChart.tsx';
import { Problem } from '../components/Problem.tsx';
import { RankBars } from '../components/RankBars.tsx';
import { SkillTable } from '../components/SkillTable.tsx';
import { SkillTimeline } from '../components/SkillTimeline.tsx';

const base = (s: Source) => (s.kind === 'run' ? `/run/${s.id}` : `/r/${s.token}`);

export function RunPage({ source, fight }: { source: Source; fight: string | null }) {
	const { t, date } = useI18n();
	const run = useApi<Run>(runUrl(source));
	if (run.error) return <Problem error={run.error} />;
	if (!run.data) return <p className="dim">{t('loading')}</p>;
	const r = run.data;
	const go = (f: string | null) => navigate(f ? `${base(source)}/kampf/${encodeURIComponent(f)}` : base(source));

	return (
		<>
			<header className="run-head">
				{source.kind === 'run' && <a className="back" href={href('/')} onClick={(e) => { e.preventDefault(); navigate('/'); }}>{t('run.allRuns')}</a>}
				<h1>{r.dungeon}</h1>
				<p className="meta">
					{r.difficulty && <span className="chip">{r.difficulty}</span>}
					<span className={`chip ${r.bosses_killed === r.bosses_total ? 'ok' : 'warn'}`}>{t('run.bosses', { k: r.bosses_killed, t: r.bosses_total })}</span>
					<span className="dim">{date(r.start_ms)}</span>
					<span className="dim">{t('run.fightTime', { d: formatDuration(r.summary.fight_ms) })}</span>
					{r.uploader && <span className="dim">{t('run.by', { name: r.uploader })}</span>}
				</p>
			</header>

			<nav className="fights" aria-label={t('run.fights')}>
				<button type="button" className={fight === null ? 'active' : undefined} onClick={() => go(null)}>
					<strong>{t('run.overall')}</strong>
					<span className="dim num">{formatDuration(r.summary.fight_ms)}</span>
				</button>
				{r.summary.bosses.map((b) => (
					<button type="button" key={b.fight} className={fight === b.fight ? 'active' : undefined} onClick={() => go(b.fight)}>
						<strong>{b.name}</strong>
						<span className="dim num">
							<i className={b.killed ? 'kill' : 'wipe'} aria-label={b.killed ? t('fight.killed') : t('fight.wipe')} />
							{formatDuration(b.duration_ms)}
						</span>
					</button>
				))}
			</nav>

			{fight === null ? (
				<section className="glass pad">
					<h2>{t('run.damageRun')}</h2>
					<RankBars players={r.summary.players} />
				</section>
			) : (
				<FightView key={fight} source={source} fight={fight} />
			)}
		</>
	);
}

type Tab = 'damage' | 'skills' | 'timeline' | 'deaths';

function FightView({ source, fight }: { source: Source; fight: string }) {
	const { t, lang } = useI18n();
	const names = useGameNames(lang);
	const { data, error } = useApi<Fight>(fightUrl(source, fight));
	const [tab, setTab] = useState<Tab>('damage');
	const [player, setPlayer] = useState<string | null>(null);
	if (error) return <Problem error={error} />;
	if (!data) return <p className="dim">{t('loading')}</p>;
	const selected = data.players.find((p) => p.name === player) ?? data.players[0];
	const tabs: [Tab, string][] = [
		['damage', t('tab.damage')],
		['skills', t('tab.skills')],
		['timeline', t('tab.timeline')],
		['deaths', t('tab.deaths', { n: data.deaths.length })]
	];

	const picker = selected && (
		<div className="pick" role="radiogroup" aria-label={t('player.pick')}>
			{data.players.map((p) => (
				<button key={p.name} role="radio" aria-checked={p.name === selected.name}
					className={p.name === selected.name ? 'active' : undefined} onClick={() => setPlayer(p.name)}>
					<PlayerName name={p.name} cls={p.cls} />
				</button>
			))}
		</div>
	);

	return (
		<>
			<div className="tabs" role="tablist">
				{tabs.map(([id, label]) => (
					<button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : undefined} onClick={() => setTab(id)}>{label}</button>
				))}
				<span className={`chip ${data.killed ? 'ok' : 'danger'}`}>{data.killed ? t('fight.killed') : t('fight.wipe')}</span>
			</div>

			{tab === 'damage' && (
				<>
					<section className="glass pad">
						<h2>{t('chart.title')}</h2>
						<DpsChart fight={data} highlight={player} />
					</section>
					<section className="glass pad">
						<h2>{t('rank.title')}</h2>
						<p className="dim hint">{t('rank.hint')}</p>
						<RankBars players={data.players} selected={player} onSelect={(n) => setPlayer(player === n ? null : n)} />
					</section>
				</>
			)}

			{tab === 'skills' && selected && (
				<section className="glass pad">
					{picker}
					<SkillTable key={selected.name} player={selected} boss={data.name} names={names} />
				</section>
			)}

			{tab === 'timeline' && selected && (
				<>
					<section className="glass pad">
						{picker}
						<SkillTimeline key={selected.name} player={selected} durationMs={data.duration_ms} boss={data.name} names={names} />
					</section>
					<section className="glass pad">
						<h2>{t('timeline.buffs')}</h2>
						<BuffTimeline buffs={data.buffs} actor={selected.actor} target={data.target} playerName={selected.name}
							boss={data.name} durationMs={data.duration_ms} names={names} />
					</section>
				</>
			)}

			{tab === 'deaths' && (
				<section className="glass pad">
					{data.deaths.length === 0 ? (
						<p className="dim">{t('deaths.none')}</p>
					) : (
						<table className="table">
							<thead><tr><th>{t('deaths.time')}</th><th>{t('deaths.player')}</th><th>{t('deaths.revived')}</th></tr></thead>
							<tbody>
								{data.deaths.map((d, i) => {
									const p = data.players.find((x) => x.name === d.name);
									return (
										<tr key={i}>
											<td className="num">{formatDuration(d.t_ms)}</td>
											<td><PlayerName name={d.name} cls={p?.cls ?? null} /></td>
											<td className="dim num">{d.revived_ms != null ? t('deaths.after', { d: formatDuration(d.revived_ms - d.t_ms) }) : t('deaths.no')}</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					)}
				</section>
			)}
		</>
	);
}
