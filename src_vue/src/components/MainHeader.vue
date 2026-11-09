<template>
  <header
    ref="headerRef"
    class="main-header"
    :class="{ 'main-header--organizer': props.currentRoute === '/organizer' }"
  >
    <!-- Lado izquierdo: Solo el botón de toggle sidebar -->
    <div style="display: flex; align-items: center; flex-shrink: 0;">
      <button
        @click="toggleSidebar"
        class="btn btn-sm btn-ghost btn-square"
        :title="sidebarClosed ? 'Mostrar barra' : 'Ocultar barra'"
      >
        <PanelLeftOpen v-if="sidebarClosed" :size="20" />
        <PanelLeftClose v-else :size="20" />
      </button>
    </div>

    <!-- Lado derecho: Toda la navegación (tradicional o hamburguesa) -->
    <div class="main-header-navigation">
      <!-- Menú tradicional (visible cuando width >= 1000px) -->
      <div v-if="!showMobileMenu" style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: nowrap;">
        <!-- Rutas individuales -->
          <button
            v-for="route in individualRoutes"
            :key="route.path"
            @click="navigateTo(route.path)"
            class="btn btn-sm btn-ghost"
            :class="{ 'btn-active': props.currentRoute === route.path }"
          >
          <component :is="route.icon" :size="16" />
          <span>{{ route.label }}</span>
        </button>
        
        <!-- Grupos de menús con dropdown -->
        <div
          v-for="group in menuGroups"
          :key="group.id"
          class="dropdown-container"
          @mouseenter="handleMouseEnter(group.id)"
          @mouseleave="handleMouseLeave(group.id)"
        >
          <button
            :data-dropdown="group.id"
            class="btn btn-sm btn-ghost"
            :class="{ 
              'btn-active': isGroupActive(group),
              'dropdown-open': openDropdown === group.id
            }"
            @click.stop="toggleDropdown(group.id)"
            @mouseenter="handleMouseEnter(group.id)"
          >
            <component :is="group.icon" :size="16" />
            <span>{{ group.label }}</span>
            <ChevronDown :size="14" class="dropdown-chevron" :class="{ 'rotated': openDropdown === group.id }" />
          </button>
          
          <!-- Dropdown menu -->
          <Teleport to="body">
            <div
              v-if="openDropdown === group.id"
              :ref="el => dropdownRefs[group.id] = el as HTMLElement"
              class="dropdown-menu"
              :style="dropdownStyles[group.id] || {}"
              @mouseenter="handleMouseEnter(group.id)"
              @mouseleave="handleMouseLeave(group.id)"
            >
              <button
                v-for="route in group.routes"
                :key="route.path"
                @click="handleDropdownNav(route.path)"
                class="dropdown-item"
                :class="{ 'dropdown-item-active': props.currentRoute === route.path }"
              >
                <component :is="route.icon" :size="16" />
                <span>{{ route.label }}</span>
              </button>
            </div>
          </Teleport>
        </div>
        
        <!-- Opciones (Base de Datos, Settings) -->
        <button
          v-for="route in rightRoutes"
          :key="route.path"
          @click="navigateTo(route.path)"
          class="btn btn-sm btn-ghost"
          :class="{ 'btn-active': props.currentRoute === route.path }"
        >
          <component :is="route.icon" :size="16" />
          <span>{{ route.label }}</span>
        </button>
      </div>

      <!-- Botón hamburguesa (visible cuando width < 1000px) -->
      <div v-else ref="mobileMenuButtonRef" style="position: relative;">
        <button
          @click="toggleMobileMenu"
          class="btn btn-sm btn-ghost btn-square mobile-menu-button"
          :class="{ 'btn-active': mobileMenuOpen }"
          title="Menú de navegación"
        >
          <Menu v-if="!mobileMenuOpen" :size="20" />
          <X v-else :size="20" />
        </button>

        <!-- Menú desplegable (usando Teleport para evitar overflow del header) -->
        <Teleport to="body">
          <div v-if="mobileMenuOpen" ref="mobileMenuDropdownRef" class="mobile-menu-dropdown" :style="mobileMenuStyle">
            <!-- Rutas individuales -->
            <div class="mobile-menu-section">
              <div class="mobile-menu-title">Navegación</div>
              <button
                v-for="route in individualRoutes"
                :key="route.path"
                @click="handleMobileNav(route.path)"
                class="mobile-menu-item"
                :class="{ 'mobile-menu-item-active': currentRoute === route.path }"
              >
                <component :is="route.icon" :size="18" />
                <span>{{ route.label }}</span>
              </button>
            </div>
            
            <!-- Grupos de menús -->
            <div
              v-for="group in menuGroups"
              :key="group.id"
              class="mobile-menu-section"
            >
              <div class="mobile-menu-title">{{ group.label }}</div>
              <button
                v-for="route in group.routes"
                :key="route.path"
                @click="handleMobileNav(route.path)"
                class="mobile-menu-item"
                :class="{ 'mobile-menu-item-active': currentRoute === route.path }"
              >
                <component :is="route.icon" :size="18" />
                <span>{{ route.label }}</span>
              </button>
            </div>
            
            <!-- Opciones -->
            <div class="mobile-menu-section">
              <div class="mobile-menu-title">Opciones</div>
              <button
                v-for="route in rightRoutes"
                :key="route.path"
                @click="handleMobileNav(route.path)"
                class="mobile-menu-item"
                :class="{ 'mobile-menu-item-active': currentRoute === route.path }"
              >
                <component :is="route.icon" :size="18" />
                <span>{{ route.label }}</span>
              </button>
            </div>
          </div>
        </Teleport>
      </div>
    </div>

    <div v-if="props.currentRoute === '/organizer'" class="organizer-header-destination">
      <div class="organizer-header-title">
        <strong>Carpeta ordenada</strong>
        <span>Nueva estructura</span>
      </div>
      <button type="button" class="organizer-header-new-folder" @click="emit('organizerNewFolder')">
        <FolderPlus :size="16" />
        <span>Nueva carpeta</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { 
  PanelLeftOpen, 
  PanelLeftClose, 
  Image as ImageIcon,
  Table as TableIcon,
  FolderTree as FolderTreeIcon,
  Database as DatabaseIcon,
  LayoutDashboard as LayoutDashboardIcon,
  Settings as SettingsIcon,
  FolderPlus,
  Menu,
  X,
  ChevronDown,
} from 'lucide-vue-next'

