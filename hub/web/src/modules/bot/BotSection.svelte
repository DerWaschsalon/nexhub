<!-- Formular für einen Bereich des Bots. Felder, Beschriftungen und Hinweise kommen aus dem
     Schema des Bots (bot/bot/cogs/control.py, SECTIONS); wie ein Feldtyp aussieht, steht in BotFieldInput.
     Gespeichert wird der ganze Bereich auf einmal, der Bot prüft alle Werte vorher. -->
<script lang="ts">
	import { send } from '#lib/api.ts';
	import { BOT_API, type BotField, type BotGuild, type BotSection } from '#modules/bot/api.ts';
	import BotFieldInput from './BotFieldInput.svelte';

	let { section, guild }: { section: BotSection; guild: BotGuild } = $props();

	type Value = BotField['value'];

	// Startwerte; danach gilt, was der Bot beim Speichern zurückgibt (die Seite setzt {#key} je Bereich)
	// svelte-ignore state_referenced_locally
	let current = $state(section);
	// svelte-ignore state_referenced_locally
	let values = $state(snapshot(section));
	// svelte-ignore state_referenced_locally
	let saved = $state(snapshot(section));
	let busy = $state(false);
	let error = $state('');
	let ok = $state('');
	let revealed = $state<Record<string, boolean>>({});

	function snapshot(s: BotSection): Record<string, Value> {
		return Object.fromEntries(s.fields.map((f) => [f.key, $state.snapshot(f.value)]));
	}

	const kind = $derived(Object.fromEntries(current.fields.map((f) => [f.key, f.kind])));

	const dirty = $derived(JSON.stringify(values) !== JSON.stringify(saved));

	// Felder in der Reihenfolge des Schemas, nach Gruppe zusammengefasst
	const groups = $derived.by(() => {
		const out: { name: string; fields: BotField[] }[] = [];
		for (const f of current.fields) {
			const last = out.at(-1);
			if (last && last.name === f.group) last.fields.push(f);
			else out.push({ name: f.group, fields: [f] });
		}
		return out;
	});

	function apply(s: BotSection) {
		current = s;
		values = snapshot(s);
		saved = snapshot(s);
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = ok = '';
		try {
			// Nur geänderte Felder schicken; leere Auswahl heißt „keiner“
			const changed = Object.fromEntries(
				Object.entries(values)
					.filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(saved[k]))
					.map(([k, v]) => [k, v === '' ? null : v ?? (kind[k] === 'int' ? 0 : null)])
			);
			apply(await send<BotSection>(`${BOT_API}/sections/${current.id}`, 'PUT', { values: changed }));
			ok = 'Gespeichert.';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function action(id: string, label: string) {
		if (!confirm(`${label}?`)) return;
		error = ok = '';
		try {
			apply(await send<BotSection>(`${BOT_API}/sections/${current.id}/actions/${id}`, 'POST'));
			ok = 'Erledigt.';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	const copy = (text: string) => navigator.clipboard?.writeText(text);
</script>

<form class="section" onsubmit={save}>
	{#each groups as group (group.name)}
		<fieldset class="glass pad">
			{#if group.name}<legend>{group.name}</legend>{/if}
			<div class="grid">
				{#each group.fields as f (f.key)}
					<BotFieldInput field={f} bind:value={values[f.key]} {guild} id={`f-${current.id}-${f.key}`} />
				{/each}
			</div>
		</fieldset>
	{/each}

	{#if current.info.length || current.actions.length}
		<section class="glass pad">
			<dl>
				{#each current.info as i (i.label)}
					<dt>{i.label}</dt>
					<dd>
						{#if !i.value}
							<span class="dim">noch nicht eingerichtet</span>
						{:else}
							<code class:blur={i.secret && !revealed[i.label]}>{i.value}</code>
							{#if i.secret}
								<button type="button" class="btn small" onclick={() => (revealed[i.label] = !revealed[i.label])}>
									{revealed[i.label] ? 'Verbergen' : 'Anzeigen'}
								</button>
							{/if}
							<button type="button" class="btn small" onclick={() => copy(i.value!)}>Kopieren</button>
						{/if}
					</dd>
				{/each}
			</dl>
			{#each current.actions as a (a.id)}
				<button type="button" class="btn danger" onclick={() => action(a.id, a.label)}>{a.label}</button>
			{/each}
		</section>
	{/if}

	{#if current.note}<p class="dim note">{current.note}</p>{/if}

	<div class="bar">
		<button class="btn primary" disabled={busy || !dirty}>Speichern</button>
		{#if dirty}<span class="dim">Ungespeicherte Änderungen</span>{/if}
		{#if ok && !dirty}<span class="notice ok" role="status">{ok}</span>{/if}
	</div>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</form>

<style>
	.section {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	fieldset {
		margin: 0;
		min-width: 0;
	}
	legend {
		/* Legende im Glas statt auf dem Rand */
		float: left;
		width: 100%;
		margin-bottom: 16px;
		font-size: 17px;
		font-weight: 650;
	}
	.grid {
		clear: both;
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 18px 20px;
	}
	dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 10px 18px;
		margin: 0 0 16px;
		align-items: center;
	}
	dt {
		color: var(--dim);
		font-size: 14px;
	}
	dd {
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	code {
		font-size: 13px;
		overflow-wrap: anywhere;
		padding: 3px 8px;
		border-radius: 8px;
		background: rgba(0, 0, 0, 0.35);
	}
	code.blur {
		filter: blur(5px);
		user-select: none;
	}
	.note {
		margin: 0;
		padding: 0 4px;
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 14px;
	}
	.bar .notice {
		padding: 6px 12px;
	}
	@media (max-width: 700px) {
		.grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	@media (max-width: 600px) {
		dl {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
