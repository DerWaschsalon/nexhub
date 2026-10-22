<!-- Charakterprofil aus einer Momentaufnahme: Kopf, Ausrüstung, Werte, Titel, Skills, Daevanion.
     Dieselbe Ansicht für Mitspieler eines Runs und die Armory; `source` sagt, woher der Stand kommt. -->
<script lang="ts">
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import { ARCANA, LEFT, RIGHT } from '../slots.ts';
	import { localized, type CharacterListItem, type CharacterSnapshot } from '../api.ts';
	import { CHARACTER_ART } from '../assets.ts';
	import DaevanionBoard from './DaevanionBoard.svelte';
	import ItemCard from './ItemCard.svelte';
	import ItemIcon from './ItemIcon.svelte';
	import PlayerName from './PlayerName.svelte';
	import SkillGrid from './SkillGrid.svelte';
	import StatPanel from './StatPanel.svelte';

	let {
		character,
		data: snapshot,
		source,
		loadDetails
	}: {
		character: CharacterListItem;
		data: CharacterSnapshot;
		source?: string;
		/** Runs: Werte je Gegenstand nachladen (Knopf in der Ausrüstung); die Armory hat sie immer */
		loadDetails?: () => Promise<void>;
	} = $props();

	const data = $derived(localized(snapshot, i18n.lang));
	const details = $derived('v' in snapshot ? snapshot.details : undefined);

	// Plätze wie im Ausrüstungsfenster: links Waffen und Rüstung, rechts Schmuck, dann Arkana, dann der Rest
	const bySlot = $derived(new Map(data.equipment.map((e) => [e.slot_name, e])));
	const inSlots = (names: string[]) => names.map((n) => bySlot.get(n)).filter((e) => e !== undefined);
	const rest = $derived(data.equipment.filter((e) => ![...LEFT, ...RIGHT, ...ARCANA].includes(e.slot_name)));
	const arcana = $derived(inSlots(ARCANA));
	const arcanaSet = $derived(arcana.find((e) => e.detail?.set)?.detail?.set);
	// Werte je Gegenstand vorhanden (Armory immer, Runs nach „Item-Werte laden“)
	const withValues = $derived(data.equipment.some((e) => e.detail !== undefined));
	const canLoad = $derived(!!loadDetails && details?.state !== 'laden' && (!withValues || details?.state === 'fehler'));

	let busy = $state(false);
	let error = $state('');
	async function load() {
		busy = true;
		error = '';
		try {
			await loadDetails?.();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = false;
		}
	}
</script>

