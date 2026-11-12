// Deckkraft der Ebenen einer Klassenfigur (data/figureZones.ts, SLOT_LAYERS), damit die Figur beim Zeigen den
// Platz unter dem Zeiger pixelgenau findet statt über Rechtecke.

/** ab dieser Deckkraft gehört ein Pixel zum Platz (wie in hub/tools/figure_layers.py) */
const MIN_ALPHA = 40;

type Mask = { width: number; height: number; alpha: Uint8Array };

export class FigureMasks {
	private constructor(private readonly masks: [string, Mask][]) {}

	/** Liest die Ebenen (Platz, Bild) einmal ein; eine Ebene, die nicht lädt, fehlt dann einfach. */
	static async load(layers: [string, string][]): Promise<FigureMasks> {
		const read = await Promise.all(layers.map(async ([slot, src]) => [slot, await readMask(src)] as const));
		return new FigureMasks(read.filter((entry): entry is [string, Mask] => entry[1] !== null));
	}

	/** Platz an der Stelle (Anteil 0 bis 1 von Breite und Höhe der Figur), sonst null */
	slotAt(fx: number, fy: number): string | null {
		for (const [slot, mask] of this.masks) {
			const x = Math.floor(fx * mask.width);
			const y = Math.floor(fy * mask.height);
			const inside = x >= 0 && y >= 0 && x < mask.width && y < mask.height;
			if (inside && mask.alpha[y * mask.width + x] > MIN_ALPHA) return slot;
		}
		return null;
	}
}

async function readMask(src: string): Promise<Mask | null> {
	try {
		const img = new Image();
		img.src = src;
		await img.decode();
		const canvas = document.createElement('canvas');
		canvas.width = img.naturalWidth;
		canvas.height = img.naturalHeight;
		const ctx = canvas.getContext('2d', { willReadFrequently: true });
		if (!ctx) return null;
		ctx.drawImage(img, 0, 0);
		const rgba = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
		const alpha = new Uint8Array(canvas.width * canvas.height);
		for (let i = 0; i < alpha.length; i++) alpha[i] = rgba[i * 4 + 3];
		return { width: canvas.width, height: canvas.height, alpha };
	} catch {
		return null;
	}
}
