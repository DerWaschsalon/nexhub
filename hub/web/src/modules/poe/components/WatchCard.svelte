<!-- Ein Eintrag der Merkliste: Preis, Änderung 24 h / 7 Tage, Verlauf der Liga, Alarmschwelle,
     Link zu poe.ninja und Entfernen. Nach jeder Änderung lädt die Seite die Liste neu. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import DayChart from '#lib/components/DayChart.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import { removeWatch, setThreshold, type PoeWatch } from '../api.ts';
	import { changeColor, formatAmount, formatChange, formatPrice } from '../format.ts';

	let { w, unit }: { w: PoeWatch; unit: string | null } = $props();

	let error = $state('');

	async function run(action: () => Promise<unknown>) {
		error = '';
		try {
			await action();
			await invalidateAll();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	function changeThreshold(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		if (!input.checkValidity()) return input.reportValidity();
		run(() => setThreshold(w.id, input.valueAsNumber));
	}

	function remove() {
		if (confirm(t('poe.confirmRemove', { name: w.name }))) run(() => removeWatch(w.id));
	}
</script>

<article class="glass card">
	<header>
		{#if w.icon}<img src={w.icon} alt="" width="40" height="40" referrerpolicy="no-referrer" />{/if}
		<h3>{w.name}</h3>
		{#if w.price !== null}
			<strong class="num">{formatPrice(w.price, unit)}</strong>
		{/if}
	</header>

	{#if w.price === null}
		<p class="dim">{t('poe.noPrice')}</p>
	{:else}
		<p class="changes num">
			<span style:color={changeColor(w.change_24h)}>{formatChange(w.change_24h)}</span>
			<span class="dim">{t('poe.change24h')}</span>
			<span style:color={changeColor(w.change_7d)}>{formatChange(w.change_7d)}</span>
			<span class="dim">{t('poe.change7d')}</span>
		</p>
		<DayChart title={t('poe.history')} days={w.days.map((d) => ({ day: d.day, value: d.price }))} color="var(--accent)"
			format={(v) => formatPrice(v, unit)} axisFormat={formatAmount} />
	{/if}

	<footer>
		<label class="threshold">
			{t('poe.threshold')}
			<input class="input num" type="number" min="1" max="1000" step="1" value={w.threshold} onchange={changeThreshold} />
			%
		</label>
		<span class="links">
			{#if w.url}<a class="btn small" href={w.url} target="_blank" rel="noopener noreferrer">{t('poe.ninja')}</a>{/if}
			<button class="btn small danger" onclick={remove}>{t('poe.remove')}</button>
		</span>
	</footer>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</article>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 18px;
	}
	header {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	header img {
		object-fit: contain;
	}
	h3 {
		flex: 1;
		min-width: 0;
		font-size: 16px;
	}
	strong {
		font-size: 18px;
		white-space: nowrap;
	}
	p {
		margin: 0;
	}
	.changes {
		display: flex;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.changes .dim {
		font-weight: 400;
		margin-right: 10px;
	}
	footer {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		margin-top: auto;
	}
	.threshold {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 14px;
		color: var(--dim);
	}
	.threshold .input {
		width: 80px;
		padding: 6px 8px;
	}
	.links {
		display: flex;
		gap: 8px;
	}
</style>
