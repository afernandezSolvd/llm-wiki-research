import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { fetchSources, fetchSourcePages, type SourceSummary, type WikiPageSummary } from '../api/client'
import type { OutletCtx } from '../components/Layout'

function fmtBytes(n: number | null): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

function fmtDate(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const STATUS_CLASS: Record<string, string> = {
  completed: 'badge badge-completed',
  failed: 'badge badge-failed',
  ingesting: 'badge badge-ingesting',
  pending: 'badge badge-pending',
}

export default function SourcesView() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  const { setApiError } = useOutletContext<OutletCtx>()
  const [sources, setSources] = useState<SourceSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sourcePages, setSourcePages] = useState<Record<string, WikiPageSummary[]>>({})
  const [loadingPages, setLoadingPages] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!workspaceId) return
    setLoading(true)
    fetchSources(workspaceId)
      .then((s) => { setSources(s); setApiError(null) })
      .catch((e) => setApiError(e.message))
      .finally(() => setLoading(false))
  }, [workspaceId, setApiError])

  async function toggleExpand(src: SourceSummary) {
    if (expandedId === src.id) { setExpandedId(null); return }
    setExpandedId(src.id)
    if (sourcePages[src.id] !== undefined || !workspaceId) return
    setLoadingPages((p) => ({ ...p, [src.id]: true }))
    try {
      const pages = await fetchSourcePages(workspaceId, src.id)
      setSourcePages((p) => ({ ...p, [src.id]: pages }))
    } catch (e: unknown) {
      setApiError((e as Error).message)
    } finally {
      setLoadingPages((p) => ({ ...p, [src.id]: false }))
    }
  }

  if (loading) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="skeleton" style={{ height: 36, width: 160, marginBottom: 8 }} />
      {[100, 95, 85, 90, 80].map((w, i) => (
        <div key={i} className="skeleton" style={{ height: 52, width: `${w}%` }} />
      ))}
    </div>
  )

  return (
    <div>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{
          fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)',
          letterSpacing: '-0.02em', margin: '0 0 6px',
        }}>
          Sources
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13.5, margin: 0 }}>
          {sources.length} ingested source{sources.length !== 1 ? 's' : ''}
        </p>
      </div>

      {sources.length === 0 ? (
        <div style={{ padding: '56px 0', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>No sources ingested into this workspace yet.</p>
        </div>
      ) : (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          {sources.map((src, i) => (
            <div key={src.id}>
              <div
                onClick={() => toggleExpand(src)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto auto auto auto auto',
                  alignItems: 'center',
                  gap: 16,
                  padding: '14px 20px',
                  background: expandedId === src.id ? 'var(--surface)' : '#fff',
                  borderTop: i === 0 ? 'none' : '1px solid var(--border)',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                  userSelect: 'none',
                }}
              >
                <div style={{ overflow: 'hidden' }}>
                  <span style={{
                    fontWeight: 500, fontSize: 14, color: 'var(--text-primary)',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'block',
                  }}>
                    {src.title}
                  </span>
                </div>
                <span className="badge badge-type" style={{ whiteSpace: 'nowrap' }}>{src.source_type}</span>
                <span className={STATUS_CLASS[src.ingest_status] ?? 'badge badge-pending'}>
                  {src.ingest_status}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: 13, whiteSpace: 'nowrap' }}>{fmtBytes(src.byte_size)}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 13, whiteSpace: 'nowrap' }}>{fmtDate(src.created_at)}</span>
                <svg
                  width="14" height="14" viewBox="0 0 14 14" fill="none"
                  style={{
                    transform: expandedId === src.id ? 'rotate(180deg)' : 'none',
                    transition: 'transform 0.15s',
                    color: 'var(--text-muted)',
                    flexShrink: 0,
                  }}
                >
                  <path d="M2 4.5L7 9.5L12 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>

              {expandedId === src.id && (
                <div style={{
                  padding: '12px 20px 16px',
                  background: 'var(--surface)',
                  borderTop: '1px solid var(--border)',
                }}>
                  {loadingPages[src.id] ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {[80, 65, 75].map((w, i) => (
                        <div key={i} className="skeleton" style={{ height: 16, width: `${w}%` }} />
                      ))}
                    </div>
                  ) : !sourcePages[src.id] || sourcePages[src.id].length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: 13, margin: 0 }}>
                      No pages produced by this source yet.
                    </p>
                  ) : (
                    <div>
                      <p style={{
                        fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                        letterSpacing: '0.07em', color: 'var(--text-muted)', margin: '0 0 10px',
                      }}>
                        Generated pages ({sourcePages[src.id].length})
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {sourcePages[src.id].map((p) => (
                          <Link
                            key={p.id}
                            to={`/workspaces/${workspaceId}/pages/${p.page_path}`}
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              fontSize: 13, color: 'var(--accent)', fontWeight: 500,
                              display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none',
                            }}
                          >
                            <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>▶</span>
                            {p.title}
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
