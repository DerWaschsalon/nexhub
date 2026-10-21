<!-- Modul Logs: alle hochgeladenen Runs, neueste zuerst. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { formatDuration, formatMs, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<header class="page-head">
	<h1>{t('logs.list.title')}</h1>
	<p>{t('logs.list.intro')}</p>
</header>

{#if data.runs.length}
	<section class="glass pad table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>{t('logs.col.dungeon')}</th>
					<th>{t('logs.col.bosses')}</th>
					<th class="right">{t('logs.col.duration')}</th>
					<th>{t('logs.col.played')}</th>
					<th>{t('logs.col.uploadedBy')}</th>
				</tr>
			</thead>
			<tbody>
				{#each data.runs as r (r.id)}
					<tr class="link" onclick={() => goto(`/hub/runs/${r.id}`)}>
						<td>
							<a href="/hub/runs/{r.id}"><strong>{r.dungeon}</strong></a>
							{#if r.difficulty}<span class="chip">{r.difficulty}</span>{/if}
						</td>
						<td>
							<span class="chip" class:ok={r.bosses_killed === r.bosses_total} class:warn={r.bosses_killed !== r.bosses_total}>
								{r.bosses_killed}/{r.bosses_total}
							</span>
						</td>
						<td class="right num">{formatDuration(r.end_ms - r.start_ms)}</td>
						<td class="dim">{formatMs(r.start_ms)}</td>
						<td class="dim">{r.uploader}{r.character ? ` (${r.character})` : ''}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="dim count">{t('logs.list.count', { n: formatNumber(data.runs.length) })}</p>
	</section>
{:else}
	<section class="glass pad"><p class="dim empty">{t('logs.list.empty')}</p></section>
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
	.count {
		margin: 12px 14px 0;
		font-size: 13px;
	}
	.empty {
		margin: 0;
	}
</style>
