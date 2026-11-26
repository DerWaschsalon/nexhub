<!-- Run gesamt, aufgebaut wie ein Bericht bei Warcraft Logs: Gruppe, Schaden nach Spieler (mit EU-Parse als
     Schnitt der Bosse), Schaden nach Fähigkeit und Tode über alle Bosskämpfe. Namen führen zum Charakterprofil. -->
<script lang="ts">
	import { formatCompact, formatDuration, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Player } from '#modules/logs/api.ts';
	import PlayerName from '#modules/logs/components/PlayerName.svelte';
	import RankBars from '#modules/logs/components/RankBars.svelte';
	import SkillIcon from '#modules/logs/components/SkillIcon.svelte';
	import { skillName } from '#modules/logs/names.svelte.ts';
	import type { Parse } from '#modules/parses/api.ts';
	import ParseBadge from '#modules/parses/components/ParseBadge.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const run = $derived(data.run);
	const byName = $derived(new Map(data.characters.map((c) => [c.name, c])));
	const href = (p: Player) => {
		const c = byName.get(p.name);
		return c ? `/hub/runs/${run.id}/spieler/${c.id}` : undefined;
	};
	const note = (p: Player) => {
		const cp = byName.get(p.name)?.combat_power;
		return cp ? `${t('logs.char.combatPower')} ${formatCompact(cp)}` : undefined;
	};

	// Rollen nach Klasse: Templer halten, Kleriker heilen, alle anderen machen Schaden
	const ROLES = [
		{ key: 'tanks', classes: ['templar'] },
		{ key: 'healers', classes: ['cleric'] },
		{ key: 'dps', classes: null }
	] as const;
	const players = $derived(run.summary.players);
	const roles = $derived(ROLES.map((r) => ({
		key: r.key,
		players: players.filter((p) => (r.classes ? (r.classes as readonly string[]).includes(p.cls ?? '') :
			!ROLES.some((o) => o.classes?.includes((p.cls ?? '') as never))))
	})).filter((r) => r.players.length));
	const knownCp = $derived(players.map((p) => byName.get(p.name)?.combat_power).filter((x): x is number => !!x));
	const avgCp = $derived(knownCp.length ? knownCp.reduce((s, x) => s + x, 0) / knownCp.length : null);

	/** Parse über den ganzen Run: Schnitt der Bosse, an denen es einen Wert gibt */
	const runParse = $derived.by(() => {
		const out = new Map<string, Parse>();
		if (!data.parses) return out;
		const all = new Map<string, Parse[]>();
		for (const fight of Object.values(data.parses.fights))
			for (const [name, p] of Object.entries(fight)) all.set(name, [...(all.get(name) ?? []), p]);
		const avg = (xs: number[]) => (xs.length ? Math.round(xs.reduce((s, x) => s + x, 0) / xs.length) : null);
		for (const [name, ps] of all) {
			const eu = ps.filter((p) => p.eu != null);
			const guild = ps.filter((p) => p.guild != null);
			const latest = ps.map((p) => p.eu_at).filter((x): x is string => !!x).sort().at(-1) ?? null;
			out.set(name, {
				eu: avg(eu.map((p) => p.eu!)),
				eu_n: eu.length ? Math.max(...eu.map((p) => p.eu_n ?? 0)) : (ps[0].eu_n ?? null),
				eu_at: latest,
				eu_cp: ps.find((p) => p.eu_cp != null)?.eu_cp ?? null,
				eu_few: !eu.length && ps.some((p) => p.eu_few),
				guild: avg(guild.map((p) => p.guild!)),
				guild_n: Math.max(...ps.map((p) => p.guild_n)),
				member: ps.some((p) => p.member),
				bench: null
			});
		}
		return out;
	});
	const ov = $derived(data.overview);
</script>

