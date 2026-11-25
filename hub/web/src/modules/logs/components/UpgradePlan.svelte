<!-- Upgrade-Plan eines Charakters (API: upgrades.py). Oben die Zielnote, dann was schnell erledigt ist,
     dann je Teil die Würfe, sortiert nach Punkten je Versuch; das erste ist „Als Nächstes“. Darunter die
     Teile, die nur noch gebunden werden müssen, das Ziel nicht erreichen oder schon dort sind. -->
<script lang="ts">
	import Fold from '#lib/components/Fold.svelte';
	import Tabs from '#lib/components/Tabs.svelte';
	import { formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { ArmoryHint } from '#modules/armory/api.ts';
	import { GOALS, type PlanPiece, type UpgradePlan } from '../rating.ts';
	import ItemIcon from './ItemIcon.svelte';
	import RatingBadge from './RatingBadge.svelte';
	import UpgradeSteps from './UpgradeSteps.svelte';

	let { plan, hints, base }: { plan: UpgradePlan; hints: ArmoryHint[]; /** Adresse des Reiters, ohne Ziel */ base: string } = $props();

	const goals = $derived(GOALS.map((g) => ({ id: g, label: g, href: `${base}?goal=${encodeURIComponent(g)}` })));

	/** Text eines Hinweises aus dem Ratgeber (ratgeber.py) */
	function hintText(h: ArmoryHint): string {
		if (h.art === 'set') return t('logs.upgrades.hint.set', { set: h.set, n: h.hat, of: h.braucht });
		if (h.art === 'sockel') return t('logs.upgrades.hint.sockel', { item: h.item, n: h.frei });
		const values = h.werte.join(', ');
		if (h.art === 'verzaubern') return t('logs.upgrades.hint.verzaubern', { item: h.item, n: h.stufe, values });
		return t(`logs.upgrades.hint.${h.art}`, { item: h.item, values });
	}
</script>

{#snippet piece(p: PlanPiece, note?: string)}
	<li>
		<ItemIcon name={p.name ?? p.slot} icon={p.icon} grade={p.grade} size={36} />
		<span class="name">{p.name ?? p.slot}</span>
		{#if p.letter && p.score !== null}<RatingBadge letter={p.letter} score={p.score} />{/if}
		{#if note}<span class="dim">{note}</span>{/if}
	</li>
{/snippet}

<!-- Teile, an denen nichts zu würfeln ist: als Akkordeon, damit der Plan oben im Blick bleibt -->
{#snippet group(id: string, title: string, pieces: PlanPiece[], note?: string)}
	{#if pieces.length}
		<div class="fold-row">
			<Fold id="upgrades.{id}" title={title} hint={String(pieces.length)}>
				{#if note}<p class="dim note">{note}</p>{/if}
				<ul class="pieces">
					{#each pieces as p (p.slot)}{@render piece(p)}{/each}
				</ul>
			</Fold>
		</div>
	{/if}
{/snippet}

<div class="head">
	<span class="dim">{t('logs.upgrades.goal')}</span>
	<Tabs tabs={goals} active={plan.goal} label={t('logs.upgrades.goal')} />
	{#if plan.group}<span class="chip">{plan.group}</span>{/if}
	<a class="how" href="/hub/bewertung#upgrades">{t('logs.upgrades.how')}</a>
</div>

{#if hints.length}
	<section class="panel">
		<h3>{t('logs.upgrades.quick')}</h3>
		<ul class="hints">
			{#each hints as h, i (i)}<li>{hintText(h)}</li>{/each}
		</ul>
	</section>
{/if}

<h3 class="section">{t('logs.upgrades.reroll')}</h3>
{#each plan.cards as card, i (card.slot)}
	<article class="panel card">
		<header>
			<ItemIcon name={card.name ?? card.slot} icon={card.icon} grade={card.grade} size={44} />
			<div class="title">
				<strong>{card.name ?? card.slot}</strong>
				<span class="way">
					{#if card.letter && card.score !== null}<RatingBadge letter={card.letter} score={card.score} />{/if}
					<span aria-hidden="true">→</span>
					<RatingBadge letter={card.after_letter} score={card.after[0]} />
					<span class="dim">
						{Math.round(card.after[0])}–{Math.round(card.after[1])}, {t('logs.upgrades.mean', { n: Math.round(card.mean) })}
						· {t('logs.upgrades.tries', { n: formatNumber(Math.ceil(card.tries)) })}
					</span>
				</span>
			</div>
			{#if i === 0}<span class="chip accent">{t('logs.upgrades.next')}</span>{/if}
		</header>
		<UpgradeSteps steps={card.steps} />
	</article>
{:else}
	<p class="dim">{t('logs.upgrades.none')}</p>
{/each}

{@render group('bind', t('logs.upgrades.bindOnly'), plan.bind)}
{#if plan.unreachable.length}
	<div class="fold-row">
		<Fold id="upgrades.unreachable" title={t('logs.upgrades.unreachable', { goal: plan.goal })} hint={String(plan.unreachable.length)}>
			<ul class="pieces">
				{#each plan.unreachable as p (p.slot)}{@render piece(p, t(`logs.upgrades.reason.${p.reason}`))}{/each}
			</ul>
		</Fold>
	</div>
{/if}
{@render group('done', t('logs.upgrades.done', { goal: plan.goal }), plan.done)}
{@render group('arcana', t('logs.upgrades.arcana'), plan.arcana, t('logs.upgrades.arcanaHint'))}

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		margin-bottom: 14px;
	}
	.how {
		margin-left: auto;
		font-size: 13px;
	}
	.panel {
		padding: 14px 16px;
		margin-bottom: 12px;
	}
	h3 {
		font-size: 15px;
		margin: 0 0 8px;
	}
	.fold-row {
		margin-bottom: 12px;
	}
	.section {
		margin: 18px 0 10px;
	}
	.note {
		margin: 0 0 8px;
		font-size: 13px;
	}
	.card header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px;
	}
	.title {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
		flex: 1;
	}
	.way {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		font-size: 13px;
	}
	.pieces,
	.hints {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 8px;
		font-size: 14px;
	}
	.pieces li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
	}
	.hints li::before {
		content: '›';
		margin-right: 8px;
		color: var(--faint);
	}
</style>
