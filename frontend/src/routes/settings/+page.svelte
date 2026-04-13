<script lang="ts">
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import Select from '$lib/components/Select.svelte';
	import { getSettings, saveSettings, type Settings } from '$lib/api';
	import { goto } from '$app/navigation';
	import { ArrowLeft, Check, ExternalLink, Cpu, Sparkles, Eye, EyeOff } from 'lucide-svelte';
	import { onMount } from 'svelte';

	let settings = $state<Settings | null>(null);
	let provider = $state<'google' | 'openrouter'>('google');
	let model = $state('');
	let newKey = $state('');
	let showKey = $state(false);
	let computeType = $state('int8');
	let saving = $state(false);
	let flash = $state<string | null>(null);
	let error = $state<string | null>(null);

	const COMPUTE_LABELS: Record<string, string> = {
		int8: 'Rápido',
		int8_float32: 'Intermediário',
		float32: 'Melhor qualidade'
	};
	const COMPUTE_HINTS: Record<string, string> = {
		int8: 'Recomendado. Resultado bom em menos tempo.',
		int8_float32: 'Um pouco melhor, um pouco mais demorado.',
		float32: 'Resultado mais apurado. Pode demorar bastante.'
	};

	const PROVIDER_META: Record<string, { label: string; short: string; url: string; placeholder: string; models: string[] }> = {
		google: {
			label: 'Google AI Studio',
			short: 'Google',
			url: 'https://aistudio.google.com/apikey',
			placeholder: 'AIza...',
			models: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-3-flash-preview']
		},
		openrouter: {
			label: 'OpenRouter',
			short: 'OpenRouter',
			url: 'https://openrouter.ai/keys',
			placeholder: 'sk-or-...',
			models: [
				'google/gemini-2.5-flash',
				'google/gemini-2.5-pro',
				'anthropic/claude-sonnet-4.5',
				'openai/gpt-4o-mini'
			]
		}
	};

	const hasKey = $derived(
		provider === 'google' ? !!settings?.has_gemini_key : !!settings?.has_openrouter_key
	);
	const keyPreview = $derived(
		provider === 'google' ? settings?.gemini_key_preview : settings?.openrouter_key_preview
	);
	const meta = $derived(PROVIDER_META[provider]);
	const hasChanges = $derived(
		!!settings &&
			(provider !== settings.llm_provider ||
				model !== settings.llm_model ||
				!!newKey.trim())
	);

	onMount(load);

	async function load() {
		try {
			settings = await getSettings();
			provider = settings.llm_provider;
			model = settings.llm_model;
			computeType = settings.whisper_compute_type;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	function notify(msg: string) {
		flash = msg;
		setTimeout(() => (flash = null), 2500);
	}

	async function saveAI() {
		saving = true;
		error = null;
		try {
			const patch: Parameters<typeof saveSettings>[0] = { llm_provider: provider };
			if (model.trim()) patch.llm_model = model.trim();
			if (newKey.trim()) {
				patch[provider === 'google' ? 'gemini_api_key' : 'openrouter_api_key'] = newKey.trim();
			}
			settings = await saveSettings(patch);
			provider = settings.llm_provider;
			model = settings.llm_model;
			newKey = '';
			notify('Salvo');
		} catch (e) {
			error = (e as Error).message;
		} finally {
			saving = false;
		}
	}

	async function removeKey() {
		saving = true;
		error = null;
		try {
			settings = await saveSettings({
				[provider === 'google' ? 'gemini_api_key' : 'openrouter_api_key']: ''
			} as Parameters<typeof saveSettings>[0]);
			notify('Chave removida');
		} catch (e) {
			error = (e as Error).message;
		} finally {
			saving = false;
		}
	}

	async function saveCompute(value: string) {
		computeType = value;
		saving = true;
		error = null;
		try {
			settings = await saveSettings({ whisper_compute_type: value });
			notify('Qualidade atualizada');
		} catch (e) {
			error = (e as Error).message;
		} finally {
			saving = false;
		}
	}

	let prevProvider = $state<string | null>(null);
	$effect(() => {
		if (!settings) return;
		if (prevProvider === null) {
			prevProvider = provider;
			return;
		}
		if (provider !== prevProvider) {
			model = '';
			prevProvider = provider;
		}
	});
</script>

<main class="mx-auto w-full max-w-xl px-4 py-10 lg:max-w-5xl lg:py-14">
	<button
		class="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
		onclick={() => goto('/')}
	>
		<ArrowLeft class="h-4 w-4" /> Voltar
	</button>

	<header class="mb-8">
		<h1 class="text-2xl font-semibold tracking-tight">Configurações</h1>
		<p class="mt-1 text-sm text-muted-foreground">
			Escolha qual IA usar e como a transcrição deve ser feita.
		</p>
	</header>

	<div class="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
		<!-- AI -->
		<Card>
			<div class="space-y-6 p-6">
				<div class="flex items-start gap-3">
					<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-lg shadow-indigo-500/20">
						<Sparkles class="h-5 w-5" />
					</div>
					<div class="flex-1">
						<div class="flex items-center gap-2">
							<p class="text-sm font-medium">Inteligência Artificial</p>
							{#if hasKey}
								<span class="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
									<Check class="h-3 w-3" /> Conectado
								</span>
							{:else}
								<span class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Falta conectar</span>
							{/if}
						</div>
						<p class="mt-0.5 text-xs text-muted-foreground">
							Usada para limpar a fala e melhorar as legendas.
						</p>
					</div>
				</div>

				<div class="grid gap-3 sm:grid-cols-2">
					<Select
						bind:value={provider}
						label="Serviço de IA"
						options={[
							{ value: 'google', label: 'Google AI Studio' },
							{ value: 'openrouter', label: 'OpenRouter' }
						]}
					/>
					<div class="flex flex-col gap-2">
						<label for="model-input" class="text-sm font-medium">Modelo</label>
						<input
							id="model-input"
							type="text"
							bind:value={model}
							placeholder={settings?.llm_models?.[provider] || meta.models[0]}
							class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
						/>
						<p class="text-xs text-muted-foreground">
							{#if settings?.llm_models?.[provider]}
								Atual: {settings.llm_models[provider]}
							{:else}
								Ex: {meta.models.slice(0, 2).join(', ')}
							{/if}
						</p>
					</div>
				</div>

				<div class="space-y-2">
					<div class="flex items-center justify-between gap-2">
						<label for="api-key-input" class="text-sm font-medium">Chave de acesso</label>
						{#if hasKey}
							<span class="font-mono text-xs text-muted-foreground">{keyPreview}</span>
						{/if}
					</div>
					<div class="relative">
						<input
							id="api-key-input"
							type={showKey ? 'text' : 'password'}
							bind:value={newKey}
							placeholder={hasKey ? 'Cole uma nova chave para trocar' : meta.placeholder}
							class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
						/>
						<button
							type="button"
							class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
							onclick={() => (showKey = !showKey)}
							aria-label={showKey ? 'Ocultar' : 'Mostrar'}
						>
							{#if showKey}<EyeOff class="h-4 w-4" />{:else}<Eye class="h-4 w-4" />{/if}
						</button>
					</div>
					<a
						href={meta.url}
						target="_blank"
						rel="noopener"
						class="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
					>
						Onde pegar a chave <ExternalLink class="h-3 w-3" />
					</a>
				</div>

				<div class="flex items-center justify-between gap-2 border-t pt-4">
					<div>
						{#if hasKey}
							<Button variant="ghost" size="sm" onclick={removeKey} disabled={saving}>
								Desconectar
							</Button>
						{/if}
					</div>
					<Button onclick={saveAI} disabled={saving || !hasChanges}>
						{saving ? 'Salvando...' : 'Salvar'}
					</Button>
				</div>
			</div>
		</Card>

		<!-- Whisper -->
		<Card>
			<div class="space-y-5 p-6">
				<div class="flex items-start gap-3">
					<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-emerald-500 text-white shadow-lg shadow-cyan-500/20">
						<Cpu class="h-5 w-5" />
					</div>
					<div class="flex-1">
						<p class="text-sm font-medium">Velocidade da transcrição</p>
						<p class="mt-0.5 text-xs text-muted-foreground">Mais qualidade demora mais.</p>
					</div>
				</div>

				{#if settings}
					<div class="space-y-2">
						{#each settings.valid_compute_types as v}
							<button
								type="button"
								onclick={() => saveCompute(v)}
								disabled={saving}
								class="group flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors disabled:opacity-60 {computeType === v ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent/40'}"
							>
								<span
									class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border {computeType === v ? 'border-primary bg-primary' : 'border-muted-foreground/40'}"
								>
									{#if computeType === v}
										<span class="h-1.5 w-1.5 rounded-full bg-primary-foreground"></span>
									{/if}
								</span>
								<span class="flex-1">
									<span class="block text-sm font-medium">{COMPUTE_LABELS[v] ?? v}</span>
									<span class="block text-xs text-muted-foreground">{COMPUTE_HINTS[v] ?? ''}</span>
								</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</Card>
	</div>

	{#if error}
		<p class="mt-4 text-sm text-destructive">{error}</p>
	{/if}
	{#if flash}
		<p class="mt-4 flex items-center gap-1.5 text-sm text-primary">
			<Check class="h-4 w-4" /> {flash}
		</p>
	{/if}
</main>
