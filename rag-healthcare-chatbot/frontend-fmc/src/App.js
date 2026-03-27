import React, { useEffect, useMemo, useRef, useState } from 'react';
import lottie from 'lottie-web';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkGemoji from 'remark-gemoji';
import { 
  Plus, 
  Paperclip, 
  Mic, 
  Send, 
  History,
  ThumbsDown,
  ThumbsUp,
  Pencil,
  Trash2,
  Bell,
  ChevronDown,
  Menu,
  ChevronsLeft,
  Settings,
  HelpCircle,
  GraduationCap,
  Search,
  Square,
  ArrowDown,
  Users,
  Calendar,
  AlertCircle,
  AlertTriangle,
  X
} from 'lucide-react';

// --- Precise 1:1 Official Branding Assets ---

const FreseniusLogo = () => (
  <div className="flex items-center gap-[14px]">
    {/* Exact geometrically accurate SVG of the FMC emblem */}
    <svg width="44" height="30" viewBox="0 0 480 320" fill="white" className="shrink-0">
      <path d="M 0 40 H 480 L 420 100 L 240 145 L 60 100 Z" />
      <path d="M 90 130 L 240 167.5 L 390 130 L 342 178 L 240 215.5 L 138 178 Z" />
      <path d="M 168 208 L 240 245.5 L 312 208 L 240 280 Z" />
    </svg>
    <div className="flex flex-col justify-center">
      <span className="text-[17px] font-[900] leading-none tracking-[0.02em] antialiased text-white">FRESENIUS</span>
      <span className="text-[10.5px] font-[800] leading-tight tracking-[0.09em] antialiased text-white mt-[3px] opacity-95">MEDICAL CARE</span>
    </div>
  </div>
);

// Exact Left Sidebar Icons
const ChatIcon = ({ active }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={active ? "text-white" : "text-white/80"}>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const CyclerIcon = ({ active }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={active ? "text-white" : "text-white/80"}>
    <rect x="5" y="4" width="14" height="8" rx="1.5" />
    <path d="M12 7v2" />
    <path d="M8 12v3" />
    <path d="M16 12v3" />
    <path d="M4 16h16" />
    <path d="M4 20h16" />
  </svg>
);

const AdminIcon = ({ active }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={active ? "text-white" : "text-white/80"}>
    <path d="M9 22c-4-2-6-6-6-11V5l8-3 8 3v4" />
    <circle cx="16" cy="16" r="6" />
    <circle cx="16" cy="14" r="1.5" />
    <path d="M13.5 19c.5-1.5 1.5-2 2.5-2s2 .5 2.5 2" />
  </svg>
);

// Dashboard Body Icons
const ListIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600">
    <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
    <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
  </svg>
);

const TherapyGapIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-500">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" opacity="0.4" />
    <line x1="3" y1="3" x2="21" y2="21" stroke="currentColor" strokeWidth="2" />
  </svg>
);

const FEEDBACK_LABELS = {
  like: 'Like response',
  dislike: 'Dislike response',
};


