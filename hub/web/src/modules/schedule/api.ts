// Antwort von GET /api/public/termine (hub/api/nexhub_api/routes/schedule.py). Zeiten in Sekunden seit 1970.

export type ScheduleEvent = {
	key: string;
	name_en: string;
	name_de: string;
	start: number;
	/** nur solange der Termin offen ist */
	open_until: number | null;
	place: string;
};

export type Schedule = {
	now: number;
	/** IANA-Name der Server-Uhr */
	server_zone: string;
	events: ScheduleEvent[];
	/** Wochentermine der nächsten sieben Tage, nach Beginn */
	week: { key: string; start: number }[];
};
