/**
 * Store para gestionar paneles laterales de forma centralizada
 */
import { ref } from 'vue'

export type PanelType = 'image-details' | null

interface PanelState {
  type: PanelType
  data: any
}

const currentPanel = ref<PanelState>({
  type: null,
  data: null
})

export function usePanelStore() {
  const openPanel = (type: PanelType, data: any = null) => {
    currentPanel.value = { type, data }
  }

  const closePanel = () => {
    currentPanel.value = { type: null, data: null }
  }

  const isOpen = (type: PanelType) => {
    return currentPanel.value.type === type
  }

  const getCurrentPanel = () => {
    return currentPanel.value
  }

  return {
    currentPanel,
    openPanel,
    closePanel,
    isOpen,
    getCurrentPanel
  }
}