const App = () => {
  const CHAT_STORAGE_KEY = 'fmc-chat-threads-v1';
  const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';
  const FOLLOW_UP_PROMPT_HINT = 'would you like a detailed walkthrough from the documents';
  const KNOWLEDGE_BASE_MISS_HINT = 'i could not find this in the knowledge base';

  const createThread = (title = 'New Chat') => ({
    id: `thread-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title,
    updatedAt: Date.now(),
    messages: [],
  });

  const loadStoredThreads = () => {
    try {
      const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
      if (!raw) {
        return [createThread()];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.length) {
        return [createThread()];
      }
      return parsed;
    } catch {
      return [createThread()];
    }
  };

  const [currentPage, setCurrentPage] = useState('chat'); // Default to Chat for development
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(false);
  const [isChatHistoryVisible, setIsChatHistoryVisible] = useState(false);
  const [isFaqExpanded, setIsFaqExpanded] = useState(false);
  const [chatThreads, setChatThreads] = useState(loadStoredThreads);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [queryScope, setQueryScope] = useState('auto');
  const [inputValue, setInputValue] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [feedbackLoadingById, setFeedbackLoadingById] = useState({});
  const [failedImageUrls, setFailedImageUrls] = useState({});
  const [error, setError] = useState("");
  const [introAnimationFailed, setIntroAnimationFailed] = useState(false);
  const streamAbortControllerRef = useRef(null);
  const introAnimationRef = useRef(null);
  const chatScrollContainerRef = useRef(null);

  const activeThread = useMemo(
    () => chatThreads.find((thread) => thread.id === activeThreadId) || chatThreads[0] || null,
    [chatThreads, activeThreadId]
  );

  const messages = activeThread?.messages || [];

  useEffect(() => {
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatThreads));
  }, [chatThreads]);

  useEffect(() => {
    if (!chatThreads.length) {
      const fallback = createThread();
      setChatThreads([fallback]);
      setActiveThreadId(fallback.id);
      return;
    }
    if (!activeThreadId || !chatThreads.some((thread) => thread.id === activeThreadId)) {
      setActiveThreadId(chatThreads[0].id);
    }
  }, [chatThreads, activeThreadId]);

  useEffect(() => () => {
    streamAbortControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (messages.length !== 0 || !introAnimationRef.current) return undefined;

    let isCancelled = false;
    let animationInstance;

    const loadIntroAnimation = async () => {
      try {
        setIntroAnimationFailed(false);
        const response = await fetch(`${process.env.PUBLIC_URL || ''}/live-chatbot.json`);
        if (!response.ok) {
          throw new Error(`Failed to load intro animation: ${response.status}`);
        }

        const animationData = await response.json();
        if (isCancelled || !introAnimationRef.current) return;

        animationInstance = lottie.loadAnimation({
          container: introAnimationRef.current,
          renderer: 'svg',
          loop: true,
          autoplay: true,
          animationData,
          rendererSettings: {
            preserveAspectRatio: 'xMidYMid meet',
          },
        });
      } catch (animationError) {
        console.error(animationError);
        if (!isCancelled) {
          setIntroAnimationFailed(true);
        }
      }
    };

    loadIntroAnimation();

    return () => {
      isCancelled = true;
      if (animationInstance) {
        animationInstance.destroy();
      }
    };
  }, [messages.length]);

  useEffect(() => {
    const container = chatScrollContainerRef.current;
    if (!container) return;

    if (typeof container.scrollTo === 'function') {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth',
      });
      return;
    }

    container.scrollTop = container.scrollHeight;
  }, [messages]);

  const updateThread = (threadId, updater) => {
    setChatThreads((prev) =>
      prev.map((thread) =>
        thread.id === threadId
          ? {
              ...updater(thread),
              updatedAt: Date.now(),
            }
          : thread
      )
    );
  };

  const startNewChat = () => {
    const thread = createThread();
    setChatThreads((prev) => [thread, ...prev]);
    setActiveThreadId(thread.id);
    setError('');
    setInputValue('');
  };

  const renameThread = (threadId) => {
    const thread = chatThreads.find((item) => item.id === threadId);
    if (!thread) return;

    const nextTitle = window.prompt('Rename chat', thread.title || 'New Chat');
    if (nextTitle === null) return;

    const cleanTitle = nextTitle.trim();
    if (!cleanTitle) return;

    updateThread(threadId, (item) => ({
      ...item,
      title: cleanTitle,
    }));
  };

  const deleteThread = (threadId) => {
    const thread = chatThreads.find((item) => item.id === threadId);
    if (!thread) return;

    const confirmed = window.confirm(`Delete chat "${thread.title || 'New Chat'}"?`);
    if (!confirmed) return;

    setChatThreads((prev) => {
      const remaining = prev.filter((item) => item.id !== threadId);

      if (!remaining.length) {
        const fallback = createThread();
        setActiveThreadId(fallback.id);
        return [fallback];
      }

      if (activeThreadId === threadId) {
        setActiveThreadId(remaining[0].id);
      }

      return remaining;
    });

    setError('');
  };

  const buildHistoryPayload = (items) =>
    items
      .filter((message) => message.sender === "user" || message.sender === "ai")
      .slice(-4)
      .map((message) => ({
        role: message.sender === "ai" ? "assistant" : "user",
        text: message.text,
      }));

  const sendMessage = async (questionText, options = {}) => {
    const question = String(questionText || '').trim();
    if (!question || isSending || !activeThread) return;

    const threadId = activeThread.id;
    const abortController = new AbortController();
    streamAbortControllerRef.current = abortController;

    const userMsg = { id: `user-${Date.now()}`, text: question, sender: 'user' };
    const nextMessages = [...messages, userMsg];
    
    // Create an initial empty bot message
    const botMsgId = `bot-${Date.now() + 1}`;
    const botMsg = {
      id: botMsgId,
      text: '',
      sender: 'ai',
      createdAt: new Date().toISOString(),
      sourceQuestion: question,
      feedback: null,
      isComplete: false,
      showImages: Boolean(options.showImages),
      sources: [],
      collection: null,
      app: null,
      routing: null,
    };
    
    updateThread(threadId, (thread) => ({
      ...thread,
      title: thread.title === 'New Chat' ? question.slice(0, 48) : thread.title,
      messages: [...nextMessages, botMsg],
    }));
    if (question === inputValue.trim()) {
      setInputValue('');
    }
    setIsSending(true);
    setError("");

    try {
      const payload = {
        question,
        history: buildHistoryPayload(nextMessages),
      };

      if (queryScope !== 'auto') {
        payload.app = queryScope;
      }

      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        signal: abortController.signal,
        body: JSON.stringify(payload),
      });

      if (!response.ok || !response.body) {
        throw new Error("Backend request failed.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const processEvent = (event) => {
        if (event.type === 'meta') {
          updateThread(threadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((m) =>
              m.id === botMsgId
                ? {
                    ...m,
                    sources: Array.isArray(event.sources) ? event.sources : [],
                    collection: event.collection || null,
                    app: event.app || null,
                    routing: event.routing || null,
                  }
                : m
            ),
          }));
          return;
        }

        if (event.type === "token") {
          updateThread(threadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((m) =>
              m.id === botMsgId ? { ...m, text: m.text + (event.text || '') } : m
            ),
          }));
          return;
        }

        if (event.type === "done") {
          updateThread(threadId, (thread) => ({
            ...thread,
            messages: thread.messages.map((m) =>
              m.id === botMsgId ? { ...m, isComplete: true } : m
            ),
          }));
          return;
        }

        if (event.type === "error") {
          setError(event.detail || "Error processing request");
        }
      };

      const processLine = (line) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        try {
          const event = JSON.parse(trimmed);
          processEvent(event);
        } catch {
          // Ignore malformed chunks and continue processing subsequent lines.
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          processLine(line);
        }
      }

      buffer += decoder.decode();
      
      // Process remaining buffer
      if (buffer.trim()) {
         for (const line of buffer.split("\n")) {
           processLine(line);
         }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        updateThread(threadId, (thread) => ({
          ...thread,
          messages: thread.messages.map((m) =>
            m.id === botMsgId
              ? {
                  ...m,
                  isComplete: true,
                  stopped: true,
                  text: m.text || 'Generation stopped.',
                }
              : m
          ),
        }));
        setError('');
      } else {
        console.error(err);
        setError(err.message || "Failed to communicate with the server");
      }
    } finally {
      streamAbortControllerRef.current = null;
      setIsSending(false);
    }
  };

  const handleSendMessage = async () => {
    await sendMessage(inputValue, { showImages: false });
  };

  const handleSuggestedQuestion = async (question) => {
    const nextQuestion = String(question || '').trim();
    if (!nextQuestion) return;

    setInputValue(nextQuestion);
    await sendMessage(nextQuestion, { showImages: false });
    setInputValue('');
  };

  const handleStopGeneration = () => {
    streamAbortControllerRef.current?.abort();
  };

  const shouldRenderFollowUpActions = (message) => {
    if (!message || message.sender !== 'ai' || !message.isComplete) return false;
    const text = String(message.text || '').toLowerCase();
    if (text.includes(KNOWLEDGE_BASE_MISS_HINT)) return false;
    return text.includes(FOLLOW_UP_PROMPT_HINT);
  };

  const shouldOfferReferenceImages = (message) => {
    const text = String(message?.text || '').toLowerCase();
    if (text.includes(KNOWLEDGE_BASE_MISS_HINT)) return false;
    return getRenderableImageSources(message).length > 0;
  };

  const handleFollowUpAction = async (message, action) => {
    if (!message || isSending) return;

    if (action === 'details') {
      await sendMessage('Please provide a detailed walkthrough from the documents.');
      return;
    }

    await sendMessage('Please show reference images related to this answer.', { showImages: true });
  };

  const buildFigureContextParam = (source) => {
    const raw = String(source?.text || '').replace(/\s+/g, ' ').trim();
    if (!raw) {
      return '';
    }
    return encodeURIComponent(raw.slice(0, 220));
  };

  const getRenderableImageSources = (message) => {
    const sources = Array.isArray(message?.sources) ? message.sources : [];
    if (!sources.length) {
      return [];
    }

    const seen = new Set();
    const renderable = [];

    for (const source of sources) {
      const page = Number(source?.page);
      const collection = String(source?.collection || message?.collection || '').trim();
      if (!collection || !Number.isFinite(page) || page < 1) {
        continue;
      }

      const section = encodeURIComponent(String(source?.section || ''));
      const context = buildFigureContextParam(source);
      const query = context ? `?section=${section}&context=${context}` : `?section=${section}`;
      const figureUrl = `${API_BASE_URL}/kb-figures/${encodeURIComponent(collection)}/${page}${query}`;
      if (seen.has(figureUrl)) {
        continue;
      }
      seen.add(figureUrl);
      renderable.push({
        url: figureUrl,
        section: source?.section || `Page ${page}`,
        page,
      });
      if (renderable.length >= 1) {
        return renderable;
      }
    }

    for (const source of sources) {
      const imageUrl = String(source?.image_url || '').trim();
      if (!imageUrl) {
        continue;
      }

      const absoluteUrl = imageUrl.startsWith('http')
        ? imageUrl
        : `${API_BASE_URL}${imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`}`;

      if (seen.has(absoluteUrl)) {
        continue;
      }
      seen.add(absoluteUrl);
      renderable.push({
          url: absoluteUrl,
          section: source?.section || 'Reference image',
          page: source?.page,
      });
      if (renderable.length >= 1) {
        return renderable;
      }
    }

    return renderable;
  };

  const shouldRenderImagesForMessage = (message, index, allMessages) => {
    if (!message || message.sender !== 'ai') return false;
    if (!message.isComplete || !String(message.text || '').trim()) return false;
    if (message.showImages === true) return true;
    if (message.showImages === false) return false;

    const previous = index > 0 ? allMessages[index - 1] : null;
    const previousText = String(previous?.text || '').toLowerCase();
    if (previous?.sender === 'user' && previousText.includes('show reference images')) {
      return true;
    }
    return false;
  };

  const orderedThreads = [...chatThreads].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));

  const formatAssistantText = (text) => {
    const raw = String(text || '').trim();
    if (!raw) return raw;

    const withoutFollowUpPrompt = raw.replace(
      /\n*\s*Would you like a detailed walkthrough from the documents,\s*or should I show reference images\?\s*$/i,
      ''
    );

    // Normalize inline bullet patterns into one-bullet-per-line rendering.
    return withoutFollowUpPrompt
      .replace(/\s-\s+/g, '\n- ')
      .replace(/^\s*\n+/, '')
      .trim();
  };

  const setMessageFeedback = (threadId, messageId, feedback) => {
    updateThread(threadId, (thread) => ({
      ...thread,
      messages: thread.messages.map((message) =>
        message.id === messageId
          ? {
              ...message,
              feedback,
            }
          : message
      ),
    }));
  };

  const submitFeedback = async (message, feedback) => {
    if (!activeThread || !message?.sourceQuestion || message.feedback === feedback) {
      return;
    }

    const threadId = activeThread.id;
    const previousFeedback = message.feedback ?? null;

    setMessageFeedback(threadId, message.id, feedback);
    setFeedbackLoadingById((prev) => ({
      ...prev,
      [message.id]: true,
    }));

    try {
      const response = await fetch(`${API_BASE_URL}/feedback/${feedback}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message_id: message.id,
          question: message.sourceQuestion,
          answer: message.text,
          created_at: message.createdAt,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to save ${feedback} feedback.`);
      }
    } catch (err) {
      console.error(`Failed to save ${feedback} feedback`, err);
      setMessageFeedback(threadId, message.id, previousFeedback);
    } finally {
      setFeedbackLoadingById((prev) => {
        const next = { ...prev };
        delete next[message.id];
        return next;
      });
    }
  };

  const handleImageLoadError = (imageUrl) => {
    if (!imageUrl) return;
    setFailedImageUrls((prev) => {
      if (prev[imageUrl]) {
        return prev;
      }
      return {
        ...prev,
        [imageUrl]: true,
      };
    });
  };

  return (
    <div className="h-screen flex flex-col font-sans overflow-hidden text-[#333]">
      {/* HEADER - MATCHING EXACT COLOR AND LAYOUT */}
      <header className="bg-[#003DA5] h-14 flex items-center justify-between px-4 text-white shrink-0 z-50">
        <FreseniusLogo />
        <div className="flex items-center gap-6 text-[13px] mr-2">
            <div className="flex items-center gap-1 cursor-pointer">
              <span className="font-medium">KinexAssist</span>
              <ChevronDown size={14} />
            </div>
          <div className="relative cursor-pointer">
            <Bell size={18} />
            <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-red-500 rounded-full"></span>
          </div>
          {/* User Avatar Circle */}
          <div className="flex items-center justify-center w-[26px] h-[26px] bg-[#B3D4FF] text-[#003DA5] rounded-full font-bold text-[10px] cursor-pointer">
            KN
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* SIDEBAR - PRECISE BACKGROUND COLOR AND CORRECT ACTIVE STATE */}
        <aside className={`bg-[#5D6D84] text-white flex flex-col transition-all duration-300 ${isSidebarExpanded ? 'w-64' : 'w-16'} shrink-0 z-40`}>
          <div className={`flex w-full py-5 mb-1 ${isSidebarExpanded ? 'px-6 justify-start' : 'justify-center'}`}>
            <button 
              onClick={() => setIsSidebarExpanded(!isSidebarExpanded)} 
              className="text-white hover:text-gray-300 transition-colors"
            >
              {isSidebarExpanded ? <ChevronsLeft size={22} /> : <Menu size={22} />}
            </button>
          </div>

          <nav className="flex flex-col gap-1 w-full">
            <SidebarItem 
              icon={<ChatIcon active={currentPage === 'chat'} />} 
              label="Chat" 
              active={currentPage === 'chat'} 
              expanded={isSidebarExpanded}
              onClick={() => setCurrentPage('chat')} 
            />
            
            <SidebarItem 
              icon={<CyclerIcon active={currentPage === 'summary'} />} 
              label="Treatments" 
              active={currentPage === 'summary'} 
              expanded={isSidebarExpanded}
              onClick={() => setCurrentPage('summary')} 
            />
            
            <div className={`my-3 border-t border-white/20 ${isSidebarExpanded ? 'mx-6' : 'mx-4'}`}></div>
            
            <SidebarItem 
              icon={<AdminIcon active={false} />} 
              label="Administration" 
              expanded={isSidebarExpanded}
              hasDropdown={true}
            />
            
            <SidebarItem 
              icon={<Settings size={22} className="text-white/80" />} 
              label="Settings" 
              expanded={isSidebarExpanded} 
              hasDropdown={true}
            />
            
            <SidebarItem 
              icon={<HelpCircle size={22} className="text-white/80" />} 
              label="User Manuals" 
              expanded={isSidebarExpanded} 
            />
            
            <div className={`my-3 border-t border-white/20 ${isSidebarExpanded ? 'mx-6' : 'mx-4'}`}></div>

            <SidebarItem 
              icon={<div className="w-[22px] h-[22px]" />} 
              label="About" 
              expanded={isSidebarExpanded} 
            />
          </nav>
        </aside>

        {/* MAIN CONTENT AREA */}
        <main className="flex-1 flex flex-col overflow-hidden bg-[#F5F6F8]">
          {currentPage === 'summary' ? (
            <div className="flex-1 overflow-auto p-8">
              <h1 className="text-[26px] font-bold text-gray-800 mb-6">KinexAssist</h1>
              
              <div className="flex gap-8 mb-6 border-b border-gray-200 px-1">
                <div className="pb-3 border-b-[3px] border-[#003DA5] text-[#003DA5] font-bold text-sm cursor-pointer">Summary</div>
                <div className="pb-3 text-gray-500 font-medium text-sm cursor-pointer hover:text-gray-700">Treatments ( • 1 )</div>
                <div className="pb-3 text-gray-500 font-medium text-sm cursor-pointer hover:text-gray-700">Patients</div>
                <div className="pb-3 text-gray-500 font-medium text-sm cursor-pointer hover:text-gray-700">Equipment</div>
              </div>

              <div className="grid grid-cols-12 gap-6">
                <div className="col-span-12 lg:col-span-3">
                  <div className="bg-white rounded-md border border-gray-200 p-5">
                    <h3 className="text-[15px] font-bold text-gray-800 mb-4">Patients</h3>
                    
                    <div className="space-y-3">
                      <div className="border border-blue-500 rounded-md p-3 px-4">
                        <span className="text-blue-600 font-bold text-[12px] block mb-1">All</span>
                        <div className="flex items-center gap-2 text-gray-800">
                          <ListIcon />
                          <span className="text-[22px] font-bold">32</span>
                        </div>
                      </div>

                      <div className="border border-gray-200 rounded-md p-3 px-4">
                        <span className="text-blue-600 font-bold text-[12px] block mb-1">Therapy Gaps</span>
                        <div className="flex items-center gap-2 text-gray-800">
                          <TherapyGapIcon />
                          <span className="text-[22px] font-bold">5</span>
                        </div>
                      </div>

                      <div className="border border-gray-200 rounded-md p-3 px-4">
                        <span className="text-blue-600 font-bold text-[12px] block mb-1">First 90 Days</span>
                        <div className="flex items-center gap-2 text-gray-800">
                          <GraduationCap size={20} className="text-gray-500" strokeWidth={2} />
                          <span className="text-[22px] font-bold">0</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="col-span-12 lg:col-span-9">
                  <div className="bg-white rounded-md border border-gray-200 flex flex-col h-full">
                    {/* Panel Header */}
                    <div className="flex justify-between items-center p-4 border-b border-gray-100">
                      <h2 className="font-bold text-[15px] text-gray-800">Alerts & Alarms - Last 7 Days</h2>
                      <div className="flex bg-gray-50 border border-gray-200 rounded text-[12px] font-medium">
                        <button className="px-3 py-1.5 bg-white border-r border-gray-200 text-gray-700 flex items-center gap-1.5">
                          <Users size={14}/> By Patients
                        </button>
                        <button className="px-3 py-1.5 text-gray-400 flex items-center gap-1.5 hover:bg-gray-100">
                          <Calendar size={14}/> By Date
                        </button>
                      </div>
                    </div>
                    
                    {/* Panel Body */}
                    <div className="flex-1 min-h-[250px] flex flex-col items-center justify-center border-b border-gray-100">
                       <p className="text-gray-400 text-[13px]">No treatments with alerts and alarms within the last 7 days.</p>
                    </div>
                    
                    {/* Panel Footer */}
                    <div className="px-4 py-2.5 bg-[#FAFAFA] flex justify-between items-center text-[11px] text-gray-500">
                       <span>0 Patients | 0 Treatments</span>
                       <div className="flex items-center gap-5">
                          <span className="flex items-center gap-1.5"><AlertCircle size={14} className="text-gray-400"/> Clinical Alerts</span>
                          <span className="flex items-center gap-1.5"><AlertTriangle size={14} className="text-red-600"/> Cycler Alarms</span>
                          <span className="flex items-center gap-1.5"><AlertTriangle size={14} className="text-yellow-500"/> Cycler Cautions</span>
                       </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom Table Section */}
              <div className="mt-8">
                <h2 className="font-bold text-[15px] text-gray-800 mb-4">Last 7 Days Treatments (0)</h2>
                
                <div className="flex justify-between items-center mb-4">
                   <div className="relative">
                      <Search size={14} className="absolute left-3 top-[10px] text-gray-400" />
                      <input 
                        type="text" 
                        placeholder="Search by patient..." 
                        className="pl-8 pr-4 py-2 border border-gray-200 rounded-md text-[13px] w-[280px] focus:outline-none focus:border-blue-500" 
                      />
                   </div>
                   <div className="flex gap-2">
                      <button className="px-5 py-2 bg-gray-200 text-gray-400 rounded-full text-[12px] font-bold cursor-not-allowed">Mark as Reviewed</button>
                      <button className="px-5 py-2 bg-white border border-gray-200 text-gray-400 rounded-full text-[12px] font-bold cursor-not-allowed">Mark as Un-Reviewed</button>
                   </div>
                </div>
                
                <div className="border-t border-b border-gray-200 py-3.5 flex text-[12px] font-bold text-gray-700 px-4">
                   <div className="w-[12%] flex items-center gap-1">Date, Start <ArrowDown size={14}/></div>
                   <div className="w-[8%]">DUR, min</div>
                   <div className="w-[18%]">Patient Name</div>
                   <div className="w-[8%]">Alarms</div>
                   <div className="w-[8%]">Notes</div>
                   <div className="w-[10%]">Weight, kg</div>
                   <div className="w-[10%]">BP, mmHg</div>
                   <div className="w-[10%]">Pulse, bpm</div>
                   <div className="w-[6%]">UF, L</div>
                   <div className="w-[10%]">Dialysate, L</div>
                   <div className="w-[10%]">Blood, L</div>
                </div>
                
                <div className="py-12 flex justify-center text-gray-500 text-[13px]">
                   No available treatments.
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 overflow-hidden bg-white">
              {/* Gemini Chat Sidebar */}
              <div className={`${isChatHistoryVisible ? 'w-72' : 'w-0'} transition-all duration-300 border-r bg-gray-50 flex flex-col overflow-hidden`}>
                <div className="p-4">
                  <button 
                    onClick={startNewChat}
                    className="w-full flex items-center justify-center gap-2 bg-[#003DA5] text-white px-4 py-2.5 rounded-full text-sm font-bold hover:bg-[#002b75] transition-all shadow-sm"
                  >
                    <Plus size={18} />
                    <span>New Chat</span>
                  </button>
                </div>
                
                <div className="flex-1 overflow-y-auto px-4 pb-4">
                  <p className="text-[11px] font-bold text-gray-500 mb-3 px-1">Recent Chats</p>
                  <div className="space-y-1">
                    {orderedThreads.map((thread) => (
                      <div
                        key={thread.id}
                        onClick={() => {
                          setActiveThreadId(thread.id);
                          setCurrentPage('chat');
                        }}
                        className={`group flex items-center gap-2 p-2.5 rounded-lg cursor-pointer text-[13px] transition-all ${
                          activeThreadId === thread.id
                            ? 'bg-blue-50 text-[#003DA5] border border-blue-100'
                            : 'hover:bg-gray-200 text-gray-700'
                        }`}
                      >
                        <History size={14} className="text-gray-400" />
                        <span className="truncate flex-1">{thread.title || 'New Chat'}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            renameThread(thread.id);
                          }}
                          className="opacity-0 group-hover:opacity-100 rounded p-1 text-gray-400 hover:bg-white hover:text-gray-700 transition"
                          title="Rename chat"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteThread(thread.id);
                          }}
                          className="opacity-0 group-hover:opacity-100 rounded p-1 text-gray-400 hover:bg-white hover:text-red-600 transition"
                          title="Delete chat"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Chat Viewport */}
              <div className="flex-1 flex flex-col relative">
                {/* Updated Toggle with History Icon and New Chat button when collapsed */}
                <div className="absolute left-4 top-4 z-10 flex items-center gap-2">
                  <button 
                    onClick={() => setIsChatHistoryVisible(!isChatHistoryVisible)}
                    className="p-2 hover:bg-gray-100 rounded-md text-gray-500 transition-all border border-transparent hover:border-gray-200"
                    title={isChatHistoryVisible ? "Hide history" : "Show history"}
                  >
                    <History size={20} />
                  </button>
                  {!isChatHistoryVisible && (
                    <button 
                      onClick={startNewChat}
                      className="p-2 hover:bg-gray-100 rounded-md text-gray-500 transition-all border border-transparent hover:border-gray-200"
                      title="New Chat"
                    >
                      <Plus size={20} />
                    </button>
                  )}
                </div>

                <div className="h-14 border-b border-gray-200 flex items-center justify-end px-6">
                  <label className="mr-3 text-[12px] font-semibold text-gray-500">Collection</label>
                  <select
                    value={queryScope}
                    onChange={(e) => setQueryScope(e.target.value)}
                    className="mr-4 rounded-md border border-gray-300 bg-white px-2.5 py-1.5 text-[12px] font-semibold text-gray-700 focus:border-blue-500 focus:outline-none"
                    disabled={isSending}
                  >
                    <option value="auto">Auto</option>
                    <option value="kinexushhd">Kinexus HHD</option>
                    <option value="nx2meapp">Nx2Me App</option>
                  </select>
                  <button 
                    onClick={() => setIsFaqExpanded(!isFaqExpanded)}
                    className={`flex items-center gap-2 text-[13px] font-bold px-3 py-1.5 rounded-md transition-all ${isFaqExpanded ? 'bg-blue-50 text-[#003DA5]' : 'text-gray-600 hover:bg-gray-100'}`}
                  >
                    <HelpCircle size={16} />
                    <span>FAQs</span>
                  </button>
                </div>

                <div
                  ref={chatScrollContainerRef}
                  className="flex-1 overflow-y-auto p-6 md:p-10 space-y-8 flex flex-col items-center"
                >
                  {error ? (
                    <div className="w-full max-w-3xl rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
                      {error}
                    </div>
                  ) : null}
                  {messages.length === 0 ? (
                    <div className="mt-16 text-center space-y-4 max-w-xl">
                      <div className="mx-auto mb-6 flex justify-center">
                        {introAnimationFailed ? (
                          <img
                            src={`${process.env.PUBLIC_URL || ''}/botlogo.png`}
                            alt="KinexAssist"
                            className="h-[180px] w-auto object-contain"
                          />
                        ) : (
                          <div
                            ref={introAnimationRef}
                            aria-hidden="true"
                            className="h-[280px] w-[280px]"
                          />
                        )}
                      </div>
                      <h2 className="text-[32px] font-bold text-gray-800">
                        Hello
                      </h2>
                      <p className="text-[15px] text-gray-500">How can I assist you with clinical data today?</p>
                      
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-12 text-left">
                        {[
                          { title: "What is therapy gap?", desc: "Understand what a therapy gap means and why it matters." },
                          { title: "How can I use the reports module?", desc: "Learn where reports are available and how to use them." },
                          { title: "How to Review Treatments", desc: "See how to review and manage treatments in the portal." }
                        ].map((card, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => handleSuggestedQuestion(card.title)}
                            disabled={isSending}
                            className={`w-full p-4 border border-gray-200 rounded-lg text-left transition-all ${isSending ? 'cursor-not-allowed opacity-60' : 'hover:bg-gray-50 cursor-pointer'}`}
                          >
                            <p className="text-[13px] font-bold text-gray-800">{card.title}</p>
                            <p className="text-[12px] text-gray-500 mt-1">{card.desc}</p>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="w-full max-w-3xl space-y-6 pb-12">
                      {messages.map((m, index) => {
                        const imageSources = getRenderableImageSources(m);
                        const availableImageSources = imageSources.filter((item) => !failedImageUrls[item.url]);
                        const shouldRenderImages = shouldRenderImagesForMessage(m, index, messages);
                        const canOfferReferenceImages = shouldOfferReferenceImages(m);
                        return (
                        <div key={m.id} className={`flex gap-4 ${m.sender === 'user' ? 'justify-end' : ''}`}>
                          {m.sender === 'ai' && (
                            <div className="w-8 h-8 rounded-full bg-[#003DA5] flex items-center justify-center shrink-0">
                              <svg width="14" height="14" viewBox="0 0 54 38" fill="white">
                                <path d="M0 4.5L27 33L54 4.5H41L27 19L13 4.5H0Z" />
                              </svg>
                            </div>
                          )}
                          <div className={`max-w-[80%] px-4 py-2.5 rounded-lg text-[14px] ${
                            m.sender === 'user' 
                            ? 'bg-blue-50 text-blue-900 border border-blue-100' 
                            : 'bg-white border border-gray-200 text-gray-800'
                          }`}>
                            {m.sender === 'ai' ? (
                              <div className="leading-relaxed text-[14px]">
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm, remarkGemoji]}
                                  components={{
                                    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                                    ul: ({ children }) => <ul className="mb-2 list-disc pl-5 space-y-1">{children}</ul>,
                                    ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 space-y-1">{children}</ol>,
                                    li: ({ children }) => <li className="text-gray-800">{children}</li>,
                                    a: ({ href, children }) => (
                                      <a href={href} target="_blank" rel="noreferrer" className="text-[#003DA5] underline">
                                        {children}
                                      </a>
                                    ),
                                    strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                                    table: ({ children }) => <table className="my-2 w-full border-collapse text-[13px]">{children}</table>,
                                    th: ({ children }) => <th className="border border-gray-300 bg-gray-50 px-2 py-1 text-left">{children}</th>,
                                    td: ({ children }) => <td className="border border-gray-300 px-2 py-1 align-top">{children}</td>,
                                  }}
                                >
                                  {formatAssistantText(m.text) || (!m.isComplete ? 'Thinking... ⏳' : '')}
                                </ReactMarkdown>
                              </div>
                            ) : (
                              <div className="whitespace-pre-line leading-relaxed">{m.text}</div>
                            )}
                            {m.sender === 'ai' && m.isComplete && String(m.text || '').trim() ? (
                              <div className="mt-3 flex items-center justify-between gap-3 border-t border-gray-100 pt-3">
                                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-400">
                                  Rate response
                                </span>
                                <div className="flex items-center gap-2">
                                  {['like', 'dislike'].map((feedbackType) => {
                                    const isActive = m.feedback === feedbackType;
                                    const isLoading = Boolean(feedbackLoadingById[m.id]);
                                    const baseClasses = isActive
                                      ? feedbackType === 'like'
                                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                        : 'border-red-200 bg-red-50 text-red-700'
                                      : 'border-gray-200 bg-white text-gray-500 hover:border-blue-200 hover:text-[#003DA5]';

                                    return (
                                      <button
                                        key={feedbackType}
                                        type="button"
                                        onClick={() => submitFeedback(m, feedbackType)}
                                        disabled={isLoading}
                                        aria-pressed={isActive}
                                        aria-label={FEEDBACK_LABELS[feedbackType]}
                                        title={FEEDBACK_LABELS[feedbackType]}
                                        className={`inline-flex h-9 w-9 items-center justify-center rounded-full border transition ${baseClasses} ${isLoading ? 'cursor-not-allowed opacity-60' : ''}`}
                                      >
                                        {feedbackType === 'like' ? <ThumbsUp size={16} /> : <ThumbsDown size={16} />}
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}
                            {shouldRenderFollowUpActions(m) ? (
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                  onClick={() => handleFollowUpAction(m, 'details')}
                                  disabled={isSending}
                                  className={`rounded-full border px-3 py-1 text-[12px] font-semibold transition ${isSending ? 'border-gray-200 text-gray-400 cursor-not-allowed' : 'border-blue-200 bg-blue-50 text-[#003DA5] hover:bg-blue-100'}`}
                                >
                                  Detailed walkthrough
                                </button>
                                {canOfferReferenceImages ? (
                                  <button
                                    onClick={() => handleFollowUpAction(m, 'images')}
                                    disabled={isSending}
                                    className={`rounded-full border px-3 py-1 text-[12px] font-semibold transition ${isSending ? 'border-gray-200 text-gray-400 cursor-not-allowed' : 'border-blue-200 bg-white text-[#003DA5] hover:bg-blue-50'}`}
                                  >
                                    Show reference images
                                  </button>
                                ) : null}
                              </div>
                            ) : null}
                            {m.sender === 'ai' && shouldRenderImages && availableImageSources.length ? (
                              <div className="mt-3 space-y-2">
                                {availableImageSources.map((item) => (
                                  <div key={item.url} className="overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
                                    <img
                                      src={item.url}
                                      alt={item.section}
                                      className="w-full max-h-[360px] object-contain bg-white"
                                      loading="eager"
                                      fetchPriority="high"
                                      onError={() => handleImageLoadError(item.url)}
                                    />
                                    <div className="flex items-center justify-between px-2 py-1 text-[11px] text-gray-500">
                                      <span className="truncate pr-2">{item.section}</span>
                                      {item.page ? <span>Page {item.page}</span> : null}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : null}
                            {m.sender === 'ai' && shouldRenderImages && imageSources.length && !availableImageSources.length ? (
                              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
                                Reference image unavailable.
                              </div>
                            ) : null}
                            {m.sender === 'ai' && Array.isArray(m.sources) && m.sources.length ? (
                              <div className="mt-2 text-[11px] text-gray-500">
                                Source: {m.sources[0]?.section || 'Knowledge base'}
                              </div>
                            ) : null}
                          </div>
                          {m.sender === 'user' && (
                            <div className="w-8 h-8 rounded-full bg-[#B3D4FF] text-[#003DA5] flex items-center justify-center shrink-0 text-[10px] font-bold">
                              KN
                            </div>
                          )}
                        </div>
                      );
                      })}
                    </div>
                  )}
                </div>

                <div className="px-6 pb-6 flex flex-col items-center w-full">
                  <div className="w-full max-w-3xl bg-white rounded-lg p-1.5 px-4 flex items-center gap-2 border border-gray-300 shadow-sm focus-within:border-blue-500 transition-all">
                    <button className="p-2 text-gray-400 hover:text-gray-600 rounded transition-colors shrink-0">
                      <Plus size={20} />
                    </button>
                    <textarea 
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      placeholder="Ask KinexAssist..."
                      disabled={isSending}
                      rows={1}
                      className="flex-1 bg-transparent border-none focus:outline-none focus:ring-0 resize-none py-3 text-gray-800 text-[14px] leading-tight"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                    />
                    <div className="flex items-center gap-1 shrink-0">
                      <button disabled={isSending} className={`p-2 rounded transition-colors ${isSending ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:text-gray-600'}`}><Mic size={20} /></button>
                      <button disabled={isSending} className={`p-2 rounded transition-colors ${isSending ? 'text-gray-300 cursor-not-allowed' : 'text-gray-400 hover:text-gray-600'}`}><Paperclip size={20} /></button>
                      {isSending ? (
                        <button
                          onClick={handleStopGeneration}
                          type="button"
                          className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700 transition hover:bg-red-100"
                          title="Stop generating"
                        >
                          <Square size={14} />
                          <span>Stop</span>
                        </button>
                      ) : null}
                      <button 
                        onClick={handleSendMessage}
                        disabled={!inputValue.trim() || isSending}
                        className={`p-2 rounded transition-all ${inputValue.trim() && !isSending ? 'text-[#003DA5] hover:bg-blue-50' : 'text-gray-300 cursor-not-allowed'}`}
                      >
                        <Send size={20} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* FAQ Right Sidebar */}
              <div className={`${isFaqExpanded ? 'w-80' : 'w-0'} transition-all duration-300 border-l border-gray-200 bg-[#F9FAFB] flex flex-col overflow-hidden shrink-0`}>
                <div className="px-5 h-14 border-b border-gray-200 flex justify-between items-center bg-white shrink-0">
                  <h3 className="font-bold text-[#003DA5] flex items-center gap-2 text-[14px]">
                    <HelpCircle size={16}/> Frequently Asked Questions
                  </h3>
                  <button onClick={() => setIsFaqExpanded(false)} className="text-gray-400 hover:text-gray-600 p-1.5 rounded-md hover:bg-gray-100 transition-colors">
                    <X size={18} />
                  </button>
                </div>
                <div className="p-5 overflow-y-auto space-y-4">
                  {[
                    { q: "What can KinexAssist help me with?", a: "KinexAssist can summarize clinical alerts, analyze patient lab trends, and answer questions about treatment histories." },
                    { q: "How do I filter treatments by date?", a: "Navigate to the Summary tab and use the 'By Date' toggle under the Alerts & Alarms panel." },
                    { q: "What does a 'Therapy Gap' mean?", a: "A therapy gap indicates a missed or incomplete dialysis session based on the patient's individual prescription." },
                    { q: "Can I export patient data?", a: "Yes, you can export compliance reports and alert histories from the Administration panel under 'Data Exports'." }
                  ].map((faq, i) => (
                    <div key={i} className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm hover:border-blue-200 transition-colors cursor-pointer group">
                      <h4 className="font-bold text-[13px] text-gray-800 mb-1.5 group-hover:text-[#003DA5] transition-colors">{faq.q}</h4>
                      <p className="text-[12px] text-gray-500 leading-relaxed">{faq.a}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

// PRECISE Sidebar Item - Grouping & Dropdown Support
const SidebarItem = ({ icon, label, active, expanded, onClick, hasDropdown }) => (
  <div className="w-full flex justify-center py-[2px]">
    <div 
      onClick={onClick}
      className={`flex items-center cursor-pointer transition-colors ${
        expanded ? 'justify-between w-full mx-4 px-3 py-2.5 rounded-md' : 'justify-center w-[44px] h-[44px] rounded-[10px]'
      } ${
        active 
        ? 'bg-[#3A4B61] text-white' 
        : 'hover:bg-white/10 text-white/80 hover:text-white'
      }`}
    >
      <div className="flex items-center shrink-0">
        <div className="flex items-center justify-center">
          {icon}
        </div>
        {expanded && (
          <span className="whitespace-nowrap text-[14.5px] font-normal tracking-wide ml-4">
            {label}
          </span>
        )}
      </div>
      {expanded && hasDropdown && (
        <ChevronDown size={18} className="text-white/80 shrink-0 mr-1" />
      )}
    </div>
  </div>
);

export default App;
