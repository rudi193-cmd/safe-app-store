/**
 * Backend API client for Vision Board
 *
 * Handles communication with FastAPI backend.
 * Falls back gracefully if backend unavailable.
 */

const API_BASE = '/api'

let backendAvailable = null
let visionModel = null

/**
 * Check if backend is available and has vision capability.
 */
export async function checkBackend() {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    })

    if (!response.ok) {
      backendAvailable = false
      return { available: false, ollamaAvailable: false }
    }

    const data = await response.json()
    backendAvailable = data.ollama_available
    visionModel = data.vision_model

    return {
      available: true,
      ollamaAvailable: data.ollama_available,
      visionModel: data.vision_model,
    }
  } catch (err) {
    console.log('Backend not available:', err.message)
    backendAvailable = false
    return { available: false, ollamaAvailable: false }
  }
}

/**
 * Check cached backend status.
 */
export function isBackendAvailable() {
  return backendAvailable === true
}

/**
 * Get the active vision model name.
 */
export function getVisionModel() {
  return visionModel
}

/**
 * Classify an image using the backend.
 *
 * @param {string} base64Data - Base64-encoded image (without data URL prefix)
 * @param {string} filename - Original filename
 * @returns {Promise<{category: string, label: string, confidence: number, description?: string}>}
 */
export async function classifyImageBackend(base64Data, filename) {
  const response = await fetch(`${API_BASE}/classify`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      image_base64: base64Data,
      filename: filename,
    }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Classification failed')
  }

  return response.json()
}

/**
 * Upload and classify a file directly.
 *
 * @param {File} file - Image file
 * @returns {Promise<{category: string, label: string, confidence: number}>}
 */
export async function classifyFileBackend(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/classify/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Classification failed')
  }

  return response.json()
}

/**
 * Classify multiple files in batch.
 *
 * @param {File[]} files - Array of image files
 * @returns {Promise<{results: Array, total: number}>}
 */
export async function classifyBatchBackend(files) {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))

  const response = await fetch(`${API_BASE}/classify/batch`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Batch classification failed')
  }

  return response.json()
}

/**
 * Get available categories from backend.
 */
export async function getCategories() {
  const response = await fetch(`${API_BASE}/categories`)

  if (!response.ok) {
    throw new Error('Failed to fetch categories')
  }

  return response.json()
}
