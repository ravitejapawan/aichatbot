import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const ThemeIcon = ({ theme }) => (
  <svg
    className="theme-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {theme === "dark" ? (
      <>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
      </>
    ) : (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2.2" />
        <path d="M12 19.8V22" />
        <path d="M4.93 4.93l1.56 1.56" />
        <path d="M17.51 17.51l1.56 1.56" />
        <path d="M2 12h2.2" />
        <path d="M19.8 12H22" />
        <path d="M4.93 19.07l1.56-1.56" />
        <path d="M17.51 6.49l1.56-1.56" />
      </>
    )}
  </svg>
);

const FeedbackIcon = ({ type }) => {
  const isLike = type === "like";

  return (
    <svg
      className="feedback-icon"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      {isLike ? (
        <>
          <path d="M8.864.325c-.956-.063-1.843.484-2.187 1.419l-.016.04L4.2 7.714v7.79l1.74 1.744A2 2 0 0 0 7.354 19h6.357a2 2 0 0 0 1.95-1.557l1.56-6.241A2 2 0 0 0 15.28 8H12V4.5A2.5 2.5 0 0 0 9.864 2.025z" />
          <path d="M4 8H2a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2z" />
        </>
      ) : (
        <>
          <path d="M8.864 23.675c-.956.063-1.843-.484-2.187-1.419l-.016-.04L4.2 16.286V8.496l1.74-1.744A2 2 0 0 1 7.354 6h6.357a2 2 0 0 1 1.95 1.557l1.56 6.241A2 2 0 0 1 15.28 17H12v3.5a2.5 2.5 0 0 1-2.136 2.475z" />
          <path d="M4 16H2a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2z" />
        </>
      )}
    </svg>
  );
};

