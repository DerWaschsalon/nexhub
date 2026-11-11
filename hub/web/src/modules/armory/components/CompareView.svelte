<!-- Zwei Charaktere nebeneinander: Kampfkraft, Werte samt zusammengezählter Effekte, Ausrüstung und
     Arkana je Platz mit allem, was darauf ist (Grundwerte, Durchbruch, Seelenbindung, Manasteine,
     verstärkte Skills, Set), Skills und Daevanion. Der Unterschied steht immer aus Sicht des linken
     Charakters: grün = vorne, rot = hinten. -->
<script lang="ts">
	import { formatNumber, formatPct } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { CharacterData } from '#modules/logs/api.ts';
	import DaevanionBoard from '#modules/logs/components/DaevanionBoard.svelte';
	import ItemIcon from '#modules/logs/components/ItemIcon.svelte';
	import PlayerName from '#modules/logs/components/PlayerName.svelte';
	import { ARCANA, LEFT, RIGHT } from '#modules/logs/slots.ts';
	import { sumEffects } from '#modules/logs/stats.ts';
	import { compareItems, type CompareSide, type ItemPart } from '../compare.ts';

	let { left, right }: { left: CompareSide; right: CompareSide } = $props();

	let board = $state(0);

	const itemLevel = (d: CharacterData) => d.stats.find((s) => s.type === 'ItemLevel')?.value ?? 0;

	// Werte in der Reihenfolge des linken Charakters, ohne Gegenstandsstufe (steht oben)
	const stats = $derived(
		left.data.stats
			.filter((s) => s.type !== 'ItemLevel')
			.map((s) => ({ name: s.name, a: s.value, b: right.data.stats.find((o) => o.type === s.type)?.value ?? 0 }))
	);

	// Zusammengezählte Effekte beider (Angriff +5,9 % …), verbunden über Name und Einheit
	const totals = $derived.by(() => {
		const key = (n: string, u: string) => `${n}|${u}`;
		const a = new Map(sumEffects(left.data.stats).map((s) => [key(s.name, s.unit), s]));
		const b = new Map(sumEffects(right.data.stats).map((s) => [key(s.name, s.unit), s]));
		return [...new Set([...a.keys(), ...b.keys()])].map((k) => {
			const found = a.get(k) ?? b.get(k);
			return { name: found?.name ?? k, unit: found?.unit ?? '', a: a.get(k)?.value ?? 0, b: b.get(k)?.value ?? 0 };
		});
	});

	// Überschrift je Teil eines Gegenstands
	const PART_LABEL: Record<ItemPart, string> = {
		main: 'armory.compare.part.main',
		sub: 'logs.char.soulBinding',
		stones: 'logs.char.manastones',
		skills: 'logs.char.skillEffects',
		set: 'armory.compare.part.set'
	};

	// Plätze, die mindestens einer der beiden belegt hat
	const slots = $derived(
		[...LEFT, ...RIGHT, ...ARCANA]
			.map((slot) => ({
				a: left.data.equipment.find((e) => e.slot_name === slot),
				b: right.data.equipment.find((e) => e.slot_name === slot)
			}))
			.filter((row) => row.a || row.b)
	);
	// Ein Gegenstand zählt als besser, wenn Verzauberung und Durchbruch zusammen höher sind
	const power = (e?: { enchant: number; exceed: number }) => (e ? e.enchant + e.exceed : 0);

	/** Zahl für die Tabelle: Prozent und Kommazahlen mit einer Nachkommastelle, sonst ganze Zahl */
	function show(v: number | null, unit = ''): string {
		if (v === null) return '—';
		if (unit === '%') return formatPct(v);
		return Number.isInteger(v) ? formatNumber(v) : v.toLocaleString(i18n.locale, { maximumFractionDigits: 1 });
	}

	// Skills mit Stufe bei mindestens einem der beiden, sortiert wie beim linken
	const skills = $derived(
		[...new Set([...left.data.skills, ...right.data.skills].map((s) => s.name))]
			.map((name) => ({
				name,
				icon: (left.data.skills.find((s) => s.name === name) ?? right.data.skills.find((s) => s.name === name))?.icon,
				a: left.data.skills.find((s) => s.name === name)?.level ?? 0,
				b: right.data.skills.find((s) => s.name === name)?.level ?? 0
			}))
			.filter((s) => s.a || s.b)
	);
</script>