interface Route {
  path: string
  label: string
  icon: any
}

const props = defineProps<{
  currentRoute?: string
}>()

const emit = defineEmits<{
  toggleSidebar: []
  navigate: [path: string]
  organizerNewFolder: []
}>()

const sidebarClosed = ref(false)
const showMobileMenu = ref(false)
const mobileMenuOpen = ref(false)
const headerRef = ref<HTMLElement | null>(null)
const mobileMenuButtonRef = ref<HTMLElement | null>(null)
const mobileMenuDropdownRef = ref<HTMLElement | null>(null)
const mobileMenuStyle = ref<{ top: string; left?: string; right?: string }>({ top: '0px', left: '0px' })
const BREAKPOINT = 1000 // px
let resizeTimeout: number | null = null

// Estados de dropdowns
const openDropdown = ref<string | null>(null)
const dropdownRefs = ref<Record<string, HTMLElement | null>>({})
const dropdownStyles = ref<Record<string, { top: string; left: string }>>({})
const dropdownOpenByClick = ref<string | null>(null) // Track if opened by click vs hover

interface MenuGroup {
  id: string
  label: string
  icon: any
  routes: Route[]
}

const menuGroups: MenuGroup[] = []

// Rutas individuales (sin agrupar)
const individualRoutes: Route[] = [
  { path: '/images', label: 'Imágenes', icon: ImageIcon },
  { path: '/manage', label: 'Gestión Masiva', icon: TableIcon },
  { path: '/organizer', label: 'Organizar', icon: FolderTreeIcon },
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboardIcon },
]


// Rutas del lado derecho
const rightRoutes: Route[] = [
  { path: '/database', label: 'Base de Datos', icon: DatabaseIcon },
  { path: '/settings', label: 'Settings', icon: SettingsIcon },
]

function toggleSidebar() {
  sidebarClosed.value = !sidebarClosed.value
  const layout = document.getElementById('layout')
  if (layout) {
    layout.classList.toggle('sidebar-closed', sidebarClosed.value)
    localStorage.setItem('sidebar:closed', sidebarClosed.value ? '1' : '0')
  }
  emit('toggleSidebar')
  // Recalcular después de cambiar el sidebar (puede cambiar el ancho disponible)
  nextTick(() => {
    checkBreakpoint()
  })
}

function navigateTo(path: string) {
  emit('navigate', path)
}

function updateMobileMenuPosition() {
  if (!mobileMenuButtonRef.value || !mobileMenuOpen.value) return
  
  nextTick(() => {
    const buttonRect = mobileMenuButtonRef.value!.getBoundingClientRect()
    // Posicionar el menú a la derecha, alineado con el botón
    mobileMenuStyle.value = {
      top: `${buttonRect.bottom + 8}px`,
      right: `${window.innerWidth - buttonRect.right}px`,
      left: 'auto'
    }
  })
}

function toggleMobileMenu() {
  mobileMenuOpen.value = !mobileMenuOpen.value
  if (mobileMenuOpen.value) {
    updateMobileMenuPosition()
    // Actualizar posición al hacer scroll o redimensionar
    window.addEventListener('scroll', updateMobileMenuPosition, true)
    window.addEventListener('resize', updateMobileMenuPosition)
  } else {
    window.removeEventListener('scroll', updateMobileMenuPosition, true)
    window.removeEventListener('resize', updateMobileMenuPosition)
    // No necesitamos recalcular aquí, el breakpoint se maneja automáticamente
  }
}

