import { classInfo } from '../lib/classes.ts';

/** Klassensymbol aus dem Spiel; ohne bekannte Klasse ein neutraler Punkt. */
export function ClassIcon({ cls, size = 22 }: { cls: string | null; size?: number }) {
	const info = classInfo(cls);
	if (!info) return <span className="class-dot" style={{ width: size, height: size }} aria-hidden />;
	return <img className="class-icon" src={info.icon} alt={info.label} title={info.label} width={size} height={size} />;
}

/** Spielername in Klassenfarbe mit Symbol davor. */
export function PlayerName({ name, cls }: { name: string; cls: string | null }) {
	const info = classInfo(cls);
	return (
		<span className="player">
			<ClassIcon cls={cls} />
			<span style={{ color: info?.color }}>{name}</span>
		</span>
	);
}
