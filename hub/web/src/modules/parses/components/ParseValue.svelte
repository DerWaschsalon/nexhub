<!-- Ein Parse als Zahl in der Farbstufe wie bei Warcraft Logs. Ab Lila mit Effekt: Lila leuchtet, Orange pulsiert,
     Rosa schimmert, Gold schimmert und funkelt (ohne Bewegung bei reduced motion). -->
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
	.purple {
		color: #b673ff;
		text-shadow: 0 0 8px rgb(167 80 238 / 0.75);
	}
	.orange {
		color: #ff8a1a;
		animation: glow 2.2s ease-in-out infinite;
	}
	.pink,
	.gold {
		position: relative;
		background-size: 200% 100%;
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		animation: shine 2.4s linear infinite;
	}
	.pink {
		background-image: linear-gradient(100deg, #e268a8 20%, #ffd6ec 40%, #e268a8 60%);
		filter: drop-shadow(0 0 6px rgb(226 104 168 / 0.8));
	}
	.gold {
		background-image: linear-gradient(100deg, #c9a23a 20%, #fff4c8 40%, #c9a23a 60%);
		filter: drop-shadow(0 0 8px rgb(242 197 34 / 0.85));
		animation-duration: 1.9s;
	}
	.gold::after {
		content: '';
		position: absolute;
		top: -5px;
		right: -7px;
		width: 7px;
		height: 7px;
		background: #fff4c8;
		clip-path: polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%);
		animation: spark 1.5s ease-in-out infinite;
	}
	@keyframes glow {
		0%,
		100% {
			text-shadow: 0 0 5px rgb(255 128 0 / 0.5);
		}
		50% {
			text-shadow: 0 0 14px rgb(255 128 0 / 1);
		}
	}
	@keyframes shine {
		to {
			background-position: -200% 0;
		}
	}
	@keyframes spark {
		0%,
		100% {
			opacity: 0;
			transform: scale(0.3) rotate(0deg);
		}
		50% {
			opacity: 1;
			transform: scale(1) rotate(90deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.orange,
		.pink,
		.gold,
		.gold::after {
			animation: none;
		}
	}
</style>
