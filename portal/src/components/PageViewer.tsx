import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { WikiPageDetail } from '../api/client'

interface Props { page: WikiPageDetail }

export default function PageViewer({ page }: Props) {
  return (
    <article>
      <header style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
          <span className="badge badge-type">{page.page_type}</span>
          {page.word_count != null && (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {page.word_count.toLocaleString()} words
            </span>
          )}
          {page.updated_at && (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              Updated {new Date(page.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
          )}
        </div>
        <h1 style={{
          fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)',
          letterSpacing: '-0.025em', lineHeight: 1.2, margin: 0,
        }}>
          {page.title}
        </h1>
      </header>
      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '0 0 28px' }} />
      <div className="prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {page.content}
        </ReactMarkdown>
      </div>
    </article>
  )
}
