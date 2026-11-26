<!-- Parse eines Spielers an einem Boss: EU (Abyss Logs), Gilde und Klasse (Klassenstatistik von Abyss Logs: Platz in
     der DPS-Verteilung der letzten Woche für Klasse und Kampfkraft), je als Zahl in der Farbstufe (ParseValue). -->
<script lang="ts">
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { classInfo } from '#modules/logs/classes.ts';
	import { CP_RANGE, type Parse } from '../api.ts';
	import ParseValue from './ParseValue.svelte';

	let { parse, cls, guildMin, classStats = true }: {
		parse: Parse | undefined;
		cls: string | null;
		guildMin: number;
		/** Klassenstatistik zeigen (nur je Kampf, nicht im Schnitt über den Run) */
		classStats?: boolean;
	} = $props();

	/** „251.000–261.000“: der CP-Bereich, gegen den EU vergleicht */
	const cpRange = (cp: number) => `${formatNumber(Math.max(0, cp - CP_RANGE))}–${formatNumber(cp + CP_RANGE)}`;

	const euTip = $derived.by(() => {
		if (!parse || !classInfo(cls)) return t('parses.eu.noClass');
		if (parse.eu_at === null) return t('parses.eu.loading');
		const range = parse.eu_cp != null ? cpRange(parse.eu_cp) : null;
		if (parse.eu_few && range) return t('parses.eu.few', { n: parse.eu_n ?? 0, range });
		if (parse.eu === null) return t('parses.eu.none');
		const values = {
			pct: parse.eu,
			n: formatNumber(parse.eu_n ?? 0),
			cls: classInfo(cls)?.label ?? '',
			date: formatDateTime(parse.eu_at)
		};
		return range ? t('parses.eu.tipCp', { ...values, range }) : t('parses.eu.tip', values);
	});
	const guildTip = $derived.by(() => {
		if (parse?.guild != null) return t('parses.guild.tip', { pct: parse.guild, n: formatNumber(parse.guild_n) });
		if (parse && !parse.member) return t('parses.guild.notMember');
		return t('parses.guild.few', { n: parse?.guild_n ?? 0, min: guildMin });
	});
	const classTip = $derived.by(() => {
		const b = parse?.bench;
		if (!b) return t('parses.class.none');
		const range = b.cp_floor != null && b.cp_ceil != null
			? `${formatNumber(b.cp_floor)}–${formatNumber(b.cp_ceil)}` : t('parses.class.allCp');
		return t('parses.class.tip', {
			pct: b.pct, cls: classInfo(cls)?.label ?? '', range, median: formatNumber(b.median),
			top25: formatNumber(b.top25), top10: formatNumber(b.top10), n: formatNumber(b.samples)
		});
	});
	const loading = $derived(!!parse && !!classInfo(cls) && parse.eu_at === null);
</script>

{#snippet value(label: string, v: number | null | undefined, tip: string, pending = false)}
	<span class="parse" title={tip} aria-label={tip}>
		<small>{label}</small>
		{#if v != null}<b><ParseValue value={v} /></b>{:else}<b class="none">{pending ? '…' : '–'}</b>{/if}
	</span>
{/snippet}

<span class="parses num">
	{@render value(t('parses.eu'), parse?.eu, euTip, loading)}
	{@render value(t('parses.guild'), parse?.guild, guildTip)}
	{#if classStats}{@render value(t('parses.class'), parse?.bench?.pct, classTip)}{/if}
</span>

<style>
	.parses {
		display: inline-flex;
		gap: 10px;
		white-space: nowrap;
	}
	.parse {
		display: inline-flex;
		align-items: baseline;
		gap: 4px;
		cursor: help;
	}
	small {
		font-size: 11px;
		color: var(--faint);
	}
	b {
		min-width: 2ch;
		text-align: right;
		font-weight: 700;
	}
	.none {
		color: var(--faint);
		font-weight: 450;
	}
</style>
