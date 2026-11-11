<!-- Effekte aller Werte zusammengezählt (Angriff +5,9 % …) als Zeilen, ein- oder zweispaltig. -->
<script lang="ts">
	import type { CharacterData } from '../api.ts';
	import { formatTotal, sumEffects } from '../stats.ts';

	let { stats, columns = 2 }: { stats: CharacterData['stats']; columns?: 1 | 2 } = $props();
	const totals = $derived(sumEffects(stats));
</script>

<dl style:--columns={columns}>
	{#each totals as total (total.name + total.unit)}
		<div>
			<dt>{total.name}</dt>
			<dd class="num">{formatTotal(total)}</dd>
		</div>
	{/each}
</dl>

<style>
	dl {
		display: grid;
		grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
		gap: 4px;
		margin: 0;
	}
	@media (max-width: 560px) {
		dl {
			grid-template-columns: 1fr;
		}
	}
	div {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		padding: 9px 14px;
		background: rgba(255, 255, 255, 0.06);
		font-size: 15px;
	}
	dt {
		color: #d8dde6;
	}
	dd {
		margin: 0;
		font-weight: 700;
		color: #fff;
	}
</style>
