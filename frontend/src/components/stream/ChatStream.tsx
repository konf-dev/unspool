import React, { useState } from 'react';
import { useAppStore } from '../../store/appStore';
import { Send, Loader2 } from 'lucide-react';

export const ChatStream: React.FC = () => {
  const { messages, sendMessage, isStreaming } = useAppStore();
  const [input, setInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    sendMessage(input);
    setInput('');
  };

  return (
    <div className="flex flex-col h-full bg-[#1A1A1A] text-gray-200 p-4 font-sans">
      <div className="flex-1 overflow-y-auto space-y-6 pb-20">
        {messages.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div 
              className={`max-w-[85%] p-3 rounded-2xl ${
                msg.role === 'user' 
                  ? 'bg-[#3A3A3C] text-white rounded-br-none' 
                  : 'bg-transparent text-gray-300 border border-[#333]'
              }`}
            >
              {msg.content || (msg.isStreaming && <Loader2 className="w-4 h-4 animate-spin text-gray-500" />)}
            </div>
          </div>
        ))}
      </div>

      <div className="absolute bottom-0 left-0 w-full p-4 bg-gradient-to-t from-[#1A1A1A] to-transparent">
        <form 
          onSubmit={handleSubmit}
          className="flex items-center bg-[#2C2C2E] p-2 rounded-full border border-[#444] shadow-lg"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="What's on your mind?"
            className="flex-1 bg-transparent border-none outline-none px-4 text-white placeholder-gray-500"
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isStreaming}
            className="p-2 bg-white text-black rounded-full disabled:opacity-50 transition-transform active:scale-95"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
