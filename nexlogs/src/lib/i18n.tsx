// Sprache der Oberfläche: Englisch (Standard) oder Deutsch, umschaltbar oben rechts.
// Texte hier, Namen von Fähigkeiten und Buffs in names.ts (Spieldaten je Sprache).
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Lang = 'en' | 'de';

const EN = {
	'nav.hub': 'NexHub',
	'list.title': 'Runs',
	'list.intro': 'Everything your NexBoards uploaded, newest first.',
	'list.empty': 'No runs yet. NexBoard uploads every finished dungeon once it is paired with the hub.',
	'list.count': '{n} runs',
	'col.dungeon': 'Dungeon',
	'col.bosses': 'Bosses',
	'col.duration': 'Duration',
	'col.played': 'Played',
	'col.uploadedBy': 'Uploaded by',
	'run.allRuns': 'All runs',
	'run.bosses': '{k}/{t} bosses',
	'run.fightTime': 'Fight time {d}',
	'run.by': 'by {name}',
	'run.overall': 'Overall',
	'run.damageRun': 'Damage over the whole run',
	'run.fights': 'Fights',
	'fight.killed': 'killed',
	'fight.wipe': 'not killed',
	'tab.damage': 'Damage',
	'tab.skills': 'Skills',
	'tab.timeline': 'Timeline',
	'tab.deaths': 'Deaths ({n})',
	'chart.title': 'DPS over time',
	'chart.none': 'This fight has no single hits, so there is no timeline.',
	'chart.label': 'DPS over {d}',
	'rank.title': 'Ranking',
	'rank.hint': 'Click a name to highlight it in the chart.',
	'player.pick': 'Player',
	'skills.against': 'Skills against {boss}',
	'skills.summary': '{n} skills · {c} casts · {h} hits',
	'skills.col.skill': 'Skill',
	'skills.col.damage': 'Damage',
	'skills.col.pct': '%',
	'skills.col.hits': 'Hits',
	'skills.col.crit': 'Crit %',
	'skills.col.min': 'Min',
	'skills.col.max': 'Max',
	'skills.col.avg': 'Avg',
	'skills.col.back': 'Back',
	'skills.col.parry': 'Parry',
	'skills.col.perfect': 'Perfect',
	'skills.col.double': 'Double',
	'skills.col.multi': 'Multi',
	'skills.specs': '{n} spec.',
	'skills.specsActive': 'Active specializations',
	'skills.noSpecs': 'No specialization active.',
	'skills.multiDetail': '{n} multi hits, {d} extra damage',
	'skills.expand': 'Show details for {name}',
	'timeline.opener': 'Opener',
	'timeline.skills': 'Skill timeline',
	'timeline.buffs': 'Buff timeline',
	'timeline.noCasts': 'No casts recorded for this player.',
	'filter.skills': 'Skills',
	'filter.none': 'Deselect all',
	'filter.all': 'Select all',
	'filter.target': 'Target',
	'buffs.onPlayer': 'Buffs on {name}',
	'buffs.onTarget': 'Debuffs on {boss}',
	'buffs.none': 'No buffs recorded.',
	'buffs.uptime': 'Uptime',
	'buffs.stacks': '{n} stacks',
	'deaths.time': 'Time',
	'deaths.player': 'Player',
	'deaths.revived': 'Revived',
	'deaths.after': 'after {d}',
	'deaths.no': 'no',
	'deaths.none': 'Nobody died.',
	'login.title': 'Sign in',
	'login.text': 'Only people signed in to NexHub can see your runs.',
	'login.button': 'Sign in with Discord',
	'loading': 'Loading …',
	'notFound': 'This page does not exist.',
	'lang.label': 'Language'
} as const;

export type Key = keyof typeof EN;