function App() {
  const scopeOptions = [
    { value: "auto", label: "Auto route" },
    { value: "kinexushhd", label: "KINEXUS HHD" },
    { value: "nx2meapp", label: "Nx2meApp" },
  ];
  const [selectedApp, setSelectedApp] = useState("auto");
  const [isScopeMenuOpen, setIsScopeMenuOpen] = useState(false);
  const [theme, setTheme] = useState(() => {
    const savedTheme = window.localStorage.getItem("chatbot-theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      return savedTheme;
    }

    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const chatRef = useRef(null);
  const messagesEndRef = useRef(null);
  const scopeMenuRef = useRef(null);
  const selectedScopeLabel =
    scopeOptions.find((option) => option.value === selectedApp)?.label || "Auto route";

  useLayoutEffect(() => {
    if (!chatRef.current || !messagesEndRef.current) return;

    const frameId = window.requestAnimationFrame(() => {
      messagesEndRef.current.scrollIntoView({
        block: "end",
        behavior: messages.length > 0 || isSending ? "smooth" : "auto",
      });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [messages, isSending]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("chatbot-theme", theme);
  }, [theme]);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (!scopeMenuRef.current?.contains(event.target)) {
        setIsScopeMenuOpen(false);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setIsScopeMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  useEffect(() => {
    let visibleTimerId = null;

    const setPageState = (state) => {
      document.documentElement.setAttribute("data-page-state", state);
    };

    const handleVisibilityChange = () => {
      if (visibleTimerId) {
        window.clearTimeout(visibleTimerId);
        visibleTimerId = null;
      }

      if (document.hidden) {
        setPageState("hidden");
        return;
      }

      setPageState("stabilizing");
      visibleTimerId = window.setTimeout(() => {
        setPageState("active");
        visibleTimerId = null;
      }, 250);
    };

    handleVisibilityChange();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      if (visibleTimerId) {
        window.clearTimeout(visibleTimerId);
      }
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const createMessage = (role, text) => ({
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    feedback: null,
    createdAt: new Date().toISOString(),
    sourceQuestion: "",
  });

  const appendToMessage = (id, text) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id
          ? {
              ...message,
              text: `${message.text}${text}`,
            }
          : message
      )
    );
  };

  const updateMessage = (id, updates) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id
          ? {
              ...message,
              isComplete: true,
              ...updates,
            }
          : message
      )
    );
  };

  const buildHistoryPayload = (items) =>
    items
      .filter((message) => message.role === "user" || message.role === "bot")
      .slice(-4)
      .map((message) => ({
        role: message.role === "bot" ? "assistant" : "user",
        text: message.text,
      }));

  const setMessageFeedback = (id, feedback) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.id === id
          ? {
              ...message,
              feedback,
            }
          : message
      )
    );
  };

  const formatTime = (value) =>
    new Intl.DateTimeFormat("en", {
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value));

  const buildFigureContextParam = (source) => {
    const raw = String(source?.text || "").replace(/\s+/g, " ").trim();
    if (!raw) {
      return "";
    }
    return encodeURIComponent(raw.slice(0, 220));
  };

  const getRenderableImageSources = (sources) => {
    if (!Array.isArray(sources) || !sources.length) {
      return [];
    }

    const seen = new Set();
    const renderable = [];

    for (const source of sources) {
      const page = Number(source?.page);
      const collection = String(source?.collection || "").trim();
      if (!collection || !Number.isFinite(page) || page < 1) {
        continue;
      }

      const section = encodeURIComponent(String(source?.section || ""));
      const context = buildFigureContextParam(source);
      const query = context ? `?section=${section}&context=${context}` : `?section=${section}`;
      const url = `http://127.0.0.1:8000/kb-figures/${encodeURIComponent(collection)}/${page}${query}`;
      if (seen.has(url)) {
        continue;
      }
      seen.add(url);

      renderable.push({
        url,
        section: source?.section || `Page ${page}`,
        page,
      });
      if (renderable.length >= 1) {
        return renderable;
      }
    }

    for (const source of sources) {
      const imageUrl = String(source?.image_url || "").trim();
      if (!imageUrl) {
        continue;
      }

      const absoluteUrl = imageUrl.startsWith("http")
        ? imageUrl
        : `http://127.0.0.1:8000${imageUrl.startsWith("/") ? imageUrl : `/${imageUrl}`}`;

      if (seen.has(absoluteUrl)) {
        continue;
      }
      seen.add(absoluteUrl);

      renderable.push({
        url: absoluteUrl,
        section: source?.section || "Reference image",
        page: source?.page,
      });
      if (renderable.length >= 1) {
        return renderable;
      }
    }

    return renderable;
  };

  const shouldRenderImagesForMessage = (message, index, allMessages) => {
    if (!message || message.role !== "bot") return false;
    if (!message.isComplete || !String(message.text || "").trim()) return false;

    const sourceQuestion = String(message.sourceQuestion || "").toLowerCase();
    if (sourceQuestion.includes("show reference images") || sourceQuestion.includes("image")) {
      return true;
    }

    const previous = index > 0 ? allMessages[index - 1] : null;
    const previousText = String(previous?.text || "").toLowerCase();
    return previous?.role === "user" && (
      previousText.includes("show reference images") ||
      previousText.includes("show images") ||
      previousText.includes("show image")
    );
  };

  const submitFeedback = async (message, feedback) => {
    if (!message?.sourceQuestion || message.feedback === feedback) return;

    setMessageFeedback(message.id, feedback);

    try {
      await axios.post(`http://127.0.0.1:8000/feedback/${feedback}`, {
        message_id: message.id,
        question: message.sourceQuestion,
        answer: message.text,
        created_at: message.createdAt,
      });
    } catch (err) {
      console.error(`Failed to save ${feedback} feedback`, err);
    }
  };

  const send = async () => {
    const question = input.trim();
    if (!question || isSending) return;

    const userMsg = createMessage("user", question);
    const nextMessages = [...messages, userMsg];
    const botMsg = {
      ...createMessage("bot", ""),
      sourceQuestion: question,
      routing: null,
      sources: [],
      isComplete: false,
    };
    setError("");
    setIsSending(true);
    setInput("");
    setMessages([...messages, userMsg, botMsg]);

    try {
      const response = await fetch("http://127.0.0.1:8000/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question,
          ...(selectedApp !== "auto" ? { app: selectedApp } : {}),
          history: buildHistoryPayload(nextMessages.slice(0, -1)),
        }),
      });

      if (!response.ok || !response.body) {
        let detail = "Backend request failed.";
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch (streamError) {
          detail = "Backend request failed. Check that FastAPI is running on http://127.0.0.1:8000 and CORS is enabled.";
        }
        throw new Error(detail);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;

          const event = JSON.parse(line);
          if (event.type === "meta") {
            updateMessage(botMsg.id, {
              routing: event.routing || null,
              sources: event.sources || [],
              isComplete: false,
            });
          } else if (event.type === "token") {
            appendToMessage(botMsg.id, event.text || "");
          } else if (event.type === "done") {
            updateMessage(botMsg.id, {
              isComplete: true,
            });
          } else if (event.type === "error") {
            throw new Error(event.detail || "Streaming request failed.");
          }
        }
      }

      if (buffer.trim()) {
        const event = JSON.parse(buffer.trim());
        if (event.type === "meta") {
          updateMessage(botMsg.id, {
            routing: event.routing || null,
            sources: event.sources || [],
            isComplete: false,
          });
        } else if (event.type === "token") {
          appendToMessage(botMsg.id, event.text || "");
        } else if (event.type === "done") {
          updateMessage(botMsg.id, {
            isComplete: true,
          });
        } else if (event.type === "error") {
          throw new Error(event.detail || "Streaming request failed.");
        }
      }

      setMessages((prev) =>
        prev.map((message) =>
          message.id === botMsg.id && !message.text.trim()
            ? {
                ...message,
                text: "I could not find this in the knowledge base. Please check with the L3 administration team.",
              }
            : message
        )
      );
    } catch (err) {
      const message =
        err.response?.data?.detail ||
        err.message ||
        "Backend request failed. Check that FastAPI is running on http://127.0.0.1:8000 and CORS is enabled.";
      setError(message);
      updateMessage(botMsg.id, {
        text: "I could not reach the backend service.",
        isComplete: true,
      });
    } finally {
      setIsSending(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter") {
      send();
    }
  };

  return (
    <div className="page-shell">
      <div className="page-backdrop" aria-hidden="true" />
      <div className="ambient ambient-left" />
      <div className="ambient ambient-right" />

      <main className="app-card">
        <section className="hero">
          <div className="hero-stage" aria-hidden="true">
            <div className="hero-stage-grid" />
            <div className="hero-stage-scan" />
            <div className="hero-stage-figure">
              <span className="stage-core stage-core-main" />
              <span className="stage-core stage-core-orbit stage-core-orbit-a" />
              <span className="stage-core stage-core-orbit stage-core-orbit-b" />
              <span className="stage-pulse stage-pulse-a" />
              <span className="stage-pulse stage-pulse-b" />
            </div>
            <div className="hero-stage-card hero-stage-card-top">
              <span>Agent Sync</span>
              <strong>Active</strong>
            </div>
            <div className="hero-stage-card hero-stage-card-side">
              <span>Response Model</span>
              <strong>Retrieval + Context</strong>
            </div>
          </div>
          <div className="hero-orbit" aria-hidden="true">
            <span className="orbit-ring orbit-ring-lg" />
            <span className="orbit-ring orbit-ring-sm" />
            <span className="orbit-core" />
          </div>
          <div className="hero-badge">Healthcare Knowledge Assistant</div>
          <h1>Kinexus Assistant</h1>
          <p>
            Ask grounded questions against your indexed healthcare content and
            get concise answers with retrieval-backed context.
          </p>
        </section>

        <section className="chat-panel">
          <div className="chat-header">
            <div>
              <span className="eyebrow">Session</span>
              <h2>Clinical Operations Chat</h2>
            </div>
            <div className="header-actions">
              <div className="scope-control" ref={scopeMenuRef}>
                <span className="scope-control-label">Scope</span>
                <button
                  type="button"
                  className={`scope-trigger ${isScopeMenuOpen ? "is-open" : ""}`}
                  onClick={() => setIsScopeMenuOpen((current) => !current)}
                  aria-label="Choose application scope"
                  aria-haspopup="menu"
                  aria-expanded={isScopeMenuOpen}
                >
                  <span>{selectedScopeLabel}</span>
                  <span className="scope-chevron" aria-hidden="true">
                    ▾
                  </span>
                </button>
                {isScopeMenuOpen ? (
                  <div className="scope-menu" role="menu" aria-label="Application scope options">
                    {scopeOptions.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        role="menuitemradio"
                        aria-checked={selectedApp === option.value}
                        className={`scope-option ${
                          selectedApp === option.value ? "is-active" : ""
                        }`}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          setSelectedApp(option.value);
                          setIsScopeMenuOpen(false);
                        }}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className="theme-toggle"
                onClick={() =>
                  setTheme((currentTheme) =>
                    currentTheme === "dark" ? "light" : "dark"
                  )
                }
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
                title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              >
                <ThemeIcon theme={theme} />
                <span>{theme === "dark" ? "Dark" : "Light"}</span>
              </button>
              <div className={`status-pill ${isSending ? "is-busy" : ""}`}>
                <span className="status-dot" />
                {isSending ? "Generating" : "Ready"}
              </div>
            </div>
          </div>

          <div ref={chatRef} className="chat">
            {messages.length === 0 ? (
              <div className="empty-state">
                <p>Start with questions like:</p>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("What is therapy gap?")}
                  style={{ animationDelay: "120ms" }}
                >
                  What is therapy gap?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("How MFA works?")}
                  style={{ animationDelay: "220ms" }}
                >
                  How MFA works?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("What dashboard shows?")}
                  style={{ animationDelay: "320ms" }}
                >
                  What dashboard shows?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("How do I reset my password?")}
                  style={{ animationDelay: "420ms" }}
                >
                  How do I reset my password?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("What are the key workflow steps?")}
                  style={{ animationDelay: "520ms" }}
                >
                  What are the key workflow steps?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("How can I use the reports module?")}
                  style={{ animationDelay: "620ms" }}
                >
                  How can I use the reports module?
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setInput("Where can I find patient eligibility details?")}
                  style={{ animationDelay: "720ms" }}
                >
                  Where can I find patient eligibility details?
                </button>
              </div>
            ) : (
              messages.map((m, i) => {
                const imageSources = getRenderableImageSources(m.sources);
                const shouldRenderImages = shouldRenderImagesForMessage(m, i, messages);

                return (
                  <div
                    key={m.id}
                    className={`message-row ${m.role}`}
                    style={{ animationDelay: `${i * 90}ms` }}
                  >
                    <div className="message-label">
                      <span className="message-author">
                        <span className={`message-avatar ${m.role}`} />
                        {m.role === "user" ? "You" : "Assistant"}
                      </span>
                      <span className="message-time">{formatTime(m.createdAt)}</span>
                    </div>
                    <div className="message-bubble">
                      {m.text}
                      {m.role === "bot" && shouldRenderImages && imageSources.length ? (
                        <div className="source-image-grid" aria-label="Reference images">
                          {imageSources.map((item) => (
                            <figure key={item.url} className="source-image-card">
                              <img src={item.url} alt={item.section} loading="eager" fetchPriority="high" />
                              <figcaption>
                                <span>{item.section}</span>
                                {item.page ? <span>Page {item.page}</span> : null}
                              </figcaption>
                            </figure>
                          ))}
                        </div>
                      ) : null}
                      {m.role === "bot" && m.routing?.app ? (
                        <div className="message-actions">
                          <span className="message-actions-label">
                            Routed to {m.routing.app}
                          </span>
                          {Array.isArray(m.sources) && m.sources.length ? (
                            <span className="message-actions-label">
                              {m.sources.length} source{m.sources.length === 1 ? "" : "s"}
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                      {m.role === "bot" && m.isComplete && m.text.trim() ? (
                        <div className="message-actions">
                          <span className="message-actions-label">Rate response</span>
                          <div className="reaction-group">
                            <button
                              type="button"
                              className={`feedback-button ${
                                m.feedback === "like" ? "active like" : ""
                              }`}
                              onClick={() => submitFeedback(m, "like")}
                              aria-pressed={m.feedback === "like"}
                              aria-label="Like response"
                              title="Like response"
                            >
                              <FeedbackIcon type="like" />
                            </button>
                            <button
                              type="button"
                              className={`feedback-button ${
                                m.feedback === "dislike" ? "active dislike" : ""
                              }`}
                              onClick={() => submitFeedback(m, "dislike")}
                              aria-pressed={m.feedback === "dislike"}
                              aria-label="Dislike response"
                              title="Dislike response"
                            >
                              <FeedbackIcon type="dislike" />
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}

            {isSending ? (
              <div className="message-row bot typing-row">
                <div className="message-label">Assistant</div>
                <div className="message-bubble typing-bubble" aria-live="polite">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            ) : null}

            <div ref={messagesEndRef} className="chat-scroll-anchor" aria-hidden="true" />
          </div>

          {error ? <div className="error">{error}</div> : null}

          <div className="input-row">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask about therapy gap, MFA, dashboards, workflows..."
            />
            <button onClick={send} disabled={isSending}>
              {isSending ? "Sending..." : "Send"}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
