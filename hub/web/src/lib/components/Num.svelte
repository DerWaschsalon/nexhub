<!-- Gekürzte Zahl („38,4K“) mit dem exakten Wert im Tooltip. Regel im Hub: Jede gekürzte Zahl zeigt
     ihren exakten Wert, wenn man auf sie zeigt; Screenreader lesen ihn aus dem title vor. -->
<script lang="ts">
	import { formatCompact, formatNumber } from '#lib/format.ts';

	let {
		value,
		unit = '',
		dash = false
	}: {
		value: number;
		/** Zusatz im Tooltip, z. B. „Schaden“ */
		unit?: string;
		/** 0 als „–“ zeigen (leere Tabellenzelle) */
		dash?: boolean;
	} = $props();

	const exact = $derived(unit ? `${formatNumber(value)} ${unit}` : formatNumber(value));
</script>

{#if dash && !value}–{:else}<abbr title={exact}>{formatCompact(value)}</abbr>{/if}

<style>
	abbr {
		text-decoration: none;
	}
</style>
