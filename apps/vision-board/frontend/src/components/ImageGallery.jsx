import { useBoardStore, CATEGORY_COLORS } from '../store/boardStore'
import ImageCard from './ImageCard'

export default function ImageGallery() {
  const { images, currentFilter, getFilteredImages } = useBoardStore()

  const filteredImages = currentFilter === 'all'
    ? images
    : images.filter(img => img.category === currentFilter)

  if (filteredImages.length === 0) {
    return null
  }

  // Determine which images should be large/medium
  const total = filteredImages.length
  const largeCount = Math.max(1, Math.floor(total * 0.05))
  const mediumCount = Math.max(2, Math.floor(total * 0.1))

  return (
    <div
      id="image-gallery"
      className="grid gap-4 p-6 pb-20"
      style={{
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gridAutoRows: '200px',
        gridAutoFlow: 'dense',
      }}
    >
      {filteredImages.map((image, index) => {
        let size = 'normal'
        if (index < largeCount) size = 'large'
        else if (index < largeCount + mediumCount) size = 'medium'

        return (
          <ImageCard
            key={image.id}
            image={image}
            size={size}
          />
        )
      })}
    </div>
  )
}
