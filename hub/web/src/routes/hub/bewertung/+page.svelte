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
	     (CP_RANGE = 5000, EU_MIN = 10, GUILD_MIN = 10, Abruf täglich), diesen Abschnitt mit ändern. -->
	{#if i18n.lang === 'de'}
		<h2 id="parses">Parses in der Kampfansicht</h2>
		<p>
			Bei getöteten Bossen steht hinter dem DPS jedes Spielers eine Zahl von 0 bis 100: wie viel Prozent der
			Vergleichswerte derselben Klasse am selben Boss dein DPS erreicht oder übertrifft. Die Farben folgen
			Warcraft Logs, von Grau (unter 25) über Grün, Blau, Lila und Orange bis Rosa (99) und Gold (100).
		</p>
		<h3>EU: gegen Spieler mit ähnlicher Kampfkraft</h3>
		<p>
			Die Kampfkraft (CP) zeigt den Ausrüstungsstand. Wer 40.000 CP mehr hat, macht fast immer mehr Schaden, auch
			bei gleich gutem Spiel. Deshalb vergleicht EU dich nur mit Spielern deiner Klasse, deren CP höchstens
			<strong>5.000 über oder unter deiner</strong> liegt. So misst der Wert, wie gut du aus deiner Ausrüstung
			spielst, nicht wie gut die Ausrüstung ist.
		</p>
		<ol>
			<li>
				Der Hub holt einmal am Tag die Ranglisten von Abyss Logs (Region EU), nur für Bosse und Klassen aus unseren
				Runs der letzten 30 Tage. Je Spieler zählt sein bester Kampf von mindestens 30 Sekunden, mit der CP aus
				diesem Kampf.
			</li>
			<li>Deine CP stammt aus deiner Momentaufnahme von der AION-2-Website zu diesem Run.</li>
			<li>Aus der Rangliste bleiben die Spieler mit CP im Bereich deiner CP ± 5.000.</li>
			<li>Der Parse ist der Anteil davon, deren DPS kleiner oder gleich deinem ist, abgerundet.</li>
		</ol>
		<p>
			<strong>Beispiel:</strong> Du spielst Kantor mit 250.000 CP und machst 120.000 DPS. Verglichen wird mit
			allen Kantoren von 245.000 bis 255.000 CP. Das sind 80 Spieler, 60 davon haben 120.000 DPS oder weniger.
			Dein Parse ist 60 / 80 = 75, also Lila.
		</p>
		<ul>
			<li>Liegen weniger als 10 Spieler im CP-Bereich, gibt es keinen EU-Wert. Er sagt dann zu wenig aus.</li>
			<li>
				Ist deine CP noch nicht bekannt (Momentaufnahme fehlt), vergleicht EU ausnahmsweise mit allen Spielern
				deiner Klasse. Der Tooltip sagt dann nichts von einem CP-Bereich.
			</li>
			<li>Hard und Normal sind bei Abyss Logs eigene Bosse und werden getrennt verglichen.</li>
			<li>Die API von Abyss Logs ist inoffiziell, und deren Messung kann leicht von unserer abweichen.</li>
		</ul>
		<h3>Klasse: die Klassenstatistik von Abyss Logs</h3>
		<p>
			Abyss Logs wertet jede Woche alle hochgeladenen Kämpfe eines Bosses aus, getrennt nach Klasse und Kampfkraft in
			Stufen von 25.000 CP: Tiefstwert, untere 25 %, Median, Top 25 %, Top 10 % und Höchstwert. Der Wert „Klasse“
			sagt, wo dein DPS in dieser Verteilung liegt, zwischen den Stufen gerade verbunden. 50 heißt Median, 75 heißt
			so gut wie die Top 25 %. Liegen in deiner CP-Stufe weniger als 20 Kämpfe, gilt die Verteilung über alle CP.
			Der Tooltip nennt Median, Top 25 % und Top 10 % in DPS. Anders als EU zählt hier jeder Kampf der letzten
			Woche, nicht nur der Bestwert je Spieler; der Hub holt die Werte einmal am Tag.
		</p>
		<h3>Gilde: gegen eure eigenen Charaktere</h3>
		<p>
			Gilde vergleicht mit dem Bestwert jedes Gildencharakters derselben Klasse an diesem Boss, aus allen Runs im
			Hub. Zur Gilde gehört, wer in seiner jüngsten Momentaufnahme in einer der Legionen ist, die ein Admin unter
			Verwaltung &gt; Gilde eingetragen hat. Mitspieler von außerhalb zählen nicht und bekommen keinen Gildenwert.
			Angezeigt wird er erst ab 10 Charakteren, die Kampfkraft spielt hier keine Rolle.
		</p>
	{:else}
		<h2 id="parses">Parses in the fight view</h2>
		<p>
			For killed bosses each player's DPS gets a number from 0 to 100: the share of comparison values of the same
			class at the same boss that your DPS reaches or beats. Colours follow Warcraft Logs, from grey (below 25)
			through green, blue, purple and orange to pink (99) and gold (100).
		</p>
		<h3>EU: against players with similar combat power</h3>
		<p>
			Combat power (CP) shows how geared you are. Someone with 40,000 more CP almost always deals more damage, even
			when playing equally well. So EU only compares you with players of your class whose CP is at most
			<strong>5,000 above or below yours</strong>. The value measures how well you play with your gear, not how good
			the gear is.
		</p>
		<ol>
			<li>
				Once a day the hub fetches the Abyss Logs rankings (region EU), only for bosses and classes from our runs of
				the last 30 days. Each player counts with their best fight of at least 30 seconds and the CP from that fight.
			</li>
			<li>Your CP comes from your snapshot from the AION 2 website for this run.</li>
			<li>From the ranking, the players with CP within your CP ± 5,000 remain.</li>
			<li>The parse is the share of them whose DPS is lower than or equal to yours, rounded down.</li>
		</ol>
		<p>
			<strong>Example:</strong> you play Chanter with 250,000 CP and deal 120,000 DPS. You are compared with all
			Chanters from 245,000 to 255,000 CP. That is 80 players, 60 of them have 120,000 DPS or less. Your parse is
			60 / 80 = 75, purple.
		</p>
		<ul>
			<li>With fewer than 10 players in the CP range there is no EU value, it would say too little.</li>
			<li>
				If your CP is not known yet (snapshot missing), EU compares with all players of your class as an exception.
				The tooltip then shows no CP range.
			</li>
			<li>Hard and Normal are separate bosses on Abyss Logs and are compared separately.</li>
			<li>The Abyss Logs API is unofficial, and their measurement can differ slightly from ours.</li>
		</ul>
		<h3>Class: the class statistics of Abyss Logs</h3>
		<p>
			Every week Abyss Logs evaluates all uploaded fights of a boss, split by class and combat power in steps of
			25,000 CP: lowest, bottom 25%, median, top 25%, top 10% and highest. The “Class” value says where your DPS
			lies in that distribution, straight lines between the steps. 50 means median, 75 means as good as the top
			25%. With fewer than 20 fights in your CP step, the distribution over all CP counts. The tooltip names median,
			top 25% and top 10% in DPS. Unlike EU, every fight of the last week counts, not just each player's best; the
			hub fetches the values once a day.
		</p>
		<h3>Guild: against your own characters</h3>
		<p>
			Guild compares with the best value of every guild character of the same class at this boss, from all runs in
			the hub. A character belongs to the guild if their latest snapshot shows one of the legions an admin entered
			under Administration &gt; Guild. Players from outside do not count and get no guild value. It is shown from 10
			characters on; combat power plays no part here.
		</p>
	{/if}
</article>

<style>
	.bounds {
		max-width: 320px;
		margin: 10px 0 18px;
	}
</style>
