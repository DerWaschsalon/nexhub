<script lang="ts">
	import { page } from '$app/state';
	import FightView from '#lib/components/FightView.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<FightView fight={data.fight} back="/hub/runs/{page.params.id}" />
