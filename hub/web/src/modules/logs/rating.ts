// Bewertung der Ausrüstung gegen Top-Spieler derselben Klasse (Vorbild kisk.app/scoring): Note je
// Gegenstand und der Weg zu Best in Slot durch Neuwürfeln (fehlende ideale Zeilen nach Priorität).
// Gerechnet wird im Hub (API), hier nur Typen und Farben.

/** Eine Zeile der Seelenbindung: Wert, Höchstwert dieses Gegenstands, Anteil der Top-Spieler mit ihr.
 *  Manasteine und Göttersteine (stone, godstone) kommen nur von den BiS-Listen. */
export type RatedLine = {
	kind: 'stat' | 'skill' | 'stone' | 'godstone';
	name: string;
	value: number;
	unit: string;
	max: number | null;
	share: number;
};

/** Ziel beim Neuwürfeln und was es an Punkten bringt (niedrigster bis höchster Wurf) */
export type RerollTarget = { name: string; gain_lo: number; gain_hi: number };

/** Ein Schritt: diese Zeile neu würfeln, bis eines der Ziele kommt */
export type RerollStep = {
	line: string;
	chance: number;
	tiers: Partial<Record<'best' | 'good' | 'fine', RerollTarget[]>>;
};

export type Rating = {
	slot: string;
	score: number;
	letter: string;
	lines: RatedLine[];
	ideal: number;
	ideal_of: number;
	/** Seite mit den Würfeldaten (MetaBot.GG), muss verlinkt werden */
	source: string | null;
	upgrade: { steps: RerollStep[]; after: [number, number]; after_letter: string } | null;
};

/** Bewertung eines Charakters: je Ausrüstungsplatz, dazu woher die Vergleichsgruppe stammt */
export type Ratings = { size: number; group: string; items: Rating[] };

/** Farbe je Note, von BiS (orange) bis D (grau) */
export const LETTER_COLOR: Record<string, string> = {
	BiS: '#ff9d3a',
	'S+': '#f2c522',
	S: '#c7a82b',
	A: '#3fd6e8',
	B: '#4f9cf0',
	C: '#9aa0a6',
	D: '#6b7280'
};

/** Bewertung je Platz zum schnellen Nachschlagen */
export function bySlot(ratings: Ratings | null | undefined): Map<string, Rating> {
	return new Map((ratings?.items ?? []).map((r) => [r.slot, r]));
}
