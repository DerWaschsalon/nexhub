// Farben für Spieler in Diagrammen. Kategorische Palette (8 Farben, dunkle Stufen), geprüft auf der
// Hub-Fläche: unterscheidbar auch bei Farbsehschwäche. Klassenfarben taugen dafür nicht – zwei
// Spieler derselben Klasse wären gleich.
const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
const OTHER = '#8a90a3';

/** Feste Farbe je Spieler: Reihenfolge des ganzen Runs, damit sie in jedem Kampf gleich bleibt. */
export function playerColors(order: string[]): (name: string) => string {
	const index = new Map(order.map((name, i) => [name, i]));
	return (name) => SERIES[index.get(name) ?? -1] ?? OTHER;
}
