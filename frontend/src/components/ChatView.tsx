import React, { useState, useRef, useEffect } from 'react'
import {
  PanelLeftOpen,
  ChevronDown,
  ChevronRight,
  Sparkles,
  ArrowUp,
  RotateCcw,
  Layers,
  Code2,
  Copy,
  Check,
  Cpu,
  ShieldCheck,
  Search,
  FolderGit2,
  Loader2,
  GitFork,
} from 'lucide-react'
import type { ChatMessage, RepoSummary } from '../types'

interface ChatViewProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  canvasOpen: boolean
  onToggleCanvas: () => void
  activeRepoId: string
  repositories: RepoSummary[]
  onSelectRepo: (repoId: string) => void
  messages: ChatMessage[]
  isStreaming: boolean
  onSendMessage: (query: string) => Promise<void>
  onSelectCitation: (filePath: string, startLine?: number, endLine?: number) => void
  onNewChat: () => void
  totalFiles: number
  totalSymbols: number
}

const STARTER_PROMPTS = [
  {
    icon: <Cpu size={18} />,
    title: 'Architecture Overview',
    desc: 'Explain the 5-stage agentic RAG pipeline and CRAG decision workflow.',
    prompt: 'Explain the multi-stage autonomous reasoning engine, CRAG decision flow, and architecture of this repository.',
  },
  {
    icon: <GitFork size={18} />,
    title: 'AST & PageRank Topology',
    desc: 'Identify the most central classes and modules by PageRank centrality.',
    prompt: 'What are the most central classes and symbols in this repository according to the PageRank centrality repo map?',
  },
  {
    icon: <Search size={18} />,
    title: 'Hybrid Retrieval Engine',
    desc: 'How does FastEmbed dense vectors combine with BM25 via RRF?',
    prompt: 'How does the hybrid search engine combine dense FastEmbed embeddings and BM25 full-text search with Reciprocal Rank Fusion?',
  },
  {
    icon: <ShieldCheck size={18} />,
    title: 'Security & Traversal Guards',
    desc: 'Examine how path traversal attacks and secret leakages are prevented.',
    prompt: 'How does the repository protect against path traversal vulnerabilities and secret leakage during scanning and code inspection?',
  },
]

