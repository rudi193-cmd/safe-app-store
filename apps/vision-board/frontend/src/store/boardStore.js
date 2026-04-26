import { create } from 'zustand'
import { openDB } from 'idb'

const DB_NAME = 'VisionBoardDB'
const DB_VERSION = 3
const STORE_NAME = 'images'
const BOARDS_STORE = 'boards'

// Initialize IndexedDB
async function getDB() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(BOARDS_STORE)) {
        db.createObjectStore(BOARDS_STORE, { keyPath: 'id' })
      }
    },
  })
}

// Category colors mapping
export const CATEGORY_COLORS = {
  Personal: '#ff6b9d',
  Travel: '#00d2ff',
  Career: '#00ff9d',
  Wealth: '#ffd700',
  Fitness: '#ff6b35',
  Creative: '#bd00ff',
  Home: '#7dd87d',
  Food: '#ffb347',
  Relationships: '#ff69b4',
  Inspiration: '#666666',
}

export const useBoardStore = create((set, get) => ({
  // State
  images: [],
  boardImages: [], // Images placed on the pin board
  categories: {},
  currentFilter: 'all',
  isProcessing: false,
  processProgress: 0,
  modelStatus: 'loading', // loading | ready | error

  // Actions
  setModelStatus: (status) => set({ modelStatus: status }),

  setFilter: (filter) => set({ currentFilter: filter }),

  setProcessing: (isProcessing, progress = 0) => set({
    isProcessing,
    processProgress: progress
  }),

  addImage: (image) => set((state) => {
    const newImages = [...state.images, image]
    const newCategories = { ...state.categories }

    if (!newCategories[image.category]) {
      newCategories[image.category] = []
    }
    newCategories[image.category].push(image.id)

    return { images: newImages, categories: newCategories }
  }),

  removeImage: async (id) => {
    const state = get()
    const image = state.images.find(img => img.id === id)
    if (!image) return

    const newImages = state.images.filter(img => img.id !== id)
    const newBoardImages = state.boardImages.filter(img => img.id !== id)
    const newCategories = { ...state.categories }

    if (newCategories[image.category]) {
      newCategories[image.category] = newCategories[image.category].filter(imgId => imgId !== id)
      if (newCategories[image.category].length === 0) {
        delete newCategories[image.category]
      }
    }

    set({ images: newImages, boardImages: newBoardImages, categories: newCategories })

    // Persist
    const db = await getDB()
    await db.delete(STORE_NAME, id)
  },

  addToBoard: (imageId, position) => set((state) => {
    const image = state.images.find(img => img.id === imageId)
    if (!image) return state

    // Check if already on board
    if (state.boardImages.find(img => img.id === imageId)) {
      return state
    }

    const boardImage = {
      ...image,
      position: position || { x: 0, y: 0 },
      size: { width: 200, height: 200 },
    }

    return { boardImages: [...state.boardImages, boardImage] }
  }),

  removeFromBoard: (imageId) => set((state) => ({
    boardImages: state.boardImages.filter(img => img.id !== imageId)
  })),

  updateBoardImagePosition: (imageId, position) => set((state) => ({
    boardImages: state.boardImages.map(img =>
      img.id === imageId ? { ...img, position } : img
    )
  })),

  updateBoardImageSize: (imageId, size) => set((state) => ({
    boardImages: state.boardImages.map(img =>
      img.id === imageId ? { ...img, size } : img
    )
  })),

  updateImageCategory: async (imageId, newCategory) => {
    const state = get()
    const image = state.images.find(img => img.id === imageId)
    if (!image) return

    const oldCategory = image.category
    const newCategories = { ...state.categories }

    // Remove from old category
    if (newCategories[oldCategory]) {
      newCategories[oldCategory] = newCategories[oldCategory].filter(id => id !== imageId)
      if (newCategories[oldCategory].length === 0) {
        delete newCategories[oldCategory]
      }
    }

    // Add to new category
    if (!newCategories[newCategory]) {
      newCategories[newCategory] = []
    }
    newCategories[newCategory].push(imageId)

    // Update image
    const newImages = state.images.map(img =>
      img.id === imageId ? { ...img, category: newCategory } : img
    )

    set({ images: newImages, categories: newCategories })

    // Persist
    const db = await getDB()
    const updatedImage = newImages.find(img => img.id === imageId)
    await db.put(STORE_NAME, updatedImage)
  },

  // Persistence
  saveImages: async () => {
    const db = await getDB()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)

    await store.clear()
    for (const img of get().images) {
      await store.put(img)
    }

    await tx.done
  },

  loadImages: async () => {
    try {
      const db = await getDB()
      const images = await db.getAll(STORE_NAME)

      const categories = {}
      for (const img of images) {
        if (!categories[img.category]) {
          categories[img.category] = []
        }
        categories[img.category].push(img.id)
      }

      set({ images, categories })
    } catch (err) {
      console.error('Failed to load images:', err)
    }
  },

  clearAll: async () => {
    const db = await getDB()
    await db.clear(STORE_NAME)
    set({ images: [], boardImages: [], categories: {} })
  },

  // Filtered images getter
  getFilteredImages: () => {
    const state = get()
    if (state.currentFilter === 'all') {
      return state.images
    }
    return state.images.filter(img => img.category === state.currentFilter)
  },
}))
