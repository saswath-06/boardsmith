import type {
  JobSnapshot,
  JobSummary,
  LineageEntry,
  PipelineEvent,
} from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface CreateJobResponse {
  job_id: string;
}

export async function createJob(description: string): Promise<CreateJobResponse> {
  const res = await fetch(`${API_URL}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to create job: ${res.status} ${text}`);
  }
  return (await res.json()) as CreateJobResponse;
}

export async function refineJob(
  parentId: string,
  instruction: string
): Promise<CreateJobResponse> {
  const res = await fetch(`${API_URL}/api/jobs/${parentId}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to refine job: ${res.status} ${text}`);
  }
  return (await res.json()) as CreateJobResponse;
}

export async function listJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${API_URL}/api/jobs`);
  if (!res.ok) throw new Error(`Failed to list jobs: ${res.status}`);
  return (await res.json()) as JobSummary[];
}

export async function getJob(jobId: string): Promise<JobSnapshot> {
  const res = await fetch(`${API_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch job: ${res.status}`);
  return (await res.json()) as JobSnapshot;
}

export async function getLineage(jobId: string): Promise<LineageEntry[]> {
  const res = await fetch(`${API_URL}/api/jobs/${jobId}/lineage`);
  if (!res.ok) throw new Error(`Failed to fetch lineage: ${res.status}`);
  return (await res.json()) as LineageEntry[];
}

export function subscribeToJob(
  jobId: string,
  onEvent: (event: PipelineEvent) => void,
  onError?: (err: Event) => void
): EventSource {
  const source = new EventSource(`${API_URL}/api/jobs/${jobId}/events`);
  source.onmessage = (msg: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(msg.data) as PipelineEvent;
      onEvent(parsed);
    } catch (err) {
      console.error("Failed to parse SSE event", err, msg.data);
    }
  };
  if (onError) source.onerror = onError;
  return source;
}

// Resolve an absolute URL for an artifact path returned by the backend
// (which may already be absolute or relative like "/api/jobs/<id>/artifact/<name>")
export function artifactUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
