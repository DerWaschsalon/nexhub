import { useState } from 'react';
import { skillIcon } from '../lib/skillIcons.ts';

// Standardangriff: gekreuzte Schwerter wie im Meter (Lucide „swords“)
const SWORDS = (
	<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
		<path d="M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M14.5 6.5 18 3h3v3l-3.5 3.5M5 14l4 4M7 17l-3 3M3 19l2 2" />
	</svg>
);

export function SkillIcon({ code, size = 28 }: { code: number | null; size?: number }) {
	const src = skillIcon(code);
	const [broken, setBroken] = useState(false);
	if (src === 'auto' || !src || broken) {
		return (
			<span className="skill-icon fallback" style={{ width: size, height: size }} aria-hidden>
				{src === 'auto' ? SWORDS : null}
			</span>
		);
	}
	return (
		<img className="skill-icon" src={src} width={size} height={size} alt="" loading="lazy"
			referrerPolicy="no-referrer" onError={() => setBroken(true)} />
	);
}
