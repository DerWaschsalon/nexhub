// Farben der Seltenheit wie im Spiel (Gegenstände, Daevanion-Knoten); unbekannte Stufen neutral.
// Im Spiel: Rare grün, Legend blau, Unique gold.
const GRADES: Record<string, string> = {
  Common: "#9aa0a6",
  Rare: "#55ad65",
  Legend: "#3f9fd8",
  Unique: "#c7a82b",
  Epic: "#ff7a59",
  Special: "#38d39f",
};

export const gradeColor = (
  grade: string | null | undefined,
  fallback = "var(--edge)",
): string => (grade && GRADES[grade]) || fallback;
