<!-- Ein Parse als Zahl in der Farbstufe wie bei Warcraft Logs. Ab Lila mit deutlichem Effekt (siehe Stil unten), ohne
     Bewegung bei reduced motion. -->
<script lang="ts">
	import { parseColor } from '../api.ts';

	let { value }: { value: number } = $props();
</script>

<span class="pv {parseColor(value)}">{value}</span>

<style>
	.pv {
		position: relative;
		display: inline-block;
		font-variant-numeric: tabular-nums;
	}
	/* Farbstufen wie bei Warcraft Logs, etwas gedämpft, damit sie auf hellem und dunklem Grund lesbar bleiben */
	.grey {
		color: #9aa0a6;
	}
	.green {
		color: #2fbf3a;
	}
	.blue {
		color: #3d86f0;
	}
	/* Ab Lila mit deutlichem Effekt, je höher, desto stärker: Lila leuchtet und atmet, Orange glüht und pulsiert,
	   Rosa schimmert mit Funke, Gold schimmert mit Strahlenkranz und zwei Funken */
	.purple,
	.orange,
	.pink,
	.gold {
		font-weight: 800;
		padding: 0 3px;
		isolation: isolate;
	}
	.purple {
		color: #d4a6ff;
		animation: breathe-purple 2.6s ease-in-out infinite;
	}
	.orange {
		color: #ffb05c;
		animation: breathe-orange 1.8s ease-in-out infinite;
	}
	.pink,
	.gold {
		background-size: 220% 100%;
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
	}
	.pink {
		background-image: linear-gradient(100deg, #ff5fb0 15%, #fff0f8 38%, #ff8cc8 52%, #ff5fb0 70%);
		animation: shine 1.8s linear infinite, breathe-pink 1.8s ease-in-out infinite;
	}
	.gold {
		background-image: linear-gradient(100deg, #e0a91e 15%, #fffbe6 36%, #ffd75a 50%, #e0a91e 70%);
		animation: shine 1.4s linear infinite, breathe-gold 1.6s ease-in-out infinite;
	}
	/* Strahlenkranz hinter Rosa und Gold */
	.pink::before,
	.gold::before {
		content: '';
		position: absolute;
		inset: -45% -35%;
		z-index: -1;
		border-radius: 50%;
		background: radial-gradient(circle, var(--halo), transparent 68%);
		animation: halo 1.8s ease-in-out infinite;
		pointer-events: none;
	}
	.pink::before {
		--halo: rgb(255 95 176 / 0.45);
	}
	.gold::before {
		--halo: rgb(255 210 80 / 0.55);
		animation-duration: 1.4s;
	}
	/* Funken oben rechts (Rosa einer, Gold zwei über einen Schatten) */
	.pink::after,
	.gold::after {
		content: '';
		position: absolute;
		top: -6px;
		right: -6px;
		width: 9px;
		height: 9px;
		background: #fff;
		clip-path: polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%);
		animation: spark 1.3s ease-in-out infinite;
		pointer-events: none;
	}
	.gold::after {
		background: #fff6cf;
		filter: drop-shadow(-16px 14px 0 #ffe27a);
		animation-duration: 1.1s;
	}
	@keyframes breathe-purple {
		0%,
		100% {
			text-shadow: 0 0 4px rgb(167 80 238 / 0.9), 0 0 10px rgb(167 80 238 / 0.6);
		}
		50% {
			text-shadow: 0 0 6px rgb(190 110 255 / 1), 0 0 18px rgb(167 80 238 / 0.9), 0 0 28px rgb(167 80 238 / 0.5);
		}
	}
	@keyframes breathe-orange {
		0%,
		100% {
			text-shadow: 0 0 5px rgb(255 128 0 / 0.9), 0 0 12px rgb(255 128 0 / 0.6);
			transform: scale(1);
		}
		50% {
			text-shadow: 0 0 8px rgb(255 160 40 / 1), 0 0 22px rgb(255 128 0 / 0.95), 0 0 36px rgb(255 100 0 / 0.55);
			transform: scale(1.08);
		}
	}
	@keyframes breathe-pink {
		0%,
		100% {
			filter: drop-shadow(0 0 4px rgb(255 95 176 / 0.9));
			transform: scale(1);
		}
		50% {
			filter: drop-shadow(0 0 12px rgb(255 95 176 / 1));
			transform: scale(1.1);
		}
	}
	@keyframes breathe-gold {
		0%,
		100% {
			filter: drop-shadow(0 0 5px rgb(255 200 60 / 0.95));
			transform: scale(1);
		}
		50% {
			filter: drop-shadow(0 0 16px rgb(255 215 90 / 1));
			transform: scale(1.12);
		}
	}
	@keyframes shine {
		to {
			background-position: -220% 0;
		}
	}
	@keyframes halo {
		0%,
		100% {
			opacity: 0.55;
			transform: scale(0.85);
		}
		50% {
			opacity: 1;
			transform: scale(1.15);
		}
	}
	@keyframes spark {
		0%,
		100% {
			opacity: 0;
			transform: scale(0.2) rotate(0deg);
		}
		50% {
			opacity: 1;
			transform: scale(1.1) rotate(90deg);
		}
	}
	/* Ohne Bewegung: die Farben und der Schein bleiben, nichts pulsiert */
	@media (prefers-reduced-motion: reduce) {
		.purple,
		.orange,
		.pink,
		.gold,
		.pink::before,
		.gold::before,
		.pink::after,
		.gold::after {
			animation: none;
		}
		.purple {
			text-shadow: 0 0 6px rgb(167 80 238 / 0.9), 0 0 16px rgb(167 80 238 / 0.6);
		}
		.orange {
			text-shadow: 0 0 6px rgb(255 128 0 / 0.9), 0 0 18px rgb(255 128 0 / 0.6);
		}
		.pink::after,
		.gold::after {
			opacity: 1;
		}
	}
</style>
