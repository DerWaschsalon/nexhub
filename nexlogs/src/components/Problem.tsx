import type { ApiError } from '../lib/api.ts';

/** Fehler der API als Hinweis; ohne Anmeldung ein Weg zum Login des Hubs. */
export function Problem({ error }: { error: ApiError }) {
	if (error.status === 401) {
		const next = encodeURIComponent(location.pathname);
		return (
			<section className="glass pad problem">
				<h2>Anmelden</h2>
				<p className="dim">Eure Runs sieht nur, wer im NexHub angemeldet ist.</p>
				<a className="btn" href={`/login?next=${next}`}>Mit Discord anmelden</a>
			</section>
		);
	}
	return <p className="notice" role="alert">{error.message}</p>;
}
