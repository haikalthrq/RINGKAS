"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { useAuth } from "@/components/auth-provider";
import { RingkasLogo } from "@/components/ringkas-logo";
import { ApiClientError, apiRequest } from "@/lib/api-client";
import { useInterfaceLanguage, type InterfaceLanguage } from "@/lib/language";

type MessageRole = "user" | "assistant" | "system";

interface ChatCitation {
  document_id: string;
  chunk_id: string;
  title: string;
  year: number;
  region: string;
  page_start: number | null;
  page_end: number | null;
  source_url: string;
  pdf_url?: string | null;
  snippet: string;
}

interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  source_sufficiency: "sufficient" | "partial" | "insufficient";
  provider: string | null;
  session_id?: string | null;
}

interface ChatSessionSummary {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

interface ChatHistoryMessage {
  message_id: string;
  role: MessageRole;
  content: string;
  citations: ChatCitation[];
  provider: string | null;
  created_at: string;
}

interface ChatSessionDetail extends ChatSessionSummary {
  messages: ChatHistoryMessage[];
}

interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  citations: ChatCitation[];
  provider: string | null;
  created_at?: string;
  sourceSufficiency?: ChatResponse["source_sufficiency"];
}

const copy = {
  id: {
    workspace: "Ruang riset",
    scope: "Corpus BPS DKI Jakarta",
    guest: "Mode tamu",
    signedIn: "Akun aktif",
    menu: "Buka navigasi chat",
    closeMenu: "Tutup navigasi chat",
    newChat: "Chat baru",
    history: "Riwayat pertanyaan",
    historyEmpty: "Belum ada riwayat. Pertanyaan pertama kamu akan muncul di sini.",
    historyLoading: "Memuat riwayat...",
    historyError: "Riwayat belum bisa dimuat.",
    retry: "Coba lagi",
    signIn: "Masuk untuk menyimpan riwayat",
    signInHint: "Tamu tetap bisa mencoba satu pertanyaan dengan citation.",
    emptyTitle: "Apa yang ingin kamu verifikasi?",
    emptyDescription: "Tanyakan data atau indikator dari publikasi BPS DKI Jakarta. Setiap jawaban menyertakan rujukan halaman dan kutipan dokumen.",
    suggestions: [
      "Apa definisi indikator kemiskinan menurut publikasi terbaru?",
      "Berapa jumlah penduduk DKI Jakarta pada publikasi terbaru?",
      "Publikasi mana yang membahas ketenagakerjaan di DKI Jakarta?"
    ],
    questionLabel: "Pertanyaan kamu",
    placeholder: "Tulis pertanyaan tentang publikasi BPS DKI Jakarta...",
    shortcut: "Enter untuk mengirim · Shift+Enter untuk baris baru",
    characterLimit: "Maksimal 2.000 karakter",
    ask: "Tanyakan ke RINGKAS",
    checking: "Memeriksa dokumen...",
    answer: "Jawaban RINGKAS",
    ready: "Siap membantu",
    searching: "Mencari publikasi BPS dan memverifikasi rujukan...",
    sufficient: "Bukti cukup",
    partial: "Bukti sebagian",
    insufficient: "Bukti belum cukup",
    statusUnavailable: "Status bukti tidak tersedia",
    sources: "Sumber dan sitasi",
    closestSources: "Sumber terdekat",
    sourceCount: (count: number) => `${count} sumber`,
    noSources: "Tidak ada sitasi untuk jawaban ini.",
    unverified: "Jawaban belum dapat diverifikasi karena rujukan kutipan tidak ditemukan di dokumen.",
    noAnswer: "Jawaban tidak ditemukan.",
    limitationPartial: "Bukti dokumen hanya mendukung sebagian jawaban. Periksa kutipan sumber sebelum menggunakan datanya.",
    limitationInsufficient: "Bukti dokumen belum mencukupi untuk menjawab data ini. Dokumen di bawah merupakan hasil pencarian terdekat.",
    errorEmpty: "Tulis pertanyaan sebelum mengirim.",
    errorDefault: "Layanan penelusuran belum dapat dihubungi. Periksa koneksi dan coba lagi.",
    errorRate: "Batas penggunaan tercapai sementara. Coba lagi nanti.",
    errorAuth: "Sesi berakhir. Masuk kembali untuk melanjutkan.",
    errorServer: "Terjadi gangguan pada layanan. Pertanyaan Anda tetap tersimpan di kotak input.",
    retryQuestion: "Kirim ulang pertanyaan",
    sourcesOpen: (count: number) => `Buka ${count} sitasi`,
    sourceDetail: "Detail sumber",
    closeSource: "Tutup detail sumber",
    openCitation: (index: number) => `Buka sitasi ${index}`,
    document: "Dokumen",
    region: "Wilayah",
    page: "Halaman",
    sourcePublication: "Buka publikasi sumber",
    sourceUnavailable: "Tautan publikasi tidak tersedia.",
    language: "Bahasa",
    userQuestion: "Pertanyaan pengguna",
    assistantAnswer: "Jawaban asisten"
  },
  en: {
    workspace: "Research workspace",
    scope: "BPS DKI Jakarta corpus",
    guest: "Guest mode",
    signedIn: "Signed in",
    menu: "Open chat navigation",
    closeMenu: "Close chat navigation",
    newChat: "New chat",
    history: "Question history",
    historyEmpty: "No history yet. Your first question will appear here.",
    historyLoading: "Loading history...",
    historyError: "History is unavailable.",
    retry: "Try again",
    signIn: "Sign in to save history",
    signInHint: "Guests can still try one question with citations.",
    emptyTitle: "What do you want to verify?",
    emptyDescription: "Ask about statistics or indicators from BPS DKI Jakarta publications. Answers include page numbers and source quotes.",
    suggestions: [
      "What is the definition of the poverty indicator in the latest publication?",
      "What was DKI Jakarta's population in the latest publication?",
      "Which publication covers employment in DKI Jakarta?"
    ],
    questionLabel: "Your question",
    placeholder: "Ask about BPS publications for DKI Jakarta...",
    shortcut: "Enter to send · Shift+Enter for a new line",
    characterLimit: "Maximum 2,000 characters",
    ask: "Ask RINGKAS",
    checking: "Checking documents...",
    answer: "RINGKAS answer",
    ready: "Ready to help",
    searching: "Searching BPS publications and verifying references...",
    sufficient: "Sufficient evidence",
    partial: "Partial evidence",
    insufficient: "Insufficient evidence",
    statusUnavailable: "Evidence status unavailable",
    sources: "Sources and citations",
    closestSources: "Closest sources",
    sourceCount: (count: number) => `${count} source${count === 1 ? "" : "s"}`,
    noSources: "No citations are available for this answer.",
    unverified: "Answer could not be verified because no source citation was found in the documents.",
    noAnswer: "No answer found.",
    limitationPartial: "Retrieved documents only support part of this answer. Check the cited passages before using this data.",
    limitationInsufficient: "Retrieved documents are insufficient to answer this statistical query. Publications below are the closest matches found.",
    errorEmpty: "Write a question before sending it.",
    errorDefault: "Search service is unreachable. Check your connection and try again.",
    errorRate: "Usage limit reached temporarily. Try again later.",
    errorAuth: "Session ended. Sign in again to continue.",
    errorServer: "Service encountered an issue. Your question remains in the composer.",
    retryQuestion: "Send the question again",
    sourcesOpen: (count: number) => `Open ${count} citation${count === 1 ? "" : "s"}`,
    sourceDetail: "Source detail",
    closeSource: "Close source detail",
    openCitation: (index: number) => `Open citation ${index}`,
    document: "Document",
    region: "Region",
    page: "Page",
    sourcePublication: "Open source publication",
    sourceUnavailable: "Source publication link unavailable.",
    language: "Language",
    userQuestion: "User question",
    assistantAnswer: "Assistant answer"
  }
} as const;

