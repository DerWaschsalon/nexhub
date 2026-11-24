// Eine Uhr für alle Countdowns: `clock.now` (Sekunden seit 1970) springt jede Sekunde weiter, solange
// jemand zusieht. So tickt ein Timer für die ganze Seite statt einer je Countdown.
import { createSubscriber } from 'svelte/reactivity';

const seconds = () => Math.floor(Date.now() / 1000);

class Clock {
	#subscribe = createSubscriber((update) => {
		const timer = setInterval(update, 1000);
		return () => clearInterval(timer);
	});

	get now(): number {
		this.#subscribe();
		return seconds();
	}
}

export const clock = new Clock();
