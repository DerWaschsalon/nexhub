<!-- Gegenstand wie im Spiel: Symbol vom NCSOFT-CDN im Rahmen der Seltenheit, Verzauberung und
     Durchbruch an den Ecken, Name als Tooltip. -->
<script lang="ts">
	import { gradeColor } from '../grades.ts';

	let {
		name,
		icon,
		grade = null,
		enchant = 0,
		exceed = 0,
		size = 48
	}: { name: string; icon: string | null; grade?: string | null; enchant?: number; exceed?: number; size?: number } =
		$props();

	const color = $derived(gradeColor(grade));
</script>

<span class="item" style:width="{size}px" style:height="{size}px" style:border-color={color} title={name}>
	{#if icon}
		<img src={icon} alt={name} width={size - 6} height={size - 6} loading="lazy" referrerpolicy="no-referrer" />
	{/if}
	{#if enchant}<span class="enchant">+{enchant}</span>{/if}
	{#if exceed}<span class="exceed">{exceed}</span>{/if}
</span>

<style>
	.item {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 2px solid;
		border-radius: 10px;
		background: rgba(0, 0, 0, 0.32);
		flex-shrink: 0;
	}
	img {
		object-fit: contain;
		border-radius: 7px;
	}
	.enchant,
	.exceed {
		position: absolute;
		font-size: 11px;
		font-weight: 700;
		line-height: 1;
		padding: 2px 4px;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.75);
	}
	.enchant {
		right: 1px;
		bottom: 1px;
	}
	.exceed {
		left: 1px;
		top: 1px;
		color: var(--warn);
	}
</style>
