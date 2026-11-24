// Antwort von GET /api/loot (hub/api/nexhub_api/routes/loot.py).

export type LootItem = {
	item_id: number;
	/** Siege, bei denen der Gegenstand zum Würfeln stand */
	drops: number;
	kills: number;
	/** „1 zu N“ mit Band; null bei zu wenigen Siegen */
	one_in: number | null;
	one_in_low: number | null;
	one_in_high: number | null;
};

export type LootBoss = { mob: number; name: string; kills: number; items: LootItem[] };

export type LootDungeon = {
	dungeon_id: number;
	dungeon: string;
	difficulty: string | null;
	/** Runs, deren Aufnahme Beute meldet */
	runs: number;
	bosses: LootBoss[];
};

export type Loot = { min_kills: number; dungeons: LootDungeon[] };
