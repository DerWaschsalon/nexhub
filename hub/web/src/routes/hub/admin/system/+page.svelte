<!-- System: Zustand des Hubs auf einen Blick. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const s = $derived(data.status);
</script>

<header class="page-head">
	<h1>{t('system.title')}</h1>
	<p>{t('system.intro')} <code>/srv/nexhub/.env</code></p>
</header>

<section class="tiles">
	<div class="glass pad tile">
		<span class="label">{t('system.version')}</span>
		<strong>{s.version}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">{t('system.db')}</span>
		<strong>{t('system.schema', { rev: s.db_revision })}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">{t('system.login')}</span>
		<strong><span class="chip" class:ok={s.login} class:danger={!s.login}>{t(s.login ? 'system.on' : 'system.off')}</span></strong>
	</div>
	<div class="glass pad tile">
		<span class="label">{t('system.members')}</span>
		<strong>
			<span class="chip" class:ok={s.member_check} class:warn={!s.member_check}>
				{t(s.member_check ? 'system.membersOn' : 'system.membersOff')}
			</span>
		</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">{t('system.accounts')}</span>
		<strong class="num">{s.accounts}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">{t('system.sessions')}</span>
		<strong class="num">{s.active_sessions}</strong>
	</div>
</section>

<style>
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 14px;
	}
	.tile {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.label {
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--faint);
	}
	strong {
		font-size: 17px;
		overflow-wrap: anywhere;
	}
	.num {
		font-size: 30px;
		font-variant-numeric: tabular-nums;
	}
	code {
		font-size: 13px;
	}
</style>
