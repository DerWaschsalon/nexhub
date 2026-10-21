<!-- System: Zustand des Hubs auf einen Blick. -->
<script lang="ts">
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const s = $derived(data.status);
</script>

<header class="page-head">
	<h1>System</h1>
	<p>Version, Datenbank und Login. Einstellungen stehen in <code>/srv/nexhub/.env</code> auf dem Server.</p>
</header>

<section class="tiles">
	<div class="glass pad tile">
		<span class="label">Version</span>
		<strong>{s.version}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Datenbank</span>
		<strong>Schema {s.db_revision}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Discord-Login</span>
		<strong><span class="chip" class:ok={s.login} class:danger={!s.login}>{s.login ? 'an' : 'aus'}</span></strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Mitglieder über Discord-Rolle</span>
		<strong>
			<span class="chip" class:ok={s.member_check} class:warn={!s.member_check}>
				{s.member_check ? 'eingerichtet' : 'nur Admins'}
			</span>
		</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Konten</span>
		<strong class="num">{s.accounts}</strong>
	</div>
	<div class="glass pad tile">
		<span class="label">Aktive Sitzungen</span>
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
