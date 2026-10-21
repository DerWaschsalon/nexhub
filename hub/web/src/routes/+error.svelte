<!-- Fehlerseite für beide Bereiche, z. B. wenn die API nicht antwortet. -->
<script lang="ts">
	import { page } from '$app/state';
</script>

<section class="glass pad card">
	<h1>{page.status}</h1>
	<p class="dim">{page.error?.message ?? 'Da ist etwas schiefgegangen.'}</p>
	<a class="btn" href="/">Zur Startseite</a>
</section>

<style>
	.card {
		max-width: 440px;
		margin: 14vh auto 0;
		text-align: center;
	}
	h1 {
		font-size: 44px;
	}
	p {
		margin: 6px 0 22px;
	}
</style>
