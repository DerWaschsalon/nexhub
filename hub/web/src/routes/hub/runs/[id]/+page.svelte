<!-- Run gesamt: Schaden über alle Kämpfe; Namen führen zum Charakterprofil. -->
<script lang="ts">
	import { formatCompact } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Player } from '#modules/logs/api.ts';
	import RankBars from '#modules/logs/components/RankBars.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const byName = $derived(new Map(data.characters.map((c) => [c.name, c])));
	const href = (p: Player) => {
		const c = byName.get(p.name);
		return c ? `/hub/runs/${data.run.id}/spieler/${c.id}` : undefined;
	};
	const note = (p: Player) => {
		const cp = byName.get(p.name)?.combat_power;
		return cp ? `${t('logs.char.combatPower')} ${formatCompact(cp)}` : undefined;
	};
</script>

<section class="glass pad">
	<h2>{t('logs.run.damageRun')}</h2>
	<RankBars players={data.run.summary.players} {href} {note} />
</section>

<style>
	h2 {
		font-size: 17px;
		margin-bottom: 14px;
	}
</style>
