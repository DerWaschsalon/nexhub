<!-- Logo + Name, verlinkt auf die Startseite des jeweiligen Bereichs. -->
<script lang="ts">
	let { href = '/' }: { href?: string } = $props();
</script>

<a {href} class="brand">
	<img src="/favicon.svg" alt="" width="28" height="28" />
	<span>NexHub</span>
</a>

<style>
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		color: var(--text);
		text-decoration: none;
		font-weight: 700;
		font-size: 18px;
		letter-spacing: -0.01em;
	}
	img {
		border-radius: 8px;
	}
</style>
