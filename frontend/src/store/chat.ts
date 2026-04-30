import { create } from 'zustand';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: { tool: string; input: unknown; output: string }[];
  timestamp: number;
}

interface ChatState {
  messages: ChatMessage[];
  streaming: boolean;
  streamContent: string;
  addMessage: (msg: ChatMessage) => void;
  setStreaming: (streaming: boolean) => void;
  appendStream: (content: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  streaming: false,
  streamContent: '',
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setStreaming: (streaming) => set({ streaming }),
  appendStream: (content) => set((s) => ({ streamContent: s.streamContent + content })),
  clearMessages: () => set({ messages: [], streamContent: '' }),
}));
