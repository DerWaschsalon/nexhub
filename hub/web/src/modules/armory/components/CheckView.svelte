<!-- Build-Check: Ausrüstung wie im Spiel um das Charakterbild, jeder Platz mit Ampel gegen die Top-Spieler,
     darunter Werte, Daevanion, Skills und Titel, ganz unten „Zuerst“. Gezeigt wird nur, was nicht grün ist. -->
<script lang="ts">
	import { formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData } from '#modules/logs/api.ts';
	import ItemIcon from '#modules/logs/components/ItemIcon.svelte';
	import PlayerName from '#modules/logs/components/PlayerName.svelte';
	import { ARCANA, LEFT, RIGHT } from '#modules/logs/slots.ts';
	import { type CheckField, type CheckResult, worst } from '../check.ts';

	let { name, cls, data, result }: { name: string; cls: string | null; data: CharacterData; result: CheckResult } =
		$props();

	const PRESENCE = ['sub', 'stone', 'godstone', 'skill'];
	const open = $derived(result.fields.filter((f) => f.light !== 'green'));
	const cp = $derived(result.fields.find((f) => f.area === 'profile' && f.key === 'combat_power'));
	const il = $derived(result.fields.find((f) => f.area === 'profile' && f.key === 'item_level'));

	/** Eine Karte je Ausrüstungsplatz, den der Charakter trägt oder zu dem es etwas zu sagen gibt */
	function slots(names: string[]) {
		return names
			.map((slot) => ({
				item: data.equipment.find((e) => e.slot_name === slot),
				fields: result.fields.filter((f) => f.area === 'equipment' && f.slot === slot)
			}))
			.filter((s) => s.item || s.fields.length);
	}

	const boxes = $derived([
		{ title: t('logs.char.stats'), fields: open.filter((f) => f.area === 'stats') },
		{ title: t('logs.char.daevanion'), fields: open.filter((f) => f.area === 'daevanion') },
		{ title: t('logs.char.skills'), fields: open.filter((f) => f.area === 'skills') },
		{ title: t('armory.check.more'), fields: open.filter((f) => ['titles', 'wing', 'pet'].includes(f.area)) }
	]);

	function label(f: CheckField): string {
		const [prefix, rest] = f.key.split(/:(.*)/s);
		if (rest !== undefined && PRESENCE.includes(prefix)) return t(`armory.check.has.${prefix}`, { name: rest });
		if (f.area === 'stats') return data.stats.find((s) => s.type === f.key)?.name ?? f.key;
		if (f.area === 'daevanion' || f.area === 'skills') return f.slot;
		if (f.area === 'titles') return t('armory.check.titleSlot', { category: f.slot });
		if (f.area === 'wing') return t(f.key === 'name' ? 'logs.char.wing' : 'armory.check.key.wingEnchant');
		if (f.area === 'pet') return t('logs.char.pet');
		return t(`armory.check.key.${f.key}`);
	}

	const itemName = (slot: string) => data.equipment.find((e) => e.slot_name === slot)?.name ?? slot;
	const num = (v: number | string | null) => (typeof v === 'number' ? formatNumber(v) : (v ?? ''));
	const isPresence = (f: CheckField) => PRESENCE.includes(f.key.split(':')[0]) && f.key.includes(':');

	function value(f: CheckField): string {
		const n = { better: f.better, size: result.size };
		if (isPresence(f)) return t('armory.check.missing', n);
		if (f.kind === 'number') return t('armory.check.number', { mine: num(f.mine), median: num(f.median), ...n });
		const top = f.common[0];
		return t('armory.check.choice', { mine: f.mine, top: top?.value ?? '', count: top?.count ?? 0, size: result.size });
	}
</script>

