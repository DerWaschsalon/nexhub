<!-- Datenschutzerklärung. Beschreibt, was der Hub tatsächlich verarbeitet (Stand des Codes im Repo):
     Ändert sich, was gespeichert, protokolliert oder von fremden Servern geladen wird, hier nachziehen.
     Verantwortlicher und Hoster kommen vom Server (HUB_OPERATOR_*, HUB_HOSTER). -->
<script lang="ts">
	import OperatorAddress from '#lib/components/OperatorAddress.svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const hoster = $derived(data.info.hoster);
</script>

<svelte:head><title>{t('legal.privacy')} · NexHub</title></svelte:head>

<article class="glass pad legal-page">
	{#if i18n.lang === 'de'}
		<h1>Datenschutzerklärung</h1>
		<p class="dim">Stand: Oktober 2026</p>

		<h2>1. Verantwortlich</h2>
		<OperatorAddress operator={data.info.operator} />
		<p>
			NexHub ist ein privates, nicht kommerzielles Angebot für eine Spielgemeinschaft (AION 2). Es gibt
			keine Werbung, kein Tracking und keine Analysewerkzeuge.
		</p>

		<h2>2. Hosting und Aufruf der Seite</h2>
		<p>
			Der Hub läuft auf einem gemieteten Server{hoster ? ` (${hoster})` : ''}. Bei jedem Aufruf
			verarbeitet der Server technisch notwendig deine IP-Adresse, Zeitpunkt, aufgerufene Adresse,
			Anfragemethode und Statuscode und schreibt sie in ein Protokoll. Das dient dem Betrieb, der
			Fehlersuche und der Abwehr von Angriffen (Art. 6 Abs. 1 lit. f DSGVO). Die Protokolle werden
			automatisch rotiert und überschrieben (höchstens etwa 100 MB je Dienst). Den Anmeldecode von
			Discord entfernt der Hub vor dem Protokollieren.
		</p>

		<h2>3. Anmeldung mit Discord</h2>
		<p>
			Zum Anmelden leitet dich der Hub zu Discord (Discord Inc., USA) weiter; dort gelten die
			Datenschutzbestimmungen von Discord. Discord übermittelt dem Hub deine Discord-ID, deinen
			Benutzernamen, Anzeigenamen und dein Profilbild sowie, ob du auf dem Discord-Server der Gemeinschaft
			die nötige Rolle hast. Gespeichert werden ID, Namen, Profilbild-Kennung, Rolle (Admin/Mitglied),
			Zeitpunkt der ersten und letzten Anmeldung und gegebenenfalls eine Sperre. Den Zugriffsschlüssel von
			Discord gibt der Hub sofort nach der Anmeldung zurück und speichert ihn nicht. Rechtsgrundlage ist
			die Nutzung des Hubs auf deinen Wunsch (Art. 6 Abs. 1 lit. b DSGVO). Die Daten bleiben gespeichert,
			bis dein Konto gelöscht wird – sag dafür dem Betreiber Bescheid.
		</p>

		<h2>4. Cookies und Speicher im Browser</h2>
		<ul>
			<li><code>nexhub_session</code>: hält dich angemeldet, 30 Tage, nur nach dem Login.</li>
			<li><code>nexhub_oauth</code>: nur während der Anmeldung, höchstens 10 Minuten.</li>
			<li><code>nexhub.lang</code> (lokaler Speicher): deine Sprachwahl.</li>
		</ul>
		<p>
			Alle drei sind für die Funktion nötig (§ 25 Abs. 2 TDDDG). Andere Cookies setzt der Hub nicht.
		</p>

		<h2>5. Geräte und hochgeladene Runs</h2>
		<p>
			Wer ein NexBoard koppelt, für das speichert der Hub Gerätename, Zeitpunkt der Kopplung, letzten
			Kontakt und Programmversion. Ein gekoppeltes NexBoard lädt beendete Dungeon-Runs hoch. Sie enthalten
			Kampfdaten aus dem Spiel, auch die Charakternamen und Klassen aller Mitspieler der Gruppe, Schaden,
			Fähigkeiten, Buffs und Zeitpunkte, dazu, wer hochgeladen hat. Angemeldete Mitglieder sehen alle Runs.
			Zu jedem Run ruft der Hub die öffentlichen Charakterseiten der Mitspieler auf der offiziellen
			AION-2-Website von NCSOFT ab und speichert eine Momentaufnahme (Kampfkraft, Ausrüstung, Werte, Titel,
			Skills, Daevanion). Sie ist nur für angemeldete Mitglieder sichtbar, nicht über geteilte Links, und
			wird mit dem Run gelöscht.
			In der Armory können Mitglieder Charaktere eintragen. Dazu speichert der Hub, wer den Charakter
			eingetragen hat, eine Momentaufnahme wie oben samt den Werten der Gegenstände, die einmal täglich und auf Knopfdruck neu von der
			AION-2-Website geholt wird, und je Tag Kampfkraft und Gegenstandsstufe als Verlauf. Das sehen nur
			angemeldete Mitglieder. Es wird gelöscht, wenn der Charakter ausgetragen oder das Konto gelöscht wird.
			Ein geteilter Link zeigt einen Run allen, die den Link haben, ohne Anmeldung. Ebenso lässt sich ein
			Vergleich teilen: Dafür speichert der Hub, wer geteilt hat, welcher Armory-Charakter verglichen wird
			und Name und Server des anderen Charakters. Beim Öffnen zeigt der Link die Momentaufnahme des
			Armory-Charakters und holt den anderen Charakter neu von der AION-2-Website, ohne ihn zu speichern;
			wer eingetragen oder geteilt hat, zeigt er nicht. Der Link gilt, bis er zurückgezogen oder der
			Armory-Charakter ausgetragen wird. Suchmaschinen werden gebeten, solche Seiten nicht aufzunehmen. Zweck ist die gemeinsame Auswertung der Spielrunden in der
			Gemeinschaft (Art. 6 Abs. 1 lit. f DSGVO). Runs bleiben gespeichert, bis die Hochladenden oder ein
			Admin sie löschen; eine automatische Löschfrist gibt es derzeit nicht.
		</p>

		<h2>6. Inhalte von fremden Servern</h2>
		<p>
			Symbole von Fähigkeiten, Buffs und Gegenständen sowie Charakterbilder lädt dein Browser direkt von
			Servern des Spieleherstellers NCSOFT (<code>assets.playnccdn.com</code>,
			<code>profileimg.plaync.com</code>), Profilbilder direkt von Discord (<code>cdn.discordapp.com</code>).
			Dabei erfahren diese Anbieter deine IP-Adresse; der Hub schickt bei den Spielsymbolen keine
			Herkunftsadresse mit.
		</p>

		<h2>7. Discord-Bot</h2>
		<p>
			Unter derselben Adresse laufen die Auswertungsseiten des Discord-Bots der Gemeinschaft (TheWashBot,
			z. B. <code>/runs/…</code>). Sie zeigen Daten, die im Discord gepostet wurden.
		</p>

		<h2>8. Sicherungen</h2>
		<p>Die Datenbank wird jede Nacht gesichert; Sicherungen werden nach 14 Tagen gelöscht.</p>

		<h2>9. Deine Rechte</h2>
		<p>
			Du kannst Auskunft über deine Daten verlangen, ihre Berichtigung oder Löschung, die Einschränkung der
			Verarbeitung und die Herausgabe deiner Daten, und du kannst der Verarbeitung widersprechen (Art.
			15–21 DSGVO). Wende dich dafür an den Betreiber (oben). Außerdem kannst du dich bei einer
			Datenschutz-Aufsichtsbehörde beschweren.
		</p>
	{:else}
		<h1>Privacy policy</h1>
		<p class="dim">As of October 2026 · {t('legal.germanOnly')}</p>

		<h2>1. Controller</h2>
		<OperatorAddress operator={data.info.operator} />
		<p>
			NexHub is a private, non-commercial site for a gaming community (AION 2). There are no ads, no
			tracking and no analytics.
		</p>

		<h2>2. Hosting and visiting the site</h2>
		<p>
			The hub runs on a rented server{hoster ? ` (${hoster})` : ''}. For every request the server processes
			your IP address, time, requested address, method and status code and writes them to a log, for
			operation, debugging and defence against attacks (Art. 6(1)(f) GDPR). Logs are rotated and
			overwritten automatically (at most about 100 MB per service). The hub strips Discord's sign-in code
			before logging.
		</p>

		<h2>3. Signing in with Discord</h2>
		<p>
			To sign in, the hub redirects you to Discord (Discord Inc., USA); Discord's privacy policy applies
			there. Discord sends the hub your Discord ID, username, display name and avatar, and whether you have
			the required role on the community's Discord server. The hub stores ID, names, avatar reference, role
			(admin/member), time of first and last sign-in and, if applicable, a block. Discord's access token is
			revoked right after sign-in and not stored. Legal basis: using the hub at your request (Art. 6(1)(b)
			GDPR). The data is kept until your account is deleted – ask the operator.
		</p>

		<h2>4. Cookies and browser storage</h2>
		<ul>
			<li><code>nexhub_session</code>: keeps you signed in, 30 days, only after sign-in.</li>
			<li><code>nexhub_oauth</code>: only during sign-in, at most 10 minutes.</li>
			<li><code>nexhub.lang</code> (local storage): your language choice.</li>
		</ul>
		<p>All three are strictly necessary. The hub sets no other cookies.</p>

		<h2>5. Devices and uploaded runs</h2>
		<p>
			For a paired NexBoard the hub stores device name, pairing time, last contact and program version. A
			paired NexBoard uploads finished dungeon runs. They contain combat data from the game, including the
			character names and classes of everyone in the group, damage, skills, buffs and timestamps, plus who
			uploaded them. Signed-in members see all runs. For every run the hub fetches the public character pages
			of the players in it from NCSOFT's official AION 2 website and stores a snapshot (combat power,
			equipment, stats, titles, skills, Daevanion); only signed-in members see it, not shared links, and it is
			deleted with the run. Members can add characters to the armory. For those the hub stores who added the
			character, a snapshot as above including the item values, fetched again from the AION 2 website once a day and on request, and
			combat power and item level per day as a history. Only signed-in members see it; it is deleted when the
			character is removed or the account is deleted. A shared link shows a run to anyone who has the link,
			without signing in. A comparison can be shared the same way: for that the hub stores who shared it,
			which armory character is compared and the name and server of the other character. When opened, the
			link shows the armory character's snapshot and fetches the other character again from the AION 2
			website without storing it; it does not show who added or shared anything. The link stays valid until
			it is withdrawn or the armory character is removed. Search engines are asked not to index such pages. Purpose: analysing the
			community's runs together (Art. 6(1)(f) GDPR). Runs are kept until the uploader or an admin deletes
			them; there is currently no automatic deletion.
		</p>

		<h2>6. Content from other servers</h2>
		<p>
			Your browser loads skill, buff and item icons and character portraits directly from servers of the game
			publisher NCSOFT (<code>assets.playnccdn.com</code>, <code>profileimg.plaync.com</code>) and avatars
			directly from Discord (<code>cdn.discordapp.com</code>).
			These providers see your IP address; for the game icons the hub sends no referrer.
		</p>

		<h2>7. Discord bot</h2>
		<p>
			The analysis pages of the community's Discord bot (TheWashBot, e.g. <code>/runs/…</code>) run under
			the same address. They show data that was posted on Discord.
		</p>

		<h2>8. Backups</h2>
		<p>The database is backed up every night; backups are deleted after 14 days.</p>

		<h2>9. Your rights</h2>
		<p>
			You can request access to, correction or deletion of your data, restriction of processing and a copy
			of your data, and you can object to processing (Art. 15–21 GDPR). Contact the operator (above). You
			can also complain to a data protection authority.
		</p>
	{/if}
</article>

<style>
	.legal-page {
		max-width: 760px;
		margin: 0 auto;
	}
	h1 {
		font-size: 28px;
	}
	h2 {
		font-size: 17px;
		margin: 26px 0 8px;
	}
	p,
	li {
		color: var(--dim);
	}
	p {
		margin: 0 0 10px;
	}
	ul {
		margin: 0 0 10px;
		padding-left: 20px;
	}
	code {
		font-size: 13px;
	}
</style>
