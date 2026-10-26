export interface Provider {
  provider: string;
  model: string;
  configured: boolean;
  mode: string;
}
export interface Profile {
  id: string;
  name: string;
  email: string;
  role: string;
  organization: string;
  active: boolean;
  provider: Provider;
}
export interface KnowledgeDocument {
  id: string;
  name: string;
  size: number;
  department: string;
  status: string;
  error?: string;
  created_at: string;
  chunks: number;
}
export interface Source {
  chunk_id: string;
  doc_id: string;
  name: string;
  page: number | null;
  position: number;
  excerpt: string;
  score: number;
}
export interface Message {
  id: string;
  role: string;
  content: string;
  sources: Source[];
  status: string;
}
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}
export interface Analytics {
  documents: number;
  indexed: number;
  pending: number;
  failed: number;
  chunks: number;
  queries: number;
  users: number;
  storage_bytes: number;
  average_latency_ms: number;
  daily: { date: string; queries: number }[];
  departments: { name: string; documents: number }[];
}
export interface Preview extends KnowledgeDocument {
  sections: {
    id: string;
    page: number | null;
    position: number;
    content: string;
  }[];
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/v2${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg;
    throw new Error(
      detail ||
        `Request failed (${response.status}). Ensure the API is running.`,
    );
  }
  return response.json() as Promise<T>;
}

export async function readStream(
  response: Response,
  onEvent: (event: string, data: unknown) => void,
) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Unable to start the answer stream.");
  }
  if (!response.body)
    throw new Error("Streaming is unavailable in this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    completed = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event =
          frame
            .split("\n")
            .find((l) => l.startsWith("event:"))
            ?.slice(6)
            .trim() || "message";
        const data = frame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (data) onEvent(event, JSON.parse(data));
        if (event === "done") completed = true;
      }
      if (done) break;
    }
    if (!completed)
      throw new Error(
        "The response connection ended early. Reload the conversation to check saved results.",
      );
  } finally {
    reader.releaseLock();
  }
}

export function bytes(value: number) {
  return value >= 1048576
    ? `${(value / 1048576).toFixed(1)} MB`
    : value >= 1024
      ? `${(value / 1024).toFixed(1)} KB`
      : `${value} B`;
}
