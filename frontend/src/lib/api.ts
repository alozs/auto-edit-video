import { io, type Socket } from 'socket.io-client';

export type JobStatus = 'queued' | 'processing' | 'done' | 'error' | 'cancelling' | 'cancelled';

export interface Job {
	id: string;
	status: JobStatus;
	progress: number;
	progress_text: string;
	options: Record<string, unknown>;
	has_output: boolean;
	error: string | null;
	created_at: number;
	updated_at: number;
	log?: string[];
}

export interface JobOptions {
	remove_silence: boolean;
	silence_method: 'speech' | 'volume';
	remove_fillers: boolean;
	captions: boolean;
	model: string;
	language: string;
}

export async function createJob(file: File, options: JobOptions): Promise<Job> {
	const fd = new FormData();
	fd.append('video', file);
	for (const [k, v] of Object.entries(options)) fd.append(k, String(v));
	const res = await fetch('/api/jobs', { method: 'POST', body: fd });
	if (!res.ok) throw new Error((await res.json()).error || 'upload failed');
	return res.json();
}

export async function getJob(id: string): Promise<Job> {
	const res = await fetch(`/api/jobs/${id}`);
	if (!res.ok) throw new Error('not found');
	return res.json();
}

export async function deleteJob(id: string): Promise<void> {
	await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
}

export async function cancelJob(id: string): Promise<void> {
	await fetch(`/api/jobs/${id}/cancel`, { method: 'POST' });
}

export function downloadUrl(id: string): string {
	return `/api/jobs/${id}/download`;
}

export interface Settings {
	llm_provider: 'google' | 'openrouter';
	valid_providers: string[];
	llm_model: string;
	llm_models: Record<string, string>;
	has_gemini_key: boolean;
	gemini_key_preview: string;
	has_openrouter_key: boolean;
	openrouter_key_preview: string;
	whisper_compute_type: string;
	valid_compute_types: string[];
}

export type SettingsPatch = Partial<{
	llm_provider: 'google' | 'openrouter';
	llm_model: string;
	gemini_api_key: string;
	openrouter_api_key: string;
	whisper_compute_type: string;
}>;

export async function getSettings(): Promise<Settings> {
	const res = await fetch('/api/settings');
	if (!res.ok) throw new Error('settings fetch failed');
	return res.json();
}

export async function saveSettings(data: SettingsPatch): Promise<Settings> {
	const res = await fetch('/api/settings', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error(err.error || 'save failed');
	}
	return res.json();
}

let socket: Socket | null = null;

export function getSocket(): Socket {
	if (!socket) {
		socket = io('/', { path: '/socket.io' });
	}
	return socket;
}
