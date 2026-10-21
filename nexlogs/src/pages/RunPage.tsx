import { useState } from 'react';
import { fightUrl, runUrl, type Fight, type Run, type Source } from '../lib/api.ts';
import { formatDate, formatDuration } from '../lib/format.ts';
import { href, navigate } from '../lib/router.ts';
import { useApi } from '../lib/useApi.ts';
import { PlayerName } from '../components/ClassBadge.tsx';
import { DpsChart } from '../components/DpsChart.tsx';
import { Problem } from '../components/Problem.tsx';
import { RankBars } from '../components/RankBars.tsx';
import { SkillTable } from '../components/SkillTable.tsx';

const base = (s: Source) => (s.kind === 'run' ? `/run/${s.id}` : `/r/${s.token}`);

export function RunPage({ source, fight }: { source: Source; fight: string | null }) {
	const run = useApi<Run>(runUrl(source));
	if (run.error) return <Problem error={run.error} />;
	if (!run.data) return <p className="dim">Lädt …</p>;
	const r = run.data;
	const go = (f: string | null) => navigate(f ? `${base(source)}/kampf/${encodeURIComponent(f)}` : base(source));

	return (
		<>
			<header className="run-head">
				{source.kind === 'run' && <a className="back" href={href('/')} onClick={(e) => { e.preventDefault(); navigate('/'); }}>Alle Runs</a>}
				<h1>{r.dungeon}</h1>
				<p className="meta">
					{r.difficulty && <span className="chip">{r.difficulty}</span>}
					<span className={`chip ${r.bosses_killed === r.bosses_total ? 'ok' : 'warn'}`}>{r.bosses_killed}/{r.bosses_total} Bosse</span>
					<span className="dim">{formatDate(r.start_ms)}</span>
					<span className="dim">Kampfzeit {formatDuration(r.summary.fight_ms)}</span>
					{r.uploader && <span className="dim">von {r.uploader}</span>}
				</p>
			</header>

			<nav className="fights" aria-label="Kämpfe">
				<button type="button" className={fight === null ? 'active' : undefined} onClick={() => go(null)}>
					<strong>Gesamt</strong>
					<span className="dim num">{formatDuration(r.summary.fight_ms)}</span>
				</button>
				{r.summary.bosses.map((b) => (
					<button type="button" key={b.fight} className={fight === b.fight ? 'active' : undefined} onClick={() => go(b.fight)}>
						<strong>{b.name}</strong>
						<span className="dim num">
							<i className={b.killed ? 'kill' : 'wipe'} aria-label={b.killed ? 'besiegt' : 'nicht besiegt'} />
							{formatDuration(b.duration_ms)}
						</span>
					</button>
				))}
			</nav>

			{fight === null ? (
				<section className="glass pad">
					<h2>Schaden im ganzen Run</h2>
					<RankBars players={r.summary.players} />
				</section>
			) : (
				<FightView key={fight} source={source} fight={fight} />
			)}
		</>
	);
}

type Tab = 'schaden' | 'skills' | 'tode';

function FightView({ source, fight }: { source: Source; fight: string }) {
	const { data, error } = useApi<Fight>(fightUrl(source, fight));
	const [tab, setTab] = useState<Tab>('schaden');
	const [player, setPlayer] = useState<string | null>(null);
	if (error) return <Problem error={error} />;
	if (!data) return <p className="dim">Lädt …</p>;
	const selected = data.players.find((p) => p.name === player) ?? data.players[0];

	return (
		<>
			<div className="tabs" role="tablist">
				{([['schaden', 'Schaden'], ['skills', 'Fähigkeiten'], ['tode', `Tode (${data.deaths.length})`]] as const).map(([id, label]) => (
					<button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : undefined} onClick={() => setTab(id)}>{label}</button>
				))}
				<span className={`chip ${data.killed ? 'ok' : 'danger'}`}>{data.killed ? 'besiegt' : 'nicht besiegt'}</span>
			</div>

			{tab === 'schaden' && (
				<>
					<section className="glass pad">
						<h2>DPS-Verlauf</h2>
						<DpsChart fight={data} highlight={player} />
					</section>
					<section className="glass pad">
						<h2>Rangliste</h2>
						<p className="dim hint">Auf einen Namen klicken hebt ihn im Verlauf hervor.</p>
						<RankBars players={data.players} selected={player} onSelect={(n) => setPlayer(player === n ? null : n)} />
					</section>
				</>
			)}

			{tab === 'skills' && selected && (
				<section className="glass pad">
					<div className="pick" role="radiogroup" aria-label="Spieler">
						{data.players.map((p) => (
							<button key={p.name} role="radio" aria-checked={p.name === selected.name}
								className={p.name === selected.name ? 'active' : undefined} onClick={() => setPlayer(p.name)}>
								<PlayerName name={p.name} cls={p.cls} />
							</button>
						))}
					</div>
					<SkillTable player={selected} />
				</section>
			)}

			{tab === 'tode' && (
				<section className="glass pad">
					{data.deaths.length === 0 ? (
						<p className="dim">Niemand ist gestorben.</p>
					) : (
						<table className="table">
							<thead><tr><th>Zeit</th><th>Spieler</th><th>Wiederbelebt</th></tr></thead>
							<tbody>
								{data.deaths.map((d, i) => {
									const p = data.players.find((x) => x.name === d.name);
									return (
										<tr key={i}>
											<td className="num">{formatDuration(d.t_ms)}</td>
											<td><PlayerName name={d.name} cls={p?.cls ?? null} /></td>
											<td className="dim num">{d.revived_ms != null ? `nach ${formatDuration(d.revived_ms - d.t_ms)}` : 'nein'}</td>
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
