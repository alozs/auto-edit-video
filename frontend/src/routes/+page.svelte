<script lang="ts">
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import Progress from '$lib/components/Progress.svelte';
	import Switch from '$lib/components/Switch.svelte';
	import Select from '$lib/components/Select.svelte';
	import {
		cancelJob,
		createJob,
		deleteJob,
		downloadUrl,
		getJob,
		getSocket,
		type Job,
		type JobOptions
	} from '$lib/api';
	import Dialog from '$lib/components/Dialog.svelte';
	import { Upload, Film, Loader2, Download, Trash2, RotateCcw, Check, Settings, X, Ban } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	const STORAGE_KEY = 'auto-editor:current_job_id';

	type Step = 'upload' | 'options' | 'processing' | 'done' | 'cancelled';

	let step = $state<Step>('upload');
	let file = $state<File | null>(null);
	let dragOver = $state(false);
	let error = $state<string | null>(null);

	let options = $state<JobOptions>({
		remove_silence: true,
		silence_method: 'speech',
		remove_fillers: false,
		captions: true,
		model: 'small',
		language: 'pt'
	});

	let job = $state<Job | null>(null);
	let log = $state<string[]>([]);
	let showCancel = $state(false);

	function onPick(e: Event) {
		const t = e.target as HTMLInputElement;
		if (t.files?.[0]) {
			file = t.files[0];
			step = 'options';
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		const f = e.dataTransfer?.files?.[0];
		if (f) {
			file = f;
			step = 'options';
		}
	}

	function subscribe(jobId: string) {
		const sock = getSocket();
		sock.emit('subscribe', { job_id: jobId });
		sock.off('job_update');
		sock.off('job_log');
		sock.on('job_update', (j: Job) => {
			if (j.id === job?.id) {
				job = { ...job!, ...j };
				if (j.status === 'done') step = 'done';
				if (j.status === 'cancelled') step = 'cancelled';
				if (j.status === 'error') {
					error = j.error || 'Erro no processamento';
				}
			}
		});
		sock.on('job_log', (p: { line: string }) => {
			log = [...log, p.line];
		});
	}

	function pollJob(jobId: string) {
		const poll = setInterval(async () => {
			if (!job || job.id !== jobId) return clearInterval(poll);
			try {
				const fresh = await getJob(jobId);
				job = fresh;
				if (fresh.log) log = fresh.log;
				if (fresh.status === 'done') {
					step = 'done';
					clearInterval(poll);
				} else if (fresh.status === 'cancelled') {
					step = 'cancelled';
					clearInterval(poll);
				} else if (fresh.status === 'error') {
					error = fresh.error || 'Erro no processamento';
					clearInterval(poll);
				}
			} catch {
				clearInterval(poll);
				localStorage.removeItem(STORAGE_KEY);
				reset();
			}
		}, 4000);
	}

	async function start() {
		if (!file) return;
		error = null;
		try {
			job = await createJob(file, options);
			localStorage.setItem(STORAGE_KEY, job.id);
			log = [];
			step = 'processing';
			subscribe(job.id);
			pollJob(job.id);
			return;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	onMount(async () => {
		const savedId = localStorage.getItem(STORAGE_KEY);
		if (!savedId) return;
		try {
			const fresh = await getJob(savedId);
			job = fresh;
			log = fresh.log ?? [];
			if (fresh.status === 'done') step = 'done';
			else if (fresh.status === 'cancelled') step = 'cancelled';
			else if (fresh.status === 'error') {
				step = 'processing';
				error = fresh.error || 'Erro no processamento';
			} else {
				step = 'processing';
				subscribe(savedId);
				pollJob(savedId);
			}
		} catch {
			localStorage.removeItem(STORAGE_KEY);
		}
	});

	async function discard() {
		if (job) await deleteJob(job.id);
		localStorage.removeItem(STORAGE_KEY);
		reset();
	}

	async function confirmCancel() {
		if (!job) return;
		await cancelJob(job.id);
		localStorage.removeItem(STORAGE_KEY);
	}

	function reset() {
		localStorage.removeItem(STORAGE_KEY);
		file = null;
		job = null;
		log = [];
		error = null;
		step = 'upload';
	}

	function fmtSize(n: number) {
		if (n < 1e6) return (n / 1e3).toFixed(0) + ' KB';
		if (n < 1e9) return (n / 1e6).toFixed(1) + ' MB';
		return (n / 1e9).toFixed(2) + ' GB';
	}
</script>

<main class="mx-auto w-full max-w-2xl px-4 py-10 lg:max-w-4xl lg:py-16 xl:max-w-5xl">
	<header class="mb-10 flex items-center gap-3">
		<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/20">
			<Film class="h-5 w-5" />
		</div>
		<div class="flex-1">
			<h1 class="bg-gradient-to-r from-indigo-400 via-violet-300 to-fuchsia-400 bg-clip-text text-xl font-semibold tracking-tight text-transparent">
				Auto Video Editor
			</h1>
		</div>
		<Button variant="ghost" size="icon" onclick={() => goto('/settings')} aria-label="Configurações">
			<Settings class="h-5 w-5" />
		</Button>
	</header>

	{#if step === 'upload'}
		<Card class="mx-auto max-w-2xl">
			<label
				for="file-input"
				class="flex cursor-pointer flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed p-12 text-center transition-colors lg:p-16 {dragOver
					? 'border-primary bg-accent/40'
					: 'border-border hover:border-primary/50 hover:bg-accent/20'}"
				ondragover={(e) => {
					e.preventDefault();
					dragOver = true;
				}}
				ondragleave={() => (dragOver = false)}
				ondrop={onDrop}
			>
				<div class="flex h-14 w-14 items-center justify-center rounded-full bg-secondary">
					<Upload class="h-6 w-6 text-muted-foreground" />
				</div>
				<div>
					<p class="text-base font-medium">Arraste um vídeo ou clique para escolher</p>
					<p class="mt-1 text-sm text-muted-foreground">MP4, MOV, MKV, AVI, WEBM</p>
				</div>
				<input id="file-input" type="file" accept="video/*" class="hidden" onchange={onPick} />
			</label>
		</Card>
	{/if}

	{#if step === 'options' && file}
		<div class="grid gap-4 lg:grid-cols-[320px_1fr]">
			<!-- Left: file info -->
			<Card class="lg:sticky lg:top-6 lg:self-start">
				<div class="space-y-4 p-5">
					<div class="flex items-center gap-3">
						<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
							<Film class="h-5 w-5" />
						</div>
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium">{file.name}</p>
							<p class="text-xs text-muted-foreground">{fmtSize(file.size)}</p>
						</div>
					</div>
					<Button variant="outline" size="sm" class="w-full" onclick={reset}>Trocar vídeo</Button>
				</div>
			</Card>

			<!-- Right: options + action -->
			<div class="space-y-4">
				<Card>
					<div class="space-y-5 p-6">
						<h2 class="text-base font-semibold">O que fazer com o vídeo</h2>
						<div class="grid gap-5 sm:grid-cols-2">
							<Switch
								bind:checked={options.remove_silence}
								label="Remover pausas"
								description="Corta silêncios e partes sem áudio"
							/>
							<Switch
								bind:checked={options.remove_fillers}
								label="Limpar a fala"
								description="Tira 'é...', 'tipo', 'né' e falas repetidas"
							/>
							<Switch
								bind:checked={options.captions}
								label="Adicionar legendas"
								description="Legendas animadas direto no vídeo"
							/>
						</div>
						<div class="grid gap-4 pt-2 sm:grid-cols-2">
							<Select
								bind:value={options.model}
								label="Qualidade da transcrição"
								options={[
									{ value: 'tiny', label: 'Bem rápida (menos precisa)' },
									{ value: 'base', label: 'Rápida' },
									{ value: 'small', label: 'Equilibrada (recomendada)' },
									{ value: 'medium', label: 'Precisa (demora mais)' },
									{ value: 'large', label: 'Máxima (bem mais demorada)' }
								]}
							/>
							<Select
								bind:value={options.language}
								label="Idioma do vídeo"
								options={[
									{ value: 'pt', label: 'Português' },
									{ value: 'en', label: 'Inglês' },
									{ value: 'es', label: 'Espanhol' }
								]}
							/>
						</div>
					</div>
				</Card>

				{#if error}
					<p class="text-sm text-destructive">{error}</p>
				{/if}

				<div class="flex justify-end gap-2">
					<Button variant="outline" onclick={reset}>Cancelar</Button>
					<Button onclick={start}>Começar</Button>
				</div>
			</div>
		</div>
	{/if}

	{#if step === 'processing' && job}
		<Card class="mx-auto max-w-3xl">
			<div class="space-y-6 p-6">
				<div class="flex items-center gap-3">
					<Loader2 class="h-5 w-5 animate-spin text-primary" />
					<div class="flex-1">
						<p class="text-sm font-medium">{job.progress_text}</p>
						<p class="text-xs text-muted-foreground">{job.progress}% concluído</p>
					</div>
					<Button
						variant="ghost"
						size="sm"
						onclick={() => (showCancel = true)}
						disabled={job.status === 'cancelling'}
					>
						<X class="h-4 w-4" />
						{job.status === 'cancelling' ? 'Cancelando...' : 'Cancelar'}
					</Button>
				</div>
				<Progress value={job.progress} />
				<div class="max-h-64 overflow-y-auto rounded-md bg-muted p-3 font-mono text-xs">
					{#each log as line}
						<div class="whitespace-pre-wrap text-muted-foreground">{line}</div>
					{/each}
				</div>
				{#if error}
					<div class="space-y-3">
						<p class="text-sm text-destructive">{error}</p>
						<Button variant="outline" onclick={reset}>Tentar de novo</Button>
					</div>
				{/if}
			</div>
		</Card>
	{/if}

	{#if step === 'cancelled'}
		<Card class="mx-auto max-w-2xl">
			<div class="space-y-4 p-6 text-center">
				<div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
					<Ban class="h-6 w-6 text-muted-foreground" />
				</div>
				<div>
					<p class="text-base font-semibold">Processamento cancelado</p>
					<p class="mt-1 text-sm text-muted-foreground">Os arquivos temporários foram apagados.</p>
				</div>
				<Button onclick={reset}>Começar de novo</Button>
			</div>
		</Card>
	{/if}

	<Dialog
		bind:open={showCancel}
		title="Cancelar processamento?"
		description="A etapa atual pode levar alguns segundos para parar. O vídeo em andamento será descartado."
		confirmLabel="Sim, cancelar"
		cancelLabel="Continuar processando"
		variant="destructive"
		onConfirm={confirmCancel}
	/>

	{#if step === 'done' && job}
		<div class="grid gap-4 lg:grid-cols-[1fr_260px]">
			<Card>
				<div class="space-y-4 p-6">
					<div class="flex items-center gap-2 text-sm font-medium text-primary">
						<Check class="h-4 w-4" /> Tudo pronto!
					</div>
					<div class="flex items-center justify-center overflow-hidden rounded-lg bg-black">
						<video
							controls
							class="max-h-[60vh] w-full object-contain"
							src={downloadUrl(job.id)}
						></video>
					</div>
				</div>
			</Card>
			<div class="flex flex-col gap-2 lg:sticky lg:top-6 lg:self-start">
				<Button onclick={() => (window.location.href = downloadUrl(job!.id))}>
					<Download class="h-4 w-4" /> Baixar vídeo
				</Button>
				<Button variant="outline" onclick={reset}>
					<RotateCcw class="h-4 w-4" /> Processar outro
				</Button>
				<Button variant="ghost" onclick={discard}>
					<Trash2 class="h-4 w-4" /> Descartar
				</Button>
			</div>
		</div>
	{/if}
</main>
