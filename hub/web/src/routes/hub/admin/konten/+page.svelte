<!-- Konten: wer sich angemeldet hat; Sitzungen beenden, sperren, entsperren. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { post, type Account } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let busy = $state<number | null>(null);
	let error = $state('');

	async function act(account: Account, action: 'logout' | 'block' | 'unblock') {
		if (action === 'block' && !confirm(t('accounts.confirmBlock', { name: account.name }))) return;
		busy = account.id;
		error = '';
		try {
			await post(`/api/admin/users/${account.id}/${action}`);
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			busy = null;
		}
	}
</script>

<header class="page-head">
	<h1>{t('accounts.title')}</h1>
	<p>{t('accounts.intro')}</p>
</header>

{#if error}
	<p class="notice error" role="alert">{error}</p>
{/if}

<section class="glass pad table-wrap">
	<table class="table">
		<thead>
			<tr>
				<th>{t('accounts.col.account')}</th>
				<th>{t('accounts.col.role')}</th>
				<th>{t('accounts.col.lastLogin')}</th>
				<th>{t('accounts.col.sessions')}</th>
				<th></th>
			</tr>
		</thead>
		<tbody>
			{#each data.accounts as account (account.id)}
				<tr class:blocked={account.blocked}>
					<td>
						<div class="who">
							<Avatar name={account.name} url={account.avatar_url} />
							<div>
								<strong>{account.name}</strong>
								<div class="dim id">{account.discord_id}</div>
							</div>
						</div>
					</td>
					<td>
						<span class="chip" class:accent={account.role === 'admin'}>{t(`role.${account.role}`)}</span>
						{#if account.blocked}<span class="chip danger">{t('accounts.blocked')}</span>{/if}
					</td>
					<td class="dim">{formatDateTime(account.last_login_at)}</td>
					<td>{account.sessions}</td>
					<td class="actions">
						{#if account.sessions > 0}
							<button class="btn small" disabled={busy === account.id} onclick={() => act(account, 'logout')}>
								{t('accounts.logout')}
							</button>
						{/if}
						{#if account.role !== 'admin'}
							{#if account.blocked}
								<button class="btn small" disabled={busy === account.id} onclick={() => act(account, 'unblock')}>
									{t('accounts.unblock')}
								</button>
							{:else}
								<button class="btn small danger" disabled={busy === account.id} onclick={() => act(account, 'block')}>
									{t('accounts.block')}
								</button>
							{/if}
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</section>

<style>
	.who {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.id {
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.actions {
		text-align: right;
		white-space: nowrap;
	}
	.actions .btn + .btn {
		margin-left: 6px;
	}
	tr.blocked .who {
		opacity: 0.55;
	}
	.notice {
		margin: 0 0 16px;
	}
</style>
