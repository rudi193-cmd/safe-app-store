import { useBoardStore, CATEGORY_COLORS } from '../store/boardStore'

export default function CategoryBar() {
  const { images, categories, currentFilter, setFilter } = useBoardStore()

  const sortedCategories = Object.entries(categories)
    .filter(([_, ids]) => ids.length > 0)
    .sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="flex gap-2 px-6 py-4 flex-wrap border-b border-gray-800 bg-card-bg">
      {/* All button */}
      <button
        onClick={() => setFilter('all')}
        className={`px-4 py-2 rounded-full text-sm transition-all ${
          currentFilter === 'all'
            ? 'bg-accent text-black font-semibold'
            : 'border border-gray-700 text-gray-400 hover:border-accent hover:text-accent'
        }`}
      >
        All <span className="ml-1 opacity-70">{images.length}</span>
      </button>

      {/* Category buttons */}
      {sortedCategories.map(([category, ids]) => (
        <button
          key={category}
          onClick={() => setFilter(category)}
          style={{
            borderColor: currentFilter === category ? CATEGORY_COLORS[category] : undefined,
          }}
          className={`px-4 py-2 rounded-full text-sm transition-all ${
            currentFilter === category
              ? 'font-semibold'
              : 'border border-gray-700 text-gray-400 hover:text-white'
          }`}
        >
          <span
            className="inline-block w-2 h-2 rounded-full mr-2"
            style={{ backgroundColor: CATEGORY_COLORS[category] }}
          />
          {category}
          <span className="ml-1 opacity-70">{ids.length}</span>
        </button>
      ))}
    </div>
  )
}
