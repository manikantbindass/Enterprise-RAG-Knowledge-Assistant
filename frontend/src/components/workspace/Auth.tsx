"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Layers3,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/runtime";

export default function Auth({ register = false }: { register?: boolean }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      window.location.assign("/dashboard");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <main className="auth-scene">
      <section className="auth-story">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <Layers3 size={23} />
          </span>{" "}
          Lumina <span className="brand-caption">KNOWLEDGE</span>
        </Link>
        <div className="auth-story-content">
          <span className="eyebrow">
            <span className="live-dot" /> YOUR ORGANIZATION, CONNECTED
          </span>
          <h1>
            Great answers.
            <br />
            Already in
            <br />
            <span className="gradient-text">your knowledge.</span>
          </h1>
          <p>
            Bring your documents together. Turn scattered information into clear
            answers, with the evidence always one click away.
          </p>
          <div className="auth-proof">
            <BookOpen />
            <div>
              <strong>Knowledge with a source</strong>
              <span>Search real documents. Follow every citation.</span>
            </div>
          </div>
          <div className="auth-proof">
            <ShieldCheck />
            <div>
              <strong>A workspace of your own</strong>
              <span>Server-side sessions and organization-scoped access.</span>
            </div>
          </div>
        </div>
        <span className="muted text-xs">
          Enterprise RAG Knowledge Assistant · Local workspace
        </span>
      </section>
      <section className="auth-form-panel">
        <form onSubmit={submit} className="auth-form">
          <span className="icon-tile">
            <Sparkles size={24} />
          </span>
          <h2>{register ? "Create your workspace" : "Welcome back"}</h2>
          <p className="muted">
            {register
              ? "Start a private knowledge library for your organization."
              : "Sign in to your organization’s knowledge workspace."}
          </p>
          {register && (
            <>
              <label>
                Your name
                <input
                  name="name"
                  required
                  maxLength={100}
                  autoComplete="name"
                  placeholder="Alex Morgan"
                />
              </label>
              <label>
                Organization
                <input
                  name="organization"
                  required
                  maxLength={100}
                  placeholder="Acme workspace"
                />
              </label>
            </>
          )}
          <label>
            Email address
            <input
              name="email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@company.com"
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              minLength={12}
              maxLength={128}
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="At least 12 characters"
            />
          </label>
          {error && (
            <p className="error-banner" role="alert">
              {error}
            </p>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? "Connecting…" : register ? "Create workspace" : "Sign in"}
            <ArrowRight size={17} />
          </button>
          <p className="text-sm muted">
            {register ? "Already have a workspace?" : "New here?"}{" "}
            <Link href={register ? "/" : "/register"} className="accent">
              {register ? "Sign in" : "Create a workspace"}
            </Link>
          </p>
          <div className="auth-note">
            <ShieldCheck size={16} />
            <span>
              Credentials are verified on the server. Each workspace starts
              empty. SSO and email recovery are not configured in this local
              edition.
            </span>
          </div>
        </form>
      </section>
    </main>
  );
}
