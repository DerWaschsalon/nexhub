import type { ApiError } from '../lib/api.ts';
import { useI18n } from '../lib/i18n.tsx';

/** Fehler der API als Hinweis; ohne Anmeldung ein Weg zum Login des Hubs. */
export function Problem({ error }: { error: ApiError }) {
	const { t } = useI18n();
	if (error.status === 401) {
		const next = encodeURIComponent(location.pathname);
		return (
			<section className="glass pad problem">
				<h2>{t('login.title')}</h2>
				<p className="dim">{t('login.text')}</p>
				<a className="btn" href={`/login?next=${next}`}>{t('login.button')}</a>
			</section>
		);
	}
	return <p className="notice" role="alert">{error.message}</p>;
}
