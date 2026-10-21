import { href, navigate, useRoute } from './lib/router.ts';
import { RunList } from './pages/RunList.tsx';
import { RunPage } from './pages/RunPage.tsx';

export function App() {
	const route = useRoute();
	return (
		<>
			<header className="top">
				<a className="brand" href={href('/')} onClick={(e) => { e.preventDefault(); navigate('/'); }}>NexLogs</a>
				<a className="dim" href="/hub/runs">NexHub</a>
			</header>
			<main>
				{!route && <p className="notice">Diese Seite gibt es nicht.</p>}
				{route?.page === 'list' && <RunList />}
				{route?.page === 'run' && <RunPage key={JSON.stringify(route.source)} source={route.source} fight={route.fight} />}
			</main>
		</>
	);
}
