"use client";

import { useState } from "react";
import Image from "next/image";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  Code2,
  Database,
  FileText,
  Github,
  Layers3,
  MessageSquare,
  Monitor,
  ShieldCheck,
  Smartphone,
  Sparkles,
} from "lucide-react";
import "./showcase.css";

const repository =
  "https://github.com/manikantbindass/Enterprise-RAG-Knowledge-Assistant";
const screens = [
  {
    id: "dashboard",
    name: "Overview",
    icon: Monitor,
    title: "Everything your knowledge is becoming.",
    description:
      "A calm overview of indexed documents, source passages, query activity, and workspace health. Every figure in the working local app comes from persisted records.",
    alt: "Lumina dark dashboard showing the fictional demo workspace, three indexed documents, query activity and workspace health",
  },
  {
    id: "documents",
    name: "Document library",
    icon: FileText,
    title: "A home for the details that matter.",
    description:
      "Upload, index, filter, preview, reindex, and download documents. Real PDF, DOCX, XLSX and text parsing turns files into searchable source passages.",
    alt: "Lumina document library containing three explicitly fictional sample documents across HR, Engineering and IT",
  },
  {
    id: "chat",
    name: "Ask knowledge",
    icon: MessageSquare,
    title: "From a question to the evidence.",
    description:
      "Persistent conversations bring retrieved evidence into focus. Open a citation to inspect its exact source. Without a configured model, responses are clearly labeled retrieved excerpts.",
    alt: "Lumina conversation answering an annual leave question with retrieved passages and clickable source evidence",
  },
  {
    id: "mobile",
    name: "On the move",
    icon: Smartphone,
    title: "Knowledge goes where you do.",
    description:
      "Mobile navigation, conversation selection and a comfortable composer adapt the workspace to smaller screens. Dark, light and live system appearance are supported.",
    alt: "Lumina mobile chat in light mode with responsive navigation and conversation selection",
  },
];

