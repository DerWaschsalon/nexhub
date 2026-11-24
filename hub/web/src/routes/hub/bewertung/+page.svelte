<!-- „Wie wir bewerten“: die Rechnung hinter Note und Upgrade-Plan in Worten. Die Zahlen (Notenbänder,
     Zielnoten, Stufen) kommen von der API (routes/rating.py), damit Text und Code nicht auseinanderlaufen.
     Ändert sich die Rechnung in rating.py oder upgrades.py, diese Seite mit ändern. -->
<script lang="ts">
	import { formatPct } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import RatingBadge from '#modules/logs/components/RatingBadge.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const r = $derived(data.rules);
	const goals = $derived(r.goals.join(i18n.lang === 'de' ? ' oder ' : ' or '));
</script>

<svelte:head><title>{t('logs.scoring.title')} · NexHub</title></svelte:head>

<article class="glass pad prose">
	<h1>{t('logs.scoring.title')}</h1>

	{#if i18n.lang === 'de'}
		<p class="dim">
			Die Note eines Teils sagt, wie nah es an dem ist, was die besten Spieler deiner Klasse auf diesem Platz
			tragen. Vorbild ist kisk.app.
		</p>

		<h2>Womit wir vergleichen</h2>
		<p>
			Je Klasse bis zu {r.pool_size} Top-Spieler aus den Ranglisten von Abyss Logs ({r.region}), über den Tag
			verteilt abgerufen und stündlich gezählt. Gespeichert wird nur die Zählung, keine Namen. Was diese
			Spieler tragen, zeigen die <a href="/hub/bis">BiS-Listen</a>.
		</p>

		<h2>Die Note eines Teils</h2>
		<ol>
			<li>
				<strong>Zeile:</strong> Anteil der Top-Spieler mit dieser Zeile auf diesem Platz × dein Wert ÷ größter Wert,
				den ein Gegenstand dieses Platzes haben kann.
			</li>
			<li>
				<strong>Teil:</strong> Summe der Zeilen ÷ bestes Stück des Platzes. Das beste Stück hat die häufigsten Werte
				und Skills, voll gewürfelt, und so viele davon, wie ein Teil der Top-Spieler dort meist trägt. Es ist für
				jedes Teil des Platzes gleich: Ein Teil mit weniger Zeilen kann 100 nicht erreichen.
			</li>
			<li><strong>Note:</strong> aus den Punkten, nach dieser Tabelle.</li>
		</ol>
	{:else}
		<p class="dim">
			A piece's grade says how close it is to what the best players of your class wear on that slot. It follows
			kisk.app.
		</p>

		<h2>What we compare against</h2>
		<p>
			Up to {r.pool_size} top players per class from the Abyss Logs rankings ({r.region}), fetched throughout the
			day and counted hourly. Only the count is stored, no names. What these players wear is on the
			<a href="/hub/bis">BiS lists</a>.
		</p>

		<h2>The grade of a piece</h2>
		<ol>
			<li>
				<strong>Line:</strong> share of top players with this line on this slot × your value ÷ the largest value an
				item of this slot can have.
			</li>
			<li>
				<strong>Piece:</strong> sum of the lines ÷ the best piece of the slot. The best piece has the most common
				stats and skills, fully rolled, and as many of them as a top player's piece usually has there. It is the same
				for every piece of the slot: a piece with fewer lines cannot reach 100.
			</li>
			<li><strong>Grade:</strong> from the points, by this table.</li>
		</ol>
	{/if}

	<table class="table bounds">
		<thead>
			<tr><th>{t('logs.scoring.grade')}</th><th class="right">{t('logs.scoring.from')}</th></tr>
		</thead>
		<tbody>
			{#each r.bounds as b (b.letter)}
				<tr><td><RatingBadge letter={b.letter} /></td><td class="right num">{b.low}</td></tr>
			{/each}
		</tbody>
	</table>

	{#if i18n.lang === 'de'}
		<h2 id="upgrades">Der Upgrade-Plan</h2>
		<p>
			Ziel ist {goals}, Standard ist {r.default_goal}. Für jedes Teil sucht der Plan die höchstens {r.max_rerolls}
			Zeilen, die im Mittel die wenigsten Versuche bis zur Zielnote brauchen.
		</p>
		<ul>
			<li>
				Ein Ziel zählt nur, wenn es schon beim schlechtesten Wurf seinen Anteil bringt. Die Zielnote stimmt
				deshalb auch bei Pech.
			</li>
			<li>
				Die Chance pro Versuch kommt aus den Würfeltabellen von MetaBot.GG. Wie oft ein Wurf ein Skill wird, ist
				geschätzt.
			</li>
			<li>
				Ziele stehen in Stufen: „Ideal“ bringt mindestens {formatPct(r.tier_best * 100)} des besten Ziels,
				„Sonst gut“ mindestens {formatPct(r.tier_good * 100)}, „Geht auch“ reicht gerade noch.
			</li>
			<li>
				Die Teile sind nach Punkten je Versuch sortiert. Das erste ist „Als Nächstes“.
			</li>
			<li>
				Erst binden, wenn die Würfe sitzen: Eine neu gewürfelte Zeile muss erneut gebunden werden. Würfe, die
				nur Skills treffen, müssen nicht warten.
			</li>
		</ul>

		<h2>Grenzen</h2>
		<ul>
			<li>Verglichen wird mit dem, was Top-Spieler heute tragen, nicht mit dem, was sie am Ende wollen.</li>
			<li>Ein Wert zählt gleich viel, egal wie viel du davon schon hast.</li>
			<li>Werte aus dem Durchbruch schickt die AION-2-Website nicht, sie fehlen in der Rechnung.</li>
			<li>Ausrüstung für PvP bewerten wir nicht eigens.</li>
		</ul>
	{:else}
		<h2 id="upgrades">The upgrade plan</h2>
		<p>
			The target is {goals}, {r.default_goal} by default. For each piece the plan looks for the at most
			{r.max_rerolls} lines that need the fewest tries on average to reach the target grade.
		</p>
		<ul>
			<li>
				A target only counts if it brings its share even on the worst roll. The target grade therefore holds
				with bad luck too.
			</li>
			<li>
				The chance per try comes from the roll tables of MetaBot.GG. How often a roll becomes a skill is an
				estimate.
			</li>
			<li>
				Targets come in tiers: "Ideal" brings at least {formatPct(r.tier_best * 100)} of the best target, "Also good"
				at least {formatPct(r.tier_good * 100)}, "Fine" is just enough.
			</li>
			<li>Pieces are sorted by points per try. The first one is "Up next".</li>
			<li>
				Bind only once the rolls are right: a rerolled line has to be bound again. Rolls that only hit skills do
				not have to wait.
			</li>
		</ul>

		<h2>Limits</h2>
		<ul>
			<li>We compare with what top players wear today, not with what they want in the end.</li>
			<li>A stat counts the same no matter how much of it you already have.</li>
			<li>The AION 2 website does not send breakthrough values, so they are missing here.</li>
			<li>PvP gear is not rated separately.</li>
		</ul>
	{/if}
</article>

<style>
	.bounds {
		max-width: 320px;
		margin: 10px 0 18px;
	}
</style>
