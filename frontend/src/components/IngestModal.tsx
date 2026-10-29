import React, { useState } from 'react'
import { X, FolderGit2, Loader2, Sparkles } from 'lucide-react'
import type { RepoInitRequest } from '../types'

interface IngestModalProps {
  isOpen: boolean
  onClose: () => void
  onStartIngest: (req: RepoInitRequest) => Promise<void>
}

export const IngestModal: React.FC<IngestModalProps> = ({
  isOpen,
  onClose,
  onStartIngest,
}) => {
  const [repoId, setRepoId] = useState('')
  const [sourceType, setSourceType] = useState<'local' | 'git'>('local')
  const [sourcePath, setSourcePath] = useState('')
  const [branch, setBranch] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoId.trim() || !sourcePath.trim()) {
      setError('Repository ID and Source Path are required.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      await onStartIngest({
        repo_id: repoId.trim(),
        source_type: sourceType,
        source_path: sourcePath.trim(),
        branch: branch.trim() || undefined,
      })
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to schedule ingestion job.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '8px',
                background: 'rgba(249, 115, 22, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-primary)',
              }}
            >
              <FolderGit2 size={18} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Ingest Codebase
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Extract AST symbols, compute PageRank, and generate vector embeddings
              </p>
            </div>
          </div>
          <button
            type="button"
            className="action-icon-btn"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && (
              <div
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  background: 'rgba(239, 68, 68, 0.12)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  fontSize: '0.8rem',
                }}
              >
                {error}
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Repository ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Agentic-Code-RAG"
                value={repoId}
                onChange={(e) => setRepoId(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Source Type</label>
              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  type="button"
                  style={{
                    flex: 1,
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid',
                    borderColor: sourceType === 'local' ? 'var(--accent-primary)' : 'var(--border-subtle)',
                    background: sourceType === 'local' ? 'rgba(249, 115, 22, 0.1)' : 'transparent',
                    color: sourceType === 'local' ? '#ffedd5' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '0.84rem',
                    fontWeight: 500,
                  }}
                  onClick={() => setSourceType('local')}
                >
                  Local Directory
                </button>
                <button
                  type="button"
                  style={{
                    flex: 1,
                    padding: '8px',
                    borderRadius: '6px',
                    border: '1px solid',
                    borderColor: sourceType === 'git' ? 'var(--accent-primary)' : 'var(--border-subtle)',
                    background: sourceType === 'git' ? 'rgba(249, 115, 22, 0.1)' : 'transparent',
                    color: sourceType === 'git' ? '#ffedd5' : 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '0.84rem',
                    fontWeight: 500,
                  }}
                  onClick={() => setSourceType('git')}
                >
                  Remote Git URL
                </button>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">
                {sourceType === 'local' ? 'Filesystem Path' : 'Git Clone URL'}
              </label>
              <input
                type="text"
                className="form-input"
                placeholder={sourceType === 'local' ? 'C:/Coding/Agentic-Code-RAG' : 'https://github.com/user/repo.git'}
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                required
              />
            </div>

            {sourceType === 'git' && (
              <div className="form-group">
                <label className="form-label">Branch / Tag (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="main"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                />
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              {loading ? <Loader2 size={14} className="spinning" /> : <Sparkles size={14} />}
              <span>{loading ? 'Scheduling...' : 'Start Ingestion'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
