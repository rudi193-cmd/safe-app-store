import { useBoardStore } from '../store/boardStore'

export default function StatusBar() {
  const { images, isProcessing, processProgress } = useBoardStore()

  let statusText = images.length > 0
    ? `${images.length} images categorized`
    : 'Drop images to begin'

  if (isProcessing) {
    statusText = `Processing... ${processProgress}%`
  }

  return (
    <footer className="fixed bottom-0 left-0 right-0 px-6 py-3 bg-card-bg border-t border-gray-800 flex justify-between text-sm text-gray-500">
      <span>{statusText}</span>
      <span>96% you, 4% cloud</span>
    </footer>
  )
}
