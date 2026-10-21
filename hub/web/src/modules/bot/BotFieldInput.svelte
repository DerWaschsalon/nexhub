<!-- Ein Eingabefeld aus dem Schema des Bots (bot/bot/hubpages.py, Field). Wird von Formular-Bereichen
     (BotSection) und von Aktionen (BotForm) gleich gezeichnet; hier steht nur, wie ein Feldtyp aussieht. -->
<script lang="ts">
	import type { BotChannel, BotField, BotGuild, BotValue } from '#modules/bot/api.ts';

	let { field: f, value = $bindable(), guild, id }: { field: BotField; value: BotValue; guild: BotGuild; id: string } =
		$props();

	const categories = $derived(new Map(guild.channels.filter((c) => c.kind === 'category').map((c) => [c.id, c.name])));

	/** Kanäle einer Art, gruppiert nach Kategorie (Kanäle ohne Kategorie zuerst). */
	function channelGroups(kind: 'text' | 'voice'): { name: string | null; channels: BotChannel[] }[] {
		const out = new Map<string | null, BotChannel[]>();
		for (const c of guild.channels.filter((c) => c.kind === kind)) {
			const key = c.category && categories.has(c.category) ? c.category : null;
			out.set(key, [...(out.get(key) ?? []), c]);
		}
		return [...out].map(([cid, channels]) => ({ name: cid ? categories.get(cid)! : null, channels }));
	}

	const many = $derived(f.kind === 'channels' || f.kind === 'roles' || f.kind === 'multi');
	const picks = $derived(
		f.kind === 'roles'
			? guild.roles.map((r) => ({ value: r.id, label: r.name }))
			: f.kind === 'channels'
				? guild.channels.filter((c) => c.kind === 'text').map((c) => ({ value: c.id, label: `#${c.name}` }))
				: f.options
	);

	function toggle(v: string) {
		const list = (value as string[] | null) ?? [];
		value = list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
	}
</script>

{#if f.kind === 'bool'}
	<label class="check wide">
		<input type="checkbox" bind:checked={value as boolean} />
		<span>{f.label}</span>
	</label>
{:else if many}
	<div class="field wide" role="group" aria-labelledby={id}>
		<span {id}>{f.label}{f.required ? ' *' : ''}</span>
		<div class="picks">
			{#each picks as item (item.value)}
				{@const on = ((value as string[] | null) ?? []).includes(item.value)}
				<label class="pick" class:on>
					<input type="checkbox" checked={on} onchange={() => toggle(item.value)} />
					{item.label}
				</label>
			{:else}
				<span class="hint">Nichts zur Auswahl auf dem Server.</span>
			{/each}
		</div>
		{#if f.hint}<span class="hint">{f.hint}</span>{/if}
	</div>
{:else}
	<label class="field" class:wide={f.kind === 'textarea'} for={id}>
		<span>{f.label}{f.required ? ' *' : ''}</span>
		{#if f.kind === 'channel' || f.kind === 'voice'}
			<select {id} class="input" bind:value>
				<option value={null}>{f.required ? 'Kanal wählen' : 'Keiner'}</option>
				{#each channelGroups(f.kind === 'voice' ? 'voice' : 'text') as g (g.name)}
					{#if g.name}
						<optgroup label={g.name}>
							{#each g.channels as c (c.id)}
								<option value={c.id}>{f.kind === 'channel' ? '#' : ''}{c.name}</option>
							{/each}
						</optgroup>
					{:else}
						{#each g.channels as c (c.id)}
							<option value={c.id}>{f.kind === 'channel' ? '#' : ''}{c.name}</option>
						{/each}
					{/if}
				{/each}
			</select>
		{:else if f.kind === 'role'}
			<select {id} class="input" bind:value>
				<option value={null}>Keine</option>
				{#each guild.roles as r (r.id)}
					<option value={r.id}>{r.name}</option>
				{/each}
			</select>
		{:else if f.kind === 'member'}
			<input {id} class="input" list="{id}-people" placeholder="Name eintippen" value={guild.people.find((p) => p.id === value)?.name ?? ''}
				oninput={(e) => {
					const text = e.currentTarget.value.trim().toLowerCase();
					value = guild.people.find((p) => p.name.toLowerCase() === text || p.tag.toLowerCase() === text)?.id ?? null;
				}} />
			<datalist id="{id}-people">
				{#each guild.people as p (p.id)}
					<option value={p.name}>{p.tag}</option>
				{/each}
			</datalist>
		{:else if f.kind === 'choice'}
			<select {id} class="input" bind:value>
				{#each f.options as o (o.value)}
					<option value={o.value}>{o.label}</option>
				{/each}
			</select>
		{:else if f.kind === 'int'}
			<input {id} class="input" type="number" min={f.min ?? undefined} max={f.max ?? undefined} step="1" bind:value />
		{:else if f.kind === 'textarea'}
			<textarea {id} class="input" bind:value={value as string}></textarea>
		{:else}
			<input {id} class="input" bind:value={value as string} />
		{/if}
		{#if f.hint}<span class="hint">{f.hint}</span>{/if}
	</label>
{/if}

<style>
	.wide {
		grid-column: 1 / -1;
	}
	.picks {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.pick {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 12px;
		border-radius: 999px;
		border: 1px solid var(--edge-soft);
		background: rgba(255, 255, 255, 0.05);
		color: var(--dim);
		font-size: 14px;
		cursor: pointer;
	}
	.pick.on {
		color: var(--text);
		border-color: rgba(106, 211, 255, 0.45);
		background: rgba(106, 211, 255, 0.12);
	}
	.pick input {
		margin: 0;
		accent-color: var(--accent);
	}
	.pick:has(input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
