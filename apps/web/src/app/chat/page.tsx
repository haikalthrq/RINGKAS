import { ChatForm } from "@/components/chat/chat-form";

export default function ChatPage() {
  return (
    <section className="page-card chat-page" aria-labelledby="chat-title">
      <p className="eyebrow">Document Q&amp;A</p>
      <h1 id="chat-title">Ask about BPS publications</h1>
      <p className="page-intro">Ask a question and RINGKAS will answer only from evidence found in its indexed BPS publications.</p>
      <ChatForm />
    </section>
  );
}
