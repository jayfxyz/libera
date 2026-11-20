<script setup lang="ts" generic="T extends string">
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '.'
import type { SelectOption } from './types'

/** The app's dropdown for picking one value: a trigger plus a panel of options. */
defineProps<{ options: SelectOption<T>[], variant?: 'box' | 'inline', ariaLabel?: string, disabled?: boolean }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <Select v-model="model" :disabled="disabled">
    <SelectTrigger :variant="variant ?? 'box'" :aria-label="ariaLabel">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</SelectItem>
    </SelectContent>
  </Select>
</template>
