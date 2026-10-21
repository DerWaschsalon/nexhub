<!-- Übersicht: Zustand des Bots und Einstieg in die Bereiche. -->
<script lang="ts">
	import { formatUptime } from '#modules/bot/bot.ts';
	import { formatNumber } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const s = $derived(data.status!);
</script>

<section class="glass pad hero">
	{#if s.avatar_url}<img src={s.avatar_url} alt="" width="56" height="56" />{/if}
	<div>
		<h2>{s.name ?? 'TheWashBot'}</h2>
		<p class="dim">
			{#if s.guild}
				{s.guild.name}, {formatNumber(s.guild.members)} Mitglieder
			{:else}
				Auf keinem Discord-Server
			{/if}
		</p>
	</div>
</section>

<section class="tiles">
	<div class="glass pad tile">
		<span class="label">Verbindung zu Discord</span>
		<strong>
			<span class="chip" class:ok={s.ready} class:warn={!s.ready}>{s.ready ? 'verbunden' : 'startet'}</span>
		</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Antwortzeit</span>
		<strong class="num">{s.latency_ms ?? '–'}<small> ms</small></strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Läuft seit</span>
		<strong>{formatUptime(s.uptime_s)}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Version</span>
		<strong>{s.version}</strong>
	</div>
</section>


<style>
	.hero {
		display: flex;
		align-items: center;
		gap: 16px;
		margin-bottom: 14px;
	}
	.hero img {
		border-radius: 50%;
		border: 1px solid var(--edge);
	}
	.hero h2 {
		font-size: 20px;
	}
	.hero p {
		margin: 2px 0 0;
	}
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 14px;
	}
	.tile {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.label {
		font-size: 13px;
		color: var(--faint);
	}
	strong {
		font-size: 17px;
		overflow-wrap: anywhere;
	}
	.num {
		font-size: 30px;
		font-variant-numeric: tabular-nums;
	}
	.num small {
		font-size: 15px;
		color: var(--dim);
	}
</style>
