<!-- Seite „Termine“: oben, was offen ist oder als Nächstes kommt, dann alle Termine mit Countdown, dann der
     Wochenplan. Die Zeiten rechnet die API; die Seite zählt herunter und fragt neu, sobald ein Termin
     beginnt oder endet. Uhr wahlweise die eigene oder die des Servers (gemerkt im Browser). -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import { clock } from '#lib/clock.svelte.ts';
	import Countdown from '#lib/components/Countdown.svelte';
	import Tabs from '#lib/components/Tabs.svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { Schedule, ScheduleEvent } from '../api.ts';

	const STORAGE = 'nexhub.clock';
	type Zone = 'local' | 'server';

	let data = $state<Schedule | null>(null);
	let error = $state('');
	let zone = $state<Zone>(savedZone());

	function savedZone(): Zone {
		try {
			return localStorage.getItem(STORAGE) === 'server' ? 'server' : 'local';
		} catch {
			return 'local'; // privates Fenster
		}
	}

	function choose(id: string) {
		zone = id as Zone;
		try {
			localStorage.setItem(STORAGE, zone);
		} catch {
			/* privates Fenster: gilt bis zum Neuladen */
		}
	}

	const RELOAD_GAP_S = 5; // geht die eigene Uhr vor, fragt die Seite nicht jede Sekunde neu
	let loadedAt = 0;

	async function load() {
		loadedAt = clock.now;
		try {
			data = await api<Schedule>('/api/public/termine');
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	// der nächste Zeitpunkt, an dem sich etwas ändert: ein Beginn oder das Ende eines offenen Termins
	const nextChange = $derived(Math.min(...(data?.events ?? []).map((e) => e.open_until ?? e.start)));

	$effect(() => {
		const now = clock.now;
		if (now - loadedAt < RELOAD_GAP_S) return;
		if (!data || now > nextChange) load();
	});

	const name = (e: { name_en: string; name_de: string }) => (i18n.lang === 'de' ? e.name_de : e.name_en);
	const byKey = $derived(new Map((data?.events ?? []).map((e) => [e.key, e])));
	// offene zuerst, dann nach Beginn
	const sorted = $derived(
		[...(data?.events ?? [])].sort((a, b) => Number(!a.open_until) - Number(!b.open_until) || a.start - b.start)
	);
	const first = $derived(sorted[0]);

	const when = (seconds: number) =>
		new Intl.DateTimeFormat(i18n.locale, {
			weekday: 'short',
			hour: '2-digit',
			minute: '2-digit',
			timeZone: zone === 'server' ? data?.server_zone : undefined
		}).format(new Date(seconds * 1000));
</script>

{#snippet countdown(e: ScheduleEvent)}
	{#if e.open_until}
		<span class="chip ok">{t('schedule.openFor')} <Countdown until={e.open_until} /></span>
	{:else}
		<span class="dim">{t('schedule.in')}</span> <Countdown until={e.start} />
	{/if}
{/snippet}

<header class="page-head">
	<h1>{t('schedule.title')}</h1>
	<p class="dim">{t('schedule.intro')}</p>
</header>

{#if error}<p class="notice error" role="alert">{error}</p>{/if}

{#if data && first}
	<div class="clock">
		<span class="dim">{t('schedule.clock')}</span>
		<Tabs tabs={[{ id: 'local', label: t('schedule.clock.local') }, { id: 'server', label: t('schedule.clock.server') }]}
			active={zone} onselect={choose} label={t('schedule.clock')} />
	</div>

	<section class="glass next">
		<span class="dim">{t(first.open_until ? 'schedule.open' : 'schedule.next')}</span>
		<h2>{name(first)}</h2>
		<p class="big">{@render countdown(first)}</p>
		<p class="dim">{when(first.start)}{#if first.place} · {first.place}{/if}</p>
	</section>

	<section class="glass pad">
		<h2>{t('schedule.soon')}</h2>
		<div class="table-wrap">
			<table class="table">
				<thead>
					<tr><th>{t('schedule.col.event')}</th><th>{t('schedule.col.when')}</th><th class="right">{t('schedule.col.countdown')}</th></tr>
				</thead>
				<tbody>
					{#each sorted as e (e.key)}
						<tr>
							<td><strong>{name(e)}</strong>{#if e.place}<small class="dim">{e.place}</small>{/if}</td>
							<td class="num">{when(e.start)}</td>
							<td class="right">{@render countdown(e)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	{#if data.week.length}
		<section class="glass pad">
			<h2>{t('schedule.week')}</h2>
			<ul class="week">
				{#each data.week as p (`${p.key}-${p.start}`)}
					{@const e = byKey.get(p.key)}
					<li><span class="num">{when(p.start)}</span><span>{e ? name(e) : p.key}</span></li>
				{/each}
			</ul>
		</section>
	{/if}
{/if}

<style>
	.clock {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		margin-bottom: 14px;
	}
	section {
		margin-bottom: 14px;
	}
	.next {
		padding: 20px 22px;
	}
	.next h2 {
		font-size: 26px;
		margin: 4px 0 8px;
	}
	.big {
		font-size: 22px;
		font-weight: 600;
		margin: 0 0 6px;
	}
	h2 {
		font-size: 17px;
		margin: 0 0 10px;
	}
	td small {
		display: block;
		font-size: 12px;
	}
	.week {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 6px;
	}
	.week li {
		display: grid;
		grid-template-columns: minmax(110px, max-content) 1fr;
		gap: 16px;
	}
</style>
