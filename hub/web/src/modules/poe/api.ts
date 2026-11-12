// Antworten und Abrufe der Hub-API für Path of Exile (hub/api/nexhub_api/routes/poe.py). Ist das
// Modul im Hub ausgeschaltet (hub_poe_enabled), antwortet jeder Endpunkt mit 404; solange der Hub nach
// dem Start die Liga noch nicht kennt, mit 503 und einer Meldung.
import { api, apiOrNull, send } from '#lib/api.ts';

export const GAMES = ['poe1', 'poe2'] as const;
export type Game = (typeof GAMES)[number];

/** Spiel aus `?game=` der Adresse; unbekannt oder leer heißt PoE 1. */
export const gameFrom = (value: string | null): Game => GAMES.find((g) => g === value) ?? 'poe1';

/** Alle Preise eines Spiels auf poe.ninja */
export const ninjaEconomy = (game: Game) => `https://poe.ninja/${game}/economy`;

/** Treffer der Suche (GET /api/poe/search) */
export type PoeFound = { key: string; name: string; category: string; icon: string | null; price: number; unit: string };

export type PoeDay = { day: string; price: number };

/** Eintrag der Merkliste; price und url sind null, solange es in dieser Liga keinen Preis gibt */
export type PoeWatch = {
	id: number;
	key: string;
	name: string;
	icon: string | null;
	price: number | null;
	change_24h: number | null;
	change_7d: number | null;
	/** Alarm ab dieser Änderung in Prozent (1–1000) */
	threshold: number;
	url: string | null;
	/** Tagespreise der ganzen aktuellen Liga */
	days: PoeDay[];
};

/** Merkliste eines Spiels (GET /api/poe/watches); unit ist null ohne Preise */
export type PoeWatchList = { league: string; unit: string | null; watches: PoeWatch[] };

/** Merkliste holen; null, wenn Path of Exile im Hub ausgeschaltet ist (404). */
export const loadWatches = (game: Game, f: typeof fetch = fetch) =>
	apiOrNull<PoeWatchList>(`/api/poe/watches?game=${game}`, 404, f);

export const searchItems = (game: Game, q: string) =>
	api<PoeFound[]>(`/api/poe/search?${new URLSearchParams({ game, q })}`);

export const addWatch = (game: Game, key: string) => send<PoeWatch>('/api/poe/watches', 'POST', { game, key });

export const setThreshold = (id: number, threshold: number) =>
	send<PoeWatch>(`/api/poe/watches/${id}`, 'PATCH', { threshold });

export const removeWatch = (id: number) => send<void>(`/api/poe/watches/${id}`, 'DELETE');
