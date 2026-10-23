import { create } from 'zustand'

interface AppState {
  selectedDatasetId: string | null
  selectDataset: (dataset_id: string | null) => void
  railCollapsed: boolean
  toggleRail: () => void
  railOpen: boolean
  setRailOpen: (open: boolean) => void
}

/** 只放 UI 状态：服务端数据一律交给 TanStack Query（§2.1）。 */
export const useAppStore = create<AppState>((set) => ({
  selectedDatasetId: null,
  selectDataset: (dataset_id) => set({ selectedDatasetId: dataset_id }),
  railCollapsed: false,
  toggleRail: () => set((state) => ({ railCollapsed: !state.railCollapsed })),
  railOpen: false,
  setRailOpen: (railOpen) => set({ railOpen }),
}))
