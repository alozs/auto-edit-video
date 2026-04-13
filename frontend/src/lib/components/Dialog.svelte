<script lang="ts">
	import type { Snippet } from 'svelte';
	import Button from './Button.svelte';

	let {
		open = $bindable(false),
		title,
		description = '',
		confirmLabel = 'Confirmar',
		cancelLabel = 'Cancelar',
		variant = 'default',
		onConfirm
	}: {
		open?: boolean;
		title: string;
		description?: string;
		confirmLabel?: string;
		cancelLabel?: string;
		variant?: 'default' | 'destructive';
		onConfirm: () => void | Promise<void>;
	} = $props();
</script>

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
		onclick={() => (open = false)}
		role="presentation"
	>
		<div
			class="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			role="dialog"
			aria-modal="true"
		>
			<h2 class="text-base font-semibold">{title}</h2>
			{#if description}
				<p class="mt-2 text-sm text-muted-foreground">{description}</p>
			{/if}
			<div class="mt-6 flex justify-end gap-2">
				<Button variant="outline" onclick={() => (open = false)}>{cancelLabel}</Button>
				<Button
					variant={variant === 'destructive' ? 'destructive' : 'default'}
					onclick={async () => {
						await onConfirm();
						open = false;
					}}
				>
					{confirmLabel}
				</Button>
			</div>
		</div>
	</div>
{/if}
