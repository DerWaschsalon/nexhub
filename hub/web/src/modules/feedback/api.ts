// Antworten von /api/feedback (hub/api/nexhub_api/routes/feedback.py).

/** Stände eines Eintrags; „erledigt“ und „abgelehnt“ gelten als abgeschlossen */
export const STATUSES = ['neu', 'gesehen', 'geplant', 'erledigt', 'abgelehnt'] as const;
export type FeedbackStatus = (typeof STATUSES)[number];
export const CLOSED: FeedbackStatus[] = ['erledigt', 'abgelehnt'];

export type FeedbackEntry = {
	id: number;
	title: string;
	body: string;
	status: FeedbackStatus;
	created_at: string;
	votes: number;
	/** hat dieses Konto schon gestimmt? */
	voted: boolean;
	mine: boolean;
	/** nur für Admins, sonst null */
	author: string | null;
};
