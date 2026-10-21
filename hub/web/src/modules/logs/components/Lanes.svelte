<!-- Spuren über die Kampfzeit: je Zeile Symbol + Name, darunter Zeitpunkte (points, z. B. Zauber)
     oder Abschnitte (segments, z. B. Buffs), rechts optional ein Wert (Laufzeit). Oben die Zeitachse. -->
<script lang="ts" module>
	export type LaneRow = {
		key: string | number;
		name: string;
		/** Symbol: Skill-Code oder fertige Bildadresse */
		code?: number | null;
		src?: string | null;
		points?: number[];
		/** [start, ende, stapel] in ms */
		segments?: [number, number, number][];
		value?: string;
		valueTitle?: string;
	};
</script>

<script lang="ts">
	import { formatDuration, timeTicks } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import SkillIcon from './SkillIcon.svelte';

	let { rows, durationMs, color }: { rows: LaneRow[]; durationMs: number; color?: string } = $props();

	const withValue = $derived(rows.some((r) => r.value !== undefined));
	const pct = (ms: number) => (100 * Math.min(durationMs, Math.max(0, ms))) / durationMs;
</script>

<div class="lanes" class:with-value={withValue} style:--lane-color={color}>
	<div class="lane axis" aria-hidden="true">
		<span></span>
		<div class="track">
			{#each timeTicks(durationMs) as ms (ms)}
				<span class="tick" style:left="{pct(ms)}%">{formatDuration(ms)}</span>
			{/each}
		</div>
		{#if withValue}<span></span>{/if}
	</div>
	{#each rows as r (r.key)}
		<div class="lane">
			<span class="name">
				{#if r.src !== undefined}<SkillIcon src={r.src} size={22} />{:else}<SkillIcon code={r.code} size={22} />{/if}
				{r.name}
			</span>
			<div class="track">
				{#each r.points ?? [] as ms, i (i)}
					<span class="point" style:left="{pct(ms)}%" title={formatDuration(ms)}></span>
				{/each}
				{#each r.segments ?? [] as [start, end, stacks], i (i)}
					{#if pct(end) > pct(start)}
						<span class="seg" style:left="{pct(start)}%" style:width="{pct(end) - pct(start)}%"
							style:opacity={0.55 + Math.min(stacks, 5) * 0.09}
							title="{formatDuration(start)}–{formatDuration(end)}{stacks > 1 ? ` · ${t('logs.buffs.stacks', { n: stacks })}` : ''}"></span>
					{/if}
				{/each}
			</div>
			{#if withValue}<span class="value num" title={r.valueTitle}>{r.value ?? ''}</span>{/if}
		</div>
	{/each}
</div>

<style>
	.lanes {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.lane {
		display: grid;
		grid-template-columns: 190px minmax(0, 1fr);
		align-items: center;
		gap: 12px;
		min-height: 30px;
	}
	.with-value .lane {
		grid-template-columns: 190px minmax(0, 1fr) 46px;
	}
	.name {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.track {
		position: relative;
		height: 22px;
		border-radius: 6px;
		background: rgba(255, 255, 255, 0.035);
	}
	.axis .track {
		background: none;
		height: 18px;
	}
	.tick {
		position: absolute;
		top: 0;
		transform: translateX(-50%);
		font-size: 11px;
		color: var(--faint);
		white-space: nowrap;
	}
	.tick:first-child {
		transform: none;
	}
	.point {
		position: absolute;
		top: 3px;
		bottom: 3px;
		width: 3px;
		margin-left: -1px;
		border-radius: 2px;
		background: var(--lane-color, var(--accent));
		box-shadow: 0 0 6px -1px var(--lane-color, var(--accent));
	}
	.seg {
		position: absolute;
		top: 4px;
		bottom: 4px;
		border-radius: 4px;
		background: linear-gradient(90deg, var(--accent), var(--accent-2));
	}
	.value {
		text-align: right;
		font-size: 13px;
		font-weight: 600;
	}
	@media (max-width: 900px) {
		.lane,
		.with-value .lane {
			grid-template-columns: 110px minmax(0, 1fr) auto;
			gap: 8px;
		}
	}
</style>
