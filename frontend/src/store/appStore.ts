import { create } from 'zustand';
import { fetchEventSource } from '@microsoft/fetch-event-source';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  isStreaming?: boolean;
}

export interface Node {
  id: string;
  content: string;
  type: string;
  status: 'OPEN' | 'DONE';
  deadline?: string;
}

interface AppState {
  messages: Message[];
  nodes: Node[]; // This will eventually be synced via PowerSync Local-First DB
  isStreaming: boolean;
  
  sendMessage: (text: string) => Promise<void>;
  addMessage: (msg: Message) => void;
  updateLastMessage: (chunk: string) => void;
  setNodes: (nodes: Node[]) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  messages: [
    { id: '1', role: 'assistant', content: "Hi. Dump your thoughts here, I'll organize them." }
  ],
  nodes: [],
  isStreaming: false,
  
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  
  updateLastMessage: (chunk) => set((state) => {
    const lastMsg = state.messages[state.messages.length - 1];
    if (lastMsg.role === 'assistant') {
      const updatedMessages = [...state.messages];
      updatedMessages[updatedMessages.length - 1] = {
        ...lastMsg,
        content: lastMsg.content + chunk,
      };
      return { messages: updatedMessages };
    }
    return state;
  }),
  
  setNodes: (nodes) => set({ nodes }),

  sendMessage: async (text: string) => {
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text };
    get().addMessage(userMsg);
    
    // Add empty assistant message for streaming
    get().addMessage({ id: (Date.now() + 1).toString(), role: 'assistant', content: '', isStreaming: true });
    set({ isStreaming: true });

    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      await fetchEventSource(`${apiUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: 'local_test_session',
          user_id: '30235965-fa32-4f0f-9aec-71a7cccea859', // Mock user for now
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        }),
        onmessage(ev) {
          if (ev.event === 'message') {
            const data = JSON.parse(ev.data);
            get().updateLastMessage(data.content);
          } else if (ev.event === 'tool_start') {
             // Optional: Display "thinking..." UI based on tool usage
          } else if (ev.event === 'done') {
            set((state) => {
              const msgs = [...state.messages];
              msgs[msgs.length - 1].isStreaming = false;
              return { messages: msgs, isStreaming: false };
            });
          }
        },
        onerror(err) {
          console.error("SSE Error:", err);
          set({ isStreaming: false });
          throw err;
        }
      });
    } catch (err) {
      set({ isStreaming: false });
    }
  }
}));
