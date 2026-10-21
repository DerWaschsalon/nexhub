<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { logout, ROLE_LABEL } from '#lib/api.ts';
	import Login from '#lib/Login.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	async function signOut() {
		await logout();
		await invalidateAll();
	}
</script>

<svelte:head>
	<title>NexHub</title>
	<link rel="icon" href="/favicon.svg" />
</svelte:head>

{#if data.me}
	<header>
		<a class="brand" href="/">NexHub</a>
		<div class="user">
			{#if data.me.avatar_url}
				<img src={data.me.avatar_url} alt="" width="32" height="32" />
			{/if}
			<span class="name">{data.me.display_name ?? data.me.username}</span>
			<span class="chip">{ROLE_LABEL[data.me.role]}</span>
			<button class="ghost" onclick={signOut}>Abmelden</button>
		</div>
	</header>
	<main>
		{@render children()}
	</main>
{:else}
	<Login health={data.health} />
{/if}

<style>
	:global {
		:root {
			--bg: #0b0e1a;
			--panel: rgba(255, 255, 255, 0.055);
			--panel-2: rgba(255, 255, 255, 0.09);
			--line: rgba(255, 255, 255, 0.12);
			--text: #f2f3f7;
			--dim: rgba(242, 243, 247, 0.62);
			--accent: #5ac8fa;
			--radius: 14px;
			color-scheme: dark;
		}
		* {
			box-sizing: border-box;
		}
		body {
			margin: 0;
			background:
				radial-gradient(900px 400px at 10% -10%, rgba(88, 60, 220, 0.28), transparent 70%),
				radial-gradient(800px 400px at 100% 0%, rgba(230, 110, 60, 0.18), transparent 70%),
				var(--bg);
			color: var(--text);
			font: 14px/1.5 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif;
			min-height: 100vh;
			overflow-x: hidden;
		}
		h1,
		h2 {
			margin: 0;
			font-weight: 600;
		}
		.dim {
			color: var(--dim);
		}
		.card {
			background: var(--panel);
			border: 1px solid var(--line);
			border-radius: var(--radius);
			backdrop-filter: blur(14px);
		}
		.button,
		button {
			font: inherit;
			font-weight: 600;
			cursor: pointer;
			text-decoration: none;
			text-align: center;
			border-radius: 10px;
			padding: 11px 18px;
			border: 1px solid transparent;
			background: var(--accent);
			color: #06121a;
		}
		.button:hover,
		button:hover {
			filter: brightness(1.08);
		}
		button.ghost {
			background: transparent;
			color: var(--text);
			border-color: var(--line);
			padding: 7px 12px;
		}
		button.ghost:hover {
			background: var(--panel-2);
		}
		:focus-visible {
			outline: 2px solid var(--accent);
			outline-offset: 2px;
		}
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 14px 20px;
		border-bottom: 1px solid var(--line);
		background: rgba(11, 14, 26, 0.6);
		backdrop-filter: blur(14px);
		position: sticky;
		top: 0;
	}
	.brand {
		font-size: 18px;
		font-weight: 700;
		color: var(--text);
		text-decoration: none;
	}
	.user {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}
	.user img {
		border-radius: 50%;
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chip {
		font-size: 12px;
		padding: 2px 9px;
		border-radius: 999px;
		background: rgba(90, 200, 250, 0.15);
		color: var(--accent);
	}
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 28px 16px;
	}
	@media (max-width: 520px) {
		.name,
		.chip {
			display: none;
		}
	}
</style>
