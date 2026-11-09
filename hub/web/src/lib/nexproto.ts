// Erzeugt von proto/nexproto/codegen.py, nicht von Hand ändern.

export type GameClass = { key: string; jobId: number; en: string; de: string; color: string };

/** AION-2-Klassen in der Reihenfolge des Spiels */
export const CLASSES: readonly GameClass[] = [
  { key: "gladiator", jobId: 11, en: "Gladiator", de: "Gladiator", color: "#4FD1C5" },
  { key: "templar", jobId: 12, en: "Templar", de: "Templer", color: "#5F8CFF" },
  { key: "assassin", jobId: 13, en: "Assassin", de: "Assassine", color: "#7BE35A" },
  { key: "ranger", jobId: 14, en: "Ranger", de: "Waldläufer", color: "#41D98A" },
  { key: "sorcerer", jobId: 15, en: "Sorcerer", de: "Magier", color: "#9A6BFF" },
  { key: "spiritmaster", jobId: 16, en: "Spiritmaster", de: "Beschwörer", color: "#E06BFF" },
  { key: "cleric", jobId: 17, en: "Cleric", de: "Kleriker", color: "#F2C15A" },
  { key: "chanter", jobId: 18, en: "Chanter", de: "Kantor", color: "#FF9A3D" },
  { key: "brawler", jobId: 19, en: "Brawler", de: "Faustkämpfer", color: "#E85D5D" },
];
export const UNKNOWN_CLASS_COLOR = '#8E8E93';
