import { Link, useOutletContext } from 'react-router-dom'
import type { OutletCtx } from '../components/Layout'

export default function WorkspaceHome() {
  const { workspace, pages } = useOutletContext<OutletCtx>()

  if (!workspace) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 8 }}>
      <div className="skeleton" style={{ height: 36, width: 220 }} />
      <div className="skeleton" style={{ height: 16, width: 160, marginBottom: 24 }} />
      {[100, 90, 95, 85, 92].map((w, i) => (
        <div key={i} className="skeleton" style={{ height: 42, width: `${w}%` }} />
      ))}
    </div>
  )

  const grouped = pages.reduce<Record<string, typeof pages>>((acc, p) => {
    const k = p.page_type || 'other'
    ;(acc[k] = acc[k] ?? []).push(p)
    return acc
  }, {})

  const typeCount = Object.keys(grouped).length

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)',
          letterSpacing: '-0.02em', margin: '0 0 6px',
        }}>
          {workspace.display_name}
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13.5, margin: 0 }}>
          {pages.length} page{pages.length !== 1 ? 's' : ''}
          {typeCount > 0 ? ` · ${typeCount} type${typeCount !== 1 ? 's' : ''}` : ''}
        </p>
      </div>

      {pages.length === 0 ? (
        <div style={{ padding: '56px 0', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>No pages in this workspace yet.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          {Object.keys(grouped).sort().map((type) => (
            <section key={type}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                marginBottom: 8, paddingBottom: 8,
                borderBottom: '1px solid var(--border)',
              }}>
                <span style={{
                  fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
                  letterSpacing: '0.07em', color: 'var(--text-muted)',
                }}>
                  {type}
                </span>
                <span style={{
                  fontSize: 11, color: 'var(--text-muted)',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 99, padding: '0 7px', lineHeight: '18px',
                }}>
                  {grouped[type].length}
                </span>
              </div>
              <div>
                {grouped[type].map((p) => (
                  <Link
                    key={p.id}
                    to={`/workspaces/${workspace.id}/pages/${p.page_path}`}
                    className="page-row"
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '9px 12px', borderRadius: 'var(--radius)',
                      color: 'var(--text-primary)', textDecoration: 'none',
                    }}
                  >
                    <span style={{ fontWeight: 500, fontSize: 14 }}>{p.title}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap', marginLeft: 16 }}>
                      {p.updated_at
                        ? new Date(p.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                        : '—'}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
