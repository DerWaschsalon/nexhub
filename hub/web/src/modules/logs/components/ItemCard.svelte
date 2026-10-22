<!-- Ein Gegenstand mit allen Werten als Übersicht, nicht als Tooltip: Grundwerte mit Bonus aus der
     Verzauberung, Seelenbindung (die gewürfelten Werte), Manasteine, Göttersteine und verstärkte
     Skills – Begriffe wie auf der offiziellen Charakterseite. Für Gear und Arkana gleich. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterItem } from '../api.ts';
	import { gradeColor } from '../grades.ts';
	import ItemIcon from './ItemIcon.svelte';

	let { item }: { item: CharacterItem } = $props();
	const d = $derived(item.detail);
	// Bonus aus der Verzauberung nur zeigen, wenn es einen gibt („0“, „0%“ und „0.0%“ nicht)
	const hasExtra = (extra: string | null | undefined) => !!extra && parseFloat(extra) !== 0;
	// Manche Symbole, die NCSOFT nennt, gibt es auf dem CDN nicht: dann nur den Platz freilassen
	const hide = (e: Event) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden');
</script>

<article class="item">
	<header>
		<ItemIcon name={item.name} icon={item.icon} grade={item.grade} enchant={item.enchant} exceed={item.exceed} size={52} />
		<div class="title">
			<strong style:color={gradeColor(item.grade, 'inherit')}>{item.name}</strong>
			<span class="dim small">
				{[d?.category, d?.level ? t('logs.char.itemLvl', { n: d.level }) : ''].filter(Boolean).join(' · ')}
			</span>
		</div>
	</header>

	{#if d === null}
		<p class="dim small">{t('logs.char.notWorn')}</p>
	{:else if d}
		{#if d.main.length}
			<dl class="stats">
				{#each d.main as s, i (i)}
					<dt>{s.name}</dt>
					<dd class="num">{s.value}{#if hasExtra(s.extra)}<span class="extra"> +{s.extra}</span>{/if}</dd>
				{/each}
			</dl>
		{/if}

		{#if d.sub.length}
			<h5>{t('logs.char.soulBinding')}</h5>
			<dl class="stats rolls">
				{#each d.sub as s, i (i)}
					<dt>{s.name}</dt>
					<dd class="num">{s.value}</dd>
				{/each}
			</dl>
		{/if}

		{#if d.stones.length}
			<h5>{t('logs.char.manastones')}</h5>
			<ul class="stones">
				{#each d.stones as s, i (i)}
					<li style:border-color={gradeColor(s.grade)}>
						{#if s.icon}<img src={s.icon} alt="" width="20" height="20" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />{/if}
						<span>{s.name}</span>
						<b class="num">{s.value}</b>
					</li>
				{/each}
			</ul>
		{/if}

		{#if d.godstones.length}
			<h5>{t('logs.char.theostones')}</h5>
			{#each d.godstones as g, i (i)}
				<div class="godstone">
					{#if g.icon}<img src={g.icon} alt="" width="28" height="28" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />{/if}
					<div>
						<strong style:color={gradeColor(g.grade, 'inherit')}>{g.name}</strong>
						{#if g.desc}<p class="dim small">{g.desc}</p>{/if}
					</div>
				</div>
			{/each}
		{/if}

		{#if d.skills.length}
			<h5>{t('logs.char.skillEffects')}</h5>
			<ul class="skills">
				{#each d.skills as s, i (i)}
					<li>
						{#if s.icon}<img src={s.icon} alt="" width="24" height="24" loading="lazy" referrerpolicy="no-referrer" onerror={hide} />{/if}
						<span>{s.name}</span>
						<b class="num">+{s.level}</b>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
</article>

<style>
	.item {
		padding: 14px;
		border-radius: var(--radius-sm);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--edge-soft);
		min-width: 0;
	}
	header {
		display: flex;
		gap: 12px;
		align-items: center;
		margin-bottom: 10px;
	}
	.title {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.title strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	h5 {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--faint);
		margin: 12px 0 6px;
	}
	.stats {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 3px 12px;
		margin: 0;
		font-size: 13px;
	}
	dt {
		color: var(--dim);
	}
	dd {
		margin: 0;
		text-align: right;
		font-weight: 600;
	}
	.extra {
		color: var(--accent);
		font-weight: 500;
	}
	.rolls dd {
		color: var(--ok);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 13px;
	}
	.stones li {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 3px 8px 3px 4px;
		border-left: 3px solid;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.2);
	}
	li span {
		flex: 1;
		min-width: 0;
		color: var(--dim);
	}
	.skills li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	li img {
		border-radius: 5px;
	}
	.godstone {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 13px;
	}
	.godstone p {
		white-space: pre-line;
		margin: 2px 0 0;
	}
	.small {
		font-size: 12px;
	}
</style>
