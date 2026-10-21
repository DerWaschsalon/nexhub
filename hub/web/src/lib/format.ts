const dateTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });

/** "21.10.2026, 10:12" aus einem ISO-Zeitstempel der API. */
export function formatDateTime(iso: string): string {
	return dateTime.format(new Date(iso));
}
