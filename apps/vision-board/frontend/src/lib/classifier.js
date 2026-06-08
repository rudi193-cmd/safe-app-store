import * as mobilenet from '@tensorflow-models/mobilenet'

// Category mapping from MobileNet labels
const CATEGORY_MAP = {
  // Personal / Life
  'tabby': 'Personal', 'persian cat': 'Personal', 'siamese cat': 'Personal',
  'egyptian cat': 'Personal', 'tiger cat': 'Personal',
  'golden retriever': 'Personal', 'labrador retriever': 'Personal',
  'german shepherd': 'Personal', 'beagle': 'Personal', 'pug': 'Personal',
  'chihuahua': 'Personal', 'poodle': 'Personal', 'husky': 'Personal',

  // Nature / Travel
  'beach': 'Travel', 'seashore': 'Travel', 'lakeside': 'Travel', 'lakeshore': 'Travel',
  'mountain': 'Travel', 'alp': 'Travel', 'volcano': 'Travel', 'valley': 'Travel',
  'coral reef': 'Travel', 'cliff': 'Travel', 'promontory': 'Travel',
  'palace': 'Travel', 'castle': 'Travel', 'monastery': 'Travel',
  'church': 'Travel', 'mosque': 'Travel', 'temple': 'Travel',
  'fountain': 'Travel', 'pier': 'Travel', 'dock': 'Travel',
  'suspension bridge': 'Travel', 'viaduct': 'Travel',
  'gondola': 'Travel', 'streetcar': 'Travel',

  // Home / Lifestyle
  'dining table': 'Home', 'desk': 'Home', 'bookcase': 'Home', 'bookshop': 'Home',
  'couch': 'Home', 'studio couch': 'Home', 'chair': 'Home', 'rocking chair': 'Home',
  'lamp': 'Home', 'table lamp': 'Home', 'lampshade': 'Home',
  'refrigerator': 'Home', 'washer': 'Home', 'dishwasher': 'Home',
  'patio': 'Home', 'greenhouse': 'Home', 'flower pot': 'Home',
  'window shade': 'Home', 'window screen': 'Home',
  'shower curtain': 'Home', 'bath towel': 'Home',

  // Food
  'pizza': 'Food', 'cheeseburger': 'Food', 'hotdog': 'Food',
  'ice cream': 'Food', 'ice lolly': 'Food', 'trifle': 'Food',
  'chocolate sauce': 'Food', 'espresso': 'Food', 'cup': 'Food',
  'wine bottle': 'Food', 'beer bottle': 'Food', 'beer glass': 'Food',
  'plate': 'Food', 'soup bowl': 'Food', 'mixing bowl': 'Food',
  'banana': 'Food', 'orange': 'Food', 'lemon': 'Food', 'pineapple': 'Food',
  'broccoli': 'Food', 'cauliflower': 'Food', 'cucumber': 'Food',
  'burrito': 'Food', 'guacamole': 'Food',

  // Fitness / Health
  'dumbbell': 'Fitness', 'barbell': 'Fitness',
  'running shoe': 'Fitness', 'athletic shoe': 'Fitness',
  'bicycle': 'Fitness', 'mountain bike': 'Fitness',
  'punching bag': 'Fitness', 'swimming trunks': 'Fitness',
  'ski': 'Fitness', 'snowboard': 'Fitness',
  'tennis ball': 'Fitness', 'golf ball': 'Fitness', 'soccer ball': 'Fitness',
  'basketball': 'Fitness', 'volleyball': 'Fitness',

  // Career / Professional
  'laptop': 'Career', 'notebook': 'Career', 'desktop computer': 'Career',
  'computer keyboard': 'Career', 'mouse': 'Career', 'computer mouse': 'Career',
  'monitor': 'Career', 'screen': 'Career',
  'suit': 'Career', 'Windsor tie': 'Career', 'bow tie': 'Career',
  'briefcase': 'Career', 'envelope': 'Career',
  'printer': 'Career', 'photocopier': 'Career',
  'projector': 'Career', 'slide rule': 'Career',

  // Finance / Wealth
  'sports car': 'Wealth', 'convertible': 'Wealth', 'limousine': 'Wealth',
  'minivan': 'Wealth', 'cab': 'Wealth',
  'yacht': 'Wealth', 'speedboat': 'Wealth', 'catamaran': 'Wealth',
  'airliner': 'Wealth', 'warplane': 'Wealth',
  'chain': 'Wealth', 'necklace': 'Wealth',

  // Creative / Art
  'paintbrush': 'Creative', 'easel': 'Creative', 'palette': 'Creative',
  'guitar': 'Creative', 'acoustic guitar': 'Creative', 'electric guitar': 'Creative',
  'piano': 'Creative', 'grand piano': 'Creative', 'upright piano': 'Creative',
  'violin': 'Creative', 'cello': 'Creative', 'flute': 'Creative',
  'drum': 'Creative', 'maraca': 'Creative', 'harmonica': 'Creative',
  'camera': 'Creative', 'reflex camera': 'Creative', 'Polaroid camera': 'Creative',
  'tripod': 'Creative', 'microphone': 'Creative', 'stage': 'Creative',

  // Relationships / Social
  'groom': 'Relationships', 'bridegroom': 'Relationships',
  'bow': 'Relationships', 'bouquet': 'Relationships',
  'wine glass': 'Relationships', 'goblet': 'Relationships',
}

const DEFAULT_CATEGORY = 'Inspiration'

let cachedModel = null

export async function loadModel() {
  if (cachedModel) return cachedModel
  cachedModel = await mobilenet.load({ version: 2, alpha: 1.0 })
  return cachedModel
}

export function mapToCategory(predictions) {
  for (const pred of predictions) {
    const label = pred.className.toLowerCase()

    for (const [key, category] of Object.entries(CATEGORY_MAP)) {
      if (label.includes(key.toLowerCase())) {
        return {
          label: pred.className,
          confidence: pred.probability,
          category: category
        }
      }
    }
  }

  return {
    label: predictions[0]?.className || 'unknown',
    confidence: predictions[0]?.probability || 0,
    category: DEFAULT_CATEGORY
  }
}

export async function classifyImage(model, imageElement) {
  const predictions = await model.classify(imageElement)
  return mapToCategory(predictions)
}

export function generateId() {
  return 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
}

export function createThumbnail(img, maxDim = 400) {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas')
    let width = img.width
    let height = img.height

    if (width > height) {
      if (width > maxDim) {
        height = Math.round(height * maxDim / width)
        width = maxDim
      }
    } else {
      if (height > maxDim) {
        width = Math.round(width * maxDim / height)
        height = maxDim
      }
    }

    canvas.width = width
    canvas.height = height

    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(img, 0, 0, width, height)

    resolve(canvas.toDataURL('image/jpeg', 0.85))
  })
}

export function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => resolve({ img, dataUrl: reader.result })
      img.onerror = reject
      img.src = reader.result
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
