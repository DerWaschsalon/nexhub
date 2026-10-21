// Gekoppelte NexBoards (hub/api/nexhub_api/routes/devices.py)
export type Device = {
	id: number;
	name: string;
	created_at: string;
	last_seen_at: string | null;
	version: string | null;
};
