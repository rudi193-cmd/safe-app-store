import { useState } from 'react'
import { useBoardStore, CATEGORY_COLORS } from '../store/boardStore'

export default function ImageCard({ image, size = 'normal', onBoard = false }) {
  const [showModal, setShowModal] = useState(false)
  const [showCategoryMenu, setShowCategoryMenu] = useState(false)
  const { removeImage, addToBoard, removeFromBoard, updateImageCategory } = useBoardStore()

  const sizeClasses = {
    large: 'col-span-2 row-span-2',
    medium: 'col-span-2',
    normal: '',
  }

  const categories = Object.keys(CATEGORY_COLORS)

  const handleCategoryChange = (newCategory) => {
    updateImageCategory(image.id, newCategory)
    setShowCategoryMenu(false)
  }

  return (
    <>
      <div
        className={`
          relative bg-card-bg rounded-xl overflow-hidden cursor-pointer
          border-2 border-transparent hover:border-accent
          transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl hover:z-10
          group ${sizeClasses[size]}
        `}
        onClick={() => setShowModal(true)}
      >
        <img
          src={image.thumbnail}
          alt={image.filename}
          className="w-full h-full object-cover transition-opacity group-hover:opacity-40"
          loading="lazy"
        />

        {/* Category badge */}
        <span
          className="absolute top-2 left-2 px-2.5 py-1 rounded-full text-xs font-semibold uppercase tracking-wide"
          style={{ backgroundColor: CATEGORY_COLORS[image.category], color: '#000' }}
        >
          {image.category}
        </span>

        {/* Overlay on hover */}
        <div className="absolute inset-0 p-4 flex flex-col justify-end opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-t from-black/80 via-transparent to-transparent">
          <p className="text-sm text-gray-300">{image.label}</p>
          <p className="text-xs text-gray-500">{image.confidence}% confidence</p>
        </div>

        {/* Action buttons */}
        <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Change category */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              setShowCategoryMenu(!showCategoryMenu)
            }}
            className="w-7 h-7 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-accent hover:text-black transition-colors"
            title="Change category"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />
            </svg>
          </button>

          {/* Add/Remove from board */}
          {!onBoard ? (
            <button
              onClick={(e) => {
                e.stopPropagation()
                addToBoard(image.id, { x: 50, y: 50 })
              }}
              className="w-7 h-7 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-accent hover:text-black transition-colors"
              title="Add to board"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation()
                removeFromBoard(image.id)
              }}
              className="w-7 h-7 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-red-500 transition-colors"
              title="Remove from board"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
              </svg>
            </button>
          )}

          {/* Delete */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              removeImage(image.id)
            }}
            className="w-7 h-7 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-red-500 transition-colors"
            title="Delete"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Category dropdown */}
        {showCategoryMenu && (
          <div
            className="absolute top-10 right-2 bg-card-bg border border-gray-700 rounded-lg shadow-xl z-20 py-1 min-w-[140px]"
            onClick={(e) => e.stopPropagation()}
          >
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => handleCategoryChange(cat)}
                className={`w-full px-3 py-1.5 text-left text-sm hover:bg-gray-700 flex items-center gap-2 ${
                  cat === image.category ? 'text-accent' : 'text-gray-300'
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: CATEGORY_COLORS[cat] }}
                />
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Full image modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center"
          onClick={() => setShowModal(false)}
        >
          <button
            className="absolute top-6 right-8 text-4xl text-white/70 hover:text-white"
            onClick={() => setShowModal(false)}
          >
            &times;
          </button>
          <img
            src={image.fullImage || image.thumbnail}
            alt={image.filename}
            className="max-w-[90vw] max-h-[90vh] rounded-lg"
          />
        </div>
      )}
    </>
  )
}
