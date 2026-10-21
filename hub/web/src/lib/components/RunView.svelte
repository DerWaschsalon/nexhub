<!-- Ein Run: Titel, Eckdaten, Schaden über den ganzen Run, dann jeder Bosskampf.
     Gleiche Ansicht im Hub und auf geteilten Seiten; `actions` und `extra` füllt die jeweilige Seite. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { RunCore } from '#lib/api.ts';
	import { playerColors } from '#lib/colors.ts';
	import DamageBars from '#lib/components/DamageBars.svelte';
	import { formatDuration, formatMs, formatNumber } from '#lib/format.ts';

	let {
		run,
		fightHref,
		actions,
		extra
	}: { run: RunCore; fightHref: (fight: string) => string; actions?: Snippet; extra?: Snippet } = $props();

	// Gleiche Reihenfolge wie die Kampf-Seiten: jeder Spieler hat im ganzen Run eine Farbe
	const color = $derived(playerColors(run.summary.players.map((p) => p.name)));
</script>

<header class="page-head head">
	<div>
		<h1>
			{run.dungeon}
			{#if run.difficulty}<span class="chip">{run.difficulty}</span>{/if}
		</h1>
		<p>
			{formatMs(run.start_ms)} · {formatDuration(run.end_ms - run.start_ms)}
			{#if run.character}· aufgenommen von {run.character}{/if}
		</p>
	</div>
	{#if actions}<div class="actions">{@render actions()}</div>{/if}
</header>

{@render extra?.()}

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
	<DamageBars players={run.summary.players} colorOf={color} />
</section>

{#each run.summary.bosses as boss (boss.fight)}
	<section class="glass pad block">
		<div class="boss-head">
			<h2><a href={fightHref(boss.fight)}>{boss.name}</a></h2>
			<span class="chip" class:ok={boss.killed} class:danger={!boss.killed}>{boss.killed ? 'besiegt' : 'nicht besiegt'}</span>
			<span class="dim">{formatDuration(boss.duration_ms)}</span>
		</div>
		<DamageBars players={boss.players} colorOf={color} />
		<a class="more" href={fightHref(boss.fight)}>DPS-Verlauf und Skills →</a>
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
	h1 {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
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
	.boss-head h2 a {
		color: var(--text);
		text-decoration: none;
	}
	.boss-head h2 a:hover {
		color: var(--accent);
	}
	.more {
		display: inline-block;
		margin-top: 12px;
		font-size: 14px;
		text-decoration: none;
	}
</style>
