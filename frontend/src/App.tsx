import React, { useState, useEffect, useCallback } from 'react'
import { Sidebar } from './components/Sidebar'
import { ChatView } from './components/ChatView'
import { CanvasDrawer } from './components/CanvasDrawer'
import { IngestModal } from './components/IngestModal'
import type {
  RepoSummary,
  RepoInitRequest,
  RepoInitResponse,
  IndexingJobResponse,
  ChatMessage,
  ToolStep,
  FileContentResponse,
  RepoGraphResponse,
} from './types'

export const App: React.FC = () => {
  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Canvas Drawer state (Claude Artifacts style)
  const [canvasOpen, setCanvasOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState<{
    path: string
    startLine?: number
    endLine?: number
  } | null>(null)
  const [fileContent, setFileContent] = useState<FileContentResponse | null>(null)
  const [graphData, setGraphData] = useState<RepoGraphResponse | null>(null)
  const [repoMapText, setRepoMapText] = useState<string>('')

  // Repository state
  const [repos, setRepos] = useState<RepoSummary[]>([])
  const [activeRepoId, setActiveRepoId] = useState<string>('Agentic-Code-RAG')

  // Ingestion Modal state
  const [ingestModalOpen, setIngestModalOpen] = useState(false)

  // Chat conversation state
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId] = useState(() => `session_${Math.random().toString(36).substring(2, 9)}`)

  // 1. Fetch available repositories
  const fetchRepos = useCallback(async () => {
    try {
      const res = await fetch('/api/repos')
      if (res.ok) {
        const data = await res.json()
        const repoList: RepoSummary[] = data.repositories || []
        setRepos(repoList)
        if (repoList.length > 0 && !repoList.some((r) => r.repo_id === activeRepoId)) {
          setActiveRepoId(repoList[0].repo_id)
        }
      }
    } catch {
      // Offline fallback: keep default repo
    }
  }, [activeRepoId])

  useEffect(() => {
    fetchRepos()
  }, [fetchRepos])

  // 2. Fetch Graph Data and Repo Map when active repo changes
  useEffect(() => {
    if (!activeRepoId) return

    // Fetch Graph
    fetch(`/api/repos/${activeRepoId}/graph`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: RepoGraphResponse | null) => {
        if (data) setGraphData(data)
      })
      .catch(() => {})

    // Fetch Repo Map
    fetch(`/api/repos/${activeRepoId}/map`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { repo_map?: string } | null) => {
        if (data?.repo_map) setRepoMapText(data.repo_map)
      })
      .catch(() => {})
  }, [activeRepoId])

  // 3. Fetch file content when a file citation is clicked
  useEffect(() => {
    if (!selectedFile || !activeRepoId) return

    setFileContent(null)
    const normalizedPath = selectedFile.path.replace(/\\/g, '/')
    const sLine = selectedFile.startLine ? Math.max(1, selectedFile.startLine - 10) : 1
    const eLine = selectedFile.endLine ? selectedFile.endLine + 25 : 100

    fetch(
      `/api/repos/${activeRepoId}/file?file_path=${encodeURIComponent(
        normalizedPath
      )}&start_line=${sLine}&end_line=${eLine}`
    )
      .then((res) => (res.ok ? res.json() : null))
      .then((data: FileContentResponse | null) => {
        if (data && typeof data.content === 'string') {
          setFileContent(data)
        }
      })
      .catch(() => {})
  }, [selectedFile, activeRepoId])

  // 4. Start repository ingestion
  const handleStartIngest = async (req: RepoInitRequest) => {
    const res = await fetch('/api/repos/init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || err.message || 'Failed to initialize repo')
    }

    const initData: RepoInitResponse = await res.json()
    setActiveRepoId(initData.repo_id)

    // Listen to real-time SSE progress
    const eventSource = new EventSource(`/api/jobs/${initData.job_id}/stream`)

    eventSource.addEventListener('progress', (e) => {
      try {
        const jobUpdate = JSON.parse(e.data) as IndexingJobResponse
        if (jobUpdate.status === 'completed' || jobUpdate.status === 'failed') {
          eventSource.close()
          fetchRepos()
        }
      } catch {
        // Ignore JSON error
      }
    })

    eventSource.onerror = () => {
      eventSource.close()
    }
  }

  // 5. Send message to LangGraph Autonomous Agent
  const handleSendMessage = async (query: string) => {
    const userMsgId = `user_${Date.now()}`
    const agentMsgId = `agent_${Date.now()}`

    const userMessage: ChatMessage = {
      id: userMsgId,
      sender: 'user',
      text: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    const agentMessage: ChatMessage = {
      id: agentMsgId,
      sender: 'agent',
      text: '',
      toolSteps: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages((prev) => [...prev, userMessage, agentMessage])
    setIsStreaming(true)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_id: activeRepoId,
          message: query,
          thread_id: threadId,
        }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`Server returned ${response.status}: ${response.statusText}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''

        for (const block of blocks) {
          if (!block.trim()) continue
          const lines = block.split('\n')
          let eventType = 'message'
          let dataStr = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              dataStr = line.slice(6).trim()
            }
          }

          if (!dataStr) continue

          try {
            const data = JSON.parse(dataStr)

            if (eventType === 'token' || data.event === 'token') {
              const token = data.content || ''
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === agentMsgId ? { ...msg, text: msg.text + token } : msg
                )
              )
            } else if (eventType === 'tool_start' || data.event === 'tool_start') {
              const newStep: ToolStep = {
                tool: data.tool || 'inspect',
                input: data.input,
                status: 'running',
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === agentMsgId
                    ? { ...msg, toolSteps: [...(msg.toolSteps || []), newStep] }
                    : msg
                )
              )
            } else if (eventType === 'tool_end' || data.event === 'tool_end') {
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== agentMsgId || !msg.toolSteps) return msg
                  const updatedSteps = [...msg.toolSteps]
                  const lastRunning = updatedSteps.findLastIndex(
                    (s) => s.tool === data.tool && s.status === 'running'
                  )
                  if (lastRunning !== -1) {
                    updatedSteps[lastRunning] = {
                      ...updatedSteps[lastRunning],
                      status: 'completed',
                      output_preview: data.output_preview,
                    }
                  }
                  return { ...msg, toolSteps: updatedSteps }
                })
              )
            } else if (eventType === 'final_answer' || data.event === 'final_answer') {
              if (data.answer) {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === agentMsgId && !msg.text ? { ...msg, text: data.answer } : msg
                  )
                )
              }
            } else if (eventType === 'error') {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === agentMsgId
                    ? {
                        ...msg,
                        text: msg.text + `\n\n*(Error: ${data.error})*`,
                      }
                    : msg
                )
              )
            }
          } catch {
            // Ignore non-JSON
          }
        }
      }
    } catch (err: unknown) {
      const errorText = err instanceof Error ? err.message : 'Unknown communication error'
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === agentMsgId
            ? {
                ...msg,
                text:
                  msg.text ||
                  `Sorry, I encountered an issue connecting to the LangGraph agent: ${errorText}`,
              }
            : msg
        )
      )
    } finally {
      setIsStreaming(false)
    }
  }

  // 6. Citation click handler: open Canvas Drawer
  const handleSelectCitation = (filePath: string, startLine?: number, endLine?: number) => {
    setSelectedFile({ path: filePath, startLine, endLine })
    setCanvasOpen(true)
  }

  // 7. Reset conversation
  const handleNewChat = () => {
    setMessages([])
  }

  const currentRepo = repos.find((r) => r.repo_id === activeRepoId)
  const totalFiles = currentRepo ? currentRepo.total_files : 96
  const totalSymbols = currentRepo ? currentRepo.total_symbols : 229

  return (
    <div className="app-root">
      {/* Left Sidebar (ChatGPT / Claude style) */}
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((prev) => !prev)}
        repositories={repos}
        activeRepoId={activeRepoId}
        onSelectRepo={setActiveRepoId}
        onOpenIngestModal={() => setIngestModalOpen(true)}
        onNewChat={handleNewChat}
        totalSymbols={totalSymbols}
      />

      {/* Main Conversational Chat (Center Column) */}
      <ChatView
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        canvasOpen={canvasOpen}
        onToggleCanvas={() => setCanvasOpen((prev) => !prev)}
        activeRepoId={activeRepoId}
        repositories={repos}
        onSelectRepo={setActiveRepoId}
        messages={messages}
        isStreaming={isStreaming}
        onSendMessage={handleSendMessage}
        onSelectCitation={handleSelectCitation}
        onNewChat={handleNewChat}
        totalFiles={totalFiles}
        totalSymbols={totalSymbols}
      />

      {/* Right Canvas Drawer (Claude Artifacts style) */}
      <CanvasDrawer
        isOpen={canvasOpen}
        onClose={() => setCanvasOpen(false)}
        activeRepoId={activeRepoId}
        selectedFile={selectedFile}
        fileContent={fileContent}
        graphData={graphData}
        repoMapText={repoMapText}
        onSelectNode={() => {}}
        onSelectCitation={handleSelectCitation}
      />

      {/* Ingest Repository Modal */}
      <IngestModal
        isOpen={ingestModalOpen}
        onClose={() => setIngestModalOpen(false)}
        onStartIngest={handleStartIngest}
      />
    </div>
  )
}

export default App
