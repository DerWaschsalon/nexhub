// Mini-Router ohne Bibliothek: Pfade unter /logs/, Links per History-API.
import { useEffect, useState } from 'react';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

export type Route =
	| { page: 'list' }
	| { page: 'run'; source: { kind: 'run'; id: string } | { kind: 'shared'; token: string }; fight: string | null };

export function parse(pathname: string): Route | null {
	const path = pathname.startsWith(BASE) ? pathname.slice(BASE.length) : pathname;
	const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
	if (parts.length === 0) return { page: 'list' };
	const [kind, key, sub, fight] = parts;
	if ((kind === 'run' || kind === 'r') && key && (sub === undefined || (sub === 'kampf' && fight))) {
		const source = kind === 'run' ? { kind: 'run' as const, id: key } : { kind: 'shared' as const, token: key };
		return { page: 'run', source, fight: fight ?? null };
	}
	return null;
}

export const href = (path: string) => `${BASE}${path}`;

export function navigate(path: string) {
	history.pushState(null, '', href(path));
	dispatchEvent(new PopStateEvent('popstate'));
	scrollTo({ top: 0 });
}

export function useRoute(): Route | null {
	const [path, setPath] = useState(location.pathname);
	useEffect(() => {
		const update = () => setPath(location.pathname);
		addEventListener('popstate', update);
		return () => removeEventListener('popstate', update);
	}, []);
	return parse(path);
}
