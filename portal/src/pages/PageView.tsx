import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { fetchPage, type WikiPageDetail } from '../api/client'
import PageViewer from '../components/PageViewer'
import type { OutletCtx } from '../components/Layout'

export default function PageView() {
  const { workspaceId, '*': pagePath } = useParams<{ workspaceId: string; '*': string }>()
  const { setApiError, workspace } = useOutletContext<OutletCtx>()
  const [page, setPage] = useState<WikiPageDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!workspaceId || !pagePath) return
    setLoading(true)
    setNotFound(false)
    fetchPage(workspaceId, pagePath)
      .then((p) => { setPage(p); setApiError(null) })
      .catch((e) => {
        if (e.status === 404) setNotFound(true)
        else setApiError(e.message)
      })
      .finally(() => setLoading(false))
  }, [workspaceId, pagePath, setApiError])

  if (loading) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="skeleton" style={{ height: 14, width: 100 }} />
      <div className="skeleton" style={{ height: 44, width: '60%', margin: '12px 0 8px' }} />
      <div className="skeleton" style={{ height: 1, width: '100%', margin: '4px 0 16px' }} />
      {[92, 85, 88, 78, 90, 70].map((w, i) => (
        <div key={i} className="skeleton" style={{ height: 14, width: `${w}%` }} />
      ))}
    </div>
  )

  if (notFound) return (
    <div style={{ padding: '72px 0', textAlign: 'center' }}>
      <div style={{ fontSize: 36, marginBottom: 16 }}>📄</div>
      <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 8px' }}>
        Page not found
      </h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13.5, margin: '0 0 24px' }}>
        <code style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 4, padding: '2px 6px', fontFamily: 'monospace', fontSize: 12,
        }}>{pagePath}</code>{' '}
        does not exist in this workspace.
      </p>
      <Link to={`/workspaces/${workspaceId}`} style={{ color: 'var(--accent)', fontSize: 14, fontWeight: 500 }}>
        ← Back to pages
      </Link>
    </div>
  )

  if (!page) return null

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Link
          to={`/workspaces/${workspaceId}`}
          style={{ color: 'var(--text-muted)', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}
          className="breadcrumb-link"
        >
          ← {workspace?.display_name ?? 'Pages'}
        </Link>
      </div>
      <PageViewer page={page} />
    </div>
  )
}
