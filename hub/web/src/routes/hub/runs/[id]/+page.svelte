<!-- Ein Run: Eckdaten, Schaden über den ganzen Run, dann jeder Bosskampf. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import DamageBars from '#lib/components/DamageBars.svelte';
	import { formatDuration, formatMs, formatNumber } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const run = $derived(data.run);

	async function remove() {
		if (!confirm('Diesen Run löschen? Die Datei ist danach weg.')) return;
		try {
			await api<void>(`/api/runs/${run.id}`, { method: 'DELETE' });
			await goto('/hub/runs');
		} catch (e) {
			alert(e instanceof Error ? e.message : String(e));
		}
	}
</script>

<header class="page-head head">
	<div>
		<a class="back" href="/hub/runs">← Runs</a>
		<h1>
			{run.dungeon}
			{#if run.difficulty}<span class="chip">{run.difficulty}</span>{/if}
		</h1>
		<p>
			{formatMs(run.start_ms)} · {formatDuration(run.end_ms - run.start_ms)} · aufgenommen von {run.character ??
				run.uploader}
		</p>
	</div>
	<div class="actions">
		<a class="btn small" href="/api/runs/{run.id}/nexlog" download>NexLog herunterladen</a>
		{#if run.can_delete}<button class="btn small danger" onclick={remove}>Löschen</button>{/if}
	</div>
</header>

<section class="stats">
	<div class="glass pad stat">
		<span class="label">Bosse</span>
		<strong class:ok={run.complete}>{run.bosses_killed}/{run.bosses_total}</strong>
	</div>
	<div class="glass pad stat">
		<span class="label">Kampfzeit</span>
		<strong>{formatDuration(run.summary.fight_ms)}</strong>
	</div>
	<div class="glass pad stat">
		<span class="label">Kämpfe</span>
		<strong>{run.fights}</strong>
	</div>
	<div class="glass pad stat">
		<span class="label">Treffer</span>
		<strong>{run.hits ? formatNumber(run.hits) : '–'}</strong>
	</div>
</section>

<section class="glass pad block">
	<h2>Schaden im ganzen Run</h2>
	<DamageBars players={run.summary.players} />
</section>

{#each run.summary.bosses as boss (boss.fight)}
	<section class="glass pad block">
		<div class="boss-head">
			<h2>{boss.name}</h2>
			<span class="chip" class:ok={boss.killed} class:danger={!boss.killed}>{boss.killed ? 'besiegt' : 'nicht besiegt'}</span>
			<span class="dim">{formatDuration(boss.duration_ms)}</span>
		</div>
		<DamageBars players={boss.players} />
	</section>
{/each}

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}
	.back {
		color: var(--dim);
		text-decoration: none;
		font-size: 14px;
	}
	h1 {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		margin-top: 4px;
	}
	.actions {
		display: flex;
		gap: 8px;
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 12px;
		margin-bottom: 16px;
	}
	.stat {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 16px 20px;
	}
	.label {
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--faint);
	}
	.stat strong {
		font-size: 24px;
		font-variant-numeric: tabular-nums;
	}
	.stat strong.ok {
		color: var(--ok);
	}
	.block {
		margin-bottom: 16px;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 12px;
	}
	.boss-head {
		display: flex;
		align-items: baseline;
		gap: 10px;
		flex-wrap: wrap;
		margin-bottom: 12px;
	}
	.boss-head h2 {
		margin: 0;
	}
</style>
