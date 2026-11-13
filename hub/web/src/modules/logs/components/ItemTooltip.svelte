<!-- Gegenstandsfenster wie im Spiel: Kopf im Verlauf der Seltenheit mit großem Bild, darunter
     Grundwerte, Durchbruch (orange), Seelenbindung mit Balken, Manasteine, Gottstein, Skills und bei
     Arkana das Set (erreichte Stufen hell). Mit `rating` dazu die Note, je Roll Höchstwert und Anteil
     der Top-Spieler und der Weg zu S+ (rating.ts). Die BiS-Listen geben nur `lines` (Anteile je Zeile,
     auch Manasteine und Göttersteine) und unter dem Kopf ihren eigenen Teil (`children`). Ohne `onclose`
     (Fenster beim Zeigen auf Figur oder Platz) gibt es keinen Knopf zum Schließen. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterItem } from '../api.ts';
	import { gradeColor } from '../grades.ts';
	import type { RatedLine, Rating } from '../rating.ts';
	import RatingBadge from './RatingBadge.svelte';
	import UpgradeSteps from './UpgradeSteps.svelte';

	let {
		item,
		rating,
		lines,
		children,
		onclose
	}: { item: CharacterItem; rating?: Rating; lines?: RatedLine[]; children?: Snippet; onclose?: () => void } = $props();

	// Bewertete Zeile zu einem Roll, Skill oder Stein des Gegenstands, verbunden über Art und Namen
	const rated = (kind: RatedLine['kind'], name: string): RatedLine | undefined =>
		(lines ?? rating?.lines)?.find((l) => l.kind === kind && l.name === name);

	const d = $derived(item.detail);
	const main = $derived(d?.main.filter((s) => !s.exceed) ?? []);
	const amplify = $derived(d?.main.filter((s) => s.exceed) ?? []);
	const rate = $derived(Number(d?.soul_bind_rate ?? NaN));
	// Seelenbindung als eine Liste: Zusatzwerte und verstärkte Skills sind beide Rolls. Wie bei NC
	// erst die Werte, dann die Skills; in den BiS-Listen (`lines`) alle nach Anteil der Top-Spieler.
	type BindingRow = { name: string; value: string; icon?: string | null; line?: RatedLine };
	const binding = $derived.by((): BindingRow[] => {
		const rows: BindingRow[] = [
			...(d?.sub ?? []).map((s) => ({ name: s.name, value: s.value, line: rated('stat', s.name) })),
			...(d?.skills ?? []).map((s) => ({ name: s.name, value: `+${s.level}`, icon: s.icon, line: rated('skill', s.name) }))
		];
		return lines ? rows.sort((a, b) => (b.line?.share ?? 0) - (a.line?.share ?? 0)) : rows;
	});
	const withIcons = $derived(!!d?.skills.length);
	// Bonus aus der Verzauberung nur zeigen, wenn es einen gibt („0“, „0%“ und „0.0%“ nicht)
	const withExtra = (value: string, extra: string | null | undefined) =>
		extra && parseFloat(extra) !== 0 ? `${value}(+${extra})` : value;
	// Manche Symbole, die NCSOFT nennt, gibt es auf dem CDN nicht: dann nur den Platz freilassen
	const hide = (e: Event) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden');
</script>