// Observar cambios en mobileMenuOpen para actualizar posición
watch(mobileMenuOpen, (isOpen) => {
  if (isOpen) {
    updateMobileMenuPosition()
  }
})

// Observar cambios en showMobileMenu para cerrar el menú si se desactiva
watch(showMobileMenu, (shouldShow) => {
  if (!shouldShow && mobileMenuOpen.value) {
    mobileMenuOpen.value = false
  }
})

function handleMobileNav(path: string) {
  navigateTo(path)
  mobileMenuOpen.value = false
}

function isGroupActive(group: MenuGroup): boolean {
  return group.routes.some(route => props.currentRoute === route.path)
}

function toggleDropdown(groupId: string) {
  if (openDropdown.value === groupId) {
    closeDropdownMenu()
    dropdownOpenByClick.value = null
  } else {
    openDropdownMenu(groupId, true) // true = opened by click
  }
}

let mouseLeaveTimeout: number | null = null

function handleMouseEnter(groupId: string) {
  // Cancelar cualquier timeout de cierre pendiente
  if (mouseLeaveTimeout !== null) {
    clearTimeout(mouseLeaveTimeout)
    mouseLeaveTimeout = null
  }
  
  // Si ya está abierto, mantenerlo abierto (no hacer nada)
  if (openDropdown.value === groupId) {
    return
  }
  // Solo abrir por hover si no está abierto por click
  if (dropdownOpenByClick.value !== groupId) {
    openDropdownMenu(groupId, false) // false = opened by hover
  }
}

function handleMouseLeave(groupId: string) {
  // NUNCA cerrar si está abierto por click - solo cerrar por hover
  if (dropdownOpenByClick.value === groupId) {
    return // No cerrar si fue abierto por click
  }
  
  // Solo cerrar si fue abierto por hover, con un pequeño delay
  mouseLeaveTimeout = window.setTimeout(() => {
    // Verificar que realmente no estamos sobre el botón ni el menú
    if (dropdownOpenByClick.value !== groupId && openDropdown.value === groupId) {
      closeDropdownMenu()
    }
    mouseLeaveTimeout = null
  }, 200)
}

function openDropdownMenu(groupId: string, byClick: boolean = false) {
  openDropdown.value = groupId
  if (byClick) {
    dropdownOpenByClick.value = groupId
  }
  nextTick(() => {
    updateDropdownPosition(groupId)
  })
}

function closeDropdownMenu() {
  openDropdown.value = null
  dropdownOpenByClick.value = null
}

function updateDropdownPosition(groupId: string) {
  nextTick(() => {
    const button = document.querySelector(`[data-dropdown="${groupId}"]`) as HTMLElement
    if (!button) return
    
    const rect = button.getBoundingClientRect()
    dropdownStyles.value = {
      ...dropdownStyles.value,
      [groupId]: {
        top: `${rect.bottom + 4}px`,
        left: `${rect.left}px`
      }
    }
  })
}

function handleDropdownNav(path: string) {
  navigateTo(path)
  closeDropdownMenu()
}

function checkBreakpoint() {
  const width = window.innerWidth
  const shouldShowMobile = width < BREAKPOINT
  
  if (shouldShowMobile !== showMobileMenu.value) {
    showMobileMenu.value = shouldShowMobile
    // Si cambiamos a modo normal, cerrar el menú móvil si está abierto
    if (!shouldShowMobile && mobileMenuOpen.value) {
      mobileMenuOpen.value = false
    }
  }
}

function handleWindowResize() {
  if (resizeTimeout !== null) {
    clearTimeout(resizeTimeout)
  }
  resizeTimeout = window.setTimeout(() => {
    checkBreakpoint()
    resizeTimeout = null
  }, 100)
}