export default function Showcase() {
  const [selected, setSelected] = useState(0);
  const screen = screens[selected];
  return (
    <div className="showcase-site">
      <header className="showcase-nav">
        <a className="brand" href="#">
          <span className="brand-mark">
            <Layers3 size={22} />
          </span>
          Lumina<span className="showcase-nav-label">KNOWLEDGE</span>
        </a>
        <nav aria-label="Showcase navigation">
          <a href="#product-tour">Product tour</a>
          <a href="#how-it-works">How it works</a>
          <a href="#run-locally">Try locally</a>
        </nav>
        <a
          className="showcase-github"
          href={repository}
          target="_blank"
          rel="noreferrer"
        >
          <Github size={16} />
          <span>View on GitHub</span>
          <ArrowUpRight size={13} />
        </a>
      </header>
      <main>
        <section className="showcase-hero">
          <div className="showcase-ambient" aria-hidden="true" />
          <span className="showcase-eyebrow">
            <span /> ENTERPRISE RAG · OPEN SOURCE PROJECT
          </span>
          <h1>
            Scattered knowledge.
            <br />
            <span>Connected understanding.</span>
          </h1>
          <p>
            A thoughtful workspace for your documents, questions, and the
            evidence behind every answer. Meet Lumina.
          </p>
          <div className="showcase-actions">
            <a className="showcase-primary" href="#product-tour">
              Explore the workspace <ArrowRight size={17} />
            </a>
            <a
              className="showcase-secondary"
              href={`${repository}#quick-start`}
              target="_blank"
              rel="noreferrer"
            >
              <Code2 size={17} />
              Run the full app
            </a>
          </div>
          <div className="showcase-mode">
            <span />
            Public frontend showcase <i />
            Real app screenshots · Fictional sample knowledge
          </div>
          <a
            className="showcase-scroll"
            href="#product-tour"
            aria-label="Scroll to product tour"
          >
            <ArrowDown size={17} />
          </a>
        </section>
        <section className="showcase-tour" id="product-tour">
          <div className="showcase-section-heading">
            <span className="showcase-eyebrow">01 / A CLOSER LOOK</span>
            <h2>
              A little clarity.
              <br />
              Across your whole workspace.
            </h2>
            <p>
              Explore actual screens captured from the running local
              application.
            </p>
          </div>
          <div
            className="showcase-tabs"
            role="tablist"
            aria-label="Application screens"
          >
            {screens.map((item, index) => (
              <button
                key={item.id}
                id={`tab-${item.id}`}
                role="tab"
                aria-selected={selected === index}
                aria-controls="screen-panel"
                tabIndex={selected === index ? 0 : -1}
                className={selected === index ? "selected" : ""}
                onClick={() => setSelected(index)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                    event.preventDefault();
                    const next =
                      (selected +
                        (event.key === "ArrowRight" ? 1 : -1) +
                        screens.length) %
                      screens.length;
                    setSelected(next);
                    document.getElementById(`tab-${screens[next].id}`)?.focus();
                  }
                }}
              >
                <item.icon size={16} />
                {item.name}
              </button>
            ))}
          </div>
          <div
            id="screen-panel"
            role="tabpanel"
            aria-labelledby={`tab-${screen.id}`}
            className="showcase-screen-panel"
          >
            <div className="showcase-browser-bar">
              <span>
                <i />
                <i />
                <i />
              </span>
              <div>
                <ShieldCheck size={12} />
                lumina / {screen.id}
              </div>
              <span className="showcase-preview-badge">LOCAL APP CAPTURE</span>
            </div>
            <a
              className={`showcase-screen ${screen.id === "mobile" ? "phone" : ""}`}
              href={`/showcase/${screen.id}.png`}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open full-size ${screen.name} screenshot`}
            >
              <Image
                src={`/showcase/${screen.id}.png`}
                alt={screen.alt}
                width={screen.id === "mobile" ? 390 : 1440}
                height={screen.id === "mobile" ? 1100 : 1400}
                unoptimized
                priority={selected === 0}
              />
            </a>
          </div>
          <div className="showcase-screen-caption">
            <div>
              <span className="showcase-eyebrow">
                {screen.name.toUpperCase()}
              </span>
              <h3>{screen.title}</h3>
            </div>
            <p>{screen.description}</p>
          </div>
        </section>
        <section className="showcase-features">
          <article>
            <span>
              <BookOpen size={23} />
            </span>
            <h3>Knowledge, with a source</h3>
            <p>
              Search actual document passages and follow citations to the
              evidence. Real page references where available.
            </p>
          </article>
          <article>
            <span>
              <ShieldCheck size={23} />
            </span>
            <h3>A workspace of your own</h3>
            <p>
              Server-verified credentials, revocable sessions,
              organization-scoped records, and administrator controls in the
              local runtime.
            </p>
          </article>
          <article>
            <span>
              <Sparkles size={23} />
            </span>
            <h3>Intelligence you configure</h3>
            <p>
              Start with honest extractive search. Configure OpenAI or Ollama on
              your server for streamed AI generation.
            </p>
          </article>
        </section>
        <section className="showcase-pipeline" id="how-it-works">
          <div className="showcase-section-heading">
            <span className="showcase-eyebrow">
              02 / FROM FILES TO FINDINGS
            </span>
            <h2>
              Your knowledge.
              <br />A clearer path through it.
            </h2>
          </div>
          <div className="showcase-pipeline-steps">
            {[
              {
                icon: FileText,
                name: "Bring your files",
                description: "PDF · DOCX · XLSX · Text",
              },
              {
                icon: Layers3,
                name: "Build the context",
                description: "Extract · Chunk · Index",
              },
              {
                icon: Database,
                name: "Find the evidence",
                description: "Tenant-scoped BM25 retrieval",
              },
              {
                icon: MessageSquare,
                name: "Ask & understand",
                description: "Citations · Saved conversations",
              },
            ].map((step, index) => (
              <div key={step.name}>
                <span className="pipeline-number">0{index + 1}</span>
                <step.icon size={25} />
                <h3>{step.name}</h3>
                <p>{step.description}</p>
                {index < 3 && (
                  <ChevronRight className="pipeline-arrow" size={18} />
                )}
              </div>
            ))}
          </div>
          <div className="showcase-honesty">
            <ShieldCheck size={18} />
            <p>
              This deployment is a public visual showcase. Authentication,
              uploads and chat run in the separately started local app; a hosted
              backend is not connected here. The complete enterprise roadmap
              remains in development.
            </p>
          </div>
        </section>
        <section className="showcase-local" id="run-locally">
          <div>
            <span className="showcase-eyebrow">
              03 / MAKE IT YOUR WORKSPACE
            </span>
            <h2>
              See the design.
              <br />
              <span>Then try the real thing.</span>
            </h2>
            <p>
              Clone the repository, start the frontend and API, and seed the
              optional demo workspace. Three fictional sample documents give you
              a place to begin.
            </p>
            <a
              className="showcase-primary"
              href={`${repository}#quick-start`}
              target="_blank"
              rel="noreferrer"
            >
              Get started on GitHub <ArrowUpRight size={17} />
            </a>
          </div>
          <div className="showcase-demo-card">
            <span className="showcase-demo-label">
              <span /> LOCAL DEMO ACCESS
            </span>
            <h3>Your first look inside.</h3>
            <dl>
              <dt>Email</dt>
              <dd>demo@lumina.local</dd>
              <dt>Password</dt>
              <dd>
                <code>LuminaDemo!2026</code>
              </dd>
              <dt>Workspace</dt>
              <dd>Lumina Demo</dd>
            </dl>
            <div>
              <Check size={14} />
              Opt-in demo seed · Fictional documents only
            </div>
            <p>
              These public credentials work after running the local seed command
              in the README. They do not provide a hosted login.
            </p>
          </div>
        </section>
      </main>
      <footer className="showcase-footer">
        <a className="brand" href="#">
          <span className="brand-mark">
            <Layers3 size={18} />
          </span>
          Lumina
        </a>
        <p>Less searching. More understanding.</p>
        <a href={repository} target="_blank" rel="noreferrer">
          Explore the source <Github size={15} />
          <ArrowUpRight size={12} />
        </a>
      </footer>
    </div>
  );
}
