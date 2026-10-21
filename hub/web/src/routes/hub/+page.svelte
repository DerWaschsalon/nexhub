<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<header class="page-head">
	<h1>Hallo, {data.me.name}</h1>
	<p>Hier entsteht der Hub. Runs, Geräte und Ranglisten kommen in den nächsten Schritten dazu.</p>
</header>
