/**
 * TypeScript type definitions for Agentic-Code-RAG frontend workspace.
 */

export type JobStatus =
  | 'queued'
  | 'cloning'
  | 'scanning'
  | 'ast_parsing'
  | 'indexing'
  | 'completed'
  | 'failed'

export interface RepoSummary {
  repo_id: string
  total_files: number
  languages: string[]
  total_symbols: number
  last_indexed_at?: string
}

export interface RepoListResponse {
  repositories: RepoSummary[]
}

export interface RepoInitRequest {
  repo_id: string
  source_type: 'local' | 'git'
  source_path: string
  branch?: string
}

export interface RepoInitResponse {
  job_id: string
  repo_id: string
  status: JobStatus
  message: string
}

export interface IndexingJobResponse {
  job_id: string
  repo_id: string
  status: JobStatus
  progress_pct: number
  current_phase: string
  telemetry_logs: string[]
  error_msg?: string | null
  created_at: string
  updated_at: string
}

export interface GraphNode {
  id: string
  name: string
  kind: string
  file_path: string
  line: number
  pagerank_score: number
}

export interface GraphEdge {
  source: string
  target: string
  edge_type: string
}

export interface RepoGraphResponse {
  repo_id: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface FileContentResponse {
  repo_id: string
  file_path: string
  total_lines: number
  start_line: number
  end_line: number
  content: string
}

export interface ToolStep {
  tool: string
  input?: Record<string, unknown>
  output_preview?: string
  status: 'running' | 'completed'
}

export interface ChatMessage {
  id: string
  sender: 'user' | 'agent'
  text: string
  toolSteps?: ToolStep[]
  timestamp: string
}
