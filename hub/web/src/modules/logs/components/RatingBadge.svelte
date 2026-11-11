<!-- Note eines Gegenstands (S+, A …) mit Punkten, in der Farbe der Note -->
<script lang="ts">
	import { LETTER_COLOR } from '../rating.ts';

	let { letter, score, small = false }: { letter: string; score?: number; small?: boolean } = $props();
</script>

<span class="badge" class:small style:--c={LETTER_COLOR[letter] ?? '#9aa0a6'}>
	<b>{letter}</b>{#if score !== undefined && !small}<small>{Math.round(score)}</small>{/if}
</span>

<style>
	.badge {
		display: inline-flex;
		align-items: baseline;
		gap: 4px;
		padding: 1px 7px;
		border: 1.5px solid var(--c);
		border-radius: 4px;
		background: var(--surface);
		color: var(--c);
		line-height: 1.3;
	}
	b {
		font-size: 15px;
	}
	small {
		font-size: 11px;
	}
	.small {
		padding: 0 4px;
		border-width: 1px;
	}
	.small b {
		font-size: 11px;
	}
</style>
