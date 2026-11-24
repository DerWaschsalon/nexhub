<!-- Zählt bis zu einem Zeitpunkt herunter (Sekunden seit 1970): „2 h 05 min“, unter einer Stunde „12:34“. -->
<script lang="ts">
	import { clock } from '#lib/clock.svelte.ts';
	import { formatCountdown } from '#lib/format.ts';

	let { until }: { until: number } = $props();
</script>

<span class="num" role="timer">{formatCountdown(until - clock.now)}</span>
