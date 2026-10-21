<!-- Eine Seite des Bots aus Blöcken (bot/bot/hubpages.py): Formular, Tabelle, Status, Aktionen.
     Nach jeder Aktion schickt der Bot die ganze Seite neu, damit Tabellen und Status stimmen. -->
<script lang="ts">
	import { send } from '#lib/api.ts';
	import {
		BOT_API,
		type BotAction,
		type BotActionResult,
		type BotBlock,
		type BotGuild,
		type BotPage,
		type BotRow,
		type BotValue
	} from '#modules/bot/api.ts';
	import BotForm from './BotForm.svelte';
	import BotSection from './BotSection.svelte';

	let { page, guild }: { page: BotPage; guild: BotGuild } = $props();

	// svelte-ignore state_referenced_locally
	let current = $state(page);
	/** Offenes Formular: "<block>/<aktion>/<zeile>" */
	let open = $state('');
	/** Zeile mit aufgeklappter Aktionsleiste: "<block>/<zeile>" */
	let rowOpen = $state('');
	let busy = $state('');
	let feedback = $state<{ block: string; ok: boolean; text: string } | null>(null);

	const key = (block: string, a: BotAction, item: string | null) => `${block}/${a.id}/${item ?? ''}`;

	async function trigger(block: string, a: BotAction, item: string | null, values?: Record<string, BotValue>) {
		if (a.fields.length && !values) {
			open = open === key(block, a, item) ? '' : key(block, a, item);
			return;
		}
		if (a.confirm && !confirm(a.confirm)) return;
		busy = key(block, a, item);
		feedback = null;
		try {
			const res = await send<BotActionResult>(`${BOT_API}/pages/${current.id}/${block}/${a.id}`, 'POST', {
				values: values ?? {},
				item
			});
			current = res.page;
			open = '';
			rowOpen = '';
			feedback = { block, ok: true, text: res.message };
		} catch (err) {
			feedback = { block, ok: false, text: err instanceof Error ? err.message : String(err) };
		} finally {
			busy = '';
		}
	}

	const rowActions = (b: Extract<BotBlock, { type: 'table' }>, row: BotRow) => b.actions.filter((a) => !a.when || row[a.when]);

	const date = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
	function cell(kind: string, v: unknown): string {
		if (v === null || v === undefined || v === '') return '–';
		if (kind === 'time') return date.format(new Date(Number(v) * 1000));
		if (kind === 'num') return Number(v).toLocaleString('de-DE');
		return String(v);
	}
</script>

