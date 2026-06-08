import { useState, useCallback } from 'react'
import { useBoardStore } from '../store/boardStore'
import { classifyImage, generateId, createThumbnail, loadImageFromFile } from '../lib/classifier'
import { classifyImageBackend } from '../lib/api'

export default function DropZone({ model, useBackend = false }) {
  const [isDragging, setIsDragging] = useState(false)
  const { images, addImage, setProcessing, saveImages, isProcessing, processProgress } = useBoardStore()

  const isCollapsed = images.length > 0
  const isReady = useBackend || model

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  /**
   * Extract base64 data from a data URL.
   */
  const extractBase64 = (dataUrl) => {
    const match = dataUrl.match(/^data:image\/\w+;base64,(.+)$/)
    return match ? match[1] : dataUrl
  }

  /**
   * Classify using backend (Ollama vision).
   */
  const classifyWithBackend = async (dataUrl, filename) => {
    const base64Data = extractBase64(dataUrl)
    const result = await classifyImageBackend(base64Data, filename)
    return {
      label: result.label,
      confidence: result.confidence / 100, // Backend returns 0-100, normalize to 0-1
      category: result.category,
    }
  }

  /**
   * Classify using TensorFlow.js (local).
   */
  const classifyWithTensorFlow = async (img) => {
    return classifyImage(model, img)
  }

  const processFiles = async (files) => {
    if (!isReady) {
      alert('AI model not ready yet')
      return
    }

    const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
    if (imageFiles.length === 0) return

    setProcessing(true, 0)

    for (let i = 0; i < imageFiles.length; i++) {
      try {
        const file = imageFiles[i]
        const { img, dataUrl } = await loadImageFromFile(file)

        // Classify based on available backend
        let classification
        if (useBackend) {
          classification = await classifyWithBackend(dataUrl, file.name)
        } else {
          classification = await classifyWithTensorFlow(img)
        }

        const { label, confidence, category } = classification
        const thumbnail = await createThumbnail(img)

        const record = {
          id: generateId(),
          filename: file.name,
          thumbnail,
          fullImage: dataUrl,
          label,
          confidence: Math.round(confidence * 100),
          category,
          addedAt: new Date().toISOString(),
          classifiedBy: useBackend ? 'ollama' : 'tensorflow',
        }

        addImage(record)
      } catch (err) {
        console.error('Error processing', files[i]?.name, err)
      }

      setProcessing(true, Math.round(((i + 1) / imageFiles.length) * 100))
    }

    setProcessing(false, 0)
    await saveImages()
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    const files = e.dataTransfer.files
    processFiles(files)
  }, [useBackend, model])

  const handleFileSelect = useCallback((e) => {
    const files = e.target.files
    processFiles(files)
    e.target.value = ''
  }, [useBackend, model])

  // Folder selection
  const handleFolderSelect = useCallback((e) => {
    const files = e.target.files
    processFiles(files)
    e.target.value = ''
  }, [useBackend, model])

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        mx-6 my-4 border-2 border-dashed rounded-xl transition-all cursor-pointer
        ${isCollapsed ? 'py-4' : 'py-16'}
        ${isDragging ? 'border-accent bg-accent/5' : 'border-gray-700 hover:border-gray-500'}
        ${isProcessing ? 'animate-pulse-border' : ''}
      `}
      onClick={() => document.getElementById('file-input').click()}
    >
      <div className="text-center">
        <h2 className={`font-light ${isCollapsed ? 'text-base' : 'text-xl'}`}>
          {isProcessing ? `Processing... ${processProgress}%` : 'Drop images here'}
        </h2>
        {!isCollapsed && (
          <>
            <p className="text-gray-500 mt-2">or click to browse</p>
            <p className="text-xs text-gray-600 mt-1">
              Using: {useBackend ? '🦙 Ollama Vision' : '🧠 TensorFlow.js'}
            </p>
          </>
        )}

        {/* Progress bar */}
        {isProcessing && (
          <div className="max-w-md mx-auto mt-4 h-1 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${processProgress}%` }}
            />
          </div>
        )}
      </div>

      {/* Hidden file inputs */}
      <input
        type="file"
        id="file-input"
        className="hidden"
        multiple
        accept="image/*"
        onChange={handleFileSelect}
      />

      {/* Folder input option */}
      {!isCollapsed && (
        <div className="mt-4 text-center">
          <label className="text-sm text-gray-500 cursor-pointer hover:text-accent transition-colors">
            <input
              type="file"
              className="hidden"
              webkitdirectory=""
              directory=""
              multiple
              onChange={handleFolderSelect}
            />
            or select a folder
          </label>
        </div>
      )}
    </div>
  )
}
