<!-- Dünner Balken oben, solange eine Seite lädt (z. B. ein Live-Abruf von der AION-2-Website).
     Erscheint erst nach einer kurzen Pause, damit schnelle Seitenwechsel nicht flackern. -->
<script lang="ts">
	import { navigating } from '$app/state';
	import { t } from '#lib/i18n.svelte.ts';
</script>

{#if navigating.to}
	<div class="bar" role="progressbar" aria-label={t('shell.loading')}><span></span></div>
{/if}

<style>
	.bar {
		position: fixed;
		inset: 0 0 auto;
		z-index: 100;
		height: 3px;
		overflow: hidden;
		opacity: 0;
		animation: show 0.2s 0.25s forwards;
	}
	.bar span {
		position: absolute;
		inset: 0 auto 0 0;
		width: 40%;
		background: linear-gradient(90deg, transparent, var(--accent), var(--accent-2), transparent);
		animation: slide 1.2s ease-in-out infinite;
	}
	@keyframes show {
		to {
			opacity: 1;
		}
	}
	@keyframes slide {
		from {
			transform: translateX(-100%);
		}
		to {
			transform: translateX(250%);
		}
	}
	/* Ohne Bewegung: der Balken steht still über die ganze Breite */
	@media (prefers-reduced-motion: reduce) {
		.bar span {
			width: 100%;
			animation: none;
		}
	}
</style>
