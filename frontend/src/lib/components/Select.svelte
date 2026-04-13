<script lang="ts">
	let { value = $bindable(''), options, label = '', class: className = '' }: {
		value?: string;
		options: { value: string; label: string }[];
		label?: string;
		class?: string;
	} = $props();
</script>

<label class="flex flex-col gap-2 {className}">
	{#if label}
		<span class="text-sm font-medium">{label}</span>
	{/if}
	<select
		bind:value
		class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
	>
		{#each options as opt}
			<option value={opt.value}>{opt.label}</option>
		{/each}
	</select>
</label>
