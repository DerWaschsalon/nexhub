<!-- Rahmen eines Runs: Kopf mit Eckdaten, Auswahl Gesamt/je Boss, darunter die gewählte Ansicht.
     Gleich im Hub und auf geteilten Seiten; `actions` und `extra` füllt der jeweilige Bereich. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { formatDuration, formatMs } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Run } from '../api.ts';

	let {
		run,
		base,
		fight,
		actions,
		extra,
		children
	}: {
		run: Run;
		/** Adresse des Runs, z. B. /hub/runs/5 oder /r/<token> */
		base: string;
		/** gewählter Kampf, null = Gesamt */
		fight: string | null;
		actions?: Snippet;
		extra?: Snippet;
		children: Snippet;
	} = $props();

	const fightHref = (f: string) => `${base}/kampf/${encodeURIComponent(f)}`;
</script>

<header class="head">
	<div>
		<h1>{run.dungeon}</h1>
		<p class="meta">
			{#if run.difficulty}<span class="chip">{run.difficulty}</span>{/if}
			<span class="chip" class:ok={run.bosses_killed === run.bosses_total} class:warn={run.bosses_killed !== run.bosses_total}>
				{t('logs.run.bosses', { k: run.bosses_killed, t: run.bosses_total })}
			</span>
			<span class="dim">{formatMs(run.start_ms)}</span>
			<span class="dim">{t('logs.run.fightTime', { d: formatDuration(run.summary.fight_ms) })}</span>
			{#if run.uploader}<span class="dim">{t('logs.run.by', { name: run.uploader })}</span>{/if}
		</p>
	</div>
	{#if actions}<div class="actions">{@render actions()}</div>{/if}
</header>

{@render extra?.()}

<nav class="fights" aria-label={t('logs.run.fights')}>
	<a href={base} class:active={fight === null} aria-current={fight === null ? 'page' : undefined}>
		<strong>{t('logs.run.overall')}</strong>
		<span class="dim num">{formatDuration(run.summary.fight_ms)}</span>
	</a>
	{#each run.summary.bosses as b (b.fight)}
		<a href={fightHref(b.fight)} class:active={fight === b.fight} aria-current={fight === b.fight ? 'page' : undefined}>
			<strong>{b.name}</strong>
			<span class="dim num">
				<i class:kill={b.killed} class:wipe={!b.killed} aria-label={t(b.killed ? 'logs.fight.killed' : 'logs.fight.wipe')}></i>
				{formatDuration(b.duration_ms)}
			</span>
		</a>
	{/each}
</nav>

<div class="body">
	{@render children()}
</div>

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	h1 {
		font-size: clamp(26px, 4vw, 38px);
		letter-spacing: -0.02em;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 14px;
		margin: 10px 0 0;
		font-size: 14px;
	}
	.actions {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.fights {
		display: flex;
		gap: 10px;
		overflow-x: auto;
		padding: 2px 2px 6px;
		margin: 16px 0;
		scrollbar-width: thin;
	}
	.fights a {
		flex: 0 0 auto;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 150px;
		padding: 12px 16px;
		border-radius: var(--radius-sm);
		border: 1px solid var(--edge-soft);
		background: rgba(255, 255, 255, 0.04);
		color: var(--text);
		text-decoration: none;
	}
	.fights a:hover {
		background: rgba(255, 255, 255, 0.08);
	}
	.fights a.active {
		border-color: rgba(106, 211, 255, 0.55);
		background: rgba(106, 211, 255, 0.1);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
	}
	.fights span {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 13px;
	}
	i {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	i.kill {
		background: var(--ok);
	}
	i.wipe {
		background: var(--danger);
	}
	.body {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
</style>
