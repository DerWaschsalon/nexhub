<!-- Ein Run als Glaszeile: Zeitpunkt, ein Kästchen je Bosskampf (grün Kill, rot Wipe), die Gruppe als
     Klassensymbole, Dauer und wer aufgenommen hat. Für die Seite eines Dungeons und die Übersicht „Heute“. -->
<script lang="ts">
	import { formatDuration } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { RunListItem } from '../api.ts';
	import { classInfo } from '../classes.ts';

	let { run, title, best = false }: {
		run: RunListItem;
		/** Name statt Datum vorn (Übersicht „Heute“) */
		title?: string;
		/** schnellster Run: Dauer in Grün */
		best?: boolean;
	} = $props();

	const ICONS = 8;
	const start = $derived(new Date(run.start_ms));
	const kills = $derived(run.results.filter(Boolean).length);
	const wipes = $derived(run.results.length - kills);
	const group = $derived(run.classes.map((c, i) => ({ cls: c, name: run.players[i] })).slice(0, ICONS));
</script>

<a class="row" href="/hub/runs/{run.id}">
	<span class="when">
		{#if title}
			<strong>{title}</strong>
			<small class="num">{start.toLocaleTimeString(i18n.locale, { hour: '2-digit', minute: '2-digit' })} · Run {run.id}</small>
		{:else}
			<strong class="num">{start.toLocaleDateString(i18n.locale, { day: '2-digit', month: '2-digit', year: 'numeric' })}</strong>
			<small class="num">{start.toLocaleTimeString(i18n.locale, { hour: '2-digit', minute: '2-digit' })} · Run {run.id}</small>
		{/if}
	</span>
	<span class="result">
		<span class="pips">
			{#each run.results as killed, i (i)}
				<i class:kill={killed} title={t(killed ? 'logs.row.kill' : 'logs.row.wipe')}></i>
			{/each}
		</span>
		<small class:clean={!wipes}>
			{wipes ? t('logs.row.killsWipes', { k: kills, w: wipes }) : t('logs.row.kills', { k: kills })}
		</small>
	</span>
	<span class="group">
		{#each group as p, i (i)}
			{@const info = classInfo(p.cls)}
			{#if info}
				<img src={info.icon} alt={info.label} title="{p.name} · {info.label}" width="26" height="26" />
			{:else}
				<span class="dot" title={p.name}></span>
			{/if}
		{/each}
		{#if run.players.length > ICONS}<small class="num">+{run.players.length - ICONS}</small>{/if}
	</span>
	<span class="dur num" class:best>{formatDuration(run.end_ms - run.start_ms)}</span>
	<span class="by">{run.character ? t('logs.row.by', { name: run.character }) : run.uploader}</span>
	<span class="go" aria-hidden="true">→</span>
</a>

<style>
	.row {
		display: grid;
		grid-template-columns: minmax(110px, 0.9fr) minmax(130px, 1fr) minmax(170px, 1.3fr) 76px minmax(110px, 0.9fr) 18px;
		gap: 14px;
		align-items: center;
		padding: 12px 16px;
		border-radius: 12px;
		border: 1px solid var(--edge-soft);
		background: var(--glass);
		backdrop-filter: blur(var(--glass-blur));
		-webkit-backdrop-filter: blur(var(--glass-blur));
		color: var(--text);
		text-decoration: none;
		transition: background 0.2s, border-color 0.2s;
	}
	.row:hover {
		background: var(--fill-strong);
		border-color: var(--edge);
	}
	.when,
	.result {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.when strong {
		font-size: 14px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	small {
		font-size: 12px;
		color: var(--faint);
	}
	small.clean {
		color: var(--ok);
	}
	.pips {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
	}
	i {
		width: 11px;
		height: 11px;
		border-radius: 4px;
		background: var(--danger);
		box-shadow: 0 0 8px color-mix(in srgb, var(--danger) 55%, transparent);
	}
	i.kill {
		background: var(--ok);
		box-shadow: 0 0 8px color-mix(in srgb, var(--ok) 55%, transparent);
	}
	.group {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px;
	}
	.group img {
		border-radius: 8px;
		border: 1px solid var(--edge);
		object-fit: contain;
	}
	.dot {
		width: 26px;
		height: 26px;
		border-radius: 8px;
		background: var(--fill-strong);
	}
	.dur {
		font-size: 16px;
		font-weight: 600;
		text-align: right;
	}
	.dur.best {
		color: var(--ok);
	}
	.by {
		font-size: 13px;
		color: var(--dim);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.go {
		color: var(--accent);
	}
	@media (max-width: 760px) {
		.row {
			grid-template-columns: 1fr auto;
		}
		.group,
		.by,
		.go {
			display: none;
		}
	}
</style>
