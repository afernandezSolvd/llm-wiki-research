export interface Workspace {
  id: string
  slug: string
  display_name: string
  schema_version: number
}

export interface WikiPageSummary {
  id: string
  page_path: string
  title: string
  page_type: string
  word_count: number | null
  updated_at: string | null
}

export interface WikiPageDetail extends WikiPageSummary {
  content: string
}

export interface SourceSummary {
  id: string
  title: string
  source_type: string
  ingest_status: 'pending' | 'ingesting' | 'completed' | 'failed'
  byte_size: number | null
  created_at: string
}

export interface SearchResultItem {
  id: string
  page_path: string
  title: string
  snippet: string
  updated_at: string | null
}

export interface SearchResponse {
  total_count: number
  results: SearchResultItem[]
}

const BASE = '/api/v1/public'

async function request<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(err.detail ?? res.statusText), { status: res.status })
  }
  return res.json() as Promise<T>
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  return request<Workspace[]>(`${BASE}/workspaces`)
}

export async function fetchPages(
  workspaceId: string,
  params?: { limit?: number; offset?: number; page_type?: string }
): Promise<WikiPageSummary[]> {
  const qs = new URLSearchParams()
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.page_type) qs.set('page_type', params.page_type)
  const query = qs.toString() ? `?${qs}` : ''
  return request<WikiPageSummary[]>(`${BASE}/workspaces/${workspaceId}/pages${query}`)
}

export async function fetchPage(workspaceId: string, pagePath: string): Promise<WikiPageDetail> {
  return request<WikiPageDetail>(`${BASE}/workspaces/${workspaceId}/pages/${pagePath}`)
}

export async function fetchSources(
  workspaceId: string,
  params?: { status_filter?: string; limit?: number; offset?: number }
): Promise<SourceSummary[]> {
  const qs = new URLSearchParams()
  if (params?.status_filter) qs.set('status_filter', params.status_filter)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString() ? `?${qs}` : ''
  return request<SourceSummary[]>(`${BASE}/workspaces/${workspaceId}/sources${query}`)
}

export async function fetchSourcePages(
  workspaceId: string,
  sourceId: string
): Promise<WikiPageSummary[]> {
  return request<WikiPageSummary[]>(`${BASE}/workspaces/${workspaceId}/sources/${sourceId}/pages`)
}

export async function fetchSearch(
  workspaceId: string,
  q: string,
  limit = 20
): Promise<SearchResponse> {
  const qs = new URLSearchParams({ q, limit: String(limit) })
  return request<SearchResponse>(`${BASE}/workspaces/${workspaceId}/search?${qs}`)
}
