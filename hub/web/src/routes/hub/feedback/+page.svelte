<!-- Modul Feedback: oben ein neuer Eintrag, darunter die Einträge in den Reitern „Offen“ und „Erledigt“,
     die meisten Stimmen zuerst. Admins sehen den Namen und setzen den Status. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { send } from '#lib/api.ts';
	import Tabs from '#lib/components/Tabs.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { CLOSED, STATUSES, type FeedbackEntry, type FeedbackStatus } from '#modules/feedback/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const admin = $derived(data.me.role === 'admin');
	const open = $derived(data.entries.filter((e) => !CLOSED.includes(e.status)));
	const closed = $derived(data.entries.filter((e) => CLOSED.includes(e.status)));
	let tab = $state('open');
	const shown = $derived(tab === 'open' ? open : closed);

	let title = $state('');
	let body = $state('');
	let error = $state('');

	/** Eine Änderung an die API schicken und die Liste neu laden; Fehler erscheinen über der Liste. */
	async function change(path: string, method: string, payload?: unknown) {
		error = '';
		try {
			await send<unknown>(path, method, payload);
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function add(e: SubmitEvent) {
		e.preventDefault();
		await change('/api/feedback', 'POST', { title, body });
		if (!error) title = body = '';
	}

	const vote = (entry: FeedbackEntry) => change(`/api/feedback/${entry.id}/vote`, entry.voted ? 'DELETE' : 'POST');
	const setStatus = (entry: FeedbackEntry, status: string) =>
		change(`/api/admin/feedback/${entry.id}`, 'PUT', { status: status as FeedbackStatus });

	function remove(entry: FeedbackEntry) {
		if (confirm(t('feedback.confirmRemove', { title: entry.title }))) change(`/api/admin/feedback/${entry.id}`, 'DELETE');
	}
</script>

<svelte:head><title>{t('feedback.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('feedback.title')}</h1>
	<p class="dim">{t('feedback.intro')}</p>
</header>

<form class="glass pad new" onsubmit={add}>
	<h2>{t('feedback.new')}</h2>
	<label class="field">
		<span>{t('feedback.field.title')}</span>
		<input class="input" bind:value={title} minlength="3" maxlength="120" required />
	</label>
	<label class="field">
		<span>{t('feedback.field.body')}</span>
		<textarea class="input" bind:value={body} maxlength="2000"></textarea>
	</label>
	<button class="btn primary">{t('feedback.send')}</button>
</form>

{#if error}<p class="notice error" role="alert">{error}</p>{/if}

<Tabs tabs={[{ id: 'open', label: t('feedback.open', { n: open.length }) }, { id: 'closed', label: t('feedback.closed', { n: closed.length }) }]}
	active={tab} onselect={(id) => (tab = id)} label={t('feedback.title')} />

{#each shown as entry (entry.id)}
	<article class="glass pad entry">
		<button class="votes" class:voted={entry.voted} aria-pressed={entry.voted} onclick={() => vote(entry)}
			title={t(entry.voted ? 'feedback.unvote' : 'feedback.vote')} aria-label="{t('feedback.votes')}: {entry.votes}">
			<span aria-hidden="true">▲</span>
			<strong class="num">{entry.votes}</strong>
		</button>
		<div class="text">
			<h3>{entry.title} <span class="chip">{t(`feedback.status.${entry.status}`)}</span></h3>
			{#if entry.body}<p>{entry.body}</p>{/if}
			<p class="dim small">
				{formatDateTime(entry.created_at)}{#if entry.author} · {t('feedback.by', { name: entry.author })}{/if}
			</p>
		</div>
		{#if admin}
			<div class="manage">
				<select class="input" aria-label={t('feedback.setStatus')} value={entry.status}
					onchange={(e) => setStatus(entry, e.currentTarget.value)}>
					{#each STATUSES as s (s)}<option value={s}>{t(`feedback.status.${s}`)}</option>{/each}
				</select>
				<button class="btn small danger" onclick={() => remove(entry)}>{t('feedback.remove')}</button>
			</div>
		{/if}
	</article>
{:else}
	<p class="dim none">{t('feedback.none')}</p>
{/each}

<style>
	.new {
		display: grid;
		gap: 10px;
		max-width: 720px;
		margin-bottom: 18px;
	}
	.new button {
		justify-self: start;
	}
	h2 {
		font-size: 17px;
		margin: 0;
	}
	.entry {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		gap: 14px;
		margin-top: 12px;
	}
	.votes {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 52px;
		padding: 6px 8px;
		border: 1px solid var(--edge-soft);
		border-radius: var(--radius-sm);
		background: none;
		color: var(--dim);
		font: inherit;
		cursor: pointer;
	}
	.votes.voted {
		color: var(--accent);
		border-color: var(--accent);
	}
	.text {
		flex: 1;
		min-width: 220px;
	}
	h3 {
		font-size: 16px;
		margin: 0 0 6px;
	}
	p {
		margin: 0 0 6px;
		white-space: pre-line;
	}
	.small {
		font-size: 12px;
	}
	.manage {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.none {
		margin-top: 14px;
	}
</style>
