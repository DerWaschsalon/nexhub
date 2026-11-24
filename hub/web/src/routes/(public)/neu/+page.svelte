<!-- Changelog: jeder gemergte PR mit Datum, nach Tagen gruppiert, wählbar nach Bereich. Die Liste erzeugt
     infra/changelog.py beim Bauen des Hubs (static/changelog.json); ohne sie sagt die Seite das. -->
<script lang="ts">
	import Tabs from '#lib/components/Tabs.svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';

	type Entry = { date: string; pr: number; title: string; areas: string[] };
	const REPO = 'https://github.com/DerWaschsalon/nexhub';
	const AREAS = ['hub', 'nexboard', 'firmware', 'bot', 'core', 'infra'];

	let entries = $state<Entry[] | null>(null);
	let area = $state('all');

	$effect(() => {
		fetch('/changelog.json')
			.then((r) => (r.ok ? r.json() : []))
			.catch(() => [])
			.then((list: Entry[]) => (entries = list));
	});

	const tabs = $derived([
		{ id: 'all', label: t('changelog.all') },
		...AREAS.map((id) => ({ id, label: t(`changelog.area.${id}`) }))
	]);
	const shown = $derived((entries ?? []).filter((e) => area === 'all' || e.areas.includes(area)));
	// Einträge je Tag, die Tage in der Reihenfolge der Liste (neueste zuerst)
	const days = $derived([...Map.groupBy(shown, (e) => e.date)]);
	const dayLabel = (iso: string) =>
		new Date(`${iso}T00:00:00Z`).toLocaleDateString(i18n.locale, { dateStyle: 'long', timeZone: 'UTC' });
</script>

<svelte:head><title>{t('changelog.title')} · NexHub</title></svelte:head>

<article class="glass pad prose">
	<h1>{t('changelog.title')}</h1>
	<p>{t('changelog.intro')}</p>

	{#if entries?.length}
		<Tabs {tabs} active={area} onselect={(id) => (area = id)} label={t('changelog.title')} />
		{#each days as [day, list] (day)}
			<h2>{dayLabel(day)}</h2>
			<ul>
				{#each list as e (e.pr)}
					<li>
						{e.title}
						<a href="{REPO}/pull/{e.pr}" target="_blank" rel="noopener">#{e.pr}</a>
						{#each e.areas as a (a)}<span class="chip">{t(`changelog.area.${a}`)}</span>{/each}
					</li>
				{/each}
			</ul>
		{/each}
	{:else if entries}
		<p>{t('changelog.none')}</p>
	{/if}
</article>

<style>
	li {
		margin-bottom: 6px;
	}
	.chip {
		margin-left: 6px;
	}
</style>