const DE: Record<Key, string> = {
	'nav.hub': 'NexHub',
	'list.title': 'Runs',
	'list.intro': 'Alles, was eure NexBoards hochgeladen haben, neueste zuerst.',
	'list.empty': 'Noch keine Runs. NexBoard lädt jeden fertigen Dungeon hoch, sobald es mit dem Hub gekoppelt ist.',
	'list.count': '{n} Runs',
	'col.dungeon': 'Dungeon',
	'col.bosses': 'Bosse',
	'col.duration': 'Dauer',
	'col.played': 'Gespielt',
	'col.uploadedBy': 'Hochgeladen von',
	'run.allRuns': 'Alle Runs',
	'run.bosses': '{k}/{t} Bosse',
	'run.fightTime': 'Kampfzeit {d}',
	'run.by': 'von {name}',
	'run.overall': 'Gesamt',
	'run.damageRun': 'Schaden im ganzen Run',
	'run.fights': 'Kämpfe',
	'fight.killed': 'besiegt',
	'fight.wipe': 'nicht besiegt',
	'tab.damage': 'Schaden',
	'tab.skills': 'Fähigkeiten',
	'tab.timeline': 'Zeitleiste',
	'tab.deaths': 'Tode ({n})',
	'chart.title': 'DPS-Verlauf',
	'chart.none': 'Für diesen Kampf gibt es keine Einzeltreffer, deshalb keinen Verlauf.',
	'chart.label': 'DPS-Verlauf über {d}',
	'rank.title': 'Rangliste',
	'rank.hint': 'Auf einen Namen klicken hebt ihn im Verlauf hervor.',
	'player.pick': 'Spieler',
	'skills.against': 'Fähigkeiten gegen {boss}',
	'skills.summary': '{n} Fähigkeiten · {c} Zauber · {h} Treffer',
	'skills.col.skill': 'Fähigkeit',
	'skills.col.damage': 'Schaden',
	'skills.col.pct': '%',
	'skills.col.hits': 'Treffer',
	'skills.col.crit': 'Krit %',
	'skills.col.min': 'Min',
	'skills.col.max': 'Max',
	'skills.col.avg': 'Ø',
	'skills.col.back': 'Rücken',
	'skills.col.parry': 'Parade',
	'skills.col.perfect': 'Perfekt',
	'skills.col.double': 'Doppelt',
	'skills.col.multi': 'Multi',
	'skills.specs': '{n} Spez.',
	'skills.specsActive': 'Aktive Spezialisierungen',
	'skills.noSpecs': 'Keine Spezialisierung aktiv.',
	'skills.multiDetail': '{n} Mehrfachtreffer, {d} zusätzlicher Schaden',
	'skills.expand': 'Details zu {name} zeigen',
	'timeline.opener': 'Opener',
	'timeline.skills': 'Fähigkeiten-Zeitleiste',
	'timeline.buffs': 'Buff-Zeitleiste',
	'timeline.noCasts': 'Für diesen Spieler sind keine Zauber aufgezeichnet.',
	'filter.skills': 'Fähigkeiten',
	'filter.none': 'Alle abwählen',
	'filter.all': 'Alle auswählen',
	'filter.target': 'Ziel',
	'buffs.onPlayer': 'Buffs auf {name}',
	'buffs.onTarget': 'Debuffs auf {boss}',
	'buffs.none': 'Keine Buffs aufgezeichnet.',
	'buffs.uptime': 'Laufzeit',
	'buffs.stacks': '{n} Stapel',
	'deaths.time': 'Zeit',
	'deaths.player': 'Spieler',
	'deaths.revived': 'Wiederbelebt',
	'deaths.after': 'nach {d}',
	'deaths.no': 'nein',
	'deaths.none': 'Niemand ist gestorben.',
	'login.title': 'Anmelden',
	'login.text': 'Eure Runs sieht nur, wer im NexHub angemeldet ist.',
	'login.button': 'Mit Discord anmelden',
	'loading': 'Lädt …',
	'notFound': 'Diese Seite gibt es nicht.',
	'lang.label': 'Sprache'
};

const TEXTS: Record<Lang, Record<Key, string>> = { en: EN, de: DE };
const LOCALE: Record<Lang, string> = { en: 'en-US', de: 'de-DE' };
const STORAGE = 'nexlogs.lang';

function initialLang(): Lang {
	try {
		const saved = localStorage.getItem(STORAGE);
		if (saved === 'en' || saved === 'de') return saved;
	} catch {
		/* privates Fenster: Standard */
	}
	return 'en';
}

export type I18n = {
	lang: Lang;
	setLang: (l: Lang) => void;
	t: (key: Key, vars?: Record<string, string | number>) => string;
	num: (n: number) => string;
	compact: (n: number) => string;
	pct: (n: number) => string;
	date: (ms: number) => string;
};

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
	const [lang, setLangState] = useState<Lang>(initialLang);
	useEffect(() => {
		document.documentElement.lang = lang;
	}, [lang]);
	const value = useMemo<I18n>(() => {
		const locale = LOCALE[lang];
		const number = new Intl.NumberFormat(locale);
		const dateTime = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
		const one = (n: number) => n.toLocaleString(locale, { maximumFractionDigits: 1 });
		return {
			lang,
			setLang: (l) => {
				setLangState(l);
				try {
					localStorage.setItem(STORAGE, l);
				} catch {
					/* ohne Speicher gilt die Wahl nur bis zum Neuladen */
				}
			},
			t: (key, vars) => TEXTS[lang][key].replace(/\{(\w+)\}/g, (_, k) => String(vars?.[k] ?? `{${k}}`)),
			num: (n) => number.format(Math.round(n)),
			// 1.2M · 38.4K · 950, auf Deutsch mit Komma (1,2M), wie bei AbyssLogs: passt in schmale Spalten
			compact: (n) => {
				if (n >= 1e6) return `${one(n / 1e6)}M`;
				if (n >= 1e4) return `${one(n / 1e3)}K`;
				return number.format(Math.round(n));
			},
			pct: (n) => `${one(n)}%`,
			date: (ms) => dateTime.format(new Date(ms))
		};
	}, [lang]);
	return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
	const v = useContext(Ctx);
	if (!v) throw new Error('useI18n außerhalb von I18nProvider');
	return v;
}
