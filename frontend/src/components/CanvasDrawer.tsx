import React, { useState, useEffect, useMemo } from 'react'
import {
  X,
  FileCode,
  Network,
  FolderTree,
  Copy,
  Check,
  ExternalLink,
  Sparkles,
  Filter,
  Loader2,
} from 'lucide-react'
import type { FileContentResponse, RepoGraphResponse } from '../types'

interface CanvasDrawerProps {
  isOpen: boolean
  onClose: () => void
  activeRepoId: string
  selectedFile: { path: string; startLine?: number; endLine?: number } | null
  fileContent: FileContentResponse | null
  graphData: RepoGraphResponse | null
  repoMapText: string
  onSelectNode?: (nodeId: string) => void
  onSelectCitation?: (filePath: string, startLine?: number, endLine?: number) => void
}

const QUICK_FILES = [
  {
    path: 'src/api/job_manager.py',
    label: 'JobManager',
    desc: 'Background indexing & real-time SSE telemetry',
    startLine: 32,
    endLine: 85,
  },
  {
    path: 'src/agent/factory.py',
    label: 'AgentFactory',
    desc: 'LangGraph multi-step reasoning & tool bindings',
    startLine: 25,
    endLine: 95,
  },
  {
    path: 'src/agent/evaluator.py',
    label: 'CRAGEvaluator',
    desc: 'Corrective RAG hallucination guard & relevance grading',
    startLine: 31,
    endLine: 80,
  },
  {
    path: 'src/parser/ast_extractor.py',
    label: 'ASTExtractor',
    desc: 'Tree-sitter syntax parsing & call graph extractor',
    startLine: 25,
    endLine: 90,
  },
  {
    path: 'src/retrieval/store.py',
    label: 'VectorStore',
    desc: 'Hybrid dense embeddings & BM25 rank fusion',
    startLine: 30,
    endLine: 95,
  },
]

