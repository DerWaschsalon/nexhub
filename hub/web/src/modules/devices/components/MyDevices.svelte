<!-- Übersicht: die gekoppelten NexBoards und wann sie sich zuletzt gemeldet haben. -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Device } from '../api.ts';
</script>

{#await api<Device[]>('/api/devices') then devices}
	{#if devices.length}
		<ul>
			{#each devices as device (device.id)}
				<li>
					<Icon name="device" />
					<strong>{device.name}</strong>
					<span class="dim">{t('devices.col.seen')}: {device.last_seen_at ? formatDateTime(device.last_seen_at) : '–'}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="dim">{t('devices.none')}</p>
	{/if}
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}

<style>
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 10px;
	}
	.dim {
		font-size: 13px;
	}
</style>
