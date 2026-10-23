import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/components/app/AppShell'
import { HomePage } from '@/pages/HomePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ReportPage } from '@/pages/ReportPage'
import { WorkspacePage } from '@/pages/WorkspacePage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'workspace', element: <WorkspacePage /> },
      { path: 'workspace/:runId', element: <WorkspacePage /> },
      { path: 'runs/:runId/report', element: <ReportPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
])