export const CanvasDrawer: React.FC<CanvasDrawerProps> = ({
  isOpen,
  onClose,
  selectedFile,
  fileContent,
  graphData,
  repoMapText,
  onSelectCitation,
}) => {
  const [activeTab, setActiveTab] = useState<'code' | 'graph' | 'map'>('code')
  const [copied, setCopied] = useState(false)
  const [filterSrcOnly, setFilterSrcOnly] = useState(true)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [selectedGraphNode, setSelectedGraphNode] = useState<any | null>(null)

  // Auto switch to code tab if a file citation is clicked
  useEffect(() => {
    if (selectedFile) {
      setActiveTab('code')
    }
  }, [selectedFile])

  if (!isOpen) return null

  const handleCopy = () => {
    if (fileContent && typeof fileContent.content === 'string') {
      navigator.clipboard.writeText(fileContent.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Pre-calculate circular layout for AST Graph, separating classes and functions safely
  const { positionedNodes, nodeMap, edgesToRender } = useMemo(() => {
    if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length === 0) {
      return { positionedNodes: [], nodeMap: new Map(), edgesToRender: [] }
    }

    const filtered = graphData.nodes.filter((node) => {
      if (!node) return false
      const path = (node.file_path || '').replace(/\\/g, '/')
      if (filterSrcOnly) {
        return !path.startsWith('tests/')
      }
      return true
    })

    const subset = filtered.slice(0, 24)
    const centerX = 260
    const centerY = 230

    // Concentric layout: Classes in inner circle (radius 95), Functions in outer circle (radius 180)
    const classes = subset.filter((n) => ((n?.kind || '') + '').toLowerCase().includes('class'))
    const others = subset.filter((n) => !((n?.kind || '') + '').toLowerCase().includes('class'))

    const classNodes = classes.map((node, i) => {
      const angle = (i / Math.max(1, classes.length)) * 2 * Math.PI - Math.PI / 2
      const x = centerX + 95 * Math.cos(angle)
      const y = centerY + 95 * Math.sin(angle)
      return {
        ...node,
        x,
        y,
        isClass: true,
        name: node.name || 'Class',
        file_path: node.file_path || '',
        kind: node.kind || 'class',
        line: node.line || 1,
        pagerank_score: typeof node.pagerank_score === 'number' ? node.pagerank_score : 0,
      }
    })

    const otherNodes = others.map((node, i) => {
      const angle = (i / Math.max(1, others.length)) * 2 * Math.PI - Math.PI / 2
      const x = centerX + 180 * Math.cos(angle)
      const y = centerY + 180 * Math.sin(angle)
      return {
        ...node,
        x,
        y,
        isClass: false,
        name: node.name || 'Function',
        file_path: node.file_path || '',
        kind: node.kind || 'function',
        line: node.line || 1,
        pagerank_score: typeof node.pagerank_score === 'number' ? node.pagerank_score : 0,
      }
    })

    const allPositioned = [...classNodes, ...otherNodes]
    const map = new Map(allPositioned.map((n) => [n.id, n]))

    // Find edges that connect existing rendered nodes
    const validEdges = (Array.isArray(graphData.edges) ? graphData.edges : [])
      .filter((e) => e && map.has(e.source) && map.has(e.target))
      .slice(0, 40)

    return { positionedNodes: allPositioned, nodeMap: map, edgesToRender: validEdges }
  }, [graphData, filterSrcOnly])

  // Active node to inspect (hovered or selected)
  const rawActive =
    positionedNodes.find((n) => n.id === (hoveredNodeId || selectedGraphNode?.id)) ||
    selectedGraphNode ||
    positionedNodes[0] ||
    null

  const activeInspectedNode = rawActive
    ? {
        ...rawActive,
        name: rawActive.name || 'Symbol',
        kind: rawActive.kind || 'code',
        file_path: rawActive.file_path || '',
        line: rawActive.line || 1,
        pagerank_score:
          typeof rawActive.pagerank_score === 'number' ? rawActive.pagerank_score : 0,
      }
    : null

  // Parse repoMapText into structured file cards safely
  const parsedRepoMap = useMemo(() => {
    if (!repoMapText || typeof repoMapText !== 'string') return []
    const lines = repoMapText.split('\n')
    const sections: { file: string; symbols: { kind: string; name: string; raw: string }[] }[] = []
    let currentFile: string | null = null
    let currentSymbols: { kind: string; name: string; raw: string }[] = []

    for (const rawLine of lines) {
      const line = (rawLine || '').trim()
      if (!line || line.startsWith('#')) continue

      if (line.endsWith(':') && (line.includes('/') || line.includes('.'))) {
        if (currentFile && currentSymbols.length > 0) {
          sections.push({ file: currentFile, symbols: currentSymbols })
        }
        currentFile = line.replace(/:$/, '')
        currentSymbols = []
      } else if (line.startsWith('- ') || line.startsWith('-')) {
        const symLine = line.replace(/^[-\s]+/, '')
        const kindMatch = symLine.match(/^([a-zA-Z_]+):\s*([a-zA-Z0-9_]+)/)
        if (kindMatch) {
          currentSymbols.push({
            kind: kindMatch[1],
            name: kindMatch[2],
            raw: symLine,
          })
        } else {
          currentSymbols.push({
            kind: 'symbol',
            name: symLine.split(' ')[0] || 'symbol',
            raw: symLine,
          })
        }
      }
    }

    if (currentFile && currentSymbols.length > 0) {
      sections.push({ file: currentFile, symbols: currentSymbols })
    }

    return sections
  }, [repoMapText])

  const hasFileContent = fileContent && typeof fileContent.content === 'string'

  return (
    <aside className="canvas-drawer">
      {/* Canvas Header */}
      <div className="canvas-header">
        <div className="canvas-tabs">
          <button
            type="button"
            className={`canvas-tab-btn ${activeTab === 'code' ? 'active' : ''}`}
            onClick={() => setActiveTab('code')}
            title="Inspect source code"
          >
            <FileCode size={14} />
            <span>Code</span>
          </button>
          <button
            type="button"
            className={`canvas-tab-btn ${activeTab === 'graph' ? 'active' : ''}`}
            onClick={() => setActiveTab('graph')}
            title="AST Symbol & Dependency Call Graph"
          >
            <Network size={14} />
            <span>Graph</span>
          </button>
          <button
            type="button"
            className={`canvas-tab-btn ${activeTab === 'map' ? 'active' : ''}`}
            onClick={() => setActiveTab('map')}
            title="Tree-sitter Structural Topology Map"
          >
            <FolderTree size={14} />
            <span>Map</span>
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {activeTab === 'code' && hasFileContent && (
            <button
              type="button"
              className="action-icon-btn"
              onClick={handleCopy}
              title="Copy file contents"
            >
              {copied ? <Check size={14} style={{ color: '#10b981' }} /> : <Copy size={14} />}
            </button>
          )}
          <button
            type="button"
            className="action-icon-btn"
            onClick={onClose}
            title="Close Canvas"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Canvas Body */}
      <div className="canvas-content">
        {/* ==================================================================== */}
        {/* Tab 1: Code Viewer                                                   */}
        {/* ==================================================================== */}
        {activeTab === 'code' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div
              style={{
                padding: '10px 16px',
                background: 'rgba(255, 255, 255, 0.02)',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: '0.8rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden' }}>
                <FileCode size={14} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
                <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                  {selectedFile?.path || fileContent?.file_path || 'No file selected'}
                </span>
              </div>
              {selectedFile?.startLine && (
                <span
                  style={{
                    color: 'var(--accent-primary)',
                    fontSize: '0.72rem',
                    background: 'rgba(249, 115, 22, 0.12)',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  Lines {selectedFile.startLine}–{selectedFile.endLine || selectedFile.startLine}
                </span>
              )}
            </div>

            <div style={{ flex: 1, overflow: 'auto', padding: hasFileContent ? '12px 0' : '20px' }}>
              {hasFileContent ? (
                <div
                  style={{
                    display: 'table',
                    width: '100%',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.82rem',
                  }}
                >
                  {fileContent.content.split('\n').map((line, idx) => {
                    const lineNum = idx + 1
                    const isHighlighted =
                      Boolean(selectedFile?.startLine &&
                      selectedFile?.endLine &&
                      lineNum >= selectedFile.startLine &&
                      lineNum <= selectedFile.endLine)

                    return (
                      <div
                        key={`line-${lineNum}`}
                        style={{
                          display: 'table-row',
                          backgroundColor: isHighlighted ? 'rgba(249, 115, 22, 0.14)' : 'transparent',
                          borderLeft: isHighlighted
                            ? '3px solid var(--accent-primary)'
                            : '3px solid transparent',
                        }}
                      >
                        <span
                          style={{
                            display: 'table-cell',
                            width: '45px',
                            textAlign: 'right',
                            paddingRight: '14px',
                            userSelect: 'none',
                            color: isHighlighted ? 'var(--accent-primary)' : 'var(--text-muted)',
                            opacity: 0.6,
                          }}
                        >
                          {lineNum}
                        </span>
                        <span
                          style={{
                            display: 'table-cell',
                            paddingRight: '16px',
                            whiteSpace: 'pre',
                            color: '#e4e4e7',
                          }}
                        >
                          {line || ' '}
                        </span>
                      </div>
                    )
                  })}
                </div>
              ) : selectedFile ? (
                <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                    <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-primary)' }} />
                  </div>
                  <div style={{ fontSize: '0.88rem', fontWeight: 500, color: '#e4e4e7', marginBottom: 4 }}>
                    Loading {selectedFile.path}...
                  </div>
                  <div style={{ fontSize: '0.78rem' }}>
                    Fetching file range from repository
                  </div>
                </div>
              ) : (
                <div style={{ padding: '16px', textAlign: 'left' }}>
                  <div
                    style={{
                      background: 'rgba(249, 115, 22, 0.06)',
                      border: '1px solid rgba(249, 115, 22, 0.2)',
                      borderRadius: '8px',
                      padding: '16px',
                      marginBottom: '20px',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontWeight: 600,
                        color: 'var(--accent-primary)',
                        fontSize: '0.9rem',
                        marginBottom: 6,
                      }}
                    >
                      <Sparkles size={16} />
                      <span>Side-by-Side Code Canvas</span>
                    </div>
                    <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                      When you click any citation pill (e.g. <code>src/api/job_manager.py:32</code>) in the chat response,
                      that file and highlighted lines will open right here for instant code inspection.
                    </p>
                  </div>

                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                    Quick-Inspect Key Files:
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {QUICK_FILES.map((qf) => (
                      <button
                        key={qf.path}
                        type="button"
                        onClick={() => {
                          if (onSelectCitation) {
                            onSelectCitation(qf.path, qf.startLine, qf.endLine)
                          }
                        }}
                        style={{
                          textAlign: 'left',
                          background: 'rgba(255, 255, 255, 0.03)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: '8px',
                          padding: '10px 14px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)'
                          e.currentTarget.style.borderColor = 'var(--accent-primary)'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)'
                          e.currentTarget.style.borderColor = 'var(--border-subtle)'
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#fff' }}>
                              {qf.label}
                            </span>
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                              {qf.path}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 3 }}>
                            {qf.desc}
                          </div>
                        </div>
                        <ExternalLink size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* Tab 2: AST Dependency Graph                                          */}
        {/* ==================================================================== */}
        {activeTab === 'graph' && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative' }}>
            {/* Graph Control Bar */}
            <div
              style={{
                padding: '8px 16px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.75rem',
                background: 'rgba(0,0,0,0.2)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f97316' }} />
                  <span style={{ color: 'var(--text-secondary)' }}>Classes (Inner)</span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#06b6d4' }} />
                  <span style={{ color: 'var(--text-secondary)' }}>Functions (Outer)</span>
                </span>
              </div>

              <button
                type="button"
                onClick={() => setFilterSrcOnly((prev) => !prev)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '3px 8px',
                  borderRadius: '4px',
                  background: filterSrcOnly ? 'rgba(249, 115, 22, 0.15)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${filterSrcOnly ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
                  color: filterSrcOnly ? 'var(--accent-primary)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.72rem',
                }}
              >
                <Filter size={12} />
                <span>{filterSrcOnly ? 'Core src/ only' : 'All symbols'}</span>
              </button>
            </div>

            {/* SVG Visualizer Canvas */}
            <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
              <svg width="100%" height="100%" viewBox="0 0 520 460">
                <defs>
                  <marker
                    id="edge-arrow"
                    viewBox="0 0 10 10"
                    refX="16"
                    refY="5"
                    markerWidth="5"
                    markerHeight="5"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(255, 255, 255, 0.2)" />
                  </marker>
                </defs>

                {/* Concentric Orbital Guidelines */}
                <circle cx={260} cy={230} r={95} fill="none" stroke="rgba(255,255,255,0.04)" strokeDasharray="4 4" />
                <circle cx={260} cy={230} r={180} fill="none" stroke="rgba(255,255,255,0.03)" strokeDasharray="4 4" />

                {/* Render Directed Call Edges */}
                {edgesToRender.map((edge, i) => {
                  const s = nodeMap.get(edge.source)
                  const t = nodeMap.get(edge.target)
                  if (!s || !t) return null
                  const isHovered = hoveredNodeId && (edge.source === hoveredNodeId || edge.target === hoveredNodeId)

                  return (
                    <line
                      key={`edge-${i}`}
                      x1={s.x}
                      y1={s.y}
                      x2={t.x}
                      y2={t.y}
                      stroke={isHovered ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.12)'}
                      strokeWidth={isHovered ? 2 : 1}
                      markerEnd="url(#edge-arrow)"
                    />
                  )
                })}

                {/* Render AST Symbol Nodes */}
                {positionedNodes.map((node) => {
                  const isHovered = hoveredNodeId === node.id || selectedGraphNode?.id === node.id
                  const fill = node.isClass ? '#f97316' : '#06b6d4'
                  const radius = node.isClass ? 9 : 6.5
                  const safeName = node.name || 'Symbol'

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={() => setHoveredNodeId(node.id)}
                      onMouseLeave={() => setHoveredNodeId(null)}
                      onClick={() => {
                        setSelectedGraphNode(node)
                        if (onSelectCitation) {
                          onSelectCitation(node.file_path, node.line, (node.line || 1) + 40)
                        }
                      }}
                    >
                      {/* Glow halo on hover */}
                      {isHovered && (
                        <circle
                          r={radius + 8}
                          fill={fill}
                          opacity={0.25}
                        />
                      )}
                      <circle
                        r={radius}
                        fill={fill}
                        stroke={isHovered ? '#fff' : 'rgba(255, 255, 255, 0.4)'}
                        strokeWidth={isHovered ? 2.5 : 1.2}
                      />
                      {/* Only show persistent labels for classes or hovered elements to prevent text collision */}
                      {(node.isClass || isHovered) && (
                        <text
                          y={node.isClass ? -14 : -11}
                          textAnchor="middle"
                          fill={isHovered ? '#fff' : '#cbd5e1'}
                          fontSize={node.isClass ? '11' : '10'}
                          fontWeight={node.isClass ? '600' : '400'}
                          fontFamily="var(--font-mono)"
                          style={{
                            textShadow: '0 1px 3px rgba(0,0,0,0.9)',
                            pointerEvents: 'none',
                          }}
                        >
                          {safeName.length > 20 ? `${safeName.substring(0, 18)}…` : safeName}
                        </text>
                      )}
                    </g>
                  )
                })}
              </svg>

              {/* Node Inspector Floating Footer Card */}
              {activeInspectedNode && (
                <div
                  style={{
                    position: 'absolute',
                    bottom: 12,
                    left: 12,
                    right: 12,
                    background: 'rgba(18, 18, 20, 0.95)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          textTransform: 'uppercase',
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: '3px',
                          background: activeInspectedNode.isClass ? 'rgba(249, 115, 22, 0.2)' : 'rgba(6, 182, 212, 0.2)',
                          color: activeInspectedNode.isClass ? '#f97316' : '#06b6d4',
                        }}
                      >
                        {activeInspectedNode.kind}
                      </span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#fff' }}>
                        {activeInspectedNode.name}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 3 }}>
                      {activeInspectedNode.file_path}:{activeInspectedNode.line || 1} • Centrality {(activeInspectedNode.pagerank_score * 100).toFixed(1)}%
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      if (onSelectCitation) {
                        onSelectCitation(
                          activeInspectedNode.file_path,
                          activeInspectedNode.line,
                          (activeInspectedNode.line || 1) + 40
                        )
                      }
                    }}
                    style={{
                      background: 'var(--accent-primary)',
                      color: '#000',
                      border: 'none',
                      borderRadius: '5px',
                      padding: '5px 10px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <span>View Code</span>
                    <ExternalLink size={12} />
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* Tab 3: Tree-sitter Structural Repo Map                              */}
        {/* ==================================================================== */}
        {activeTab === 'map' && (
          <div style={{ height: '100%', overflow: 'auto', padding: '16px' }}>
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '12px 14px',
                marginBottom: '16px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  color: 'var(--accent-primary)',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  marginBottom: 4,
                }}
              >
                <FolderTree size={15} />
                <span>Tree-sitter Topology Outline</span>
              </div>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                This is the structural symbol skeleton extracted via Tree-sitter AST parsing. The AI agent uses this outline
                to instantly understand repository architecture without reading thousands of raw files.
              </p>
            </div>

            {parsedRepoMap.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {parsedRepoMap.map((section, idx) => (
                  <div
                    key={`map-sec-${idx}`}
                    style={{
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      padding: '12px',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: '8px',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          if (onSelectCitation) {
                            onSelectCitation(section.file, 1, 50)
                          }
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#fff',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: 0,
                        }}
                      >
                        <FileCode size={13} style={{ color: 'var(--accent-primary)' }} />
                        <span>{section.file}</span>
                      </button>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        {section.symbols.length} symbols
                      </span>
                    </div>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {section.symbols.map((sym, sIdx) => {
                        const isClass = sym.kind === 'class' || sym.kind === 'interface'
                        return (
                          <span
                            key={`sym-${sIdx}`}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                              background: isClass ? 'rgba(249, 115, 22, 0.1)' : 'rgba(255, 255, 255, 0.04)',
                              border: `1px solid ${isClass ? 'rgba(249, 115, 22, 0.25)' : 'var(--border-subtle)'}`,
                              borderRadius: '4px',
                              padding: '2px 6px',
                              fontSize: '0.72rem',
                              fontFamily: 'var(--font-mono)',
                              color: isClass ? 'var(--accent-primary)' : 'var(--text-secondary)',
                            }}
                            title={sym.raw}
                          >
                            <span style={{ opacity: 0.6, fontSize: '0.65rem' }}>{sym.kind}:</span>
                            <span style={{ fontWeight: 500 }}>{sym.name}</span>
                          </span>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <pre
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  lineHeight: 1.5,
                  color: 'var(--text-secondary)',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {repoMapText || 'No repo map generated yet.'}
              </pre>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
