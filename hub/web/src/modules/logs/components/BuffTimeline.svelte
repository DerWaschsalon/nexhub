<!-- Buff-Zeitleiste: Buffs auf dem gewählten Spieler, dann Debuffs auf dem Boss (wie im Meter);
     je Buff eine Spur mit den Zeiten, in denen er aktiv war, rechts die Laufzeit. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { Buff } from '../api.ts';
	import { buffIcon, buffName } from '../names.svelte.ts';
	import Lanes, { type LaneRow } from './Lanes.svelte';

	let {
		buffs,
		actor,
		target,
		playerName,
		boss,
		durationMs
	}: { buffs: Buff[]; actor: number; target: number | null; playerName: string; boss: string; durationMs: number } =
		$props();

	/** Gleiche Buffs von mehreren Quellen auf eine Spur, längste Laufzeit zuerst. */
	function rows(on: number): LaneRow[] {
		const byId = new Map<number, Buff[]>();
		for (const b of buffs) if (b.actor === on) byId.set(b.id, [...(byId.get(b.id) ?? []), b]);
		return [...byId.entries()]
			.map(([id, list]) => {
				const up = Math.min(100, (100 * Math.max(...list.map((b) => b.up))) / durationMs);
				return {
					key: id,
					name: buffName(id),
					src: buffIcon(id),
					segments: list.flatMap((b) => b.segments.map(([s, e, n]) => [s, e, n] as [number, number, number])),
					up,
					value: up > 0 && up < 1 ? '<1%' : `${Math.round(up)}%`,
					valueTitle: t('logs.buffs.uptime')
				};
			})
			.sort((a, b) => b.up - a.up);
	}

	const own = $derived(rows(actor));
	const onBoss = $derived(target != null ? rows(target) : []);
</script>

<h3>{t('logs.buffs.onPlayer', { name: playerName })}</h3>
{#if own.length}<Lanes rows={own} {durationMs} />{:else}<p class="dim">{t('logs.buffs.none')}</p>{/if}
{#if target != null}
	<h3>{t('logs.buffs.onTarget', { boss })}</h3>
	{#if onBoss.length}<Lanes rows={onBoss} {durationMs} />{:else}<p class="dim">{t('logs.buffs.none')}</p>{/if}
{/if}

<style>
	h3 {
		font-size: 15px;
		margin: 18px 0 10px;
	}
	h3:first-child {
		margin-top: 0;
	}
</style>
