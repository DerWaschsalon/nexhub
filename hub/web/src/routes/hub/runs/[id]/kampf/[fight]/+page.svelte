<script lang="ts">
	import FightView from '#modules/logs/components/FightView.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

{#key data.fight.fight}<FightView fight={data.fight} />{/key}
