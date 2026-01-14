<template>
  <Tooltip :text="text">
    <span class="help-dot">?</span>
  </Tooltip>
</template>

<script setup lang="ts">
import Tooltip from './Tooltip.vue'

defineProps<{
  text: string
}>()
</script>
