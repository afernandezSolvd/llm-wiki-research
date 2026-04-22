import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import WorkspaceHome from './pages/WorkspaceHome'
import PageView from './pages/PageView'
import SourcesView from './pages/SourcesView'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <WorkspaceHome /> },
      { path: 'workspaces/:workspaceId', element: <WorkspaceHome /> },
      { path: 'workspaces/:workspaceId/pages/*', element: <PageView /> },
      { path: 'workspaces/:workspaceId/sources', element: <SourcesView /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
