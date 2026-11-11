<!-- Werte wie auf der offiziellen Charakterseite: sechs Grundwerte und die zehn Lord-Werte mit den
     Symbolen von aion2.plaync.com, die Effekte gleich darunter statt im Tooltip. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData } from '../api.ts';
	import { BASE, LORDS, pickStats, splitLord, statIcon } from '../stats.ts';

	let { stats }: { stats: CharacterData['stats'] } = $props();
	const pick = (types: string[]) => pickStats(stats, types);
</script>

{#snippet tile(s: CharacterData['stats'][number], lord: boolean)}
	{@const n = splitLord(s.name)}
	<div class="stat" class:lord class:zero={!s.value}>
		<img src={statIcon(s.type)} alt="" width={lord ? 40 : 46} height={lord ? 40 : 46} loading="lazy" referrerpolicy="no-referrer" />
		<div class="body">
			<div class="top">
				<span class="name">{n.name}{#if n.lord}<small>{n.lord}</small>{/if}</span>
				<strong class="num">{s.value}</strong>
			</div>
			{#if s.effects.length}
				<ul>
					{#each s.effects as e, i (i)}<li>{e}</li>{/each}
				</ul>
			{/if}
		</div>
	</div>
{/snippet}

<h4>{t('logs.char.baseStats')}</h4>
<div class="grid base">
	{#each pick(BASE) as s (s.type)}{@render tile(s, false)}{/each}
</div>
{#if pick(LORDS).length}
	<h4>{t('logs.char.lordStats')}</h4>
	<div class="grid lords">
		{#each pick(LORDS) as s (s.type)}{@render tile(s, true)}{/each}
	</div>
{/if}

<style>
	h4 {
		font-size: 13px;
		margin: 4px 0 10px;
		color: var(--dim);
	}
	.grid {
		display: grid;
		gap: 10px;
		margin-bottom: 18px;
	}
	.base {
		grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr));
	}
	.lords {
		grid-template-columns: repeat(auto-fill, minmax(min(210px, 100%), 1fr));
	}
	.stat {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		padding: 10px 12px;
		border-radius: var(--radius-sm);
		background: var(--fill);
		border: 1px solid var(--edge-soft);
	}
	.stat.zero {
		opacity: 0.45;
	}
	img {
		flex-shrink: 0;
		object-fit: contain;
	}
	.body {
		flex: 1;
		min-width: 0;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.name {
		font-weight: 600;
		display: flex;
		flex-direction: column;
	}
	.name small {
		font-weight: 400;
		font-size: 11px;
		color: var(--faint);
	}
	.top strong {
		font-size: 20px;
	}
	.lord .top strong {
		font-size: 17px;
	}
	ul {
		list-style: none;
		margin: 6px 0 0;
		padding: 0;
		font-size: 12px;
		color: var(--dim);
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
</style>
