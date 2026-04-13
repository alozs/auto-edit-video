<script lang="ts">
	let { value = 0, class: className = '' }: { value?: number; class?: string } = $props();
</script>

<div class={`relative h-2 w-full overflow-hidden rounded-full bg-secondary ${className}`}>
	<div class="h-full bg-primary transition-all duration-300" style="width: {Math.min(100, Math.max(0, value))}%"></div>
</div>
