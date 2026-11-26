<!-- „Wie wir bewerten“: die Rechnung hinter Note und Upgrade-Plan in Worten. Die Zahlen (Notenbänder,
     Zielnoten, Stufen) kommen von der API (modules/armory/rating_routes.py), damit Text und Code nicht auseinanderlaufen.
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

	<!-- Parses in der Kampfansicht (Modul parses). Ändert sich modules/parses/calc.py oder fetcher.py
	     (Schwelle GUILD_MIN = 10, Abruf täglich), diesen Abschnitt mit ändern. -->
	{#if i18n.lang === 'de'}
		<h2 id="parses">Parses in der Kampfansicht</h2>
		<p>
			Bei getöteten Bossen steht hinter dem DPS jedes Spielers eine Zahl von 0 bis 100: wie viel Prozent der
			Vergleichswerte derselben Klasse am selben Boss dein DPS erreicht oder übertrifft. Die Farben folgen
			Warcraft Logs, von Grau (unter 25) über Grün, Blau, Lila und Orange bis Rosa (99) und Gold (100).
		</p>
		<ul>
			<li>
				<strong>EU:</strong> gegen die Ranglisten von Abyss Logs (Region EU), je Spieler sein bester Kampf von
				mindestens 30 Sekunden. Der Hub holt sie einmal am Tag und nur für Bosse und Klassen aus unseren Runs der
				letzten 30 Tage. Die API von Abyss Logs ist inoffiziell, und deren Messung kann leicht von unserer abweichen.
			</li>
			<li>
				<strong>Gilde:</strong> gegen den Bestwert jedes Charakters derselben Klasse an diesem Boss aus allen Runs
				im Hub. Angezeigt erst ab 10 Charakteren.
			</li>
			<li>Hard und Normal sind bei Abyss Logs eigene Bosse und werden getrennt verglichen.</li>
		</ul>
	{:else}
		<h2 id="parses">Parses in the fight view</h2>
		<p>
			For killed bosses each player's DPS gets a number from 0 to 100: the share of comparison values of the same
			class at the same boss that your DPS reaches or beats. Colours follow Warcraft Logs, from grey (below 25)
			through green, blue, purple and orange to pink (99) and gold (100).
		</p>
		<ul>
			<li>
				<strong>EU:</strong> against the Abyss Logs rankings (region EU), each player's best fight of at least 30
				seconds. The hub fetches them once a day and only for bosses and classes from our runs of the last 30 days.
				The Abyss Logs API is unofficial, and their measurement can differ slightly from ours.
			</li>
			<li>
				<strong>Guild:</strong> against the best value of every character of the same class at this boss from all
				runs in the hub. Shown from 10 characters on.
			</li>
			<li>Hard and Normal are separate bosses on Abyss Logs and are compared separately.</li>
		</ul>
	{/if}
</article>

<style>
	.bounds {
		max-width: 320px;
		margin: 10px 0 18px;
	}
</style>
