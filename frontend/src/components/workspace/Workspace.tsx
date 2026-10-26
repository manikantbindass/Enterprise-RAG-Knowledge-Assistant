"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Copy,
  Database,
  FileText,
  Layers3,
  LayoutGrid,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
  UploadCloud,
  Users,
  Zap,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Analytics,
  api,
  bytes,
  Conversation,
  KnowledgeDocument,
  Message,
  Preview,
  Profile,
  readStream,
  Source,
} from "@/lib/runtime";

const Context = createContext<{
  me: Profile;
  documents: KnowledgeDocument[];
  refresh: () => Promise<void>;
  theme: string;
  changeTheme: (value: string) => void;
} | null>(null);
function useWorkspace() {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("Workspace context missing");
  return ctx;
}
function ErrorNotice({ error }: { error: string }) {
  return error ? (
    <div role="alert" className="error-banner">
      {error}
    </div>
  ) : null;
}
function Empty({
  icon: Icon = BookOpen,
  title,
  text,
  children,
}: {
  icon?: typeof BookOpen;
  title: string;
  text: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon size={28} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span className={`status status-${value}`}>
      <span />
      {value}
    </span>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [me, setMe] = useState<Profile | null>(null),
    [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [error, setError] = useState(""),
    [mobile, setMobile] = useState(false),
    [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState("dark"),
    [globalSearch, setGlobalSearch] = useState(""),
    [results, setResults] = useState<Source[] | null>(null);
  const refresh = useCallback(async () => {
    setDocuments(await api<KnowledgeDocument[]>("/documents"));
  }, []);
  useEffect(() => {
    // Legacy browser records are preserved but never used as the new workspace's source of truth.
    api<Profile>("/me")
      .then(setMe)
      .catch((err) => setError(err.message));
    refresh().catch((err) => setError(err.message));
    const preference = localStorage.getItem("lumina-theme") || "dark";
    setTheme(preference);
  }, [refresh]);
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: light)");
    const apply = () =>
      document.documentElement.classList.toggle(
        "light",
        theme === "light" || (theme === "system" && media.matches),
      );
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    const timer = setInterval(() => refresh().catch(() => {}), 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    setMobile(false);
  }, [path]);
  function changeTheme(value: string) {
    setTheme(value);
    localStorage.setItem("lumina-theme", value);
    document.documentElement.classList.toggle(
      "light",
      value === "light" ||
        (value === "system" &&
          matchMedia("(prefers-color-scheme: light)").matches),
    );
  }
  async function find(event: React.FormEvent) {
    event.preventDefault();
    try {
      setResults(
        await api<Source[]>("/search", {
          method: "POST",
          body: JSON.stringify({ query: globalSearch }),
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  }
  if (!me)
    return (
      <main className="connection-state">
        <Layers3 size={34} />
        <h1>
          {error ? "Connect to your workspace" : "Opening your workspace…"}
        </h1>
        {error ? (
          <>
            <ErrorNotice error={error} />
            <Link href="/" className="primary">
              Sign in
            </Link>
          </>
        ) : (
          <LoaderCircle className="spin" />
        )}
      </main>
    );
  const nav = [
    { href: "/dashboard", icon: LayoutGrid, label: "Overview" },
    { href: "/chat", icon: MessageSquare, label: "Ask knowledge" },
    { href: "/documents", icon: FileText, label: "Documents" },
    ...(me.role === "admin"
      ? [{ href: "/admin", icon: ShieldCheck, label: "Administration" }]
      : []),
    { href: "/settings", icon: Settings2, label: "Settings" },
  ];
  return (
    <Context.Provider value={{ me, documents, refresh, theme, changeTheme }}>
      <div className={`workspace ${collapsed ? "sidebar-small" : ""}`}>
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        {mobile && (
          <button
            className="mobile-backdrop"
            aria-label="Close navigation"
            onClick={() => setMobile(false)}
          />
        )}
        <aside className={`app-sidebar ${mobile ? "mobile-open" : ""}`}>
          <Link href="/dashboard" className="brand">
            <span className="brand-mark">
              <Layers3 size={22} />
            </span>
            <span className="sidebar-label">
              Lumina<span className="brand-caption">KNOWLEDGE WORKSPACE</span>
            </span>
          </Link>
          <div className="workspace-name">
            <span className="workspace-avatar">
              {me.organization.slice(0, 1).toUpperCase()}
            </span>
            <span className="sidebar-label">
              <strong>{me.organization}</strong>
              <small>Organization workspace</small>
            </span>
            <ChevronDown size={14} className="sidebar-label" />
          </div>
          <div className="nav-caption sidebar-label">WORKSPACE</div>
          <nav aria-label="Main navigation">
            {nav.map((n) => (
              <Link
                title={n.label}
                aria-current={path.startsWith(n.href) ? "page" : undefined}
                className={`nav-item ${path.startsWith(n.href) ? "active" : ""}`}
                href={n.href}
                key={n.href}
              >
                <n.icon size={19} />
                <span className="sidebar-label">{n.label}</span>
                {n.href === "/documents" && (
                  <span className="nav-count sidebar-label">
                    {documents.length}
                  </span>
                )}
              </Link>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="knowledge-pulse sidebar-label">
              <span className="live-dot" />
              <strong>Your knowledge, ready</strong>
              <p>
                {documents.filter((d) => d.status === "indexed").length}{" "}
                documents indexed
              </p>
              <Link href="/documents">
                Grow your library <ArrowUpRight size={13} />
              </Link>
            </div>
            <button
              className="collapse-button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label="Toggle sidebar"
            >
              <MoreHorizontal size={18} />
              <span className="sidebar-label">Collapse navigation</span>
            </button>
            <div className="profile-row">
              <span className="user-avatar">
                {me.name.slice(0, 2).toUpperCase()}
              </span>
              <span className="sidebar-label profile-info">
                <strong>{me.name}</strong>
                <small>{me.role}</small>
              </span>
              <button
                aria-label="Sign out"
                title="Sign out"
                className="icon-button"
                onClick={async () => {
                  try {
                    await api("/auth/logout", { method: "POST" });
                    window.location.assign("/");
                  } catch (err) {
                    setError((err as Error).message);
                  }
                }}
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
        <div className="workspace-body">
          <header className="app-header">
            <button
              aria-label="Open navigation"
              className="icon-button mobile-menu"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">
              Workspace <ChevronRight size={13} />
              <strong>{nav.find((n) => path.startsWith(n.href))?.label}</strong>
            </span>
            <form className="global-search" onSubmit={find}>
              <Search size={16} />
              <input
                aria-label="Search organization knowledge"
                placeholder="Search your knowledge…"
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
              />
              <kbd>↵</kbd>
            </form>
            <span className="header-divider" />
            <button
              className="icon-button"
              aria-label="Toggle color theme"
              onClick={() => changeTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <span className="user-avatar small">{me.name.slice(0, 1)}</span>
          </header>
          <main id="main-content" className="page-content">
            <ErrorNotice error={error} />
            {children}
            <footer className="workspace-footer">
              <span>
                <span className="live-dot" /> Server-persisted workspace
              </span>
              <span>Lumina / Enterprise RAG</span>
            </footer>
          </main>
        </div>
        <Dialog
          open={results !== null}
          onOpenChange={(open) => {
            if (!open) setResults(null);
          }}
        >
          <DialogContent className="lumina-dialog">
            <DialogTitle>Knowledge search</DialogTitle>
            <DialogDescription>
              Permitted document excerpts matching “{globalSearch}”. BM25
              ranking is not a confidence estimate.
            </DialogDescription>
            {results?.length ? (
              <div className="search-results">
                {results.map((s, i) => (
                  <div className="source-result" key={s.chunk_id}>
                    <strong>
                      {i + 1}. {s.name}
                    </strong>
                    <p>{s.excerpt}</p>
                    <Link href="/documents" className="accent">
                      Open library <ArrowRight size={13} />
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <Empty
                title="No matching evidence"
                text="Try terms used in your indexed documents."
              />
            )}
          </DialogContent>
        </Dialog>
      </div>
    </Context.Provider>
  );
}

export function Dashboard() {
  const { me, documents } = useWorkspace();
  const [data, setData] = useState<Analytics | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    api<Analytics>("/analytics")
      .then(setData)
      .catch((err) => setError(err.message));
  }, [documents]);
  const stats = [
    {
      label: "Knowledge documents",
      value: data?.documents,
      sub: `${data?.indexed || 0} indexed and searchable`,
      icon: FileText,
      color: "violet",
    },
    {
      label: "Questions explored",
      value: data?.queries,
      sub: "Across your organization",
      icon: MessageSquare,
      color: "blue",
    },
    {
      label: "Knowledge chunks",
      value: data?.chunks,
      sub: "Source-linked passages",
      icon: Database,
      color: "teal",
    },
    {
      label: "Workspace members",
      value: data?.users,
      sub: "Active organization accounts",
      icon: Users,
      color: "amber",
    },
  ];
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR KNOWLEDGE AT A GLANCE</span>
          <h1>
            Welcome back, {me.name.split(" ")[0]}{" "}
            <span className="greeting-spark">✦</span>
          </h1>
          <p>A little clarity for everything your team knows.</p>
        </div>
        <Link href="/documents" className="secondary">
          <Plus size={16} />
          Add knowledge
        </Link>
      </div>
      <ErrorNotice error={error} />
      <section className="welcome-banner">
        <div className="hero-orbit" aria-hidden="true">
          <span />
          <span />
          <span />
          <Layers3 />
        </div>
        <div className="hero-content">
          <span className="pill">
            <Sparkles size={12} /> CONNECT THE DOTS
          </span>
          <h2>
            Your next answer is
            <br />
            already in your documents.
          </h2>
          <p>
            Ask a question. Discover the context.
            <br />
            Go straight to the source.
          </p>
          <Link href="/chat" className="primary">
            Ask your knowledge <ArrowRight size={16} />
          </Link>
        </div>
        <span className="hero-footnote">
          {me.provider.configured
            ? `Connected to ${me.provider.model}`
            : "Extractive search · Configure a model for AI generation"}
        </span>
      </section>
      <div className="metric-grid">
        {stats.map((s) => (
          <div className="metric-card" key={s.label}>
            <div className="metric-top">
              <span>{s.label}</span>
              <span className={`metric-icon ${s.color}`}>
                <s.icon size={17} />
              </span>
            </div>
            <strong>{s.value ?? "—"}</strong>
            <small>{s.sub}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-columns">
        <section className="panel activity-chart">
          <div className="panel-heading">
            <div>
              <h2>Knowledge in motion</h2>
              <p>Questions asked over time</p>
            </div>
            <span className="pill neutral">
              <Clock3 size={12} />
              All time
            </span>
          </div>
          {data?.daily.length ? (
            <div
              className="chart"
              role="img"
              aria-label={`Daily query volume: ${data.daily.map((d) => `${d.date}: ${d.queries}`).join(", ")}`}
            >
              <ResponsiveContainer width="100%" height={210}>
                <AreaChart data={data.daily}>
                  <defs>
                    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#8b7cf8" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#8b7cf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    stroke="var(--border-subtle)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    stroke="var(--text-muted)"
                    fontSize={11}
                    tickFormatter={(d) => d.slice(5)}
                  />
                  <YAxis
                    allowDecimals={false}
                    stroke="var(--text-muted)"
                    fontSize={11}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--surface)",
                      borderColor: "var(--border)",
                      borderRadius: 10,
                      color: "var(--text-primary)",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="queries"
                    stroke="#9b8afb"
                    fill="url(#area)"
                    strokeWidth={2.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty
              icon={MessageSquare}
              title="Every question starts something"
              text="Your organization’s real query activity will appear here after the first conversation."
            />
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Workspace health</h2>
              <p>A live look at your library</p>
            </div>
            <Zap size={17} className="accent" />
          </div>
          <div className="health-list">
            {[
              {
                label: "Indexed documents",
                value: data?.indexed ?? 0,
                color: "teal",
              },
              {
                label: "In processing",
                value: data?.pending ?? 0,
                color: "blue",
              },
              {
                label: "Need attention",
                value: data?.failed ?? 0,
                color: "amber",
              },
            ].map((row) => (
              <div key={row.label}>
                <span>
                  <i className={`dot ${row.color}`} />
                  {row.label}
                </span>
                <strong>{row.value}</strong>
              </div>
            ))}
          </div>
          <div className="storage-meter">
            <span>
              Document storage{" "}
              <strong>{bytes(data?.storage_bytes || 0)}</strong>
            </span>
            <small>Stored on this server · 20 MB upload limit per file</small>
          </div>
        </section>
      </div>
      <section className="panel recent-documents">
        <div className="panel-heading">
          <div>
            <h2>Recently added knowledge</h2>
            <p>The latest additions to your workspace</p>
          </div>
          <Link href="/documents" className="text-link">
            View library <ArrowUpRight size={15} />
          </Link>
        </div>
        {documents.length ? (
          documents.slice(0, 4).map((d) => (
            <Link className="document-row" href="/documents" key={d.id}>
              <span className="file-icon">
                <FileText size={20} />
              </span>
              <span className="document-row-info">
                <strong>{d.name}</strong>
                <small>
                  {d.department} · {bytes(d.size)}
                </small>
              </span>
              <Status value={d.status} />
              <ArrowUpRight size={15} className="muted" />
            </Link>
          ))
        ) : (
          <Empty
            title="Make room for a little knowledge"
            text="Upload your first policy, guide or document. Your team’s next great answer starts here."
          >
            <Link href="/documents" className="secondary">
              <UploadCloud size={16} />
              Upload your first document
            </Link>
          </Empty>
        )}
      </section>
    </div>
  );
}

export function Documents() {
  const { documents, refresh, me } = useWorkspace();
  const [filter, setFilter] = useState(""),
    [status, setStatus] = useState("all"),
    [department, setDepartment] = useState("General");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [preview, setPreview] = useState<Preview | null>(null),
    [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    const failures: string[] = [];
    for (const file of Array.from(files)) {
      const body = new FormData();
      body.append("file", file);
      body.append("department", department);
      try {
        await api("/documents", { method: "POST", body });
      } catch (err) {
        failures.push(`${file.name}: ${(err as Error).message}`);
      }
    }
    setError(failures.join(" "));
    setBusy(false);
    await refresh();
    if (input.current) input.current.value = "";
  }
  async function action(id: string, kind: "delete" | "reindex") {
    if (
      kind === "delete" &&
      !confirm(
        "Permanently delete this document and its indexed passages? Saved conversation text may still contain quoted information.",
      )
    )
      return;
    try {
      await api(`/documents/${id}${kind === "reindex" ? "/reindex" : ""}`, {
        method: kind === "delete" ? "DELETE" : "POST",
      });
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const filtered = documents.filter(
    (d) =>
      d.name.toLowerCase().includes(filter.toLowerCase()) &&
      (status === "all" || d.status === status),
  );
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">THE SOURCE OF GOOD ANSWERS</span>
          <h1>Knowledge library</h1>
          <p>One place for the documents that move your team forward.</p>
        </div>
        <span className="pill neutral">
          <Database size={13} />
          {documents.length} documents
        </span>
      </div>
      <ErrorNotice error={error} />
      {me.role !== "viewer" && (
        <section
          className={`upload-zone ${drag ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (!busy) void upload(e.dataTransfer.files);
          }}
        >
          <span className="upload-icon">
            {busy ? (
              <LoaderCircle className="spin" />
            ) : (
              <UploadCloud size={28} />
            )}
          </span>
          <div>
            <h2>
              {busy
                ? "Uploading to your workspace…"
                : "A new home for your knowledge"}
            </h2>
            <p>Drop documents here, or browse your files.</p>
            <small>
              PDF, DOCX, XLSX, TXT, MD, CSV, JSON, HTML and code · Up to 20 MB
              each
            </small>
          </div>
          <div className="upload-controls">
            <label className="sr-only" htmlFor="department">
              Document department
            </label>
            <select
              id="department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            >
              {[
                "General",
                "Engineering",
                "HR",
                "Legal",
                "Finance",
                "Product",
                "Sales",
                "Marketing",
                "IT",
              ].map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
            <button
              className="primary"
              onClick={() => input.current?.click()}
              disabled={busy}
            >
              <Plus size={16} />
              Browse files
            </button>
            <input
              ref={input}
              type="file"
              multiple
              hidden
              accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.json,.html,.xml,.py,.ts,.js"
              onChange={(e) => void upload(e.target.files)}
            />
          </div>
        </section>
      )}
      <section className="panel">
        <div className="library-toolbar">
          <div className="search-field">
            <Search size={16} />
            <input
              aria-label="Filter documents by name"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Find a document…"
            />
          </div>
          <select
            aria-label="Filter by processing status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {[
              "all",
              "indexed",
              "queued",
              "extracting",
              "chunking",
              "failed",
            ].map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All statuses" : s}
              </option>
            ))}
          </select>
          <span className="muted text-xs">{filtered.length} results</span>
        </div>
        {filtered.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Passages</th>
                  <th>Added</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <button
                        className="document-name"
                        onClick={async () => {
                          try {
                            setPreview(
                              await api<Preview>(`/documents/${d.id}`),
                            );
                          } catch (err) {
                            setError((err as Error).message);
                          }
                        }}
                      >
                        <span className="file-icon">
                          <FileText size={18} />
                        </span>
                        <span>
                          <strong>{d.name}</strong>
                          <small>
                            {bytes(d.size)} ·{" "}
                            {d.name.split(".").pop()?.toUpperCase()}
                          </small>
                        </span>
                      </button>
                      {d.error && (
                        <span className="inline-error">{d.error}</span>
                      )}
                    </td>
                    <td>
                      <span className="department-tag">{d.department}</span>
                    </td>
                    <td>
                      <Status value={d.status} />
                    </td>
                    <td>{d.chunks}</td>
                    <td>
                      {new Date(d.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </td>
                    <td>
                      <div className="row-actions">
                        <a
                          aria-label={`Download ${d.name}`}
                          className="icon-button"
                          href={`/api/v2/documents/${d.id}/download`}
                        >
                          <ArrowDownToLine size={16} />
                        </a>
                        {me.role !== "viewer" && (
                          <>
                            <button
                              aria-label={`Reindex ${d.name}`}
                              className="icon-button"
                              onClick={() => void action(d.id, "reindex")}
                            >
                              <RefreshCw size={15} />
                            </button>
                            <button
                              aria-label={`Delete ${d.name}`}
                              className="icon-button danger"
                              onClick={() => void action(d.id, "delete")}
                            >
                              <Trash2 size={15} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={FileText}
            title={
              documents.length
                ? "No documents match"
                : "Your library starts here"
            }
            text={
              documents.length
                ? "Adjust your search or status filter."
                : "Upload a document to make it searchable across your workspace."
            }
          />
        )}
      </section>
      <Dialog
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
      >
        <DialogContent className="lumina-dialog">
          <DialogTitle>{preview?.name}</DialogTitle>
          <DialogDescription>
            {preview?.department} · {preview?.chunks} passages · Extracted text
            preview
          </DialogDescription>
          <div className="preview-sections">
            {preview?.sections.map((s) => (
              <section key={s.id}>
                <span className="eyebrow">
                  {s.page ? `PAGE ${s.page}` : `PASSAGE ${s.position + 1}`}
                </span>
                <p>{s.content}</p>
              </section>
            ))}
            {preview?.sections.length === 0 && (
              <p className="muted">
                {preview.error || "This document has no indexed passages yet."}
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function Chat() {
  const { me, documents } = useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]),
    [active, setActive] = useState<string | null>(null),
    [messages, setMessages] = useState<Message[]>([]);
  const [query, setQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [docId, setDocId] = useState("");
  const [source, setSource] = useState<Source | null>(null),
    [searchText, setSearchText] = useState("");
  const controller = useRef<AbortController | null>(null),
    end = useRef<HTMLDivElement>(null),
    loadVersion = useRef(0);
  const loadConversations = useCallback(
    async () => setConversations(await api<Conversation[]>("/conversations")),
    [],
  );
  useEffect(() => {
    loadConversations().catch((err) => setError(err.message));
    return () => controller.current?.abort();
  }, [loadConversations]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [messages]);
  async function select(id: string) {
    if (busy) return;
    const version = ++loadVersion.current;
    setActive(id);
    setError("");
    try {
      const loaded = await api<Message[]>(`/conversations/${id}/messages`);
      if (loadVersion.current === version) setMessages(loaded);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function submit(event?: React.FormEvent, question = query) {
    event?.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError("");
    setQuery("");
    ++loadVersion.current;
    let id = active,
      currentMessages = messages;
    try {
      if (!id) {
        const created = await api<Conversation>("/conversations", {
          method: "POST",
          body: JSON.stringify({}),
        });
        id = created.id;
        setActive(id);
        currentMessages = [];
      }
      const assistantId = crypto.randomUUID();
      setMessages([
        ...currentMessages,
        {
          id: crypto.randomUUID(),
          role: "user",
          content: question,
          sources: [],
          status: "completed",
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          sources: [],
          status: "generating",
        },
      ]);
      controller.current = new AbortController();
      const response = await fetch(`/api/v2/conversations/${id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: question,
          doc_ids: docId ? [docId] : [],
        }),
        signal: controller.current.signal,
      });
      await readStream(response, (event, value) => {
        if (event === "token")
          setMessages((old) =>
            old.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + String(value) }
                : m,
            ),
          );
        if (event === "sources")
          setMessages((old) =>
            old.map((m) =>
              m.id === assistantId ? { ...m, sources: value as Source[] } : m,
            ),
          );
        if (event === "error") setError(String(value));
        if (event === "done")
          setMessages((old) =>
            old.map((m) =>
              m.id === assistantId
                ? { ...m, status: (value as { status: string }).status }
                : m,
            ),
          );
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError")
        setError((err as Error).message);
    } finally {
      setBusy(false);
      setMessages((old) =>
        old.map((m) =>
          m.status === "generating" ? { ...m, status: "cancelled" } : m,
        ),
      );
      await loadConversations().catch((err) => setError(err.message));
    }
  }
  async function remove(id: string) {
    if (!confirm("Delete this conversation and all its messages?")) return;
    try {
      await api(`/conversations/${id}`, { method: "DELETE" });
      if (active === id) {
        setActive(null);
        setMessages([]);
      }
      await loadConversations();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  function exportChat() {
    const blob = new Blob(
      [messages.map((m) => `## ${m.role}\n\n${m.content}`).join("\n\n")],
      { type: "text/markdown" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "conversation.md";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="chat-page page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">LESS SEARCHING. MORE UNDERSTANDING.</span>
          <h1>Ask your knowledge</h1>
        </div>
        <span className="pill">
          <span className="live-dot" />
          {me.provider.configured ? me.provider.model : "Extractive search"}
        </span>
      </div>
      <div className="chat-workspace panel">
        <aside className="chat-history">
          <button
            className="secondary full"
            disabled={busy}
            onClick={() => {
              ++loadVersion.current;
              setActive(null);
              setMessages([]);
              setError("");
            }}
          >
            <Plus size={16} />
            New conversation
          </button>
          <div className="search-field">
            <Search size={14} />
            <input
              aria-label="Search conversations"
              placeholder="Find a conversation"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </div>
          <span className="nav-caption">YOUR CONVERSATIONS</span>
          {conversations
            .filter((c) =>
              c.title.toLowerCase().includes(searchText.toLowerCase()),
            )
            .map((c) => (
              <div
                className={`conversation-item ${active === c.id ? "selected" : ""}`}
                key={c.id}
              >
                <button disabled={busy} onClick={() => void select(c.id)}>
                  <MessageSquare size={15} />
                  <span>{c.title}</span>
                </button>
                <button
                  disabled={busy}
                  className="icon-button"
                  aria-label={`Delete conversation ${c.title}`}
                  onClick={() => void remove(c.id)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          {!conversations.length && (
            <p className="text-xs muted">
              Your conversations will appear here.
            </p>
          )}
          <div className="chat-history-note">
            <ShieldCheck size={17} />
            <p>
              Only permitted workspace sources are searched. Your conversations
              are private to your account.
            </p>
          </div>
        </aside>
        <section className="chat-main">
          <div className="chat-mobile-history">
            <select
              aria-label="Choose conversation"
              value={active || ""}
              disabled={busy}
              onChange={(event) => {
                if (event.target.value) void select(event.target.value);
                else {
                  ++loadVersion.current;
                  setActive(null);
                  setMessages([]);
                  setError("");
                }
              }}
            >
              <option value="">New conversation</option>
              {conversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title}
                </option>
              ))}
            </select>
            <button
              className="icon-button"
              aria-label="New conversation"
              disabled={busy}
              onClick={() => {
                ++loadVersion.current;
                setActive(null);
                setMessages([]);
                setError("");
              }}
            >
              <Plus size={17} />
            </button>
          </div>
          <div className="chat-toolbar">
            <span>
              <Sparkles size={16} />
              Knowledge assistant
            </span>
            <div>
              <select
                aria-label="Document context"
                value={docId}
                disabled={busy}
                onChange={(e) => setDocId(e.target.value)}
              >
                <option value="">All knowledge</option>
                {documents
                  .filter((d) => d.status === "indexed")
                  .map((d) => (
                    <option value={d.id} key={d.id}>
                      {d.name}
                    </option>
                  ))}
              </select>
              <button
                className="icon-button"
                aria-label="Export conversation"
                disabled={!messages.length}
                onClick={exportChat}
              >
                <ArrowDownToLine size={16} />
              </button>
              {active && (
                <button
                  className="icon-button"
                  aria-label="Rename conversation"
                  disabled={busy}
                  onClick={async () => {
                    const title = prompt("Conversation title");
                    if (title)
                      try {
                        await api(`/conversations/${active}`, {
                          method: "PATCH",
                          body: JSON.stringify({ title }),
                        });
                        await loadConversations();
                      } catch (err) {
                        setError((err as Error).message);
                      }
                  }}
                >
                  <MoreHorizontal size={17} />
                </button>
              )}
            </div>
          </div>
          <div className="chat-messages" aria-live="polite">
            {!messages.length ? (
              <div className="chat-welcome">
                <span className="assistant-emblem">
                  <Layers3 size={31} />
                </span>
                <span className="eyebrow">
                  A LITTLE CURIOSITY GOES A LONG WAY
                </span>
                <h2>
                  What would you
                  <br />
                  like to understand?
                </h2>
                <p>
                  Explore your documents. Find the details.
                  <br />
                  Every answer begins with your knowledge.
                </p>
                <div className="prompt-grid">
                  {[
                    {
                      icon: BookOpen,
                      title: "Understand a policy",
                      query:
                        "What policies and procedures are described in these documents?",
                    },
                    {
                      icon: Search,
                      title: "Find the details",
                      query: "What are the key requirements and deadlines?",
                    },
                    {
                      icon: FileText,
                      title: "Explore documentation",
                      query: "What technical processes are documented?",
                    },
                    {
                      icon: Zap,
                      title: "Discover next steps",
                      query: "What actions and responsibilities are described?",
                    },
                  ].map((p) => (
                    <button
                      disabled={busy}
                      key={p.title}
                      onClick={() => setQuery(p.query)}
                    >
                      <p.icon size={17} />
                      <span>{p.title}</span>
                      <ArrowUpRight size={14} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <article className={`chat-message ${m.role}`} key={m.id}>
                  <span
                    className={`message-avatar ${m.role === "assistant" ? "ai" : ""}`}
                  >
                    {m.role === "assistant" ? (
                      <Layers3 size={17} />
                    ) : (
                      me.name[0]
                    )}
                  </span>
                  <div className="message-body">
                    <div className="message-author">
                      {m.role === "assistant" ? "Lumina" : me.name}
                      <small>
                        {m.role === "assistant"
                          ? me.provider.configured
                            ? "AI · verify against sources"
                            : "Retrieved evidence"
                          : "You"}
                      </small>
                    </div>
                    {!m.content && m.status === "generating" ? (
                      <span className="thinking">
                        <LoaderCircle className="spin" size={14} />
                        Searching your knowledge…
                      </span>
                    ) : (
                      <div className="markdown-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {m.content}
                        </ReactMarkdown>
                      </div>
                    )}
                    {m.sources.length > 0 && (
                      <div className="message-sources">
                        <span className="eyebrow">SOURCE EVIDENCE</span>
                        <div>
                          {m.sources.map((s, i) => (
                            <button
                              key={s.chunk_id}
                              onClick={() => setSource(s)}
                            >
                              <span>{i + 1}</span>
                              <FileText size={13} />
                              <strong>{s.name}</strong>
                              {s.page && <small>p. {s.page}</small>}
                              <ArrowUpRight size={12} />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {m.role === "assistant" && m.content && (
                      <div className="message-tools">
                        <button
                          className="text-link"
                          onClick={() => {
                            navigator.clipboard
                              .writeText(m.content)
                              .catch(() =>
                                setError("Clipboard access is unavailable."),
                              );
                          }}
                        >
                          <Copy size={12} />
                          Copy
                        </button>
                        <small>{m.status}</small>
                      </div>
                    )}
                  </div>
                </article>
              ))
            )}
            <div ref={end} />
          </div>
          <div className="composer-area">
            <ErrorNotice error={error} />
            <form onSubmit={submit} className="composer">
              <textarea
                aria-label="Ask a question about your documents"
                placeholder="Ask anything about your knowledge…"
                rows={2}
                value={query}
                disabled={busy}
                maxLength={4000}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void submit();
                  }
                }}
              />
              <div className="composer-bottom">
                <span>
                  <BookOpen size={13} />
                  {docId
                    ? "Selected document"
                    : `${documents.filter((d) => d.status === "indexed").length} indexed documents`}
                </span>
                {busy ? (
                  <button
                    type="button"
                    className="send-button"
                    aria-label="Stop generation"
                    onClick={() => controller.current?.abort()}
                  >
                    <Square size={15} />
                  </button>
                ) : (
                  <button
                    className="send-button"
                    aria-label="Send question"
                    disabled={!query.trim()}
                  >
                    <Send size={17} />
                  </button>
                )}
              </div>
            </form>
            <p className="composer-disclaimer">
              {me.provider.configured
                ? "AI can make mistakes. Check the cited evidence."
                : "No AI model configured. Responses show matching source excerpts."}
            </p>
          </div>
        </section>
      </div>
      <Dialog
        open={!!source}
        onOpenChange={(open) => {
          if (!open) setSource(null);
        }}
      >
        <DialogContent className="lumina-dialog">
          <DialogTitle>{source?.name}</DialogTitle>
          <DialogDescription>
            {source?.page
              ? `Page ${source.page}`
              : `Passage ${(source?.position ?? 0) + 1}`}{" "}
            · Exact retrieved excerpt. Rank scores are not confidence
            probabilities.
          </DialogDescription>
          <blockquote className="source-excerpt">{source?.excerpt}</blockquote>
          <a
            className="secondary"
            href={`/api/v2/documents/${source?.doc_id}/download`}
          >
            <ArrowDownToLine size={16} />
            Download original
          </a>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function Settings() {
  const { me, theme, changeTheme } = useWorkspace();
  return (
    <div className="page-enter settings-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">MAKE YOURSELF AT HOME</span>
          <h1>Workspace settings</h1>
          <p>Your preferences, account and intelligence configuration.</p>
        </div>
      </div>
      <section className="panel settings-section">
        <div className="section-icon">
          <Users size={20} />
        </div>
        <div>
          <h2>Your account</h2>
          <p className="muted">Authenticated and persisted on the server.</p>
          <dl className="settings-details">
            <dt>Name</dt>
            <dd>{me.name}</dd>
            <dt>Email</dt>
            <dd>{me.email}</dd>
            <dt>Organization</dt>
            <dd>{me.organization}</dd>
            <dt>Role</dt>
            <dd>
              <span className="pill neutral">{me.role}</span>
            </dd>
          </dl>
        </div>
      </section>
      <section className="panel settings-section">
        <div className="section-icon">
          <Sun size={20} />
        </div>
        <div>
          <h2>Appearance</h2>
          <p className="muted">
            Only your appearance preference is stored in your browser.
          </p>
          <div className="theme-choices">
            {["dark", "light", "system"].map((t) => (
              <button
                className={`theme-choice ${theme === t ? "chosen" : ""}`}
                key={t}
                onClick={() => changeTheme(t)}
              >
                <span className={`theme-preview ${t}`}>
                  <i />
                  <i />
                  <i />
                </span>
                <span>
                  {t}
                  {theme === t && <Check size={14} />}
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>
      <section className="panel settings-section">
        <div className="section-icon">
          <Sparkles size={20} />
        </div>
        <div>
          <h2>Intelligence</h2>
          <p className="muted">
            AI credentials are configured on the server and never sent to this
            browser.
          </p>
          <dl className="settings-details">
            <dt>Current mode</dt>
            <dd>
              <Status
                value={me.provider.configured ? "indexed" : "extractive"}
              />
            </dd>
            <dt>Provider</dt>
            <dd>{me.provider.provider}</dd>
            <dt>Model</dt>
            <dd>{me.provider.model || "Not configured"}</dd>
            <dt>Retrieval</dt>
            <dd>Server-side lexical BM25</dd>
          </dl>
          <div className="info-banner">
            <CircleHelp size={18} />
            <p>
              To enable generation, configure RAG_PROVIDER and RAG_MODEL on the
              API server. OpenAI also requires OPENAI_API_KEY; Ollama requires a
              running local model. Restart the API after changes. Dense
              retrieval, SSO, SCIM and external connectors are planned
              capabilities.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  active: boolean;
}
interface AuditEvent {
  id: string;
  action: string;
  target: string;
  created_at: string;
}
export function Admin() {
  const { me } = useWorkspace();
  const [members, setMembers] = useState<Member[]>([]),
    [events, setEvents] = useState<AuditEvent[]>([]),
    [error, setError] = useState(""),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [users, audit] = await Promise.all([
      api<Member[]>("/admin/users"),
      api<AuditEvent[]>("/admin/audit"),
    ]);
    setMembers(users);
    setEvents(audit);
  }, []);
  useEffect(() => {
    if (me.role === "admin") load().catch((err) => setError(err.message));
  }, [load, me.role]);
  async function update(member: Member, patch: Partial<Member>) {
    try {
      await api(`/admin/users/${member.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          active: member.active,
          role: member.role,
          ...patch,
        }),
      });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api("/admin/users", {
        method: "POST",
        body: JSON.stringify(values),
      });
      setOpen(false);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (me.role !== "admin")
    return (
      <Empty
        icon={ShieldCheck}
        title="Administrator access required"
        text="Ask your organization administrator to manage membership."
      />
    );
  return (
    <div className="page-enter">
      <div className="page-heading">
        <div>
          <span className="eyebrow">A WELL-CONNECTED TEAM</span>
          <h1>Administration</h1>
          <p>
            Manage your organization’s people and review workspace activity.
          </p>
        </div>
        <button className="primary" onClick={() => setOpen(true)}>
          <Plus size={16} />
          Add member
        </button>
      </div>
      <ErrorNotice error={error} />
      <div className="info-banner">
        <ShieldCheck size={19} />
        <p>
          Local identity mode: administrators create accounts directly. Email
          invitations, enterprise federation and MFA are not configured.
          Deactivating an account immediately revokes its sessions.
        </p>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Workspace members</h2>
            <p>
              {members.length} accounts in {me.organization}
            </p>
          </div>
          <Users size={19} className="muted" />
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Member</th>
                <th>Role</th>
                <th>Access</th>
                <th>Manage</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id}>
                  <td>
                    <strong>{m.name}</strong>
                    <small className="block muted">{m.email}</small>
                  </td>
                  <td>
                    <select
                      aria-label={`Role for ${m.name}`}
                      disabled={m.id === me.id}
                      value={m.role}
                      onChange={(e) => void update(m, { role: e.target.value })}
                    >
                      {["admin", "member", "viewer"].map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <Status value={m.active ? "active" : "inactive"} />
                  </td>
                  <td>
                    <button
                      className="text-link"
                      disabled={m.id === me.id}
                      onClick={() => void update(m, { active: !m.active })}
                    >
                      {m.id === me.id
                        ? "You"
                        : m.active
                          ? "Deactivate"
                          : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel audit-panel">
        <div className="panel-heading">
          <div>
            <h2>Audit trail</h2>
            <p>The latest 100 server-recorded events</p>
          </div>
          <Clock3 size={18} className="muted" />
        </div>
        {events.map((e) => (
          <div className="audit-row" key={e.id}>
            <span className="audit-mark">
              <ShieldCheck size={15} />
            </span>
            <div>
              <strong>{e.action.replaceAll(".", " / ")}</strong>
              <small>{e.target || "Organization workspace"}</small>
            </div>
            <time>{new Date(e.created_at).toLocaleString()}</time>
          </div>
        ))}
      </section>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="lumina-dialog">
          <DialogTitle>Add a workspace member</DialogTitle>
          <DialogDescription>
            Create an account in your organization. Share credentials privately;
            this local edition has no email invitation service.
          </DialogDescription>
          <form onSubmit={create} className="member-form">
            <label>
              Name
              <input name="name" required maxLength={100} />
            </label>
            <label>
              Email
              <input name="email" type="email" required />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
              />
            </label>
            <label>
              Role
              <select name="role">
                <option value="member">Member — upload and search</option>
                <option value="viewer">Viewer — read and search</option>
                <option value="admin">Administrator</option>
              </select>
            </label>
            <ErrorNotice error={error} />
            <button className="primary" disabled={busy}>
              {busy ? "Creating…" : "Create member"}
              <ArrowRight size={16} />
            </button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