{#if current.description}<p class="dim lead">{current.description}</p>{/if}

<div class="blocks">
	{#each current.blocks as b (b.id)}
		{#if b.type === 'form'}
			{#key b.id}
				<BotSection section={b.section} {guild} />
			{/key}
		{:else}
			<section class="glass pad block">
				<header>
					<div>
						<h2>{b.title}</h2>
						{#if b.description}<p class="dim">{b.description}</p>{/if}
					</div>
					{#if b.type === 'table' && b.create}
						<button type="button" class="btn primary" onclick={() => trigger(b.id, b.create!, null)}>
							{b.create.label}
						</button>
					{/if}
				</header>

				{#if feedback?.block === b.id}
					<p class="notice" class:ok={feedback.ok} class:error={!feedback.ok} role={feedback.ok ? 'status' : 'alert'}>
						{feedback.text}
					</p>
				{/if}

				{#if b.type === 'table'}
					{#if b.create && open === key(b.id, b.create, null)}
						<BotForm action={b.create} {guild} busy={!!busy} run={(v) => trigger(b.id, b.create!, null, v)}
							cancel={() => (open = '')} />
					{/if}
					{#if b.rows.length}
						<div class="table-wrap">
							<table class="table">
								<thead>
									<tr>
										{#each b.columns as c (c.key)}
											<th class:right={c.kind === 'num'}>{c.label}</th>
										{/each}
										{#if b.actions.length}<th class="act"><span class="sr">Aktionen</span></th>{/if}
									</tr>
								</thead>
								<tbody>
									{#each b.rows as row (row.id)}
										<tr>
											{#each b.columns as c (c.key)}
												<td class:right={c.kind === 'num'} class:num={c.kind === 'num' || c.kind === 'time'}>
													{#if c.kind === 'badge'}
														{@const tone = row[`${c.key}_tone`]}
														<span class="chip" class:ok={tone === 'ok'} class:warn={tone === 'warn'}
															class:danger={tone === 'danger'}>{cell('text', row[c.key])}</span>
													{:else if c.kind === 'link' && row[c.key]}
														<a href={String(row[c.key])} target="_blank" rel="noopener noreferrer">Öffnen</a>
													{:else}
														{cell(c.kind, row[c.key])}
													{/if}
												</td>
											{/each}
											{#if b.actions.length}
												{@const acts = rowActions(b, row)}
												{@const rk = `${b.id}/${row.id}`}
												<td class="row-actions">
													{#if acts.length === 1}
														<button type="button" class="btn small" class:danger={acts[0].danger}
															disabled={busy === key(b.id, acts[0], row.id)} onclick={() => trigger(b.id, acts[0], row.id)}>
															{acts[0].label}
														</button>
													{:else if acts.length}
														<button type="button" class="btn small" class:active={rowOpen === rk}
															aria-expanded={rowOpen === rk} onclick={() => (rowOpen = rowOpen === rk ? '' : rk)}>
															Aktionen
														</button>
													{/if}
												</td>
											{/if}
										</tr>
										{#if rowOpen === `${b.id}/${row.id}`}
											<tr class="form-row">
												<td colspan={b.columns.length + 1}>
													<div class="buttons">
														{#each rowActions(b, row) as a (a.id)}
															<button type="button" class="btn small" class:danger={a.danger}
																disabled={busy === key(b.id, a, row.id)} onclick={() => trigger(b.id, a, row.id)}>
																{a.label}
															</button>
														{/each}
													</div>
												</td>
											</tr>
										{/if}
										{#each rowActions(b, row).filter((a) => open === key(b.id, a, row.id)) as a (a.id)}
											<tr class="form-row">
												<td colspan={b.columns.length + 1}>
													<BotForm action={a} {guild} busy={!!busy} run={(v) => trigger(b.id, a, row.id, v)}
														cancel={() => (open = '')} />
												</td>
											</tr>
										{/each}
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<p class="dim empty">{b.empty}</p>
					{/if}
				{:else if b.type === 'status'}
					<dl>
						{#each b.items as it (it.label)}
							<dt>{it.label}</dt>
							<dd>
								{#if it.href}<a href={it.href} target="_blank" rel="noopener noreferrer">{it.value}</a>
								{:else}{it.value}{/if}
							</dd>
						{/each}
					</dl>
				{/if}

				{#if b.type === 'actions' && b.actions.length === 1 && b.actions[0].fields.length}
					<!-- Nur eine Aktion mit Feldern: Formular steht gleich offen da -->
					<BotForm action={b.actions[0]} {guild} busy={!!busy} run={(v) => trigger(b.id, b.actions[0], null, v)} />
				{:else if b.type === 'status' || b.type === 'actions'}
					{@const actions = b.type === 'status' ? b.actions.filter((a) => !a.when || b.flags[a.when]) : b.actions}
					{#if actions.length}
						<div class="buttons">
							{#each actions as a (a.id)}
								<button type="button" class="btn" class:danger={a.danger} class:active={open === key(b.id, a, null)}
									aria-expanded={a.fields.length ? open === key(b.id, a, null) : undefined}
									disabled={busy === key(b.id, a, null)} onclick={() => trigger(b.id, a, null)}>
									{a.label}
								</button>
							{/each}
						</div>
						{#each actions.filter((a) => open === key(b.id, a, null)) as a (a.id)}
							<BotForm action={a} {guild} busy={!!busy} run={(v) => trigger(b.id, a, null, v)} cancel={() => (open = '')} />
						{/each}
					{/if}
				{/if}
			</section>
		{/if}
	{/each}
</div>

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	.blocks {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.block {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
	}
	h2 {
		margin: 0;
		font-size: 17px;
		font-weight: 650;
	}
	header p {
		margin: 4px 0 0;
		font-size: 14px;
	}
	.notice {
		margin: 0;
	}
	.empty {
		margin: 0;
	}
	.row-actions {
		text-align: right;
		white-space: nowrap;
	}
	.form-row td {
		border-top: 0;
		padding-top: 0;
	}
	.form-row .buttons {
		justify-content: flex-end;
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.btn.active {
		border-color: rgba(106, 211, 255, 0.45);
	}
	dl {
		display: grid;
		grid-template-columns: max-content minmax(0, 1fr);
		gap: 10px 22px;
		margin: 0;
	}
	dt {
		color: var(--dim);
		font-size: 14px;
	}
	dd {
		margin: 0;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	/* Bezugsrahmen für .sr, sonst hängt sie an der Seite und verbreitert sie */
	.act {
		position: relative;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
	@media (max-width: 600px) {
		dl {
			grid-template-columns: minmax(0, 1fr);
			gap: 2px 0;
		}
		dd {
			margin-bottom: 10px;
		}
	}
</style>
