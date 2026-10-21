<!-- Ein Bosskampf im Detail: DPS-Verlauf, Skills je Spieler, Tode.
     Gleiche Ansicht im Hub und auf geteilten Seiten. -->
<script lang="ts">
	import type { FightDetail } from '#lib/api.ts';
	import { CLASS_LABELS } from '#lib/classes.ts';
	import { playerColors } from '#lib/colors.ts';
	import DamageBars from '#lib/components/DamageBars.svelte';
	import DpsChart from '#lib/components/DpsChart.svelte';
	import { formatDuration, formatNumber } from '#lib/format.ts';

	let { fight, back }: { fight: FightDetail; back: string } = $props();

	// DPS-Kurve: Schaden je Sekunde, geglättet über die letzten SMOOTH Sekunden
	const SMOOTH = 5;
	const color = $derived(playerColors(fight.run_players));
	const series = $derived.by(() => {
		if (!fight.timeline) return [];
		const step = fight.timeline.bucket_ms / 1000;
		return fight.players.map((p) => {
			const raw = fight.timeline!.players.find((t) => t.actor === p.actor)?.damage ?? [];
			const values = raw.map((_, i) => {
				const from = Math.max(0, i - SMOOTH + 1);
				return raw.slice(from, i + 1).reduce((a, b) => a + b, 0) / ((i - from + 1) * step);
			});
			return { name: p.name, color: color(p.name), values };
		});
	});

	let selected = $state(0);
	const player = $derived(fight.players[selected] ?? fight.players[0]);
</script>

<a class="back" href={back}>← Run</a>

<header class="page-head head">
	<h1>{fight.name}</h1>
	<span class="chip" class:ok={fight.killed} class:danger={!fight.killed}>{fight.killed ? 'besiegt' : 'nicht besiegt'}</span>
	<span class="dim">{formatDuration(fight.duration_ms)}</span>
</header>

<section class="glass pad block">
	<h2>DPS-Verlauf</h2>
	{#if fight.timeline}
		<p class="dim sub">Schaden pro Sekunde, gleitender Schnitt über {SMOOTH} s</p>
		<DpsChart {series} stepMs={fight.timeline.bucket_ms} />
	{:else}
		<p class="dim">
			Für diesen Kampf gibt es keine Einzeltreffer – er wurde vor dem Treffer-Update von NexBoard
			aufgenommen. Summen und Skills unten stimmen trotzdem.
		</p>
	{/if}
</section>

<section class="glass pad block">
	<h2>Schaden</h2>
	<DamageBars players={fight.players} colorOf={color} />
</section>

<section class="glass pad block">
	<h2>Skills</h2>
	<div class="tabs" role="tablist">
		{#each fight.players as p, i (p.actor)}
			<button role="tab" aria-selected={i === selected} class:active={i === selected} onclick={() => (selected = i)}>
				<span class="swatch" style:background={color(p.name)}></span>{p.name}
			</button>
		{/each}
	</div>
	{#if player}
		<p class="dim sub">
			{player.cls ? CLASS_LABELS[player.cls] : 'Klasse unbekannt'} · {formatNumber(player.dps)} DPS ·
			{formatNumber(player.damage)} Schaden
		</p>
		<div class="table-wrap">
			<table class="table">
				<thead>
					<tr>
						<th>Skill</th>
						<th class="num">Schaden</th>
						<th class="num">Anteil</th>
						<th class="num">Treffer</th>
						<th class="num">Krit</th>
						<th class="num">Rücken</th>
						<th class="num">Perfekt</th>
						<th class="num">Doppel</th>
					</tr>
				</thead>
				<tbody>
					{#each player.skills as s (s.code + (s.dot ? 'd' : ''))}
						<tr>
							<td>{s.name}{#if s.dot}<span class="chip">DoT</span>{/if}</td>
							<td class="num">{formatNumber(s.damage)}</td>
							<td class="num share">
								<span class="track"><span style:width="{s.share}%" style:background={color(player.name)}></span></span>
								{s.share.toLocaleString('de-DE')} %
							</td>
							<td class="num">{formatNumber(s.hits)}</td>
							<td class="num">{s.crit.toLocaleString('de-DE')} %</td>
							<td class="num">{s.back.toLocaleString('de-DE')} %</td>
							<td class="num">{s.perfect.toLocaleString('de-DE')} %</td>
							<td class="num">{s.double.toLocaleString('de-DE')} %</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>

{#if fight.deaths.length}
	<section class="glass pad block">
		<h2>Tode</h2>
		<ul class="deaths">
			{#each fight.deaths as d (d.name + d.t_ms)}
				<li>
					<span class="time">{formatDuration(d.t_ms)}</span>
					<strong>{d.name}</strong>
					<span class="dim">{d.revived_ms != null ? `wiederbelebt nach ${formatDuration(d.revived_ms - d.t_ms)}` : 'nicht wiederbelebt'}</span>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	.back {
		color: var(--dim);
		text-decoration: none;
		font-size: 14px;
	}
	.head {
		display: flex;
		align-items: baseline;
		gap: 12px;
		flex-wrap: wrap;
		margin-top: 4px;
	}
	.block {
		margin-bottom: 16px;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 4px;
	}
	.sub {
		margin: 0 0 12px;
		font-size: 13px;
	}
	.block > h2 + :global(ol),
	.block > h2 + .tabs {
		margin-top: 12px;
	}
	.tabs {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 10px;
	}
	.tabs button {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		color: var(--dim);
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid var(--edge-soft);
		border-radius: 999px;
		padding: 6px 12px;
		cursor: pointer;
	}
	.tabs button.active {
		color: var(--text);
		background: rgba(255, 255, 255, 0.12);
		border-color: var(--edge);
	}
	.swatch {
		width: 10px;
		height: 10px;
		border-radius: 3px;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.track {
		display: inline-block;
		width: 48px;
		height: 6px;
		margin-right: 8px;
		border-radius: 3px;
		background: rgba(255, 255, 255, 0.08);
		vertical-align: middle;
		overflow: hidden;
	}
	.track span {
		display: block;
		height: 100%;
		border-radius: 3px;
	}
	td .chip {
		margin-left: 8px;
	}
	.deaths {
		list-style: none;
		margin: 12px 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.deaths li {
		display: flex;
		gap: 12px;
		align-items: baseline;
		flex-wrap: wrap;
	}
	.time {
		font-variant-numeric: tabular-nums;
		color: var(--faint);
		min-width: 40px;
	}
</style>
