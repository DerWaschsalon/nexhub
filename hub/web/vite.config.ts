import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Reine Browser-App: die API liefert 200.html für alle Pfade, die keine Datei sind
			adapter: adapter({ fallback: '200.html' })
		})
	],
	// Entwicklung: API lokal mit `uv run python -m nexhub_api` (Port 8000)
	server: { proxy: { '/api': 'http://127.0.0.1:8000' } }
});
