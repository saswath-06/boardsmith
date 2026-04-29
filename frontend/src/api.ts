import type {
  JobSnapshot,
  JobSummary,
  LineageEntry,
  PipelineEvent,
} from "./types";
import { getAccessToken } from "./lib/auth";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface CreateJobResponse {
  job_id: string;
}

async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export async function createJob(
  description: string,
  image?: File | null,
): Promise<CreateJobResponse> {
  // multipart/form-data so an optional sketch/photo can be attached. We
  // intentionally don't set Content-Type — the browser fills in the
  // multipart boundary parameter automatically when given a FormData.
  const form = new FormData();
  form.set("description", description ?? "");
  if (image) form.set("image", image, image.name);
  const res = await authFetch(`/api/jobs`, { method: "POST", body: form });
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
  const res = await authFetch(`/api/jobs/${parentId}/refine`, {
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
  const res = await authFetch(`/api/jobs`);
  if (!res.ok) throw new Error(`Failed to list jobs: ${res.status}`);
  return (await res.json()) as JobSummary[];
}

export async function getJob(jobId: string): Promise<JobSnapshot> {
  const res = await authFetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch job: ${res.status}`);
  return (await res.json()) as JobSnapshot;
}

export async function getLineage(jobId: string): Promise<LineageEntry[]> {
  const res = await authFetch(`/api/jobs/${jobId}/lineage`);
  if (!res.ok) throw new Error(`Failed to fetch lineage: ${res.status}`);
  return (await res.json()) as LineageEntry[];
}

export async function deleteJob(jobId: string): Promise<string[]> {
  // Returns the list of job_ids that were actually deleted — the cascade
  // includes any descendant revisions so the caller can drop them too.
  const res = await authFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to delete job: ${res.status} ${text}`);
  }
  const body = (await res.json()) as { deleted: string[] };
  return body.deleted ?? [];
}

export async function publishJob(
  jobId: string,
): Promise<{ public: boolean; share_url: string }> {
  const res = await authFetch(`/api/jobs/${jobId}/publish`, { method: "POST" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to publish job: ${res.status} ${text}`);
  }
  return (await res.json()) as { public: boolean; share_url: string };
}

export async function getPublicJob(jobId: string): Promise<JobSnapshot> {
  // No auth — the backend gates on the job's is_public flag.
  const res = await fetch(`${API_URL}/api/public/jobs/${jobId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch public job: ${res.status} ${text}`);
  }
  return (await res.json()) as JobSnapshot;
}

/** Open an SSE stream for a job. EventSource can't set headers, so we
 *  pass the Supabase JWT in a query param. The backend accepts either. */
export async function subscribeToJob(
  jobId: string,
  onEvent: (event: PipelineEvent) => void,
  onError?: (err: Event) => void
): Promise<EventSource> {
  const token = await getAccessToken();
  const url = new URL(`${API_URL}/api/jobs/${jobId}/events`);
  if (token) url.searchParams.set("token", token);
  const source = new EventSource(url.toString());
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

/** Resolve an absolute URL for an artifact path. Note that this returns
 *  an unauthenticated URL; for authenticated downloads, browsers can't
 *  attach an Authorization header to a plain `<a download>`. We accept
 *  this trade-off for now: artifact endpoints validate ownership server-
 *  side via the JWT in a `token` query param when needed. */
export function artifactUrl(path: string | null | undefined, token?: string | null): string {
  if (!path) return "";
  const base = path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}
