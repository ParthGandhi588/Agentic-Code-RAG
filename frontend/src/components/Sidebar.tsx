import React from 'react'
import {
  Sparkles,
  Plus,
  PanelLeftClose,
  FolderGit2,
  MessageSquare,
  Activity,
  Layers,
} from 'lucide-react'
import type { RepoSummary } from '../types'

interface SidebarProps {
  isOpen: boolean
  onToggle: () => void
  repositories: RepoSummary[]
  activeRepoId: string
  onSelectRepo: (repoId: string) => void
  onOpenIngestModal: () => void
  onNewChat: () => void
  totalSymbols: number
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  repositories,
  activeRepoId,
  onSelectRepo,
  onOpenIngestModal,
  onNewChat,
  totalSymbols,
}) => {
  return (
    <aside className={`sidebar ${isOpen ? '' : 'collapsed'}`}>
      {/* Sidebar Header */}
      <div className="sidebar-header">
        <a href="/" className="brand-link">
          <div className="brand-icon-wrapper">
            <Sparkles size={16} />
          </div>
          <span>Agentic RAG</span>
        </a>
        <button
          type="button"
          className="sidebar-toggle-btn"
          onClick={onToggle}
          title="Close sidebar"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* New Chat Button (ChatGPT / Claude style) */}
      <button type="button" className="new-chat-btn" onClick={onNewChat}>
        <div className="new-chat-btn-inner">
          <Plus size={16} />
          <span>New chat</span>
        </div>
      </button>

      {/* Sidebar Navigation & Repositories */}
      <div className="sidebar-content">
        {/* Repositories / Workspaces Section */}
        <div>
          <div className="sidebar-section-title">
            <span>Repositories</span>
            <Layers size={13} />
          </div>
          <div className="repo-list">
            {repositories.map((r) => {
              const isActive = r.repo_id === activeRepoId
              return (
                <button
                  key={r.repo_id}
                  type="button"
                  className={`repo-item-btn ${isActive ? 'active' : ''}`}
                  onClick={() => onSelectRepo(r.repo_id)}
                  title={`${r.repo_id} (${r.total_files} files, ${r.total_symbols} symbols)`}
                >
                  <FolderGit2 size={15} style={{ flexShrink: 0 }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {r.repo_id}
                  </span>
                  <span className="badge">{r.total_symbols || totalSymbols}</span>
                </button>
              )
            })}
            <button
              type="button"
              className="add-repo-btn"
              onClick={onOpenIngestModal}
            >
              <Plus size={14} />
              <span>Ingest Repository</span>
            </button>
          </div>
        </div>

        {/* Recent Conversations */}
        <div>
          <div className="sidebar-section-title">
            <span>Recent</span>
            <MessageSquare size={13} />
          </div>
          <div className="session-list">
            <button
              type="button"
              className="session-item-btn active"
              onClick={() => {}}
            >
              <MessageSquare size={14} style={{ flexShrink: 0 }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                Architecture & Ingestion
              </span>
            </button>
            <button
              type="button"
              className="session-item-btn"
              onClick={onNewChat}
            >
              <MessageSquare size={14} style={{ flexShrink: 0 }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                AST Dependency Analysis
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="system-status-indicator">
          <div className="status-dot" />
          <span>Engine Connected</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)' }}>
          <Activity size={14} />
        </div>
      </div>
    </aside>
  )
}