<!-- Höchstwert dieses Gegenstands und Anteil der Top-Spieler hinter einem Roll -->
{#snippet ratedTail(line: RatedLine | undefined)}
	{#if line}
		{#if line.max}<span class="max"> / {line.kind === 'skill' ? line.max : line.unit === '%' ? `${line.max}%` : line.max}</span>{/if}
		<span class="share" title={t('logs.rating.shareHint')}><i style:width="{line.share * 100}%"></i>{Math.round(line.share * 100)}%</span>
	{/if}
{/snippet}

<div class="frame" style:--grade={gradeColor(item.grade, '#9aa0a6')}>
	<article>
		<header class="hero">
			<div class="heading">
				<h3>{item.enchant ? `+${item.enchant} ` : ''}{item.name}</h3>
				<p class="kind">{[item.grade, d?.category].filter(Boolean).join(' ')}</p>
				{#if d?.level}
					<span>{t('logs.char.itemLevel')}</span>
					<strong>{d.level}{item.enchant ? `(+${item.enchant})` : ''}</strong>
				{/if}
				{#if rating}
					<span class="rating">
						<RatingBadge letter={rating.letter} score={rating.score} />
						<small>{t('logs.rating.ideal', { n: rating.ideal, of: rating.ideal_of })}</small>
					</span>
				{/if}
			</div>
			{#if item.icon}<img src={item.icon} alt="" referrerpolicy="no-referrer" onerror={hide} />{/if}
		</header>
		{#if children}<div class="block">{@render children()}</div>{/if}

		{#if d === null}
			<p class="block dim">{t('logs.char.notWorn')}</p>
		{:else if d}
			{#if main.length}
				<dl class="block">
					{#each main as s, i (i)}<dt>{s.name}</dt><dd>{withExtra(s.value, s.extra)}</dd>{/each}
				</dl>
			{/if}
			{#if amplify.length}
				<dl class="block amplify">
					{#each amplify as s, i (i)}<dt>{s.name}</dt><dd>{s.value}</dd>{/each}
				</dl>
			{/if}

			<!-- Seelenbindung: Zusatzwerte und verstärkte Skills in einer Liste (binding) -->
			{#if d.sub.length || d.skills.length || !isNaN(rate)}
				<div class="block">
					{#if !isNaN(rate)}
						<p class="rate"><span>{t('logs.char.soulBindRate')}</span><b>{rate.toFixed(1)}%</b></p>
						<div class="bar"><i style:width="{Math.min(rate, 100)}%"></i></div>
					{:else}
						<p class="rate"><span>{t('logs.char.soulBinding')}</span></p>
					{/if}
					<ul class="binding">
						{#each binding as r, i (i)}
							<li>
								{#if r.icon}<img src={r.icon} alt="" width="26" height="26" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />
								{:else if withIcons}<i class="no-icon"></i>{/if}
								<span>{r.name}</span><b>{r.value}{@render ratedTail(r.line)}</b>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			{#if d.stones.length}
				<ul class="block stones">
					{#each d.stones as s, i (i)}
						<li style:--stone={gradeColor(s.grade, '#d8dde6')}>
							{#if s.icon}<img src={s.icon} alt="" width="30" height="30" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />{/if}
							<span>{s.name}{s.value}</span>{@render ratedTail(rated('stone', s.name))}
						</li>
					{/each}
				</ul>
			{/if}

			{#each d.godstones as g, i (i)}
				<div class="block godstone">
					{#if g.icon}<img src={g.icon} alt="" width="36" height="36" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />{/if}
					<div>
						<strong style:color={gradeColor(g.grade, 'inherit')}>{g.name}</strong>{@render ratedTail(rated('godstone', g.name))}
						{#if g.desc}<p>{g.desc}</p>{/if}
					</div>
				</div>
			{/each}

			{#if d.set}
				<div class="block set">
					<p class="set-head"><strong>{d.set.name}</strong><span>{t('logs.char.setCount', { n: d.set.equipped, t: d.set.total })}</span></p>
					{#each d.set.bonuses as b (b.degree)}
						<p class:active={d.set.equipped >= b.degree}>
							<b>{t('logs.char.setEffect', { n: b.degree })}</b>
							<span>{b.lines.join(' · ')}</span>
						</p>
					{/each}
				</div>
			{/if}
		{/if}

		{#if rating?.upgrade}
			<div class="block upgrade">
				<p class="up-head">
					{t('logs.rating.toTarget')}
					<RatingBadge letter={rating.upgrade.after_letter} score={rating.upgrade.after[0]} />
				</p>
				<UpgradeSteps steps={rating.upgrade.steps} />
			</div>
		{/if}
		{#if rating?.source}
			<p class="block source"><a href={rating.source} target="_blank">{t('logs.rating.source')}</a></p>
		{/if}

		{#if item.id}<footer><strong>#{item.id}</strong></footer>{/if}
	</article>
	{#if onclose}
		<nav>
			<button class="close" onclick={onclose} aria-label={t('logs.char.close')}>×</button>
		</nav>
	{/if}
</div>

<style>
	.frame {
		display: flex;
		background: var(--surface-3);
		border: 1px solid var(--fill-strong);
		box-shadow: 0 16px 50px var(--shade-strong);
		color: #e8ecf2;
	}
	article {
		flex: 1;
		min-width: 0;
	}
	nav {
		width: 56px;
		flex-shrink: 0;
		border-left: 1px solid var(--fill-strong);
		background: var(--surface-2);
	}
	/* bleibt beim Scrollen oben stehen, damit man das Fenster auch am Handy schließen kann */
	.close {
		position: sticky;
		top: 0;
		width: 100%;
		height: 56px;
		border: 0;
		background: none;
		color: #fff;
		font-size: 34px;
		line-height: 1;
		cursor: pointer;
	}
	.hero {
		position: relative;
		display: flex;
		justify-content: space-between;
		min-height: 170px;
		padding: 16px 18px;
		overflow: hidden;
		background:
			linear-gradient(170deg, transparent 72%, color-mix(in srgb, var(--grade) 70%, #fff) 72.5%, transparent 80%),
			linear-gradient(120deg, color-mix(in srgb, var(--grade) 55%, #000), color-mix(in srgb, var(--grade) 30%, #000) 70%);
		border-bottom: 3px solid var(--grade);
	}
	.heading {
		position: relative;
		z-index: 1;
		display: flex;
		flex-direction: column;
	}
	h3 {
		margin: 0 0 6px;
		font-family: var(--font-heading);
		font-size: 23px;
		font-weight: 400;
		color: color-mix(in srgb, var(--grade) 45%, #fff);
	}
	.kind {
		margin: 0 0 4px;
		color: color-mix(in srgb, var(--grade) 45%, #fff);
	}
	.heading span {
		color: #fff;
	}
	.heading strong {
		font-family: var(--font-heading);
		font-size: 23px;
		font-weight: 400;
		color: #fff;
	}
	.hero img {
		width: 120px;
		height: 120px;
		object-fit: contain;
		align-self: center;
		filter: drop-shadow(0 6px 10px var(--shade-strong));
	}
	.block {
		margin: 0 16px;
		padding: 12px 0;
		border-bottom: 1px solid var(--fill-strong);
	}
	dl {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 4px 12px;
		margin: 0;
		font-size: 16px;
	}
	dd {
		margin: 0;
		text-align: right;
		font-weight: 700;
	}
	.amplify {
		color: #f0a030;
	}
	.rate {
		display: flex;
		justify-content: space-between;
		margin: 0 0 6px;
		font-size: 17px;
	}
	.rate span {
		color: var(--game-cyan);
		font-weight: 600;
	}
	.rate b {
		color: var(--game-gold-soft);
	}
	.bar {
		height: 4px;
		margin-bottom: 10px;
		background: var(--fill-strong);
	}
	.bar i {
		display: block;
		height: 100%;
		background: var(--game-gold);
	}
	ul {
		list-style: none;
		padding-left: 0;
		padding-right: 0;
	}
	.stones {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px 14px;
	}
	/* mit Anteilen (BiS-Listen) braucht jeder Stein die ganze Breite */
	.stones:has(.share) {
		grid-template-columns: 1fr;
	}
	.stones li {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
		color: var(--stone);
		font-size: 15px;
		font-weight: 600;
	}
	.stones img {
		padding: 2px;
		background: var(--edge-soft);
		border: 1px solid var(--fill-strong);
	}
	/* Name füllt die Zeile, damit die Anteile wie bei der Seelenbindung rechts untereinander stehen */
	.stones span {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.godstone {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 14px;
	}
	.godstone p {
		margin: 4px 0 0;
		white-space: pre-line;
		color: var(--dim);
	}
	/* Seelenbindung: Werte und Skills in einer Liste, Skills mit Symbol */
	.binding {
		margin: 0;
		font-size: 16px;
	}
	.binding li {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 3px 0;
		min-height: 26px;
	}
	.binding span {
		flex: 1;
	}
	.no-icon {
		width: 26px;
		flex-shrink: 0;
	}
	.set p {
		display: flex;
		gap: 10px;
		margin: 4px 0;
		font-size: 14px;
		color: var(--faint);
	}
	.set .set-head {
		justify-content: space-between;
		margin-bottom: 8px;
		color: #fff;
	}
	.set-head span {
		color: var(--dim);
		font-size: 13px;
	}
	.set b {
		flex-shrink: 0;
	}
	.set .active {
		color: var(--game-green);
	}
	.rating {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 8px;
	}
	.rating small {
		color: rgba(255, 255, 255, 0.75);
		font-size: 12px;
	}
	.max {
		color: var(--faint);
		font-weight: 500;
	}
	/* Anteil der Top-Spieler: kleiner Balken mit Zahl hinter dem Wert */
	.share {
		position: relative;
		display: inline-block;
		width: 46px;
		margin-left: 8px;
		text-align: right;
		font-size: 12px;
		font-weight: 600;
		color: var(--game-gold);
	}
	.share i {
		position: absolute;
		right: 0;
		top: 2px;
		bottom: 2px;
		background: color-mix(in srgb, var(--game-gold) 18%, transparent);
	}
	.up-head {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 0;
		font-weight: 600;
	}
	.source {
		margin-top: 0;
		font-size: 12px;
	}
	.source a {
		color: var(--accent);
	}
	footer {
		display: flex;
		justify-content: flex-end;
		padding: 12px 16px;
		background: var(--surface-2);
		font-size: 15px;
	}
	/* Handy: kleinerer Kopf, kleinere Schrift, schmalere Leiste zum Schließen */
	@media (max-width: 600px) {
		nav {
			width: 40px;
		}
		.close {
			height: 44px;
			font-size: 28px;
		}
		.hero {
			min-height: 0;
			padding: 10px 12px;
		}
		h3,
		.heading strong {
			font-size: 18px;
		}
		.kind {
			font-size: 13px;
		}
		.hero img {
			width: 64px;
			height: 64px;
		}
		.block {
			margin: 0 12px;
			padding: 8px 0;
		}
		dl,
		.binding {
			font-size: 14px;
		}
		.rate {
			font-size: 15px;
		}
		.stones li {
			font-size: 13px;
		}
		.godstone,
		.set p {
			font-size: 13px;
		}
		footer {
			padding: 8px 12px;
			font-size: 13px;
		}
	}
</style>
