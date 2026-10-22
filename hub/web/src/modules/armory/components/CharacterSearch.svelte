<!-- Suche auf der AION-2-Website nach Region, Klasse und Name. Was man mit einem Treffer macht
     (eintragen, vergleichen), gibt die Seite über `action` vor. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { CLASS_KEYS, classInfo } from '#modules/logs/classes.ts';
	import PlayerName from '#modules/logs/components/PlayerName.svelte';
	import { REGIONS, type ArmoryHit } from '../api.ts';

	let { action }: { action: Snippet<[ArmoryHit]> } = $props();

	let region = $state<string>('eu');
	let cls = $state('');
	let name = $state('');
	let hits = $state<ArmoryHit[] | null>(null);
	let busy = $state(false);
	let error = $state('');

	async function search(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		const query = new URLSearchParams({ name: name.trim(), region });
		if (cls) query.set('cls', cls);
		try {
			hits = await api<ArmoryHit[]>(`/api/armory/search?${query}`);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}
</script>

<form onsubmit={search}>
	<label class="field">
		{t('armory.region')}
		<select class="input" bind:value={region}>
			{#each REGIONS as r (r)}<option value={r}>{t(`region.${r}`)}</option>{/each}
		</select>
	</label>
	<label class="field">
		{t('armory.class')}
		<select class="input" bind:value={cls}>
			<option value="">{t('armory.allClasses')}</option>
			{#each CLASS_KEYS as k (k)}<option value={k}>{classInfo(k)?.label}</option>{/each}
		</select>
	</label>
	<label class="field grow">
		{t('armory.name')}
		<input class="input" bind:value={name} minlength="2" maxlength="64" required autocomplete="off" spellcheck="false" />
	</label>
	<button class="btn primary" disabled={busy || name.trim().length < 2}>{t('armory.search')}</button>
</form>

{#if hits}
	{#if hits.length}
		<ul class="hits">
			{#each hits as h (`${h.server_id}/${h.character_id}`)}
				<li>
					{#if h.image}<img src={h.image} alt="" width="36" height="36" referrerpolicy="no-referrer" />{/if}
					<span class="hit">
						<PlayerName name={h.name} cls={h.cls} size={18} />
						<span class="dim">{[h.server, h.level ? t('logs.char.level', { n: h.level }) : ''].filter(Boolean).join(' · ')}</span>
						{#if h.taken_by}<span class="dim small">{t('armory.takenBy', { name: h.taken_by })}</span>{/if}
					</span>
					{@render action(h)}
				</li>
			{/each}
		</ul>
	{:else}
		<p class="dim">{t('armory.noHits')}</p>
	{/if}
{/if}
{#if error}<p class="notice error" role="alert">{error}</p>{/if}

<style>
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: end;
	}
	.grow {
		flex: 1;
		min-width: 180px;
	}
	.hits {
		list-style: none;
		margin: 16px 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.hits li {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.hits img {
		border-radius: 8px;
		object-fit: cover;
	}
	.hit {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
	}
	.small {
		font-size: 12px;
	}
	.notice {
		margin-top: 12px;
	}
</style>
