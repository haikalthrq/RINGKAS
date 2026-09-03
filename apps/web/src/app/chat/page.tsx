import type { Metadata } from "next";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export const metadata: Metadata = {
  title: "Ruang Riset"
};

export default function ChatPage() {
  return <div className="chat-route"><ChatWorkspace /></div>;
}
