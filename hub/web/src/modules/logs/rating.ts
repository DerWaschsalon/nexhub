// Bewertung der Ausrüstung gegen Top-Spieler derselben Klasse (Vorbild kisk.app/scoring): Note je
// Gegenstand und der Weg zur Zielnote durch Neuwürfeln (wenigste Versuche im Mittel).
// Gerechnet wird im Hub (API: rating.py, upgrades.py), hier nur Typen und Farben.

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
	/** Prozent je Versuch */
	chance: number;
	/** Versuche im Mittel */
	tries: number;
	/** nur Skills als Ziel: muss nicht vor dem Binden kommen */
	skill_only: boolean;
	tiers: Partial<Record<'best' | 'good' | 'fine', RerollTarget[]>>;
};

/** Ein Teil im Upgrade-Plan; ohne Würfeltabelle gibt es keine Note */
export type PlanPiece = {
	slot: string;
	name: string | null;
	icon: string | null;
	grade: string | null;
	score: number | null;
	letter: string | null;
};

/** Der Plan für ein Teil: Schritte, Note danach bei Pech und Glück (`after`) und im Mittel */
export type UpgradeCard = PlanPiece & {
	steps: RerollStep[];
	after: [number, number];
	mean: number;
	after_letter: string;
	tries: number;
	per_try: number;
};

/** Zielnoten des Upgrade-Plans (upgrades.py: GOALS); die erste gilt, wenn die Adresse keine nennt */
export const GOALS = ['S+', 'BiS'] as const;
export const DEFAULT_GOAL = GOALS[0];

/** Antwort von GET /api/armory/{id}/upgrades: jedes Teil in genau einer Gruppe */
export type UpgradePlan = {
	goal: (typeof GOALS)[number];
	group: string;
	cards: UpgradeCard[];
	bind: PlanPiece[];
	done: PlanPiece[];
	unreachable: (PlanPiece & { reason: 'no_rolls' | 'too_far' })[];
	arcana: PlanPiece[];
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
	upgrade: UpgradeCard | null;
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
