<!-- Skills wie im Spiel: Symbol mit Stufe, Schloss für nicht gelernte, „E“ für angelegte Stigmen,
     Name darunter. Angelegt, aber nicht gelernt: gestrichelt rot. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData } from '../api.ts';

	let { skills }: { skills: CharacterData['skills'] } = $props();

	const groups = $derived([
		{ key: 'active', label: t('logs.char.active'), skills: skills.filter((s) => s.category === 'Active') },
		{ key: 'passive', label: t('logs.char.passive'), skills: skills.filter((s) => s.category === 'Passive') },
		{ key: 'stigma', label: t('logs.char.stigma'), skills: skills.filter((s) => s.category === 'Dp') }
	]);
</script>

{#each groups as g (g.key)}
	{#if g.skills.length}
		<h4>{g.label}</h4>
		<ul class="grid">
			{#each g.skills as s (s.name)}
				{@const locked = !s.learned || !s.level}
				<li
					class:locked
					class:missing={s.equipped && !s.learned}
					title="{s.name} · {t('logs.char.level', { n: s.level })}{s.equipped && !s.learned ? ` – ${t('logs.char.notLearned')}` : ''}"
				>
					<span class="icon">
						{#if s.icon}<img src={s.icon} alt="" width="52" height="52" loading="lazy" referrerpolicy="no-referrer" />{/if}
						{#if locked}
							<span class="lock" aria-hidden="true">
								<svg viewBox="0 0 24 24" width="18" height="18"><path d="M7 11V8a5 5 0 0 1 10 0v3M5 11h14v9H5z" /></svg>
							</span>
						{:else}
							<span class="level num">{s.level}</span>
						{/if}
						{#if g.key === 'stigma' && s.equipped && s.learned}<span class="equip">E</span>{/if}
					</span>
					<span class="name">{s.name}</span>
				</li>
			{/each}
		</ul>
	{/if}
{/each}

<style>
	h4 {
		font-size: 13px;
		margin: 14px 0 10px;
		color: var(--dim);
	}
	h4:first-child {
		margin-top: 0;
	}
	.grid {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
		gap: 12px 8px;
	}
	li {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 5px;
		min-width: 0;
	}
	.icon {
		position: relative;
		width: 56px;
		height: 56px;
		border-radius: 12px;
		border: 2px solid var(--edge);
		background: rgba(0, 0, 0, 0.35);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.icon img {
		border-radius: 9px;
	}
	.locked .icon img {
		filter: grayscale(1) brightness(0.45);
	}
	.missing .icon {
		border: 2px dashed var(--danger);
	}
	.lock {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.lock path {
		fill: none;
		stroke: rgba(255, 255, 255, 0.8);
		stroke-width: 2;
		stroke-linejoin: round;
	}
	.level {
		position: absolute;
		right: 2px;
		bottom: 2px;
		min-width: 20px;
		padding: 0 4px;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.75);
		font-size: 11px;
		font-weight: 700;
		text-align: center;
	}
	.equip {
		position: absolute;
		left: 2px;
		top: 2px;
		width: 16px;
		height: 16px;
		border-radius: 4px;
		background: var(--accent);
		color: #04121b;
		font-size: 10px;
		font-weight: 800;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.name {
		font-size: 11px;
		line-height: 1.25;
		text-align: center;
		color: var(--dim);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		max-width: 100%;
	}
	.locked .name {
		color: var(--faint);
	}
</style>
