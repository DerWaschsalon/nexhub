<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const name = $derived(data.me?.display_name ?? data.me?.username);
</script>

<section class="card welcome">
	<h1>Willkommen, {name}</h1>
	<p class="dim">
		Hier entsteht der Hub. Runs, Geräte und Ranglisten kommen in den nächsten Schritten dazu.
	</p>
</section>

<style>
	.welcome {
		padding: 24px;
	}
	h1 {
		font-size: 22px;
		margin-bottom: 8px;
	}
	p {
		margin: 0;
	}
</style>
