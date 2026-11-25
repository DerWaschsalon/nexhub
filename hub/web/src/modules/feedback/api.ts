// Antworten von /api/feedback (hub/api/nexhub_api/routes/feedback.py).

/** Stände eines Eintrags; „erledigt“ und „abgelehnt“ gelten als abgeschlossen */
export const STATUSES = ['neu', 'gesehen', 'geplant', 'erledigt', 'abgelehnt'] as const;
import type { FeedbackEntry } from '#lib/api-types.ts';

export type FeedbackStatus = FeedbackEntry['status'];
export const CLOSED: FeedbackStatus[] = ['erledigt', 'abgelehnt'];

export type { FeedbackEntry } from '#lib/api-types.ts';
