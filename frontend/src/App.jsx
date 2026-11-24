import { Route, Routes } from 'react-router-dom'
import AppLayout from './layouts/AppLayout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import UploadPage from './pages/UploadPage.jsx'
import DatasetPage from './pages/DatasetPage.jsx'
import AugmentPage from './pages/AugmentPage.jsx'
import JobsPage from './pages/JobsPage.jsx'
import JobPage from './pages/JobPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import ExportsPage from './pages/ExportsPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/datasets/new" element={<UploadPage />} />
        <Route path="/datasets/:datasetId" element={<DatasetPage />} />
        <Route path="/datasets/:datasetId/augment" element={<AugmentPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:jobId" element={<JobPage />} />
        <Route path="/jobs/:jobId/results" element={<ResultsPage />} />
        <Route path="/exports" element={<ExportsPage />} />
        <Route path="*" element={<p className="p-8">Page not found.</p>} />
      </Route>
    </Routes>
  )
}
