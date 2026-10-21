<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<section class="hero">
	<h1>Runs, Ranglisten und Geräte für den Waschsalon.</h1>
	<p class="dim">
		NexHub sammelt die Dungeon-Runs aus NexBoard, wertet sie aus und macht sie teilbar – für die
		Gilde und für alle, denen ihr einen Link schickt.
	</p>
	<div class="actions">
		{#if data.me}
			<a class="btn primary large" href="/hub">Zum Hub</a>
		{:else}
			<a class="btn primary large" href="/login">Mit Discord anmelden</a>
		{/if}
	</div>
</section>

<style>
	.hero {
		max-width: 720px;
		margin: 8vh auto 0;
		text-align: center;
	}
	h1 {
		font-size: clamp(32px, 6vw, 54px);
		line-height: 1.08;
		letter-spacing: -0.03em;
		background: linear-gradient(135deg, #fff 30%, var(--accent) 70%, var(--accent-2));
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
	}
	p {
		font-size: 17px;
		margin: 20px auto 32px;
		max-width: 560px;
	}
</style>