export const ChatView: React.FC<ChatViewProps> = ({
  sidebarOpen,
  onToggleSidebar,
  canvasOpen,
  onToggleCanvas,
  activeRepoId,
  repositories,
  onSelectRepo,
  messages,
  isStreaming,
  onSendMessage,
  onSelectCitation,
  onNewChat,
  totalFiles,
  totalSymbols,
}) => {
  const [input, setInput] = useState('')
  const [thinkingExpanded, setThinkingExpanded] = useState<Record<string, boolean>>({})
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null)
  const [repoDropdownOpen, setRepoDropdownOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`
    }
  }, [input])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submitMessage()
    }
  }

  const submitMessage = () => {
    if (!input.trim() || isStreaming) return
    const text = input.trim()
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    onSendMessage(text)
  }

  const toggleThinking = (id: string) => {
    setThinkingExpanded((prev) => ({
      ...prev,
      [id]: prev[id] === undefined ? false : !prev[id],
    }))
  }

  const handleCopyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code)
    setCopiedCodeId(id)
    setTimeout(() => setCopiedCodeId(null), 2000)
  }

  // Renders rich text with code blocks, inline code, and clickable citation pills
  const renderMessageText = (text: string, messageId: string) => {
    // Split by triple-backtick code blocks
    const codeBlockRegex = /```([a-zA-Z0-9_\-+]*)\n([\s\S]*?)```/g
    const blocks: React.ReactNode[] = []
    let lastIndex = 0
    let match: RegExpExecArray | null
    let blockCount = 0

    while ((match = codeBlockRegex.exec(text)) !== null) {
      const matchIndex = match.index
      const language = match[1] || 'code'
      const codeContent = match[2].trimEnd()

      // Add preceding text
      if (matchIndex > lastIndex) {
        blocks.push(
          renderInlineContent(text.substring(lastIndex, matchIndex), `${messageId}-txt-${blockCount}`)
        )
      }

      // Add Code Block with header & copy button
      const codeId = `${messageId}-code-${blockCount}`
      const isCopied = copiedCodeId === codeId
      blocks.push(
        <div key={codeId} className="code-block-wrapper">
          <div className="code-block-header">
            <span>{language}</span>
            <button
              type="button"
              className="copy-btn"
              onClick={() => handleCopyCode(codeContent, codeId)}
            >
              {isCopied ? <Check size={13} style={{ color: '#10b981' }} /> : <Copy size={13} />}
              <span>{isCopied ? 'Copied!' : 'Copy'}</span>
            </button>
          </div>
          <pre className="code-block-pre">
            <code>{codeContent}</code>
          </pre>
        </div>
      )

      blockCount++
      lastIndex = matchIndex + match[0].length
    }

    if (lastIndex < text.length) {
      blocks.push(
        renderInlineContent(text.substring(lastIndex), `${messageId}-txt-${blockCount}`)
      )
    }

    return blocks
  }

  // Parses inline citations (e.g. `src/main.py:10-40`) and inline code
  const renderInlineContent = (content: string, keyPrefix: string) => {
    const citationRegex = /([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+):(\d+)(?:-(\d+))?/g
    const parts: React.ReactNode[] = []
    let lastIndex = 0
    let match: RegExpExecArray | null
    let count = 0

    while ((match = citationRegex.exec(content)) !== null) {
      const matchIndex = match.index
      const fullMatch = match[0]
      const filePath = match[1]
      const startLine = parseInt(match[2], 10)
      const endLine = match[3] ? parseInt(match[3], 10) : startLine

      if (matchIndex > lastIndex) {
        parts.push(content.substring(lastIndex, matchIndex))
      }

      parts.push(
        <button
          key={`${keyPrefix}-cite-${count}`}
          type="button"
          className="citation-pill"
          title={`Inspect ${filePath} in Canvas (L${startLine}${endLine ? `-${endLine}` : ''})`}
          onClick={() => onSelectCitation(filePath, startLine, endLine)}
        >
          <Code2 size={12} />
          <span>{fullMatch}</span>
        </button>
      )

      count++
      lastIndex = matchIndex + fullMatch.length
    }

    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex))
    }

    return (
      <div key={keyPrefix} style={{ whiteSpace: 'pre-wrap' }}>
        {parts}
      </div>
    )
  }

  return (
    <main className="main-chat-container">
      {/* Top Navbar (ChatGPT / Claude style) */}
      <header className="top-navbar">
        <div className="top-navbar-left">
          {!sidebarOpen && (
            <button
              type="button"
              className="sidebar-toggle-btn"
              onClick={onToggleSidebar}
              title="Open sidebar"
            >
              <PanelLeftOpen size={18} />
            </button>
          )}

          {/* Repository Selector Dropdown Pill */}
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              className="repo-selector-pill"
              onClick={() => setRepoDropdownOpen(!repoDropdownOpen)}
            >
              <FolderGit2 size={15} style={{ color: 'var(--accent-primary)' }} />
              <span>{activeRepoId || 'Select Repository'}</span>
              <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />
            </button>

            {repoDropdownOpen && (
              <div
                style={{
                  position: 'absolute',
                  top: '110%',
                  left: 0,
                  width: '260px',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-medium)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: 'var(--shadow-lg)',
                  padding: '6px',
                  zIndex: 50,
                }}
              >
                {repositories.map((r) => (
                  <button
                    key={r.repo_id}
                    type="button"
                    className="repo-item-btn"
                    onClick={() => {
                      onSelectRepo(r.repo_id)
                      setRepoDropdownOpen(false)
                    }}
                  >
                    <FolderGit2 size={14} />
                    <span>{r.repo_id}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Top Navbar Right Actions */}
        <div className="top-navbar-right">
          <button
            type="button"
            className="action-icon-btn"
            onClick={onNewChat}
            title="Start fresh conversation"
          >
            <RotateCcw size={16} />
          </button>
          <button
            type="button"
            className={`canvas-toggle-btn ${canvasOpen ? 'active' : ''}`}
            onClick={onToggleCanvas}
            title="Toggle Canvas Inspector"
          >
            <Layers size={15} />
            <span>Canvas</span>
          </button>
        </div>
      </header>

      {/* Chat Messages Scroll Area */}
      <div className="chat-scroll-area">
        <div className="chat-center-column">
          {/* Empty State Hero */}
          {messages.length === 0 && (
            <div className="hero-empty-state">
              <div className="hero-badge-icon">
                <Sparkles size={28} />
              </div>
              <h1 className="hero-title">Where knowledge meets code.</h1>
              <p className="hero-subtitle">
                Explore <strong>{activeRepoId}</strong> with autonomous multi-hop reasoning over
                AST symbol graphs, PageRank repo maps, and hybrid code embeddings.
              </p>

              <div className="quick-prompts-grid">
                {STARTER_PROMPTS.map((item) => (
                  <button
                    key={item.title}
                    type="button"
                    className="prompt-card"
                    onClick={() => onSendMessage(item.prompt)}
                  >
                    <div className="prompt-card-header">
                      {item.icon}
                      <span>{item.title}</span>
                    </div>
                    <p className="prompt-card-desc">{item.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Conversation Stream */}
          {messages.map((msg) => {
            if (msg.sender === 'user') {
              return (
                <div key={msg.id} className="message-row user">
                  <div className="user-bubble">{msg.text}</div>
                </div>
              )
            }

            // Assistant Message
            const isThinkingOpen = thinkingExpanded[msg.id] !== false // Default open
            const hasToolSteps = msg.toolSteps && msg.toolSteps.length > 0

            return (
              <div key={msg.id} className="message-row assistant">
                <div className="assistant-avatar">
                  <Sparkles size={16} />
                </div>
                <div className="assistant-body">
                  {/* Collapsible Thinking Process (Claude 3.7 / DeepSeek R1 style) */}
                  {hasToolSteps && (
                    <div className="thinking-accordion">
                      <div
                        className="thinking-header"
                        onClick={() => toggleThinking(msg.id)}
                      >
                        <div className="thinking-title-group">
                          <div className="thinking-dot" />
                          <span>
                            Thought Process ({msg.toolSteps?.length} steps)
                          </span>
                        </div>
                        {isThinkingOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </div>

                      {isThinkingOpen && (
                        <div className="thinking-body">
                          {msg.toolSteps?.map((step, idx) => (
                            <div key={`step-${idx}`} className="thinking-step-item">
                              <span className="thinking-step-badge">{step.tool}</span>
                              <span>
                                {step.output_preview ||
                                  (step.input ? JSON.stringify(step.input) : 'Executing search...')}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Prose & Code Rendering */}
                  <div className="assistant-prose">
                    {renderMessageText(msg.text, msg.id)}
                  </div>
                </div>
              </div>
            )
          })}

          {/* Streaming Indicator */}
          {isStreaming && (
            <div className="message-row assistant">
              <div className="assistant-avatar">
                <Sparkles size={16} />
              </div>
              <div className="assistant-body">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                  <Loader2 size={16} className="spinning" />
                  <span style={{ fontSize: '0.88rem' }}>Reasoning over codebase graph...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Floating Bottom Input Card (ChatGPT / Claude style) */}
      <div className="floating-input-wrapper">
        <div className="input-card">
          <textarea
            ref={textareaRef}
            rows={1}
            className="chat-textarea"
            placeholder={`Message ${activeRepoId || 'Agentic-Code-RAG'}...`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="input-card-bottom">
            <div className="input-meta-pill">
              <FolderGit2 size={12} style={{ color: 'var(--accent-primary)' }} />
              <span>{activeRepoId}</span>
              <span style={{ color: 'var(--text-muted)' }}>•</span>
              <span>{totalFiles} files</span>
              <span style={{ color: 'var(--text-muted)' }}>•</span>
              <span>{totalSymbols} symbols</span>
            </div>

            <button
              type="button"
              className={`send-btn-round ${input.trim() && !isStreaming ? 'active' : ''}`}
              onClick={submitMessage}
              disabled={!input.trim() || isStreaming}
              title="Send message"
            >
              {isStreaming ? <Loader2 size={16} className="spinning" /> : <ArrowUp size={18} />}
            </button>
          </div>
        </div>
        <p className="input-disclaimer">
          Agentic-Code-RAG analyzes AST symbols, call graphs, and code embeddings. Verify important code.
        </p>
      </div>
    </main>
  )
}
