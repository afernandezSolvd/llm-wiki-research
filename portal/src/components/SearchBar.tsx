import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchSearch, type SearchResultItem } from '../api/client'

interface Props { workspaceId: string }

export default function SearchBar({ workspaceId }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [open, setOpen] = useState(false)
  const [hint, setHint] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const navigate = useNavigate()

  const search = useCallback(async (q: string) => {
    if (q.length < 2) { setHint('Type at least 2 characters'); setResults([]); return }
    setHint(null)
    try {
      const res = await fetchSearch(workspaceId, q)
      setResults(res.results)
      if (res.results.length === 0) setHint('No results found')
    } catch (e: unknown) {
      const err = e as { status?: number }
      if (err.status === 400) setHint('Search term too short')
      else setHint('Search unavailable')
      setResults([])
    }
  }, [workspaceId])

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (!query) { setResults([]); setHint(null); return }
    timerRef.current = setTimeout(() => search(query), 300)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [query, search])

  function handleSelect(item: SearchResultItem) {
    navigate(`/workspaces/${workspaceId}/pages/${item.page_path}`)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  const showDropdown = open && query.length > 0 && (results.length > 0 || hint !== null)

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <input
        type="search"
        placeholder="Search pages…"
        className="search-input"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {showDropdown && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 6px)',
          left: 0,
          right: 0,
          background: '#fff',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 300,
          maxHeight: 400,
          overflowY: 'auto',
        }}>
          {hint && results.length === 0 && (
            <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 13 }}>{hint}</div>
          )}
          {results.map((item, i) => (
            <button
              key={item.id}
              onMouseDown={() => handleSelect(item)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '10px 16px',
                background: 'none',
                border: 'none',
                borderTop: i > 0 ? '1px solid var(--border-light)' : 'none',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              <div style={{ fontWeight: 500, fontSize: 13.5, color: 'var(--text-primary)' }}>{item.title}</div>
              <div style={{
                fontSize: 12, color: 'var(--text-secondary)', marginTop: 3, lineHeight: 1.5,
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {item.snippet}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
