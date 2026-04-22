import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchWorkspaces, type Workspace } from '../api/client'

export default function WorkspacePicker() {
  const { workspaceId } = useParams<{ workspaceId?: string }>()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    fetchWorkspaces().then(setWorkspaces).catch(() => {})
  }, [])

  if (workspaces.length === 0) return null

  function handleChange(newId: string) {
    // Preserve current section (pages vs sources)
    const onSources = window.location.pathname.includes('/sources')
    navigate(onSources ? `/workspaces/${newId}/sources` : `/workspaces/${newId}`)
  }

  return (
    <select
      value={workspaceId ?? workspaces[0]?.id ?? ''}
      onChange={(e) => handleChange(e.target.value)}
      style={{
        padding: '0.3rem 0.5rem',
        borderRadius: '4px',
        border: '1px solid #4b5563',
        background: '#2d2d44',
        color: '#fff',
        fontSize: '0.9rem',
        cursor: 'pointer',
      }}
    >
      {workspaces.map((ws) => (
        <option key={ws.id} value={ws.id}>{ws.display_name}</option>
      ))}
    </select>
  )
}
