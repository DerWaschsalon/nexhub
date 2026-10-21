<!-- Kleines Formular einer Aktion (z. B. „Neues Giveaway“, „Timeout“). Felder mit `show_if` erscheinen
     nur, wenn ein anderes Feld passt (z. B. Repository nur bei GitHub). Prüfen und Ausführen macht der Bot. -->
<script lang="ts">
	import type { BotAction, BotField, BotGuild, BotValue } from '#modules/bot/api.ts';
	import BotFieldInput from './BotFieldInput.svelte';

	let {
		action,
		guild,
		busy = false,
		run,
		cancel
	}: {
		action: BotAction;
		guild: BotGuild;
		busy?: boolean;
		run: (values: Record<string, BotValue>) => void;
		/** Ohne cancel steht das Formular fest auf der Seite (kein Abbrechen) */
		cancel?: () => void;
	} = $props();

	// svelte-ignore state_referenced_locally
	let values = $state<Record<string, BotValue>>(
		Object.fromEntries(action.fields.map((f) => [f.key, $state.snapshot(f.value)]))
	);

	const shown = (f: BotField) => !f.show_if || f.show_if.values.includes(String(values[f.show_if.key] ?? ''));

	function submit(e: SubmitEvent) {
		e.preventDefault();
		run(Object.fromEntries(action.fields.filter(shown).map((f) => [f.key, values[f.key] === '' ? null : values[f.key]])));
	}
</script>

<form class="form" onsubmit={submit}>
	<div class="grid">
		{#each action.fields as f (f.key)}
			{#if shown(f)}
				<BotFieldInput field={f} bind:value={values[f.key]} {guild} id={`a-${action.id}-${f.key}`} />
			{/if}
		{/each}
	</div>
	<div class="bar">
		<button class="btn" class:primary={!action.danger} class:danger={action.danger} disabled={busy}>{action.submit}</button>
		{#if cancel}<button type="button" class="btn" onclick={cancel}>Abbrechen</button>{/if}
	</div>
</form>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 18px;
		border-radius: var(--radius-sm);
		border: 1px solid var(--edge-soft);
		background: rgba(255, 255, 255, 0.035);
		animation: open 0.18s ease-out;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px 20px;
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	@keyframes open {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.form {
			animation: none;
		}
	}
	@media (max-width: 700px) {
		.grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
