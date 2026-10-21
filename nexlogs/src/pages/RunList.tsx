import type { RunListItem } from '../lib/api.ts';
import { formatDate, formatDuration, formatNumber } from '../lib/format.ts';
import { href, navigate } from '../lib/router.ts';
import { useApi } from '../lib/useApi.ts';
import { Problem } from '../components/Problem.tsx';

export function RunList() {
	const { data, error, loading } = useApi<RunListItem[]>('/api/runs');
	if (error) return <Problem error={error} />;
	if (loading || !data) return <p className="dim">Lädt …</p>;
	return (
		<>
			<header className="page-head">
				<h1>Runs</h1>
				<p className="dim">Alles, was eure NexBoards hochgeladen haben, neueste zuerst.</p>
			</header>
			{data.length === 0 ? (
				<p className="dim">Noch keine Runs. NexBoard lädt nach jedem fertigen Dungeon automatisch hoch, sobald es mit dem Hub gekoppelt ist.</p>
			) : (
				<section className="glass table-wrap list">
					<table className="table">
						<thead>
							<tr>
								<th>Dungeon</th>
								<th>Bosse</th>
								<th className="right">Dauer</th>
								<th>Gespielt</th>
								<th>Hochgeladen von</th>
							</tr>
						</thead>
						<tbody>
							{data.map((r) => (
								<tr key={r.id} onClick={() => navigate(`/run/${r.id}`)}>
									<td>
										<a href={href(`/run/${r.id}`)} onClick={(e) => { e.preventDefault(); navigate(`/run/${r.id}`); }}>
											<strong>{r.dungeon}</strong>
										</a>
										{r.difficulty && <span className="chip">{r.difficulty}</span>}
									</td>
									<td>
										<span className={`chip ${r.bosses_killed === r.bosses_total ? 'ok' : 'warn'}`}>
											{r.bosses_killed}/{r.bosses_total}
										</span>
									</td>
									<td className="right num">{formatDuration(r.end_ms - r.start_ms)}</td>
									<td className="dim">{formatDate(r.start_ms)}</td>
									<td className="dim">{r.uploader}{r.character ? ` (${r.character})` : ''}</td>
								</tr>
							))}
						</tbody>
					</table>
					<p className="dim small">{formatNumber(data.length)} Runs</p>
				</section>
			)}
		</>
	);
}