type ChatLabels = {
  [Key in keyof typeof copy.id]: typeof copy.id[Key] extends (...args: infer Args) => infer Result
    ? (...args: Args) => Result
    : typeof copy.id[Key] extends readonly string[]
      ? readonly string[]
    : string;
};

export function ChatWorkspace() {
  const { isLoading: authLoading, isAuthenticated, currentUser } = useAuth();
  const [language, setLanguage] = useInterfaceLanguage();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [loadingSession, setLoadingSession] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [composerError, setComposerError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isWideScreen, setIsWideScreen] = useState<boolean | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<{ citation: ChatCitation; index: number } | null>(null);
  const sessionRequestId = useRef(0);
  const lastFocusedElement = useRef<HTMLElement | null>(null);
  const sidebarMenuButton = useRef<HTMLButtonElement>(null);
  const sidebarCloseButton = useRef<HTMLButtonElement>(null);
  const labels = copy[language];

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 901px)");
    const updateScreen = () => setIsWideScreen(mediaQuery.matches);
    updateScreen();
    mediaQuery.addEventListener("change", updateScreen);
    return () => mediaQuery.removeEventListener("change", updateScreen);
  }, []);

  useEffect(() => {
    if (authLoading || !isAuthenticated) {
      if (!authLoading && !isAuthenticated) setSessions([]);
      return;
    }

    const controller = new AbortController();
    void refreshSessions(controller.signal);
    return () => controller.abort();
  }, [authLoading, isAuthenticated]);

  async function refreshSessions(signal?: AbortSignal) {
    if (!isAuthenticated) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const nextSessions = await apiRequest<ChatSessionSummary[]>("/api/chat/sessions", { signal });
      if (!signal?.aborted) setSessions(nextSessions);
    } catch (error) {
      if (!signal?.aborted) setHistoryError(getChatError(error, labels.historyError, labels));
    } finally {
      if (!signal?.aborted) setHistoryLoading(false);
    }
  }

  async function selectSession(sessionId: string) {
    if (loadingSession || requesting) return;
    const requestId = ++sessionRequestId.current;
    setLoadingSession(true);
    setHistoryError("");
    setRequestError("");
    setActiveSessionId(sessionId);
    setMessages([]);
    setSidebarOpen(false);
    try {
      const session = await apiRequest<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`);
      if (sessionRequestId.current !== requestId) return;
      setMessages(session.messages.map((message) => ({
        id: message.message_id,
        role: message.role,
        content: message.content,
        citations: message.citations,
        provider: message.provider,
        created_at: message.created_at
      })));
    } catch (error) {
      if (sessionRequestId.current !== requestId) return;
      setHistoryError(getChatError(error, labels.historyError, labels));
      setActiveSessionId(null);
    } finally {
      if (sessionRequestId.current === requestId) setLoadingSession(false);
    }
  }

  function startNewChat() {
    if (requesting) return;
    sessionRequestId.current += 1;
    setLoadingSession(false);
    setActiveSessionId(null);
    setMessages([]);
    setDraft("");
    setLastQuestion("");
    setRequestError("");
    setComposerError("");
    setSidebarOpen(false);
    setSelectedCitation(null);
  }

  async function sendQuestion(value: string) {
    const question = value.trim();
    if (!question) {
      setComposerError(labels.errorEmpty);
      return;
    }
    if (requesting) return;

    const createdAt = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      citations: [],
      provider: null,
      created_at: createdAt
    };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setLastQuestion(question);
    setComposerError("");
    setRequestError("");
    setRequesting(true);

    try {
      const response = await apiRequest<ChatResponse>("/api/chat", {
        method: "POST",
        body: { message: question, session_id: activeSessionId }
      });
      const answer = response.source_sufficiency === "insufficient"
        ? labels.limitationInsufficient
        : response.citations.length === 0
          ? labels.unverified
          : response.source_sufficiency === "partial"
            ? response.answer.replace(/^Keterbatasan:\s*/i, "")
            : response.answer || labels.noAnswer;
      setMessages((current) => [...current, {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: answer,
        citations: response.citations,
        provider: response.provider,
        created_at: new Date().toISOString(),
        sourceSufficiency: response.source_sufficiency
      }]);
      if (response.session_id) {
        setActiveSessionId(response.session_id);
        setSessions((current) => upsertSession(current, response.session_id!, question));
        void refreshSessions();
      }
    } catch (error) {
      setDraft(question);
      setRequestError(getChatError(error, labels.errorDefault, labels));
    } finally {
      setRequesting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void sendQuestion(draft);
  }

  function retryQuestion() {
    setMessages((current) => {
      const last = current.at(-1);
      return last?.role === "user" && last.content === lastQuestion ? current.slice(0, -1) : current;
    });
    void sendQuestion(lastQuestion);
  }

  function changeLanguage(nextLanguage: InterfaceLanguage) {
    setLanguage(nextLanguage);
  }

  function openCitation(citation: ChatCitation, index: number) {
    lastFocusedElement.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedCitation({ citation, index });
  }

  function closeCitation() {
    setSelectedCitation(null);
    window.requestAnimationFrame(() => lastFocusedElement.current?.focus());
  }

  return (
    <div className="chat-workspace">
      {sidebarOpen ? <button className="chat-sidebar-backdrop" type="button" aria-label={labels.closeMenu} onClick={() => setSidebarOpen(false)} /> : null}
      <ChatSidebar
        labels={labels}
        language={language}
        sessions={sessions}
        activeSessionId={activeSessionId}
        isAuthenticated={isAuthenticated}
        authLoading={authLoading}
        currentUserEmail={currentUser?.email ?? null}
        isOpen={sidebarOpen}
        isWideScreen={isWideScreen}
        isLoading={historyLoading}
        error={historyError}
        onClose={() => setSidebarOpen(false)}
        onNewChat={startNewChat}
        onRetry={() => void refreshSessions()}
        onSelect={selectSession}
        onLanguageChange={changeLanguage}
        menuButtonRef={sidebarMenuButton}
        closeButtonRef={sidebarCloseButton}
      />

      <section className="chat-main" aria-label={labels.workspace}>
        <header className="chat-topbar">
          <button className="icon-button chat-menu-button" type="button" aria-label={labels.menu} aria-expanded={sidebarOpen} ref={sidebarMenuButton} onClick={() => setSidebarOpen(true)}>
            <MenuIcon />
          </button>
          <div className="chat-topbar-title">
            <h1>{labels.workspace}</h1>
          </div>
          <div className="chat-topbar-meta">
            <span className="scope-badge"><span className="scope-dot" aria-hidden="true" />{labels.scope}</span>
          </div>
        </header>

        <div className="chat-scroll-region">
          <div className="chat-content">
            {loadingSession ? <SessionLoading labels={labels} /> : null}
            {!loadingSession && messages.length === 0 ? <EmptyChat labels={labels} language={language} onSuggestion={(value) => setDraft(value)} /> : null}
            {!loadingSession && messages.length > 0 ? <MessageList labels={labels} messages={messages} onOpenCitation={openCitation} /> : null}
            {requestError ? (
              <div className="chat-request-error" role="alert">
                <div><strong>{requestError}</strong></div>
                <button className="text-button" type="button" disabled={!lastQuestion || requesting} onClick={retryQuestion}>{labels.retryQuestion}</button>
              </div>
            ) : null}
            {requesting ? <div className="assistant-pending" role="status" aria-live="polite"><span className="pending-mark" aria-hidden="true"><span /><span /><span /></span><span>{labels.searching}</span></div> : null}
          </div>
        </div>

        <div className="chat-composer-wrap">
          <form className="chat-composer" onSubmit={handleSubmit} aria-busy={requesting}>
            <label className="sr-only" htmlFor="chat-message">{labels.questionLabel}</label>
            <textarea
              id="chat-message"
              name="message"
              value={draft}
              rows={1}
              maxLength={2000}
              disabled={requesting}
              placeholder={labels.placeholder}
              aria-describedby={composerError ? "chat-composer-error" : "chat-composer-hint"}
              aria-invalid={composerError ? true : undefined}
              onChange={(event) => { setDraft(event.target.value); if (composerError) setComposerError(""); }}
              onKeyDown={handleComposerKeyDown}
            />
            <div className="composer-footer">
              <div className="composer-hint">
                <span id="chat-composer-hint">{labels.shortcut}</span>
                <span>{draft.length}/2000</span>
              </div>
              <button className="send-button" type="submit" disabled={requesting || !draft.trim()} aria-label={requesting ? labels.checking : labels.ask}>
                {requesting ? <span className="button-spinner" aria-hidden="true" /> : <ArrowUpIcon />}
              </button>
            </div>
          </form>
          {composerError ? <p className="composer-error" id="chat-composer-error" role="alert">{composerError}</p> : null}
          <p className="composer-disclaimer">{language === "id" ? "RINGKAS dapat keliru. Selalu periksa citation dan publikasi sumber." : "RINGKAS can be wrong. Always check the citations and source publication."}</p>
        </div>
      </section>

      {selectedCitation ? <SourceDrawer labels={labels} citation={selectedCitation.citation} index={selectedCitation.index} onClose={closeCitation} /> : null}
    </div>
  );
}

function ChatSidebar(props: {
  labels: ChatLabels;
  language: InterfaceLanguage;
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  isAuthenticated: boolean;
  authLoading: boolean;
  currentUserEmail: string | null;
  isOpen: boolean;
  isWideScreen: boolean | null;
  isLoading: boolean;
  error: string;
  onClose: () => void;
  onNewChat: () => void;
  onRetry: () => void;
  onSelect: (sessionId: string) => void;
  onLanguageChange: (language: InterfaceLanguage) => void;
  menuButtonRef: RefObject<HTMLButtonElement | null>;
  closeButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  const wasOpen = useRef(false);

  useEffect(() => {
    if (props.isOpen) props.closeButtonRef.current?.focus();
    else if (wasOpen.current) props.menuButtonRef.current?.focus();
    wasOpen.current = props.isOpen;
  }, [props.isOpen, props.closeButtonRef, props.menuButtonRef]);

  return (
    <aside className={`chat-sidebar${props.isOpen ? " is-open" : ""}`} aria-label={props.labels.history} aria-hidden={props.isWideScreen === false && !props.isOpen} inert={props.isWideScreen === false && !props.isOpen ? true : undefined}>
      <div className="sidebar-action-header">
        <button className="new-chat-button" type="button" onClick={props.onNewChat}><PlusIcon />{props.labels.newChat}</button>
        <button className="icon-button sidebar-close-button" type="button" aria-label={props.labels.closeMenu} ref={props.closeButtonRef} onClick={props.onClose}><CloseIcon /></button>
      </div>
      <div className="sidebar-section-heading"><span>{props.labels.history}</span><span className="history-count">{props.isAuthenticated ? props.sessions.length : "-"}</span></div>
      <div className="history-list" aria-live="polite">
        {props.authLoading || props.isLoading ? <HistorySkeleton labels={props.labels} /> : null}
        {!props.authLoading && !props.isLoading && props.error ? <div className="sidebar-state"><p>{props.error}</p><button className="text-button" type="button" onClick={props.onRetry}>{props.labels.retry}</button></div> : null}
        {!props.authLoading && !props.isLoading && !props.error && props.isAuthenticated && props.sessions.length === 0 ? <div className="sidebar-state"><p>{props.labels.historyEmpty}</p></div> : null}
        {!props.authLoading && !props.isLoading && !props.error && props.isAuthenticated ? props.sessions.map((session) => (
          <button className={`history-item${session.session_id === props.activeSessionId ? " is-active" : ""}`} key={session.session_id} type="button" aria-pressed={session.session_id === props.activeSessionId} onClick={() => props.onSelect(session.session_id)}>
            <MessageIcon />
            <span><strong>{session.title || props.labels.newChat}</strong><small>{formatSessionDate(session.updated_at, props.language)}</small></span>
          </button>
        )) : null}
        {!props.authLoading && !props.isAuthenticated ? <div className="guest-history-state"><span className="guest-state-icon"><LockIcon /></span><strong>{props.labels.signIn}</strong><p>{props.labels.signInHint}</p><Link href="/login" onClick={props.onClose}>{props.language === "id" ? "Masuk" : "Sign in"}</Link></div> : null}
      </div>
      <div className="sidebar-footer">
        {props.currentUserEmail ? <span className="sidebar-account"><span className="account-avatar" aria-hidden="true">{props.currentUserEmail[0]?.toUpperCase()}</span><span><strong>{props.labels.signedIn}</strong><small>{props.currentUserEmail}</small></span></span> : null}
      </div>
    </aside>
  );
}

function EmptyChat({ labels, language, onSuggestion }: { labels: ChatLabels; language: InterfaceLanguage; onSuggestion: (value: string) => void }) {
  return (
    <div className="chat-empty">
      <div className="empty-mark" aria-hidden="true"><RingkasLogo size={42} /><i /></div>
      <p className="empty-kicker">{labels.scope}</p>
      <h2>{labels.emptyTitle}</h2>
      <p className="empty-description">{labels.emptyDescription}</p>
      <div className="prompt-list" aria-label={language === "id" ? "Contoh pertanyaan" : "Question examples"}>
        {labels.suggestions.map((suggestion) => <button type="button" key={suggestion} onClick={() => onSuggestion(suggestion)}><span>{suggestion}</span><ArrowUpRightIcon /></button>)}
      </div>
    </div>
  );
}

function MessageList({ labels, messages, onOpenCitation }: { labels: ChatLabels; messages: ChatMessage[]; onOpenCitation: (citation: ChatCitation, index: number) => void }) {
  return (
    <div className="message-list" aria-live="polite">
      {messages.map((message) => message.role === "user" ? (
        <article className="message-row message-row-user" key={message.id} aria-label={labels.userQuestion}><div className="user-message"><p>{message.content}</p></div></article>
      ) : (
        <article className="message-row message-row-assistant" key={message.id} aria-label={labels.assistantAnswer}>
          <div className="assistant-avatar" aria-hidden="true">R</div>
          <div className="assistant-message">
            <div className="assistant-message-header"><strong>{labels.answer}</strong>{message.sourceSufficiency === "partial" ? <span className="evidence-state evidence-state-warn">{labels.partial}</span> : message.sourceSufficiency === "insufficient" || !message.citations.length ? <span className="evidence-state evidence-state-warn">{labels.insufficient}</span> : message.sourceSufficiency === "sufficient" ? <span className="evidence-state evidence-state-good">{labels.sufficient}</span> : <span className="evidence-state evidence-state-neutral">{labels.statusUnavailable}</span>}</div>
            <div className="assistant-answer">{renderAnswer(message.content, message.citations, onOpenCitation, labels)}</div>
            {message.sourceSufficiency === "partial" ? <p className="assistant-limitation">{labels.limitationPartial}</p> : null}
            {message.citations.length ? <div className="message-sources"><div className="message-sources-heading"><span>{labels.sources}</span><span>{labels.sourceCount(message.citations.length)}</span></div><div className="source-chip-list">{message.citations.map((citation, index) => <button className="source-chip" type="button" key={citation.chunk_id} onClick={() => onOpenCitation(citation, index)}><span className="source-chip-index">[{index + 1}]</span><span>{citation.title}</span><ArrowUpRightIcon /></button>)}</div></div> : <p className="no-sources-message">{labels.noSources}</p>}
          </div>
        </article>
      ))}
    </div>
  );
}

function SessionLoading({ labels }: { labels: ChatLabels }) {
  return <div className="session-loading" role="status"><div className="loading-line loading-line-short" /><div className="loading-line" /><div className="loading-line loading-line-medium" /><p>{labels.historyLoading}</p></div>;
}

function HistorySkeleton({ labels }: { labels: ChatLabels }) {
  return <div className="history-skeleton" aria-label={labels.historyLoading}><span /><span /><span /></div>;
}

function SourceDrawer({ labels, citation, index, onClose }: { labels: ChatLabels; citation: ChatCitation; index: number; onClose: () => void }) {
  const drawerRef = useRef<HTMLElement>(null);
  useEffect(() => drawerRef.current?.focus(), []);
  const page = formatPage(citation, labels);
  const safeSource = getSafeUrl(citation.pdf_url ?? citation.source_url);

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab" || !drawerRef.current) return;
    const focusable = Array.from(drawerRef.current.querySelectorAll<HTMLElement>("a[href], button:not(:disabled), input, select, textarea, [tabindex]:not([tabindex='-1'])"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawerRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === drawerRef.current)) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="source-layer" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <aside className="source-drawer" role="dialog" aria-modal="true" aria-labelledby="source-drawer-title" tabIndex={-1} ref={drawerRef} onKeyDown={handleKeyDown}>
        <div className="source-drawer-header"><div><span className="drawer-kicker">[{index + 1}] {labels.sourceDetail}</span><h2 id="source-drawer-title">{citation.title}</h2></div><button className="icon-button" type="button" aria-label={labels.closeSource} onClick={onClose}><CloseIcon /></button></div>
        <div className="source-drawer-body">
          <dl className="source-metadata">
            <div><dt>{labels.document}</dt><dd>{citation.year}</dd></div>
            <div><dt>{labels.region}</dt><dd>{citation.region}</dd></div>
            {page ? <div><dt>{labels.page}</dt><dd>{page}</dd></div> : null}
          </dl>
          <div className="source-excerpt"><span>{labels.language === "id" ? "Kutipan sumber" : "Source excerpt"}</span><blockquote>{citation.snippet}</blockquote></div>
          {safeSource ? <a className="source-drawer-link" href={safeSource} target="_blank" rel="noreferrer">{labels.sourcePublication}<ArrowUpRightIcon /></a> : <p className="source-placeholder">{labels.sourceUnavailable}</p>}
        </div>
      </aside>
    </div>
  );
}

function renderAnswer(content: string, citations: ChatCitation[], onOpenCitation: (citation: ChatCitation, index: number) => void, labels: ChatLabels) {
  return content.split(/\r?\n/).map((line, lineIndex) => (
    <span className="answer-line" key={`${line}-${lineIndex}`}>
      {line.split(/(\[\d+\])/g).map((part, partIndex) => {
        const match = /^\[(\d+)\]$/.exec(part);
        if (!match) return <span key={`${part}-${partIndex}`}>{part}</span>;
        const index = Number(match[1]) - 1;
        const citation = citations[index];
        return citation ? <button className="citation-marker" type="button" key={part} onClick={() => onOpenCitation(citation, index)} aria-label={labels.openCitation(index + 1)}>{part}</button> : <span key={part}>{part}</span>;
      })}
      {lineIndex < content.split(/\r?\n/).length - 1 ? <br /> : null}
    </span>
  ));
}

function getChatError(error: unknown, fallback: string, labels: ChatLabels) {
  if (error instanceof ApiClientError) {
    if (error.status === 401) return labels.errorAuth;
    if (error.status === 429) return labels.errorRate;
    if (error.status >= 500) return labels.errorServer;
  }
  return fallback;
}

function upsertSession(sessions: ChatSessionSummary[], sessionId: string, question: string) {
  const now = new Date().toISOString();
  const next = { session_id: sessionId, title: question.slice(0, 80), created_at: now, updated_at: now };
  return [next, ...sessions.filter((session) => session.session_id !== sessionId)];
}

function formatSessionDate(value: string, language: InterfaceLanguage) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return new Intl.DateTimeFormat(language === "id" ? "id-ID" : "en-US", { day: "numeric", month: "short" }).format(date);
}

function formatPage(citation: ChatCitation, labels: ChatLabels) {
  if (citation.page_start === null && citation.page_end === null) return null;
  if (citation.page_start === citation.page_end || citation.page_end === null) return `${labels.page} ${citation.page_start}`;
  if (citation.page_start === null) return `${labels.page} ${citation.page_end}`;
  return `${labels.page} ${citation.page_start}-${citation.page_end}`;
}

function getSafeUrl(source: string) {
  try {
    const url = new URL(source);
    return url.protocol === "https:" || url.protocol === "http:" ? source : null;
  } catch {
    return null;
  }
}

function MenuIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
}

function PlusIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>;
}

function CloseIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>;
}

function ArrowUpIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 18V6M6.5 11.5 12 6l5.5 5.5" /></svg>;
}

function ArrowUpRightIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>;
}

function MessageIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 3v-3.2A2.5 2.5 0 0 1 5 12.5z" /></svg>;
}

function LockIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5.5" y="10" width="13" height="10" rx="2" /><path d="M8.5 10V7.5a3.5 3.5 0 0 1 7 0V10" /></svg>;
}
