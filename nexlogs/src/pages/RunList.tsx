import type { RunListItem } from '../lib/api.ts';
import { useI18n } from '../lib/i18n.tsx';
import { href, navigate } from '../lib/router.ts';
import { formatDuration } from '../lib/time.ts';
import { useApi } from '../lib/useApi.ts';
import { Problem } from '../components/Problem.tsx';

export function RunList() {
	const { t, num, date } = useI18n();
	const { data, error, loading } = useApi<RunListItem[]>('/api/runs');
	if (error) return <Problem error={error} />;
	if (loading || !data) return <p className="dim">{t('loading')}</p>;
	return (
		<>
			<header className="page-head">
				<h1>{t('list.title')}</h1>
				<p className="dim">{t('list.intro')}</p>
			</header>
			{data.length === 0 ? (
				<p className="dim">{t('list.empty')}</p>
			) : (
				<section className="glass table-wrap list">
					<table className="table">
						<thead>
							<tr>
								<th>{t('col.dungeon')}</th>
								<th>{t('col.bosses')}</th>
								<th className="right">{t('col.duration')}</th>
								<th>{t('col.played')}</th>
								<th>{t('col.uploadedBy')}</th>
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
									<td className="dim">{date(r.start_ms)}</td>
									<td className="dim">{r.uploader}{r.character ? ` (${r.character})` : ''}</td>
								</tr>
							))}
						</tbody>
					</table>
					<p className="dim small">{t('list.count', { n: num(data.length) })}</p>
				</section>
			)}
		</>
	);
}
