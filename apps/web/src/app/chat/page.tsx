import { ChatForm } from "@/components/chat/chat-form";

export default function ChatPage() {
  return (
    <section className="page-card chat-page" aria-labelledby="chat-title">
      <p className="eyebrow">Guest chat</p>
      <h1 id="chat-title">Ask about BPS publications</h1>
      <p className="page-intro">Questions will be answered from the RINGKAS document corpus when backend integration is available.</p>
      <ChatForm />
    </section>
  );
}