{#snippet line(f: CheckField)}
	<li class={f.light}><span>{label(f)}</span><span class="v">{value(f)}</span></li>
{/snippet}

{#snippet card(s: { item: CharacterData['equipment'][number] | undefined; fields: CheckField[] })}
	{@const bad = s.fields.filter((f) => f.light !== 'green')}
	<div class="glass card {worst(s.fields)}">
		<div class="head">
			{#if s.item}
				<ItemIcon name={s.item.name} icon={s.item.icon} grade={s.item.grade} enchant={s.item.enchant} exceed={s.item.exceed} size={36} />
				<span class="name">{s.item.name}</span>
			{/if}
		</div>
		{#if bad.length}<ul>{#each bad as f (f.key)}{@render line(f)}{/each}</ul>{/if}
	</div>
{/snippet}

<header class="glass pad top">
	<div>
		<h2><PlayerName {name} {cls} size={26} /></h2>
		<p class="dim">{t('armory.check.against', { size: result.size, cls: data.profile.class })}</p>
	</div>
	<div class="kpis">
		{#each [cp, il] as k, i (i)}
			{#if k}
				<div class="kpi {k.light}">
					<span class="dim">{t(i ? 'logs.char.itemLevel' : 'logs.char.combatPower')}</span>
					<strong>{num(k.mine)}</strong>
					<span class="dim">{t('armory.check.median', { median: num(k.median) })}</span>
				</div>
			{/if}
		{/each}
	</div>
</header>

<div class="gear">
	<div class="col">{#each slots(LEFT) as s, i (i)}{@render card(s)}{/each}</div>
	<div class="figure">
		{#if data.profile.image}<img src={data.profile.image} alt={name} />{/if}
	</div>
	<div class="col">{#each slots(RIGHT) as s, i (i)}{@render card(s)}{/each}</div>
</div>

{#if slots(ARCANA).length}
	<h3>{t('logs.char.arcana')}</h3>
	<div class="arcana">{#each slots(ARCANA) as s, i (i)}{@render card(s)}{/each}</div>
{/if}

<div class="boxes">
	{#each boxes.filter((b) => b.fields.length) as b (b.title)}
		<section class="glass pad box">
			<h3>{b.title}</h3>
			<ul>{#each b.fields as f (f.slot + f.key)}{@render line(f)}{/each}</ul>
		</section>
	{/each}
</div>

{#if result.todo.length}
	<section class="glass pad todo">
		<h3>{t('armory.check.todo')}</h3>
		<ol>
			{#each result.todo as f (f.area + f.slot + f.key)}
				<li><strong>{f.area === 'equipment' ? `${itemName(f.slot)} · ` : ''}{label(f)}</strong> <span class="dim">{value(f)}</span></li>
			{/each}
		</ol>
	</section>
{/if}

<style>
	.top {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 16px;
	}
	.kpis {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
	}
	.kpi {
		display: flex;
		flex-direction: column;
		padding: 8px 14px;
		border-radius: var(--radius-sm);
		background: rgba(255, 255, 255, 0.05);
		border-left: 3px solid var(--light);
		font-size: 12px;
	}
	.kpi strong {
		font-size: 20px;
	}
	.gear {
		display: grid;
		grid-template-columns: 1fr minmax(160px, 220px) 1fr;
		gap: 12px;
		margin-bottom: 16px;
	}
	.col,
	.arcana {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.arcana {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
		margin-bottom: 16px;
	}
	.figure {
		display: flex;
		align-items: flex-start;
		justify-content: center;
	}
	.figure img {
		width: 100%;
		border-radius: var(--radius);
		position: sticky;
		top: 16px;
	}
	.card {
		padding: 10px 12px;
		border-radius: var(--radius-sm);
		border-left: 4px solid var(--light);
	}
	.head {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.name {
		font-weight: 600;
		font-size: 14px;
	}
	ul,
	ol {
		margin: 6px 0 0;
		padding: 0;
		font-size: 13px;
	}
	ul {
		list-style: none;
	}
	ol {
		padding-left: 20px;
		line-height: 1.8;
	}
	li {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		padding: 2px 0;
	}
	ol li {
		display: list-item;
	}
	.v {
		color: var(--light);
		text-align: right;
	}
	h3 {
		font-size: 15px;
		margin: 0 0 10px;
	}
	.boxes {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 12px;
		margin-bottom: 16px;
	}
	.green {
		--light: var(--ok);
	}
	.yellow {
		--light: var(--warn);
	}
	.red {
		--light: var(--danger);
	}
	/* Schmal: Bild oben, Ausrüstung darunter in einer Spalte */
	@media (max-width: 820px) {
		.gear {
			grid-template-columns: 1fr;
		}
		.figure {
			order: -1;
		}
		.figure img {
			max-width: 200px;
			position: static;
		}
	}
</style>
