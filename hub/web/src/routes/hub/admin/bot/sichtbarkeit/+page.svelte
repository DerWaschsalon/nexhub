<!-- Sichtbarkeit: welche Rolle welchen Kanal sieht. Ein Klick auf eine Zelle stellt das Recht
     „Kanal ansehen“ für diese Rolle sofort auf dem Discord-Server um. -->
<script lang="ts">
	import { BOT_API, send, type VisibilityMatrix } from '#lib/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// svelte-ignore state_referenced_locally
	let matrix = $state<VisibilityMatrix>(data.matrix);
	let busy = $state('');
	let error = $state('');
	let ok = $state('');

	async function toggle(row: VisibilityMatrix['rows'][number], col: number) {
		const role = matrix.roles[col];
		const allow = !row.cells[col];
		busy = `${row.id}:${role.id}`;
		error = ok = '';
		try {
			matrix = await send<VisibilityMatrix>(`${BOT_API}/matrix`, 'PUT', {
				channel_id: row.id,
				role_id: role.id,
				allow
			});
			ok = `${role.name} ${allow ? 'sieht' : 'sieht nicht mehr'}: ${row.category ? row.name : '#' + row.name}`;
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = '';
		}
	}
</script>

<p class="dim lead">
	Ein Punkt heißt: Wer nur diese Rolle hat, sieht den Kanal. Ein Klick stellt es sofort auf dem
	Server um. Admin-Rechte und Rechte einzelner Personen zählen hier nicht.
</p>

<p class="status" aria-live="polite">
	{#if error}<span class="notice error">{error}</span>{:else if ok}<span class="notice ok">{ok}</span>{/if}
</p>

<section class="glass wrap">
	<table>
		<thead>
			<tr>
				<th class="corner">Kanal</th>
				{#each matrix.roles as r (r.id)}<th class="role"><span>{r.name}</span></th>{/each}
			</tr>
		</thead>
		<tbody>
			{#each matrix.rows as row, i (row.id ?? `ohne-${i}`)}
				<tr class:cat={row.category}>
					<th scope="row">{row.category ? row.name : `${row.kind === 'voice' ? '♪ ' : '# '}${row.name}`}</th>
					{#each row.cells as visible, col (matrix.roles[col].id)}
						{@const key = `${row.id}:${matrix.roles[col].id}`}
						<td>
							<button
								class="cell"
								class:on={visible}
								class:busy={busy === key}
								disabled={!!busy}
								aria-pressed={visible}
								aria-label={`${matrix.roles[col].name} sieht ${row.name}`}
								onclick={() => toggle(row, col)}
							></button>
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</section>

<style>
	.lead {
		margin: -6px 4px 12px;
		max-width: 70ch;
	}
	.status {
		min-height: 40px;
		margin: 0 0 8px;
	}
	.status .notice {
		display: inline-block;
		padding: 6px 12px;
	}
	.wrap {
		overflow-x: auto;
		padding: 16px 20px 18px 4px;
	}
	table {
		border-collapse: separate;
		border-spacing: 0;
		font-size: 14px;
	}
	th,
	td {
		padding: 0;
	}
	tbody th,
	.corner {
		text-align: left;
		font-weight: 450;
		white-space: nowrap;
		padding: 6px 18px 6px 20px;
		max-width: 260px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.corner {
		vertical-align: bottom;
		color: var(--faint);
		font-size: 13px;
	}
	/* Rollennamen senkrecht: viele Spalten passen nebeneinander, nichts wird abgeschnitten */
	.role {
		width: 40px;
		vertical-align: bottom;
		padding-bottom: 10px;
	}
	.role span {
		writing-mode: vertical-rl;
		transform: rotate(180deg);
		white-space: nowrap;
		font-size: 13px;
		font-weight: 550;
		color: var(--dim);
	}
	tr.cat th {
		font-weight: 650;
		color: var(--text);
		padding-top: 14px;
	}
	tbody tr:not(.cat) th {
		color: var(--dim);
	}
	tbody tr:hover th {
		color: var(--text);
	}
	td {
		text-align: center;
		width: 40px;
		height: 34px;
	}
	tr.cat td {
		padding-top: 8px;
	}
	.cell {
		width: 22px;
		height: 22px;
		padding: 0;
		border-radius: 50%;
		border: 1.5px solid var(--edge);
		background: transparent;
		cursor: pointer;
		transition:
			background 0.15s,
			box-shadow 0.15s,
			transform 0.1s;
	}
	.cell:hover:not(:disabled) {
		border-color: var(--accent);
		transform: scale(1.12);
	}
	.cell.on {
		width: 18px;
		height: 18px;
		border-color: transparent;
		background: radial-gradient(circle at 35% 30%, #c5efff, var(--accent) 60%);
		box-shadow: 0 0 12px -2px rgba(106, 211, 255, 0.7);
	}
	.cell:disabled {
		cursor: progress;
	}
	.cell.busy {
		animation: pulse 0.8s ease-in-out infinite alternate;
	}
	@keyframes pulse {
		to {
			opacity: 0.35;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.cell,
		.cell.busy {
			transition: none;
			animation: none;
		}
	}
</style>