<section class="glass panel">
	<h2>
		{t('logs.sum.group')} <span class="accent">({t('logs.sum.players', { n: players.length })})</span>
		{#if avgCp}
			· {t('logs.sum.avgCp', { cp: formatNumber(avgCp) })}
			<small>{t('logs.sum.avgCpKnown', { k: knownCp.length, n: players.length })}</small>
		{/if}
	</h2>
	<div class="roles">
		{#each roles as r (r.key)}
			<span class="role">{t(`logs.sum.${r.key}`)} ({r.players.length})</span>
			<span class="who">
				{#each r.players as p (p.name)}
					{@const c = byName.get(p.name)}
					<a class="person" href={href(p)}>
						<PlayerName name={p.name} cls={p.cls} size={26} />
						{#if c?.combat_power}<small class="num">{formatNumber(c.combat_power)} CP</small>{/if}
					</a>
				{/each}
			</span>
		{/each}
	</div>
</section>

<div class="grid">
	<section class="glass panel">
		<h2>{t('logs.sum.damage')}</h2>
		{#if data.parses}
			<RankBars players={run.summary.players} {href} {note}>
				{#snippet badge(p)}
					<ParseBadge parse={runParse.get(p.name)} cls={p.cls} guildMin={data.parses!.guild_min} classStats={false} />
				{/snippet}
			</RankBars>
			<p class="hint">{t('logs.sum.parseNote')} <a href="/hub/bewertung#parses">{t('parses.how')}</a></p>
		{:else}
			<RankBars players={run.summary.players} {href} {note} />
		{/if}
	</section>

	{#if ov}
		<section class="glass panel">
			<h2>{t('logs.sum.skills')}</h2>
			<div class="table-wrap">
				<table class="table">
					<thead>
						<tr>
							<th>{t('logs.sum.col.skill')}</th>
							<th>{t('logs.sum.col.player')}</th>
							<th class="right">{t('logs.sum.col.amount')}</th>
							<th class="right">{t('logs.sum.col.hits')}</th>
						</tr>
					</thead>
					<tbody>
						{#each ov.skills as s (`${s.player}|${s.name}`)}
							<tr>
								<td><span class="skill"><SkillIcon code={s.code} size={24} /> {skillName(s.code, s.name)}</span></td>
								<td><PlayerName name={s.player} cls={s.cls} size={20} /></td>
								<td class="right num">{formatCompact(s.damage)}</td>
								<td class="right num rate">{formatNumber(s.hits)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section class="glass panel">
			<h2>{t('logs.sum.deaths')} <span class="accent">({ov.deaths.length})</span></h2>
			{#if ov.deaths.length}
				<div class="table-wrap">
					<table class="table">
						<thead>
							<tr>
								<th>{t('logs.sum.col.name')}</th>
								<th>{t('logs.sum.col.blow')}</th>
								<th>{t('logs.sum.col.boss')}</th>
								<th class="right">{t('logs.sum.col.time')}</th>
								<th class="right">{t('logs.sum.col.revived')}</th>
							</tr>
						</thead>
						<tbody>
							{#each ov.deaths as d, i (i)}
								<tr>
									<td><PlayerName name={d.name} cls={d.cls} size={20} /></td>
									<td class="blow">{d.skill != null ? skillName(d.skill) : t('logs.sum.unknownBlow')}</td>
									<td><a href="/hub/runs/{run.id}/kampf/{encodeURIComponent(d.fight)}">{d.boss}</a></td>
									<td class="right num">{formatDuration(d.t_ms)}</td>
									<td class="right num dim">{d.revived_ms != null ? `+${formatDuration(d.revived_ms - d.t_ms)}` : '–'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else}
				<p class="dim">{t('logs.sum.noDeaths')}</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.panel {
		padding: 18px 20px;
		border-radius: 14px;
	}
	h2 {
		font-size: 17px;
		margin: 0 0 14px;
		font-weight: 600;
	}
	h2 small {
		font-size: 12px;
		font-weight: 400;
		color: var(--faint);
	}
	.accent {
		color: var(--accent);
	}
	.roles {
		display: grid;
		grid-template-columns: 120px minmax(0, 1fr);
		gap: 10px 16px;
		align-items: center;
	}
	.role {
		font-size: 14px;
		color: var(--dim);
	}
	.who {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 22px;
	}
	.person {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		text-decoration: none;
	}
	.person small {
		font-size: 11px;
		color: var(--faint);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
		gap: 16px;
	}
	.grid > :first-child {
		grid-column: 1 / -1;
	}
	.skill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
	.rate {
		color: var(--game-green, #8fd16a);
	}
	.blow {
		color: var(--warn);
	}
	.hint {
		margin: 12px 0 0;
		font-size: 12px;
		color: var(--faint);
	}
	@media (max-width: 600px) {
		.roles {
			grid-template-columns: 1fr;
		}
	}
</style>
