import { useBoardStore } from '../store/boardStore'

export default function Header({ view, setView }) {
  const { modelStatus, images, clearAll } = useBoardStore()

  const statusColors = {
    loading: 'text-yellow-400',
    ready: 'text-green-400',
    error: 'text-red-400',
  }

  const statusText = {
    loading: 'Loading AI...',
    ready: 'AI Ready',
    error: 'AI Failed',
  }

  const handleExport = async () => {
    // Dynamic import html2canvas only when needed
    const html2canvas = (await import('html2canvas')).default
    const grid = document.getElementById('board-grid') || document.getElementById('image-gallery')
    if (!grid) return

    const canvas = await html2canvas(grid, {
      backgroundColor: '#0a0a0a',
      scale: 2,
    })

    const link = document.createElement('a')
    link.download = `vision-board-${Date.now()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }

  const handleClear = () => {
    if (confirm('Clear all images from the board?')) {
      clearAll()
    }
  }

  return (
    <header className="flex justify-between items-center px-6 py-4 border-b border-gray-800 bg-gradient-to-b from-card-bg to-board-bg">
      <h1 className="text-2xl font-light tracking-wider">
        VISION <span className="text-accent">BOARD</span>
      </h1>

      <div className="flex items-center gap-4">
        {/* View Toggle */}
        <div className="flex bg-gray-800 rounded-lg p-1">
          <button
            onClick={() => setView('gallery')}
            className={`px-4 py-1.5 rounded-md text-sm transition-colors ${
              view === 'gallery'
                ? 'bg-accent text-black font-semibold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Gallery
          </button>
          <button
            onClick={() => setView('board')}
            className={`px-4 py-1.5 rounded-md text-sm transition-colors ${
              view === 'board'
                ? 'bg-accent text-black font-semibold'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Pin Board
          </button>
        </div>

        {/* Model Status */}
        <span className={`text-sm px-3 py-1.5 rounded-full bg-gray-800 ${statusColors[modelStatus]}`}>
          {statusText[modelStatus]}
        </span>

        {/* Actions */}
        <button
          onClick={handleClear}
          disabled={images.length === 0}
          className="px-4 py-2 border border-gray-700 rounded-md text-sm hover:border-accent hover:text-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Clear
        </button>
        <button
          onClick={handleExport}
          disabled={images.length === 0}
          className="px-4 py-2 bg-accent text-black rounded-md text-sm font-semibold hover:bg-yellow-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Export PNG
        </button>
      </div>
    </header>
  )
}
