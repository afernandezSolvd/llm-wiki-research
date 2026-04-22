import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import { fetchPages, fetchWorkspaces, type WikiPageSummary, type Workspace } from '../api/client'
import SearchBar from './SearchBar'

export interface OutletCtx {
  setApiError: (e: string | null) => void
  workspace: Workspace | null
  pages: WikiPageSummary[]
}

export default function Layout() {
  const { workspaceId } = useParams<{ workspaceId?: string }>()
  const navigate = useNavigate()

  const [apiError, setApiError] = useState<string | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [pages, setPages] = useState<WikiPageSummary[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(true)

  useEffect(() => {
    fetchWorkspaces()
      .then((ws) => {
        setWorkspaces(ws)
        const active = workspaceId ? ws.find((w) => w.id === workspaceId) ?? ws[0] : ws[0]
        setWorkspace(active ?? null)
        if (!workspaceId && active) navigate(`/workspaces/${active.id}`, { replace: true })
      })
      .catch((e) => setApiError(e.message))
  }, [])

  useEffect(() => {
    if (!workspaceId) return
    const ws = workspaces.find((w) => w.id === workspaceId)
    if (ws) setWorkspace(ws)
  }, [workspaceId, workspaces])

  useEffect(() => {
    if (!workspace) return
    setSidebarLoading(true)
    fetchPages(workspace.id, { limit: 200 })
      .then((p) => { setPages(p); setSidebarLoading(false) })
      .catch(() => setSidebarLoading(false))
  }, [workspace])

  const groupedPages = pages.reduce<Record<string, WikiPageSummary[]>>((acc, p) => {
    const key = p.page_type || 'other'
    ;(acc[key] = acc[key] ?? []).push(p)
    return acc
  }, {})

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* ── Top bar ── */}
      <header style={{
        height: 52,
        background: '#0f0f13',
        borderBottom: '1px solid var(--sidebar-border)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        gap: 12,
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 200,
      }}>
        <Link to="/" style={{
          color: '#fff',
          fontWeight: 700,
          fontSize: 15,
          letterSpacing: '-0.01em',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          whiteSpace: 'nowrap',
          textDecoration: 'none',
          minWidth: 'calc(var(--sidebar-w) - 16px)',
        }}>
          <span style={{ fontSize: 18 }}>📖</span> Wiki Portal
        </Link>

        {workspaces.length > 1 && (
          <select
            value={workspaceId ?? workspace?.id ?? ''}
            onChange={(e) => navigate(`/workspaces/${e.target.value}`)}
            style={{
              padding: '4px 10px',
              background: 'rgba(255,255,255,0.07)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 'var(--radius)',
              color: '#e4e4e7',
              fontSize: 13,
              fontFamily: 'inherit',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id} style={{ background: '#1e1e2e' }}>{ws.display_name}</option>
            ))}
          </select>
        )}

        {workspaces.length === 1 && workspace && (
          <span style={{ color: '#71717a', fontSize: 13 }}>{workspace.display_name}</span>
        )}

        <div style={{ flex: 1, maxWidth: 380 }}>
          {workspace && <SearchBar workspaceId={workspace.id} />}
        </div>

        {workspace && (
          <nav style={{ display: 'flex', gap: 2, marginLeft: 'auto' }}>
            <NavLink to={`/workspaces/${workspace.id}`} end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} style={{ minWidth: 0 }}>
              Pages
            </NavLink>
            <NavLink to={`/workspaces/${workspace.id}/sources`} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} style={{ minWidth: 0 }}>
              Sources
            </NavLink>
          </nav>
        )}
      </header>

      {/* ── Body ── */}
      <div style={{ display: 'flex', flex: 1, paddingTop: 52 }}>
        {/* ── Sidebar ── */}
        <aside style={{
          width: 'var(--sidebar-w)',
          background: 'var(--sidebar-bg)',
          borderRight: '1px solid var(--sidebar-border)',
          position: 'fixed',
          top: 52,
          bottom: 0,
          left: 0,
          overflowY: 'auto',
          padding: '12px 8px 24px',
          zIndex: 100,
        }}>
          {apiError && (
            <div style={{ margin: '8px 4px 12px', padding: '8px 10px', background: 'rgba(220,38,38,0.15)', borderRadius: 'var(--radius)', color: '#fca5a5', fontSize: 12 }}>
              ⚠️ {apiError}
            </div>
          )}

          {sidebarLoading ? (
            <div style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[90, 70, 80, 60, 75].map((w, i) => (
                <div key={i} className="skeleton" style={{ height: 22, width: `${w}%`, background: 'rgba(255,255,255,0.06)', animation: 'none' }} />
              ))}
            </div>
          ) : (
            <>
              {Object.keys(groupedPages).sort().map((type) => (
                <div key={type}>
                  <div className="nav-label">{type}</div>
                  {groupedPages[type].map((p) => (
                    <NavLink
                      key={p.id}
                      to={`/workspaces/${workspace?.id}/pages/${p.page_path}`}
                      className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                      title={p.title}
                    >
                      {p.title}
                    </NavLink>
                  ))}
                </div>
              ))}
              {pages.length === 0 && (
                <p style={{ color: '#52525b', fontSize: 12.5, padding: '8px 10px' }}>No pages yet.</p>
              )}
            </>
          )}
        </aside>

        {/* ── Main content ── */}
        <main style={{ marginLeft: 'var(--sidebar-w)', flex: 1, minWidth: 0, padding: '40px 48px 80px', maxWidth: 'calc(var(--sidebar-w) + 860px)' }}>
          <Outlet context={{ setApiError, workspace, pages } satisfies OutletCtx} />
        </main>
      </div>
    </div>
  )
}
