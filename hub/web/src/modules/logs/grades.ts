// Farben der Seltenheit wie im Spiel (Gegenstände, Daevanion-Knoten); unbekannte Stufen neutral.
const GRADES: Record<string, string> = {
  Common: "#9aa0a6",
  Rare: "#4f9cf0",
  Legend: "#f0b429",
  Unique: "#c77dff",
  Epic: "#ff7a59",
  Special: "#38d39f",
};

export const gradeColor = (
  grade: string | null | undefined,
  fallback = "var(--edge)",
): string => (grade && GRADES[grade]) || fallback;
