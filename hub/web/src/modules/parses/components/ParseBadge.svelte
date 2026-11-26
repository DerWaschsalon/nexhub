<!-- Parse eines Spielers an einem Boss: EU (Abyss Logs) und Gilde, je als Zahl in der Farbstufe -->
<script lang="ts">
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { classInfo } from '#modules/logs/classes.ts';
	import { parseColor, type Parse } from '../api.ts';

	let { parse, cls, guildMin }: { parse: Parse | undefined; cls: string | null; guildMin: number } = $props();

	const euTip = $derived.by(() => {
		if (!parse || !classInfo(cls)) return t('parses.eu.noClass');
		if (parse.eu_at === null) return t('parses.eu.loading');
		if (parse.eu === null) return t('parses.eu.none');
		return t('parses.eu.tip', {
			pct: parse.eu,
			n: formatNumber(parse.eu_n ?? 0),
			cls: classInfo(cls)?.label ?? '',
			date: formatDateTime(parse.eu_at)
		});
	});
	const guildTip = $derived.by(() => {
		if (parse?.guild != null) return t('parses.guild.tip', { pct: parse.guild, n: formatNumber(parse.guild_n) });
		if (parse && !parse.member) return t('parses.guild.notMember');
		return t('parses.guild.few', { n: parse?.guild_n ?? 0, min: guildMin });
	});
	const loading = $derived(!!parse && !!classInfo(cls) && parse.eu_at === null);
</script>

{#snippet value(label: string, v: number | null | undefined, tip: string, pending = false)}
	<span class="parse" title={tip} aria-label={tip}>
		<small>{label}</small>
		{#if v != null}<b class={parseColor(v)}>{v}</b>{:else}<b class="none">{pending ? '…' : '–'}</b>{/if}
	</span>
{/snippet}

<span class="parses num">
	{@render value(t('parses.eu'), parse?.eu, euTip, loading)}
	{@render value(t('parses.guild'), parse?.guild, guildTip)}
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
	/* Farbstufen wie bei Warcraft Logs, etwas gedämpft, damit sie auf hellem und dunklem Grund lesbar bleiben */
	.grey {
		color: #9aa0a6;
	}
	.green {
		color: #2fbf3a;
	}
	.blue {
		color: #3d86f0;
	}
	.purple {
		color: #a750ee;
	}
	.orange {
		color: #ff8000;
	}
	.pink {
		color: #e268a8;
	}
	.gold {
		color: #d4b45a;
	}
	.none {
		color: var(--faint);
		font-weight: 450;
	}
</style>