{#snippet slots(names: string[])}
	<div class="slots">
		{#each names as n (n)}
			{@const e = bySlot.get(n)}
			{#if e}
				<div class="slot">
					<ItemIcon name={e.name} icon={e.icon} grade={e.grade} enchant={e.enchant} exceed={e.exceed} />
					<span class="item-name">{e.name}</span>
				</div>
			{/if}
		{/each}
	</div>
{/snippet}

<header class="glass pad head">
	{#if data.profile.image}
		<img class="portrait" src={data.profile.image} alt="" width="72" height="72" referrerpolicy="no-referrer" />
	{/if}
	<div class="who">
		<h2><PlayerName name={data.profile.name} cls={character.cls} size={26} /></h2>
		<p class="dim">
			{[data.profile.class, t('logs.char.level', { n: data.profile.level }), data.profile.server, data.profile.guild]
				.filter(Boolean)
				.join(' · ')}
		</p>
		{#if data.profile.title}<p class="dim">„{data.profile.title}“</p>{/if}
	</div>
	<div class="numbers">
		<div>
			<span class="label">{t('logs.char.combatPower')}</span>
			<strong class="num">{formatNumber(data.profile.combat_power)}</strong>
		</div>
		{#if character.item_level}
			<div>
				<span class="label">{t('logs.char.itemLevel')}</span>
				<strong class="num">{formatNumber(character.item_level)}</strong>
			</div>
		{/if}
		{#if character.fetched_at}
			<span class="dim small">{t('logs.char.asOf', { d: formatDateTime(character.fetched_at) })}</span>
		{/if}
	</div>
</header>

<section class="glass pad">
	<div class="sec-head">
		<h3>{t('logs.char.equipment')}</h3>
		{#if canLoad}
			<button class="btn small" onclick={load} disabled={busy}>{t('logs.char.loadDetails')}</button>
		{/if}
	</div>
	{#if details?.state === 'laden'}
		<p class="notice" role="status">{t('logs.char.loadingDetails')}</p>
	{:else if details?.state === 'ok' && details.at}
		<p class="dim small note">{t('logs.char.detailsAsOf', { d: formatDateTime(details.at) })}</p>
	{:else if details?.state === 'fehler'}
		<p class="notice error" role="alert">{t('logs.char.detailsFailed', { why: details.error ?? '' })}</p>
	{/if}
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}

	{#if withValues}
		<div class="cards">
			{#each [...inSlots(LEFT), ...inSlots(RIGHT), ...rest] as e (e.slot)}<ItemCard item={e} />{/each}
		</div>
	{:else}
		<div class="gear">
			{@render slots(LEFT)}
			{@render slots(RIGHT)}
		</div>
	{/if}
	<div class="extra">
		{#if !withValues}
			{#each [...arcana, ...rest] as e (e.slot)}
				<ItemIcon name={e.name} icon={e.icon} grade={e.grade} enchant={e.enchant} exceed={e.exceed} size={40} />
			{/each}
		{/if}
		{#if data.wing}
			<ItemIcon name="{t('logs.char.wing')}: {data.wing.name}" icon={data.wing.icon} grade={data.wing.grade} enchant={data.wing.enchant} size={40} />
		{/if}
		{#if data.pet}
			<ItemIcon name="{t('logs.char.pet')}: {data.pet.name}" icon={data.pet.icon} size={40} />
		{/if}
	</div>
</section>

{#if withValues && arcana.length}
	<section class="glass pad">
		<h3>{t('logs.char.arcana')}</h3>
		{#if arcanaSet}
			<div class="set">
				<div class="set-head">
					<strong>{arcanaSet.name}</strong>
					<span class="chip">{t('logs.char.setCount', { n: arcanaSet.equipped, t: arcanaSet.total })}</span>
				</div>
				<ul>
					{#each arcanaSet.bonuses as b (b.degree)}
						<li class:active={arcanaSet.equipped >= b.degree}>
							<span class="degree">{t('logs.char.setEffect', { n: b.degree })}</span>
							<span>{b.lines.join(' · ')}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
		<div class="cards">
			{#each arcana as e (e.slot)}<ItemCard item={e} />{/each}
		</div>
	</section>
{/if}

<section class="glass pad">
	<h3>{t('logs.char.stats')}</h3>
	<StatPanel stats={data.stats} />
</section>

{#if data.titles.equipped.length}
	<section class="glass pad">
		<h3>{t('logs.char.titles', { o: data.titles.owned, t: data.titles.total })}</h3>
		<div class="titles">
			{#each data.titles.equipped as title (title.name)}
				<div class="title">
					{#if title.category}
						<img src="{CHARACTER_ART}/info/title_icon_{title.category.toLowerCase()}.png" alt={title.category} title={title.category}
							width="36" height="36" loading="lazy" referrerpolicy="no-referrer" />
					{/if}
					<div>
						<strong>{title.name}</strong>
						<p class="dim small">{title.effects.join(' · ')}</p>
					</div>
				</div>
			{/each}
		</div>
	</section>
{/if}

<section class="glass pad">
	<h3>{t('logs.char.skills')}</h3>
	<SkillGrid skills={data.skills} />
</section>

<section class="glass pad">
	<h3>{t('logs.char.daevanion')}</h3>
	{#if data.daevanion.some((b) => b.nodes?.length)}
		<DaevanionBoard boards={data.daevanion} cls={character.cls} />
	{:else}
	<div class="boards">
		{#each data.daevanion as b (b.id)}
			<div class="board">
				<div class="board-head">
					<strong>{b.name}</strong>
					<span class="dim small">{t('logs.char.nodes', { o: b.open_nodes, t: b.total_nodes })}</span>
				</div>
				<span class="bar"><span style:width="{b.total_nodes ? (100 * b.open_nodes) / b.total_nodes : 0}%"></span></span>
				{#if b.stats.length || b.skills.length}
					<p class="dim small">{[...b.stats, ...b.skills].join(' · ')}</p>
				{/if}
			</div>
		{/each}
	</div>
	{/if}
</section>

<p class="dim small">{source ?? t('logs.char.source')}</p>

<style>
	section,
	header {
		margin-bottom: 16px;
	}
	h3 {
		font-size: 17px;
		margin-bottom: 12px;
	}
	.head {
		display: flex;
		gap: 16px;
		align-items: center;
		flex-wrap: wrap;
	}
	.who {
		min-width: 0;
	}
	.portrait {
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.numbers {
		margin-left: auto;
		display: flex;
		gap: 20px;
		align-items: center;
		flex-wrap: wrap;
	}
	.numbers > div {
		display: flex;
		flex-direction: column;
	}
	.label {
		font-size: 12px;
		color: var(--dim);
	}
	.gear {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 10px 24px;
	}
	.slots {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.slot {
		display: flex;
		gap: 10px;
		align-items: center;
		min-width: 0;
	}
	.item-name,
	.extra {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		margin-top: 14px;
	}
	.sec-head {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		margin-bottom: 12px;
	}
	.sec-head h3 {
		margin-bottom: 0;
	}
	.note,
	.notice {
		margin-bottom: 12px;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
		gap: 12px;
	}
	.set {
		margin-bottom: 14px;
		padding: 12px 14px;
		border-radius: var(--radius-sm);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--edge-soft);
	}
	.set-head {
		display: flex;
		gap: 10px;
		align-items: center;
		margin-bottom: 8px;
	}
	.set ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 13px;
		color: var(--faint);
	}
	.set li {
		display: flex;
		gap: 10px;
	}
	.set li.active {
		color: var(--text);
	}
	.degree {
		flex-shrink: 0;
		font-weight: 600;
	}
	.titles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
		gap: 12px;
	}
	.title {
		display: flex;
		gap: 10px;
		align-items: flex-start;
	}
	.boards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 14px;
	}
	.board-head {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 6px;
	}
	.bar {
		display: block;
		height: 6px;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.35);
		overflow: hidden;
		margin-bottom: 6px;
	}
	.bar span {
		display: block;
		height: 100%;
		background: var(--accent);
	}
	.small {
		font-size: 12px;
	}
</style>
