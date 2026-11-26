<!-- Modul Parses: welche Legionen im Gildenvergleich zählen. Oben die Liste zum Bearbeiten, darunter
     Legionen aus den Momentaufnahmen der Runs als Vorschläge (ein Klick fügt hinzu). -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { send } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { LEGIONS_PATH, type LegionsOut } from '#modules/parses/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const current = $derived(data.legions.legions);
	const counted = $derived(new Set(current.map((n) => n.toLocaleLowerCase())));

	let name = $state('');
	let error = $state('');

	async function save(legions: string[]) {
		error = '';
		try {
			await send<LegionsOut>(LEGIONS_PATH, 'PUT', { legions });
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function add(e: SubmitEvent) {
		e.preventDefault();
		await save([...current, name]);
		if (!error) name = '';
	}
</script>

<svelte:head><title>{t('parses.legions.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('parses.legions.title')}</h1>
	<p class="dim">{t('parses.legions.intro')}</p>
</header>

<section class="glass pad box">
	<h2>{t('parses.legions.current')}</h2>
	{#if current.length}
		<ul class="chips">
			{#each current as legion (legion)}
				<li class="chip ok">
					{legion}
					<button class="x" aria-label={t('parses.legions.remove', { name: legion })}
						title={t('parses.legions.remove', { name: legion })}
						onclick={() => save(current.filter((n) => n !== legion))}>×</button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="dim">{t('parses.legions.none')}</p>
	{/if}
	<form class="add" onsubmit={add}>
		<input class="input" bind:value={name} maxlength="64" required aria-label={t('parses.legions.field')}
			placeholder={t('parses.legions.field')} />
		<button class="btn primary">{t('parses.legions.add')}</button>
	</form>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</section>

<section class="glass pad box">
	<h2>{t('parses.legions.known')}</h2>
	<p class="dim small">{t('parses.legions.knownIntro')}</p>
	<ul class="known">
		{#each data.legions.known as k (k.name)}
			<li>
				<span>{k.name}</span>
				<span class="dim small num">{t('parses.legions.characters', { n: k.characters })}</span>
				{#if !counted.has(k.name.toLocaleLowerCase())}
					<button class="btn small" onclick={() => save([...current, k.name])}>{t('parses.legions.add')}</button>
				{/if}
			</li>
		{/each}
	</ul>
</section>

<style>
	.box {
		display: grid;
		gap: 12px;
		max-width: 720px;
		margin-bottom: 18px;
	}
	h2 {
		font-size: 17px;
		margin: 0;
	}
	p {
		margin: 0;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.x {
		border: none;
		background: none;
		color: inherit;
		font: inherit;
		cursor: pointer;
		padding: 0 2px;
	}
	.add {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.add .input {
		flex: 1;
		min-width: 180px;
	}
	.known {
		display: grid;
		gap: 6px;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.known li {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.known li span:first-child {
		flex: 1;
	}
</style>
