// Sprache des Hubs: Englisch (Standard) oder Deutsch, umschaltbar in der Seitenleiste und im
// öffentlichen Kopf. Der Kern hält die Wahl; Kern und Module bringen ihre Texte mit
// (defineTexts), lib/modules.ts meldet sie an. Ohne Übersetzung erscheint der Schlüssel.

export type Lang = 'en' | 'de';
export const LANGS: Lang[] = ['en', 'de'];

/** Texte eines Bereichs. Deutsch muss jeden englischen Schlüssel haben, sonst meckert svelte-check. */
export type Texts = { en: Record<string, string>; de: Record<string, string> };
export function defineTexts<K extends string>(en: Record<K, string>, de: Record<K, string>): Texts {
	return { en, de };
}

const LOCALE: Record<Lang, string> = { en: 'en-US', de: 'de-DE' };
const STORAGE = 'nexhub.lang';
const dictionary: Texts = { en: {}, de: {} };

export function addTexts(texts: Texts): void {
	Object.assign(dictionary.en, texts.en);
	Object.assign(dictionary.de, texts.de);
}

function initialLang(): Lang {
	try {
		const saved = localStorage.getItem(STORAGE);
		if (saved === 'en' || saved === 'de') return saved;
	} catch {
		/* privates Fenster: Standard */
	}
	return 'en';
}

class I18n {
	lang = $state<Lang>(initialLang());
	locale = $derived(LOCALE[this.lang]);

	set(lang: Lang): void {
		this.lang = lang;
		document.documentElement.lang = lang;
		try {
			localStorage.setItem(STORAGE, lang);
		} catch {
			/* ohne Speicher gilt die Wahl nur bis zum Neuladen */
		}
	}
}

export const i18n = new I18n();

/** Text zum Schlüssel, `{name}` wird aus `vars` ersetzt. Reaktiv: wechselt mit der Sprache. */
export function t(key: string, vars?: Record<string, string | number>): string {
	const text = dictionary[i18n.lang][key] ?? dictionary.en[key] ?? key;
	return vars ? text.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`)) : text;
}
