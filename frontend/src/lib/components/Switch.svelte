<script lang="ts">
	let { checked = $bindable(false), label = '', description = '' }: {
		checked?: boolean;
		label?: string;
		description?: string;
	} = $props();
</script>

<label class="flex items-start gap-3 cursor-pointer">
	<button
		type="button"
		role="switch"
		aria-checked={checked}
		onclick={() => (checked = !checked)}
		class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring {checked ? 'bg-primary' : 'bg-input'}"
	>
		<span
			class="pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform {checked ? 'translate-x-5' : 'translate-x-0'}"
		></span>
	</button>
	<div class="flex flex-col gap-0.5">
		<span class="text-sm font-medium leading-none">{label}</span>
		{#if description}
			<span class="text-xs text-muted-foreground">{description}</span>
		{/if}
	</div>
</label>
