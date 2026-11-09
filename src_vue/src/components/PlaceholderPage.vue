<template>
  <div class="placeholder-page">
    <div class="placeholder-content">
      <div class="placeholder-icon">🚧</div>
      <h2>{{ title }}</h2>
      <p>Esta sección está en desarrollo.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style scoped>
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
}

.placeholder-content {
  text-align: center;
  opacity: 0.7;
}

.placeholder-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.placeholder-content h2 {
  font-size: 1.5rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.placeholder-content p {
  font-size: 1rem;
  opacity: 0.7;
}
</style>

