<!-- Charakterprofil aus einer Momentaufnahme: Kopf, Ausrüstung, Werte, Titel, Skills, Daevanion.
     Dieselbe Ansicht für Mitspieler eines Runs und die Armory; `source` sagt, woher der Stand kommt. -->
<script lang="ts">
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterListItem } from '../api.ts';
	import DaevanionBoard from './DaevanionBoard.svelte';
	import ItemIcon from './ItemIcon.svelte';
	import PlayerName from './PlayerName.svelte';

	let { character, data, source }: { character: CharacterListItem; data: CharacterData; source?: string } = $props();

	// Plätze wie im Ausrüstungsfenster: links Waffen und Rüstung, rechts Schmuck, darunter der Rest
	const LEFT = ['MainHand', 'SubHand', 'Helmet', 'Shoulder', 'Torso', 'Pants', 'Gloves', 'Boots', 'Cape', 'Belt'];
	const RIGHT = ['Necklace', 'Earring1', 'Earring2', 'Ring1', 'Ring2', 'Bracelet1', 'Bracelet2', 'Amulet', 'Rune1', 'Rune2'];
	const bySlot = $derived(new Map(data.equipment.map((e) => [e.slot_name, e])));
	const rest = $derived(data.equipment.filter((e) => !LEFT.includes(e.slot_name) && !RIGHT.includes(e.slot_name)));
	const groups = $derived([
		{ label: t('logs.char.active'), skills: data.skills.filter((s) => s.category === 'Active') },
		{ label: t('logs.char.passive'), skills: data.skills.filter((s) => s.category === 'Passive') },
		{ label: t('logs.char.stigma'), skills: data.skills.filter((s) => s.category === 'Dp' && (s.equipped || s.learned)) }
	]);
	const stats = $derived(data.stats.filter((s) => s.type !== 'ItemLevel'));
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
	<h3>{t('logs.char.equipment')}</h3>
	<div class="gear">
		{@render slots(LEFT)}
		{@render slots(RIGHT)}
	</div>
	<div class="extra">
		{#each rest as e (e.slot)}
			<ItemIcon name={e.name} icon={e.icon} grade={e.grade} enchant={e.enchant} exceed={e.exceed} size={40} />
		{/each}
		{#if data.wing}
			<ItemIcon name="{t('logs.char.wing')}: {data.wing.name}" icon={data.wing.icon} grade={data.wing.grade} enchant={data.wing.enchant} size={40} />
		{/if}
		{#if data.pet}
			<ItemIcon name="{t('logs.char.pet')}: {data.pet.name}" icon={data.pet.icon} size={40} />
		{/if}
	</div>
</section>

<div class="cols">
	<section class="glass pad">
		<h3>{t('logs.char.stats')}</h3>
		<div class="table-wrap">
			<table class="table">
				<tbody>
					{#each stats as s (s.type)}
						<tr>
							<td>{s.name}</td>
							<td class="num right">{s.value}</td>
							<td class="dim small">{s.effects.join(' · ')}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	<section class="glass pad">
		<h3>{t('logs.char.titles', { o: data.titles.owned, t: data.titles.total })}</h3>
		{#each data.titles.equipped as title (title.name)}
			<div class="title">
				<strong>{title.name}</strong> <span class="chip">{title.category}</span>
				<p class="dim small">{title.effects.join(' · ')}</p>
			</div>
		{/each}
	</section>
</div>

<section class="glass pad">
	<h3>{t('logs.char.skills')}</h3>
	{#each groups as g (g.label)}
		{#if g.skills.length}
			<h4>{g.label}</h4>
			<div class="skills">
				{#each g.skills as s (s.name)}
					<div
						class="skill"
						class:missing={s.equipped && !s.learned}
						title={s.equipped && !s.learned ? `${s.name} – ${t('logs.char.notLearned')}` : s.name}
					>
						{#if s.icon}<img src={s.icon} alt="" width="36" height="36" loading="lazy" referrerpolicy="no-referrer" />{/if}
						<span>{s.name}</span>
						<strong class="num">{s.level}</strong>
					</div>
				{/each}
			</div>
		{/if}
	{/each}
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
	h4 {
		font-size: 13px;
		margin: 14px 0 8px;
		color: var(--dim);
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
	.skill span {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.extra {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		margin-top: 14px;
	}
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr));
		gap: 0 16px;
	}
	.title {
		margin-bottom: 10px;
	}
	.skills {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 8px;
	}
	.skill {
		display: flex;
		gap: 8px;
		align-items: center;
		padding: 2px;
		border-radius: 8px;
	}
	.skill img {
		border-radius: 8px;
	}
	.skill span {
		flex: 1;
		min-width: 0;
	}
	.skill.missing {
		opacity: 0.6;
		outline: 1px dashed var(--danger);
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
