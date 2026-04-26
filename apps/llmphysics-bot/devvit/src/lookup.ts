// Version: 0.7.24
import { logger } from './logger';

export interface LookupSummary {
  title: string;
  extract: string;
  content_urls: { desktop: { page: string } };
}

const EXCLUSION_KEYWORDS: string[] = [
  'births', 'deaths', 'living people', 'people from', 'politicians',
  'actors', 'actresses', 'musicians', 'singers', 'athletes', 'sportspeople',
  'businesspeople', 'military personnel',
  'cities', 'countries', 'municipalities', 'populated places', 'villages',
  'towns', 'districts', 'provinces', 'states of ', 'counties',
  'films', 'television', 'albums', 'songs', 'video games', 'comics',
  'anime', 'manga', 'novels', 'books by', 'fictional',
  'football', 'basketball', 'baseball', 'soccer', 'olympic', 'cricket',
  'tennis', 'golf', 'racing', 'wrestling',
  'companies', 'brands', 'organizations', 'record labels', 'newspapers',
  'founded in',
];

function isExcluded(categories: string[]): boolean {
  if (categories.length === 0) return false;
  const match = categories.find((cat) => {
    const c = cat.toLowerCase();
    return EXCLUSION_KEYWORDS.some((key) => c.includes(key));
  });
  
  if (match) logger.info('Lookup', `Exclusion triggered: "${match}"`);
  return !!match;
}

async function fetchSummary(term: string): Promise<LookupSummary | null> {
  const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as LookupSummary;
  } catch (err) {
    logger.error('Lookup', 'FetchSummary failed', err);
    return null;
  }
}

async function fetchCategories(title: string): Promise<string[]> {
  const url = `https://en.wikipedia.org/w/api.php?action=query&prop=categories&titles=${encodeURIComponent(title)}&format=json&clshow=!hidden`;
  try {
    const res = await fetch(url);
    const data = (await res.json()) as any;
    const pages = data.query?.pages || {};
    const page = Object.values(pages)[0] as any;
    const cats = (page.categories || []).map((c: any) => c.title.replace(/^Category:/, ''));
    logger.info('Lookup', `Categories for "${title}": ${cats.slice(0, 3).join(', ')}...`);
    return cats;
  } catch (err) {
    logger.error('Lookup', 'FetchCategories failed', err);
    return [];
  }
}

async function fetchDisambiguated(term: string): Promise<string | null> {
  const query = `${term} (physics)`;
  const url = `https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(query)}&format=json&srlimit=1`;
  try {
    const res = await fetch(url);
    const data = (await res.json()) as any;
    const result = data.query?.search?.[0]?.title || null;
    if (result) logger.info('Lookup', `Disambiguated "${term}" to "${result}"`);
    return result;
  } catch (err) {
    logger.error('Lookup', 'FetchDisambiguated failed', err);
    return null;
  }
}

export interface LookupResult {
  summary: LookupSummary;
  categories: string[];
}

export async function lookupTerm(term: string): Promise<LookupResult | null> {
  logger.info('Lookup', `Searching: "${term}"`);
  
  const direct = await fetchSummary(term);
  if (direct) {
    const cats = await fetchCategories(direct.title);
    if (!isExcluded(cats)) return { summary: direct, categories: cats };
  }

  const disambigTitle = await fetchDisambiguated(term);
  if (disambigTitle) {
    const disambig = await fetchSummary(disambigTitle);
    if (disambig) {
      const cats = await fetchCategories(disambig.title);
      if (!isExcluded(cats)) return { summary: disambig, categories: cats };
    }
  }

  return null;
}