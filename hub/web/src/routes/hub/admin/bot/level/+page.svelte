<!-- Levelsystem: Einstellungen aus dem Schema, dazu Rollen als Belohnung ab einem Level. -->
<script lang="ts">
	import { BOT_API, send, type LevelReward } from '#lib/api.ts';
	import BotSection from '#lib/components/BotSection.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// svelte-ignore state_referenced_locally
	let rewards = $state<LevelReward[]>(data.rewards);
	let level = $state<number | null>(null);
	let role = $state('');
	let error = $state('');

	const assignable = $derived(data.guild!.roles.filter((r) => r.assignable));

	async function add(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		try {
			rewards = await send<LevelReward[]>(`${BOT_API}/level-rewards/${level}`, 'PUT', { role_id: role });
			level = null;
			role = '';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function remove(r: LevelReward) {
		if (!confirm(`Belohnung für Level ${r.level} entfernen?`)) return;
		error = '';
		try {
			await send<void>(`${BOT_API}/level-rewards/${r.level}`, 'DELETE');
			rewards = rewards.filter((x) => x.level !== r.level);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<p class="dim lead">{data.section.description}</p>
<BotSection section={data.section} guild={data.guild!} />

<section class="glass pad rewards">
	<h2>Rollen als Belohnung</h2>
	<p class="dim">Wer ein Level erreicht, bekommt die Rolle dazu und behält die der Stufen darunter.</p>
	{#if rewards.length}
		<div class="table-wrap">
			<table class="table">
				<thead><tr><th>Ab Level</th><th>Rolle</th><th></th></tr></thead>
				<tbody>
					{#each rewards as r (r.level)}
						<tr>
							<td class="num">{r.level}</td>
							<td>{r.role ?? 'Rolle gelöscht'}</td>
							<td class="actions"><button class="btn small danger" onclick={() => remove(r)}>Entfernen</button></td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	<form onsubmit={add}>
		<label class="field">
			<span>Ab Level</span>
			<input class="input" type="number" min="1" max="1000" bind:value={level} required />
		</label>
		<label class="field">
			<span>Rolle</span>
			<select class="input" bind:value={role} required>
				<option value="" disabled>Rolle wählen</option>
				{#each assignable as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
			</select>
		</label>
		<button class="btn primary" disabled={!level || !role}>Belohnung hinzufügen</button>
	</form>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</section>

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	.rewards {
		margin-top: 16px;
	}
	h2 {
		font-size: 17px;
	}
	.rewards > p {
		margin: 4px 0 14px;
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: flex-end;
		margin-top: 16px;
	}
	form .field {
		flex: 1 1 180px;
	}
	.num {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
	}
	.actions {
		text-align: right;
	}
	.notice {
		margin: 14px 0 0;
	}
</style>
