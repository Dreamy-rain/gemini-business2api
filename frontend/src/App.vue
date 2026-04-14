<template>
  <RouterView />
  <Toast :toasts="toastState.toasts" @remove="removeToast" />
</template>

<script setup lang="ts">
import { Toast } from 'nanocat-ui'
import { RouterView } from 'vue-router'
import { removeToast, toastState } from '@/composables/useToast'
</script>
