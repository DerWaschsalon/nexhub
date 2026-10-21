import { useEffect, useState } from 'react';
import { api, ApiError } from './api.ts';

export type Loaded<T> = { data: T | null; error: ApiError | null; loading: boolean };

/** Lädt JSON von der API, neu bei geänderter Adresse; `null` lädt nichts. */
export function useApi<T>(url: string | null): Loaded<T> {
	const [state, setState] = useState<Loaded<T>>({ data: null, error: null, loading: !!url });
	useEffect(() => {
		if (!url) return setState({ data: null, error: null, loading: false });
		let live = true;
		setState((s) => ({ ...s, loading: true, error: null }));
		api<T>(url)
			.then((data) => live && setState({ data, error: null, loading: false }))
			.catch((e) => live && setState({ data: null, error: e instanceof ApiError ? e : new ApiError(0, String(e)), loading: false }));
		return () => {
			live = false;
		};
	}, [url]);
	return state;
}
