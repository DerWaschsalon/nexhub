<!-- Run-Liste: alle hochgeladenen Runs, neueste zuerst. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { formatDuration, formatMs } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<header class="page-head">
	<h1>Runs</h1>
	<p>Dungeon-Runs, die eure NexBoards hochgeladen haben.</p>
</header>

{#if data.runs.length}
	<section class="glass pad table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>Dungeon</th>
					<th>Bosse</th>
					<th>Dauer</th>
					<th>Datum</th>
					<th>Aufgenommen von</th>
				</tr>
			</thead>
			<tbody>
				{#each data.runs as run (run.id)}
					<tr class="link" onclick={() => goto(`/hub/runs/${run.id}`)}>
						<td>
							<a href="/hub/runs/{run.id}"><strong>{run.dungeon}</strong></a>
							{#if run.difficulty}<span class="chip">{run.difficulty}</span>{/if}
						</td>
						<td>
							<span class="chip" class:ok={run.complete}>{run.bosses_killed}/{run.bosses_total}</span>
						</td>
						<td class="dim">{formatDuration(run.end_ms - run.start_ms)}</td>
						<td class="dim">{formatMs(run.start_ms)}</td>
						<td class="dim">{run.character ?? run.uploader}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{:else}
	<section class="glass pad empty">
		<p>Noch keine Runs.</p>
		<p class="dim">
			Im NexBoard-Modul „NexHub“ das Hochladen einschalten. Nach dem nächsten Dungeon erscheint der
			Run hier.
		</p>
	</section>
{/if}

<style>
	tr.link {
		cursor: pointer;
		transition: background 0.15s;
	}
	tr.link:hover {
		background: rgba(255, 255, 255, 0.04);
	}
	td a {
		color: var(--text);
		text-decoration: none;
		margin-right: 8px;
	}
	.empty p {
		margin: 0 0 4px;
	}
</style>
