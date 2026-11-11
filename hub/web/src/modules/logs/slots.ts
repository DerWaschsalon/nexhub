// Ausrüstungsplätze wie im Ausrüstungsfenster des Spiels: links Waffen und Rüstung, rechts Schmuck,
// dazu die Arkana. Profil und Vergleich zeigen sie in dieser Reihenfolge.
export const LEFT = ['MainHand', 'SubHand', 'Helmet', 'Shoulder', 'Torso', 'Pants', 'Gloves', 'Boots', 'Cape', 'Belt'];
export const RIGHT = ['Necklace', 'Earring1', 'Earring2', 'Ring1', 'Ring2', 'Bracelet1', 'Bracelet2', 'Amulet', 'Rune1', 'Rune2'];
export const ARCANA = ['Arcana1', 'Arcana2', 'Arcana3', 'Arcana4', 'Arcana5'];
/** Ausrüstungsfenster im Spiel: zwei Spalten, Zeile für Zeile; Plätze ohne Gegenstand bleiben leer sichtbar */
export const GAME_ORDER = [
	'MainHand', 'SubHand', 'Helmet', 'Shoulder', 'Torso', 'Belt', 'Pants', 'Gloves', 'Cape', 'Boots',
	'Earring1', 'Earring2', 'Necklace', 'Amulet', 'Brooch1', 'Brooch2', 'Ring1', 'Ring2',
	'Bracelet1', 'Bracelet2', 'Rune1', 'Rune2'
];