onMounted(() => {
  const saved = localStorage.getItem('sidebar:closed') === '1'
  sidebarClosed.value = saved
  const layout = document.getElementById('layout')
  if (layout) {
    layout.classList.toggle('sidebar-closed', saved)
  }
  
  // Verificar el breakpoint inicial
  checkBreakpoint()
  
  // Recalcular cuando cambie el tamaño de la ventana
  window.addEventListener('resize', handleWindowResize)

  // Track mouse position for dropdown logic
  document.addEventListener('mousemove', (e) => {
    (window as any).lastMouseX = e.clientX
    ;(window as any).lastMouseY = e.clientY
  })
  
  // Cerrar menú móvil al hacer clic fuera
  document.addEventListener('click', (e) => {
    if (mobileMenuOpen.value) {
      const target = e.target as Node
      const isClickInsideHeader = headerRef.value?.contains(target)
      const isClickInsideMenu = mobileMenuDropdownRef.value?.contains(target)
      
      if (!isClickInsideHeader && !isClickInsideMenu) {
        mobileMenuOpen.value = false
      }
    }
    
    // Cerrar dropdowns al hacer clic fuera
    if (openDropdown.value) {
      const target = e.target as HTMLElement
      const isClickInDropdown = Object.values(dropdownRefs.value).some(ref => ref?.contains(target))
      const isClickInButton = target.closest('[data-dropdown]')
      
      if (!isClickInDropdown && !isClickInButton) {
        closeDropdownMenu()
      }
    }
  })
  
  // Actualizar posición de dropdowns al hacer scroll o redimensionar
  window.addEventListener('scroll', () => {
    if (openDropdown.value) {
      updateDropdownPosition(openDropdown.value)
    }
  }, true)
  
  window.addEventListener('resize', () => {
    if (openDropdown.value) {
      updateDropdownPosition(openDropdown.value)
    }
  })
})

onUnmounted(() => {
  if (resizeTimeout !== null) {
    clearTimeout(resizeTimeout)
  }
  window.removeEventListener('resize', handleWindowResize)
  window.removeEventListener('scroll', updateMobileMenuPosition, true)
  window.removeEventListener('resize', updateMobileMenuPosition)
})
</script>

<style scoped>
.main-header {
  position: relative;
  justify-content: space-between;
}

.main-header--organizer {
  padding-top: 0;
  padding-bottom: 0;
  overflow-x: hidden;
}

.main-header-navigation {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.organizer-header-destination {
  width: 390px;
  min-width: 310px;
  height: 51px;
  flex: 0 1 390px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 12px 0 18px;
  border-left: 1px solid var(--border-base-300);
  background: rgba(13, 16, 24, 0.7);
}

.organizer-header-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.organizer-header-title strong {
  color: #f1f5f9;
  font-size: 14px;
  line-height: 1.2;
}

.organizer-header-title span {
  color: #8490a5;
  font-size: 10px;
}

.organizer-header-new-folder {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(139, 92, 246, 0.45);
  border-radius: 8px;
  padding: 7px 9px;
  background: rgba(139, 92, 246, 0.13);
  color: #d8b4fe;
  font-size: 11px;
  cursor: pointer;
}

@media (max-width: 1050px) {
  .organizer-header-destination {
    width: 320px;
    min-width: 280px;
    flex-basis: 320px;
  }
}

.mobile-menu-dropdown {
  position: fixed;
  background-color: var(--bg-base-100, #0f1118);
  border: 1px solid var(--border-base-300, #2a3040);
  border-radius: 0.5rem;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2);
  min-width: 240px;
  max-width: 90vw;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  z-index: 9999;
  padding: 0.5rem;
}

.mobile-menu-section {
  margin-bottom: 0.75rem;
}

.mobile-menu-section:last-child {
  margin-bottom: 0;
}

.mobile-menu-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-base-content, #f2f5fb);
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.25rem;
}

.mobile-menu-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 0.375rem;
  color: var(--text-base-content, #f2f5fb);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.mobile-menu-item:hover {
  background-color: rgba(139, 92, 246, 0.14);
}

.mobile-menu-item-active {
  background-color: var(--primary, #8b5cf6);
  color: white;
}

.mobile-menu-item-active:hover {
  background-color: #7c3aed;
}

.nav-container {
  overflow: hidden;
}

/* Asegurar que el botón hamburguesa capture todos los clics */
.mobile-menu-button {
  pointer-events: auto !important;
  cursor: pointer;
}

.mobile-menu-button > * {
  pointer-events: none;
}

@media (max-width: 768px) {
  .mobile-menu-dropdown {
    right: 1rem;
    left: auto !important;
  }
}

/* Dropdown styles */
.dropdown-container {
  position: relative;
  display: inline-block;
}

.dropdown-chevron {
  transition: transform 0.2s;
  margin-left: 0.25rem;
}

.dropdown-chevron.rotated {
  transform: rotate(180deg);
}

.dropdown-menu {
  position: fixed;
  background-color: var(--bg-base-100);
  border: 1px solid var(--border-base-300);
  border-radius: 0.5rem;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2);
  min-width: 200px;
  z-index: 10000;
  padding: 0.5rem;
  margin-top: 2px;
  pointer-events: auto;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  text-align: left;
  background: transparent;
  border: none;
  border-radius: 0.375rem;
  color: var(--text-base-content);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.dropdown-item:hover {
  background-color: var(--bg-base-200);
}

.dropdown-item-active {
  background-color: var(--primary);
  color: white;
}

.dropdown-item-active:hover {
  background-color: var(--primary);
  opacity: 0.9;
}
</style>
