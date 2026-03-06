import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';

export default function AIChat() {
    const [messages, setMessages] = useState([
        { role: 'bot', text: '您好，我是 AI 管控助手。您可以询问有关设备健康状态或运维建议的问题。' }
    ]);
    const [input, setInput] = useState('');
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = () => {
        if (!input.trim()) return;

        const userMsg = { role: 'user', text: input };
        setMessages(prev => [...prev, userMsg]);
        setInput('');

        // Simple mock response
        setTimeout(() => {
            let response = '收到。系统正在分析 DGA 数据趋势，建议您关注 1号主变压器的 H2 增长速率。';
            if (input.includes('建议')) {
                response = '根据当前的 AI 演算，建议在下周内安排分接开关的红外测温巡检。';
            }
            setMessages(prev => [...prev, { role: 'bot', text: response }]);
        }, 1000);
    };

    return (
        <div className="flex flex-col h-full">
            <div className="px-4 py-3 border-b border-white/10 font-medium text-cyan-400 flex items-center">
                <Bot className="w-4 h-4 mr-2" />
                AI 管控助手
            </div>
            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-white/10"
            >
                {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[85%] flex space-x-2 ${msg.role === 'user' ? 'flex-row-reverse space-x-reverse' : 'flex-row'}`}>
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'user' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-blue-500/20 text-blue-400'
                                }`}>
                                {msg.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                            </div>
                            <div className={`px-4 py-2 rounded-2xl text-sm ${msg.role === 'user'
                                    ? 'bg-cyan-500 text-white shadow-[0_4px_12px_rgba(0,208,255,0.2)]'
                                    : 'glass-panel text-gray-200'
                                }`}>
                                {msg.text}
                            </div>
                        </div>
                    </div>
                ))}
            </div>
            <div className="p-4 border-t border-white/10">
                <div className="relative">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                        placeholder="输入您的问题..."
                        className="w-full bg-white/5 border border-white/10 rounded-full px-5 py-2.5 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors"
                    />
                    <button
                        onClick={handleSend}
                        className="absolute right-2 top-1.5 w-8 h-8 rounded-full bg-cyan-500 flex items-center justify-center hover:bg-cyan-400 transition-colors"
                    >
                        <Send className="w-4 h-4 text-white" />
                    </button>
                </div>
            </div>
        </div>
    );
}
