import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// NexLogs läuft unter /logs/ auf derselben Adresse wie der Hub (Login-Cookie gilt mit).
// Beim Entwickeln leitet Vite /api an den Hub auf localhost:8000 weiter.
export default defineConfig({
	base: '/logs/',
	plugins: [react()],
	server: { port: 5174, proxy: { '/api': 'http://localhost:8000' } }
});