{#snippet diff(a: number, b: number, unit = '')}
	<td class="num diff" class:ahead={a > b} class:behind={a < b}>{a === b ? '' : (a > b ? '+' : '−') + show(Math.abs(a - b), unit)}</td>
{/snippet}

{#snippet head()}
	<thead>
		<tr>
			<th></th>
			<th><PlayerName name={left.name} cls={left.cls} size={18} /></th>
			<th><PlayerName name={right.name} cls={right.cls} size={18} /></th>
			<th class="right">{t('armory.compare.diff')}</th>
		</tr>
	</thead>
{/snippet}

<section class="glass pad">
	<div class="table-wrap">
		<table class="table">
			{@render head()}
			<tbody>
				<tr>
					<td>{t('logs.char.combatPower')}</td>
					<td class="num">{formatNumber(left.data.profile.combat_power)}</td>
					<td class="num">{formatNumber(right.data.profile.combat_power)}</td>
					{@render diff(left.data.profile.combat_power, right.data.profile.combat_power)}
				</tr>
				<tr>
					<td>{t('logs.char.itemLevel')}</td>
					<td class="num">{formatNumber(itemLevel(left.data))}</td>
					<td class="num">{formatNumber(itemLevel(right.data))}</td>
					{@render diff(itemLevel(left.data), itemLevel(right.data))}
				</tr>
			</tbody>
		</table>
	</div>
</section>

<section class="glass pad">
	<h2>{t('logs.char.stats')}</h2>
	<div class="table-wrap">
		<table class="table">
			{@render head()}
			<tbody>
				{#each stats as s (s.name)}
					<tr><td>{s.name}</td><td class="num">{s.a}</td><td class="num">{s.b}</td>{@render diff(s.a, s.b)}</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if totals.length}
		<h3 class="sub">{t('armory.compare.totals')}</h3>
		<div class="table-wrap">
			<table class="table">
				{@render head()}
				<tbody>
					{#each totals as s (s.name + s.unit)}
						<tr>
							<td>{s.name}</td>
							<td class="num">{show(s.a, s.unit)}</td>
							<td class="num">{show(s.b, s.unit)}</td>
							{@render diff(s.a, s.b, s.unit)}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>

<section class="glass pad">
	<h2>{t('logs.char.equipment')}</h2>
	<div class="table-wrap">
		<table class="table">
			<tbody>
				{#each slots as row, i (i)}
					<tr>
						{#each [row.a, row.b] as e, side (side)}
							<td class:behind={side === 0 && power(row.a) < power(row.b)} class:ahead={side === 0 && power(row.a) > power(row.b)}>
								{#if e}
									<span class="item">
										<ItemIcon name={e.name} icon={e.icon} grade={e.grade} enchant={e.enchant} exceed={e.exceed} size={40} />
										<span>{e.name}</span>
									</span>
								{:else}
									<span class="dim">–</span>
								{/if}
							</td>
						{/each}
					</tr>
					{@const parts = compareItems(row.a, row.b)}
					{#if parts.length}
						<tr class="detail-row">
							<td colspan="2">
								<details open>
									<summary class="dim small">{t('armory.compare.itemValues')}</summary>
									<table class="table values">
										{#each parts as [part, rows] (part)}
											<tbody>
												<tr><th colspan="4">{t(PART_LABEL[part])}</th></tr>
												{#each rows as r (r.name)}
													<tr>
														<td>{r.name}</td>
														<td class="num">{show(r.a, r.unit)}</td>
														<td class="num">{show(r.b, r.unit)}</td>
														{@render diff(r.a ?? 0, r.b ?? 0, r.unit)}
													</tr>
												{/each}
											</tbody>
										{/each}
									</table>
								</details>
							</td>
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
</section>

<section class="glass pad">
	<h2>{t('logs.char.skills')}</h2>
	<div class="table-wrap">
		<table class="table">
			{@render head()}
			<tbody>
				{#each skills as s (s.name)}
					<tr>
						<td>
							<span class="item">
								{#if s.icon}<img src={s.icon} alt="" width="28" height="28" referrerpolicy="no-referrer" />{/if}
								{s.name}
							</span>
						</td>
						<td class="num">{s.a}</td>
						<td class="num">{s.b}</td>
						{@render diff(s.a, s.b)}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<section class="glass pad">
	<h2>{t('logs.char.daevanion')}</h2>
	<p class="dim small">{t('armory.compare.boardHint')}</p>
	<div class="boards">
		<div>
			<h3><PlayerName name={left.name} cls={left.cls} size={18} /></h3>
			<DaevanionBoard boards={left.data.daevanion} cls={left.cls} compare={right.data.daevanion} bind:chosen={board} />
		</div>
		<div>
			<h3><PlayerName name={right.name} cls={right.cls} size={18} /></h3>
			<DaevanionBoard boards={right.data.daevanion} cls={right.cls} compare={left.data.daevanion} bind:chosen={board} />
		</div>
	</div>
</section>

<style>
	section {
		margin-bottom: 16px;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 10px;
	}
	h3 {
		font-size: 15px;
		margin-bottom: 8px;
	}
	.diff {
		font-weight: 600;
		text-align: right;
	}
	.ahead {
		color: var(--ok);
	}
	.behind {
		color: var(--danger);
	}
	td.ahead,
	td.behind {
		font-weight: 600;
	}
	.item {
		display: inline-flex;
		align-items: center;
		gap: 10px;
	}
	.item img {
		border-radius: 6px;
	}
	.boards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
		gap: 20px;
		margin-top: 10px;
	}
	.small {
		font-size: 12px;
	}
	.sub {
		margin-top: 18px;
	}
	/* Alle Werte eines Platzes: eingerückt unter dem Gegenstandspaar */
	.detail-row > td {
		padding-top: 0;
	}
	details {
		margin: 0 0 6px 50px;
	}
	summary {
		cursor: pointer;
		margin-bottom: 4px;
	}
	.values th {
		padding-top: 10px;
		text-align: left;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #3fd6e8;
	}
	.values td {
		font-size: 13px;
	}
</style>
