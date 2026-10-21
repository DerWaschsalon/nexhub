import { classInfo } from '../lib/classes.ts';
import { useI18n } from '../lib/i18n.tsx';

/** Klassensymbol aus dem Spiel; ohne bekannte Klasse ein neutraler Punkt. */
export function ClassIcon({ cls, size = 22 }: { cls: string | null; size?: number }) {
	const { lang } = useI18n();
	const info = classInfo(cls, lang);
	if (!info) return <span className="class-dot" style={{ width: size, height: size }} aria-hidden />;
	return <img className="class-icon" src={info.icon} alt={info.label} title={info.label} width={size} height={size} />;
}

/** Spielername in Klassenfarbe mit Symbol davor. */
export function PlayerName({ name, cls }: { name: string; cls: string | null }) {
	const { lang } = useI18n();
	const info = classInfo(cls, lang);
	return (
		<span className="player">
			<ClassIcon cls={cls} />
			<span style={{ color: info?.color }}>{name}</span>
		</span>
	);
}
