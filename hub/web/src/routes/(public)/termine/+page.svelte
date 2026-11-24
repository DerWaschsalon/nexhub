<!-- Seite „Termine“ (Modul schedule); dieselbe Ansicht im Hub und im öffentlichen Bereich. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import ScheduleView from '#modules/schedule/components/ScheduleView.svelte';
</script>

<svelte:head><title>{t('schedule.title')} · NexHub</title></svelte:head>

<ScheduleView />
