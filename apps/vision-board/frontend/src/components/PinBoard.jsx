import { useState } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useBoardStore, CATEGORY_COLORS } from '../store/boardStore'

function SortableImage({ image }) {
  const { removeFromBoard, updateImageCategory } = useBoardStore()
  const [showCategoryMenu, setShowCategoryMenu] = useState(false)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: image.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const categories = Object.keys(CATEGORY_COLORS)

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="relative bg-card-bg rounded-xl overflow-hidden cursor-grab active:cursor-grabbing group"
      {...attributes}
      {...listeners}
    >
      <img
        src={image.thumbnail}
        alt={image.filename}
        className="w-full h-full object-cover"
        draggable={false}
      />

      {/* Category badge */}
      <span
        className="absolute top-2 left-2 px-2 py-0.5 rounded-full text-xs font-semibold uppercase"
        style={{ backgroundColor: CATEGORY_COLORS[image.category], color: '#000' }}
      >
        {image.category}
      </span>

      {/* Action buttons */}
      <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={(e) => {
            e.stopPropagation()
            setShowCategoryMenu(!showCategoryMenu)
          }}
          onPointerDown={(e) => e.stopPropagation()}
          className="w-6 h-6 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-accent hover:text-black transition-colors"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />
          </svg>
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            removeFromBoard(image.id)
          }}
          onPointerDown={(e) => e.stopPropagation()}
          className="w-6 h-6 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-red-500 transition-colors"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Category menu */}
      {showCategoryMenu && (
        <div
          className="absolute top-8 right-2 bg-card-bg border border-gray-700 rounded-lg shadow-xl z-20 py-1 min-w-[120px]"
          onPointerDown={(e) => e.stopPropagation()}
        >
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => {
                updateImageCategory(image.id, cat)
                setShowCategoryMenu(false)
              }}
              className={`w-full px-3 py-1 text-left text-xs hover:bg-gray-700 flex items-center gap-2 ${
                cat === image.category ? 'text-accent' : 'text-gray-300'
              }`}
            >
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[cat] }} />
              {cat}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function PinBoard() {
  const { boardImages, images, addToBoard } = useBoardStore()
  const [activeId, setActiveId] = useState(null)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const handleDragStart = (event) => {
    setActiveId(event.active.id)
  }

  const handleDragEnd = (event) => {
    setActiveId(null)
    // Reordering would be handled here if we tracked order
  }

  const activeImage = activeId ? boardImages.find(img => img.id === activeId) : null

  // Images not yet on board
  const availableImages = images.filter(
    img => !boardImages.find(b => b.id === img.id)
  )

  return (
    <div className="flex h-full">
      {/* Available images sidebar */}
      <div className="w-64 bg-card-bg border-r border-gray-800 p-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-400 mb-3">Available Images</h3>
        <div className="grid grid-cols-2 gap-2">
          {availableImages.map((image) => (
            <div
              key={image.id}
              className="relative aspect-square bg-gray-800 rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-accent transition-all"
              onClick={() => addToBoard(image.id)}
            >
              <img
                src={image.thumbnail}
                alt={image.filename}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-black/0 hover:bg-black/30 transition-colors flex items-center justify-center">
                <span className="text-white text-2xl opacity-0 hover:opacity-100">+</span>
              </div>
            </div>
          ))}
        </div>
        {availableImages.length === 0 && (
          <p className="text-gray-500 text-sm text-center mt-4">
            All images are on the board
          </p>
        )}
      </div>

      {/* Main pin board */}
      <div className="flex-1 p-6 overflow-auto pb-20">
        {boardImages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-500">
            <div className="text-center">
              <p className="text-lg">Click images from the sidebar to add them to your board</p>
              <p className="text-sm mt-2">Drag to rearrange</p>
            </div>
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={boardImages.map(img => img.id)}
              strategy={rectSortingStrategy}
            >
              <div
                id="board-grid"
                className="grid gap-4"
                style={{
                  gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                  gridAutoRows: '180px',
                }}
              >
                {boardImages.map((image) => (
                  <SortableImage key={image.id} image={image} />
                ))}
              </div>
            </SortableContext>

            <DragOverlay>
              {activeImage ? (
                <div className="bg-card-bg rounded-xl overflow-hidden shadow-2xl opacity-80 w-[180px] h-[180px]">
                  <img
                    src={activeImage.thumbnail}
                    alt={activeImage.filename}
                    className="w-full h-full object-cover"
                  />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>
    </div>
  )
}
