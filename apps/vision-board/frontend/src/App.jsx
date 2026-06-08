import { useEffect, useState } from 'react'
import { useBoardStore } from './store/boardStore'
import Header from './components/Header'
import CategoryBar from './components/CategoryBar'
import DropZone from './components/DropZone'
import ImageGallery from './components/ImageGallery'
import PinBoard from './components/PinBoard'
import StatusBar from './components/StatusBar'
import { loadModel } from './lib/classifier'
import { checkBackend } from './lib/api'

function App() {
  const [view, setView] = useState('gallery') // 'gallery' | 'board'
  const [model, setModel] = useState(null)
  const [backendStatus, setBackendStatus] = useState({ available: false, ollamaAvailable: false })
  const { setModelStatus, loadImages } = useBoardStore()

  useEffect(() => {
    async function init() {
      // Load saved images first
      loadImages()

      // Check backend availability
      setModelStatus('loading')
      const backend = await checkBackend()
      setBackendStatus(backend)

      if (backend.ollamaAvailable) {
        // Backend with Ollama vision is ready
        console.log('Using Ollama vision:', backend.visionModel)
        setModelStatus('ready')
        return
      }

      // Fall back to TensorFlow.js
      console.log('Backend not available, loading TensorFlow.js...')
      try {
        const loadedModel = await loadModel()
        setModel(loadedModel)
        setModelStatus('ready')
      } catch (err) {
        console.error('TensorFlow model load failed:', err)
        setModelStatus('error')
      }
    }

    init()
  }, [])

  return (
    <div className="min-h-screen bg-board-bg flex flex-col">
      <Header view={view} setView={setView} />
      <CategoryBar />

      <main className="flex-1 overflow-hidden">
        {view === 'gallery' ? (
          <>
            <DropZone model={model} useBackend={backendStatus.ollamaAvailable} />
            <ImageGallery />
          </>
        ) : (
          <PinBoard />
        )}
      </main>

      <StatusBar />
    </div>
  )
}

export default App
