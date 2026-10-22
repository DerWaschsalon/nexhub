<!-- Schlichte Linien-Icons (24×24). Neues Icon = neuer Eintrag in PATHS. -->
<script lang="ts" module>
	const PATHS = {
		home: 'M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10',
		trophy: 'M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M9 20h6M10 17h4',
		users: 'M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm10 8v-1.5a3.5 3.5 0 0 0-2.5-3.35M15 4.15a3.5 3.5 0 0 1 0 6.7',
		server: 'M4 5h16v6H4zM4 13h16v6H4zM8 8h.01M8 16h.01',
		device: 'M3 6h18v9H3zM8 19h8M12 15v4M7 10.5h.01M10 10.5h.01M13 10.5h.01M16 10.5h.01',
		shield: 'M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6zM9 12l2 2 4-4',
		bot: 'M5 9h14v10H5zM12 5v4M12 5h.01M9 13h.01M15 13h.01M9.5 16.5h5M3 13v2M21 13v2',
		logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10'
	} as const;
	export type IconName = keyof typeof PATHS;
</script>

<script lang="ts">
	let { name, size = 18 }: { name: IconName; size?: number } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="1.8"
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	<path d={PATHS[name]} />
</svg>
