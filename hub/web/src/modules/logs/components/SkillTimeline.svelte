<!-- Fähigkeiten-Zeitleiste: der Opener als Reihe, darunter je Fähigkeit eine Spur mit jedem Zauber.
     Rechts lassen sich Fähigkeiten ein- und ausblenden. -->
<script lang="ts">
	import { SvelteSet } from 'svelte/reactivity';
	import { formatDuration } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { FightPlayer } from '../api.ts';
	import { castsOf } from '../casts.ts';
	import { classColor } from '../classes.ts';
	import { skillName } from '../names.svelte.ts';
	import Lanes from './Lanes.svelte';
	import SkillIcon from './SkillIcon.svelte';

	let { player, durationMs, boss }: { player: FightPlayer; durationMs: number; boss: string } = $props();

	const OPENER = 24; // so viele Zauber zeigt der Opener

	const casts = $derived(castsOf(player));
	// Fähigkeiten in der Reihenfolge ihres ersten Einsatzes
	const skills = $derived.by(() => {
		const seen = new Map<string, { key: string; code: number | null; name: string; times: number[] }>();
		for (const c of casts) {
			const key = `${c.code}|${c.name}`;
			if (!seen.has(key)) seen.set(key, { key, code: c.code, name: c.name, times: [] });
			seen.get(key)!.times.push(c.t);
		}
		return [...seen.values()];
	});
	const hidden = new SvelteSet<string>();
	const shown = $derived(skills.filter((s) => !hidden.has(s.key)));
	const allHidden = $derived(hidden.size === skills.length);

	function toggleAll() {
		if (allHidden) hidden.clear();
		else for (const s of skills) hidden.add(s.key);
	}
</script>

{#if !casts.length}
	<p class="dim">{t('logs.timeline.noCasts')}</p>
{:else}
	<div class="layout">
		<div class="main">
			<h3>{t('logs.timeline.opener')}</h3>
			<ol class="opener">
				{#each casts.slice(0, OPENER) as c, i (i)}
					<li title="{formatDuration(c.t)} · {skillName(c.code, c.name)}">
						<SkillIcon code={c.code} size={30} />
						<span>{skillName(c.code, c.name)}</span>
					</li>
				{/each}
			</ol>

			<h3>{t('logs.timeline.skills')}</h3>
			<Lanes {durationMs} color={classColor(player.cls)}
				rows={shown.map((s) => ({ key: s.key, code: s.code, name: skillName(s.code, s.name), points: s.times }))} />
		</div>

		<aside class="filter">
			<div class="filter-head">
				<strong>{t('logs.filter.skills')} <span class="dim">{shown.length}</span></strong>
				<button type="button" class="link" onclick={toggleAll}>
					{allHidden ? t('logs.filter.all') : t('logs.filter.none')}
				</button>
			</div>
			<ul>
				{#each skills as s (s.key)}
					<li>
						<label>
							<input type="checkbox" checked={!hidden.has(s.key)}
								onchange={() => (hidden.has(s.key) ? hidden.delete(s.key) : hidden.add(s.key))} />
							<SkillIcon code={s.code} size={20} />
							<span>{skillName(s.code, s.name)}</span>
						</label>
					</li>
				{/each}
			</ul>
			<div class="filter-head target-head">
				<strong>{t('logs.filter.target')}</strong>
			</div>
			<p class="target">{boss}</p>
		</aside>
	</div>
{/if}

<style>
	h3 {
		font-size: 15px;
		margin: 18px 0 10px;
	}
	h3:first-child {
		margin-top: 0;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 240px;
		gap: 20px;
	}
	.opener {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 6px 0;
	}
	.opener li {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 10px 4px 4px;
		border-radius: 10px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid var(--edge-soft);
		font-size: 13px;
	}
	.opener li + li {
		margin-left: 14px;
	}
	.opener li + li::before {
		content: '›';
		position: absolute;
		left: -12px;
		color: var(--faint);
	}
	.filter {
		border-left: 1px solid var(--edge-soft);
		padding-left: 18px;
		font-size: 13px;
	}
	.filter-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin: 0 0 8px;
	}
	.target-head {
		margin-top: 18px;
	}
	.link {
		border: 0;
		background: none;
		color: var(--accent);
		cursor: pointer;
		font: inherit;
		font-size: 13px;
		padding: 0;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
		max-height: 420px;
		overflow-y: auto;
	}
	label {
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
	}
	input {
		accent-color: var(--accent);
		margin: 0;
	}
	.target {
		margin: 0;
	}
	@media (max-width: 900px) {
		.layout {
			grid-template-columns: minmax(0, 1fr);
		}
		.filter {
			border-left: 0;
			padding-left: 0;
		}
		ul {
			flex-direction: row;
			flex-wrap: wrap;
			gap: 6px 14px;
			max-height: none;
		}
	}
</style>
