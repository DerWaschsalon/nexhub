<!-- Reiter „Upgrades“: je Gegenstand der Weg zu Best in Slot durch Neuwürfeln, die mit dem größten Zugewinn
     zuerst. Ein Klick auf den Gegenstand öffnet sein Fenster (onItem). -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterItem } from '../api.ts';
	import type { Rating, Ratings } from '../rating.ts';
	import ItemIcon from './ItemIcon.svelte';
	import RatingBadge from './RatingBadge.svelte';
	import UpgradeSteps from './UpgradeSteps.svelte';

	let {
		ratings,
		equipment,
		onItem
	}: { ratings: Ratings; equipment: CharacterItem[]; onItem: (item: CharacterItem) => void } = $props();

	type Card = { rating: Rating; item: CharacterItem };
	const gain = (r: Rating) => (r.upgrade ? r.upgrade.after[0] - r.score : 0);
	const cards = $derived(
		ratings.items
			.filter((r) => r.upgrade)
			.map((r) => ({ rating: r, item: equipment.find((e) => e.slot_name === r.slot) }))
			.filter((c): c is Card => c.item !== undefined)
			.sort((a, b) => gain(b.rating) - gain(a.rating))
	);
</script>

<p class="intro dim">{t('logs.rating.upgradesIntro', { size: ratings.size, group: ratings.group })}</p>

{#each cards as { rating, item } (rating.slot)}
	{@const u = rating.upgrade!}
	<article>
		<button class="head" onclick={() => onItem(item)}>
			<ItemIcon name={item.name} icon={item.icon} grade={item.grade} enchant={item.enchant} exceed={item.exceed} size={44} filled />
			<span class="title">
				<strong>{item.enchant ? `+${item.enchant} ` : ''}{item.name}</strong>
				<span class="path">
					<RatingBadge letter={rating.letter} score={rating.score} />
					→
					<RatingBadge letter={u.after_letter} score={u.after[0]} />
					<span class="dim small">{t('logs.rating.range', { lo: Math.round(u.after[0]), hi: Math.round(u.after[1]) })}</span>
				</span>
			</span>
		</button>
		<UpgradeSteps steps={u.steps} />
	</article>
{:else}
	<p>{t('logs.rating.allGood')}</p>
{/each}

<style>
	.intro {
		margin: 12px 0;
		font-size: 13px;
	}
	article {
		padding: 12px 0;
		border-top: 1px solid rgba(255, 255, 255, 0.08);
	}
	.head {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		padding: 0;
		border: 0;
		background: none;
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}
	.title {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.title strong {
		font-family: Georgia, 'Times New Roman', serif;
		font-weight: 400;
		font-size: 17px;
	}
	.path {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.small {
		font-size: 12px;
	}
</style>
