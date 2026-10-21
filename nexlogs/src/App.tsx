import { I18nProvider, useI18n, type Lang } from './lib/i18n.tsx';
import { href, navigate, useRoute } from './lib/router.ts';
import { RunList } from './pages/RunList.tsx';
import { RunPage } from './pages/RunPage.tsx';

function LangSwitch() {
	const { lang, setLang, t } = useI18n();
	return (
		<div className="lang" role="group" aria-label={t('lang.label')}>
			{(['en', 'de'] as Lang[]).map((l) => (
				<button key={l} type="button" aria-pressed={lang === l} className={lang === l ? 'active' : undefined} onClick={() => setLang(l)}>
					{l.toUpperCase()}
				</button>
			))}
		</div>
	);
}

function Shell() {
	const { t } = useI18n();
	const route = useRoute();
	return (
		<>
			<header className="top">
				<a className="brand" href={href('/')} onClick={(e) => { e.preventDefault(); navigate('/'); }}>NexLogs</a>
				<nav>
					<a className="dim" href="/hub/runs">{t('nav.hub')}</a>
					<LangSwitch />
				</nav>
			</header>
			<main>
				{!route && <p className="notice">{t('notFound')}</p>}
				{route?.page === 'list' && <RunList />}
				{route?.page === 'run' && <RunPage key={JSON.stringify(route.source)} source={route.source} fight={route.fight} />}
			</main>
		</>
	);
}

export function App() {
	return (
		<I18nProvider>
			<Shell />
		</I18nProvider>
	);
}
