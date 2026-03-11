import { useRef, useState } from 'react';
import { Upload, CheckCircle, Loader2 } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { adminUploadGuideline } from '../../services/api';
import type { IngestionReport } from '../../services/api';

const SOURCE_GROUPS = [
  {
    group: 'Rheumatology',
    sources: [
      { key: 'NICE',             label: 'NICE Guidelines'             },
      { key: 'BSR',              label: 'BSR Guidelines'              },
      { key: 'BNF_RHEUMATOLOGY',   label: 'BNF (British National Formulary)' },
      { key: 'OTHER_RHEUMATOLOGY', label: 'Other (Rheumatology)'              },
    ],
  },
  {
    group: 'Neurology',
    sources: [
      { key: 'NICE_NEURO', label: 'NICE Guidelines' },
    ],
  },
  {
    group: 'Other',
    sources: [
      { key: 'OTHER', label: 'Other / Miscellaneous' },
    ],
  },
];

export function AdminGuidelinesPage() {
  const [selectedSource, setSelectedSource] = useState(SOURCE_GROUPS[0].sources[0].key);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<IngestionReport | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setError('');
    setResult(null);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a PDF file.');
      return;
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported.');
      return;
    }
    setUploading(true);
    setError('');
    setResult(null);
    try {
      const report = await adminUploadGuideline(file, selectedSource);
      setResult(report);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <AdminLayout>
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Guidelines</h1>
          <p className="text-gray-600 mt-1">Upload a PDF guideline to index it into the knowledge base</p>
        </div>

        {/* Upload Form */}
        <form onSubmit={handleUpload} className="bg-white rounded-xl shadow-sm p-6 space-y-5">
          {/* Source selector */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              Source
            </label>
            <select
              value={selectedSource}
              onChange={e => setSelectedSource(e.target.value)}
              disabled={uploading}
              className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white text-sm disabled:opacity-50"
            >
              {SOURCE_GROUPS.map(g => (
                <optgroup key={g.group} label={g.group}>
                  {g.sources.map(s => (
                    <option key={s.key} value={s.key}>{s.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {/* File picker */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              PDF File
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              disabled={uploading}
              className="w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-[#005eb8] file:text-white hover:file:bg-[#003087] file:cursor-pointer disabled:opacity-50"
            />
            {file && (
              <p className="mt-1.5 text-xs text-gray-500">
                Selected: <span className="font-medium">{file.name}</span> ({(file.size / 1024).toFixed(0)} KB)
              </p>
            )}
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={uploading || !file}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#005eb8] text-white rounded-lg text-sm font-medium hover:bg-[#003087] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Processing…
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                Upload &amp; Ingest
              </>
            )}
          </button>
        </form>

        {/* Error */}
        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Success result */}
        {result && (
          <div className="mt-4 bg-white rounded-xl shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <h2 className="text-base font-semibold text-gray-900">Ingestion complete</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              <span className="font-medium">{result.filename}</span> indexed under{' '}
              <span className="font-medium">{result.source_name}</span>
            </p>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: 'Chunks created', value: result.total_chunks },
                { label: 'Embeddings OK', value: result.embeddings_succeeded },
                { label: 'DB inserted', value: result.db.inserted },
                { label: 'DB updated', value: result.db.updated },
              ].map(({ label, value }) => (
                <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
                  <dd className="text-2xl font-bold text-[#005eb8]">{value}</dd>
                  <dt className="text-xs text-gray-500 mt-0.5">{label}</dt>
                </div>
              ))}
            </dl>
            {(result.files_failed > 0 || result.embeddings_failed > 0 || result.db.failed > 0) && (
              <p className="mt-3 text-xs text-amber-600">
                Warning: {result.files_failed} file(s) failed, {result.embeddings_failed} embedding(s) failed,{' '}
                {result.db.failed} DB write(s) failed.
              </p>
            )}
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
