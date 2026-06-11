import React from 'react';

type LayoutProps = {
    children: React.ReactNode;
    activeTab: 'fleet' | 'reasoning' | 'approval' | 'agent';
    setActiveTab: (tab: 'fleet' | 'reasoning' | 'approval' | 'agent') => void;
};

export default function Layout({ children, activeTab, setActiveTab }: LayoutProps) {
    return (
        <div className="bg-tech-container font-sans selection:bg-cyan-500/30 h-screen flex flex-col">
            <div className="bg-grid"></div>
            <div className="bg-glow-1"></div>

            {/* Header */}
            <header className="relative z-50 flex items-center justify-between h-16 px-6 border-b border-white/10 bg-[#0A0B10]/80 backdrop-blur-lg flex-shrink-0">
                <div className="flex items-center space-x-8">
                    <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center shadow-[0_0_15px_rgba(0,208,255,0.5)]">
                            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                        </div>
                        <h1 className="text-xl font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-500">
                            主设备全寿命周期管控智能体助手
                        </h1>
                    </div>

                    <nav className="flex items-center space-x-1">
                        <TabButton
                            active={activeTab === 'fleet'}
                            onClick={() => setActiveTab('fleet')}
                        >
                            综合评估
                        </TabButton>
                        <TabButton
                            active={activeTab === 'reasoning'}
                            onClick={() => setActiveTab('reasoning')}
                        >
                            AI分析
                        </TabButton>
                        <TabButton
                            active={activeTab === 'approval'}
                            onClick={() => setActiveTab('approval')}
                        >
                            专家复核
                        </TabButton>
                        <TabButton
                            active={activeTab === 'agent'}
                            onClick={() => setActiveTab('agent')}
                        >
                            智能体平台
                        </TabButton>
                    </nav>
                </div>

                <div className="flex items-center space-x-4 text-sm">
                    <div className="flex items-center px-3 py-1.5 rounded-full bg-white/5 border border-white/10">
                        <div className="w-2 h-2 rounded-full bg-green-400 mr-2 led-pulse-green"></div>
                        <span className="text-gray-300">电网管理单位</span>
                    </div>
                    <div className="px-3 py-1.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-mono">
                        ID: 829145
                    </div>
                </div>
            </header>

            {/* Main Content Area */}
            <main className="relative z-10 flex-1 p-4 overflow-y-auto custom-scrollbar">
                {children}
            </main>
        </div>
    );
}

function TabButton({ active, onClick, children }: { active: boolean, onClick: () => void, children: React.ReactNode }) {
    return (
        <button
            onClick={onClick}
            className={`relative px-5 py-2 text-sm font-medium transition-all duration-300 rounded-lg ${active
                ? 'text-cyan-300 bg-cyan-500/10 border border-cyan-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
                }`}
        >
            {children}
            {active && (
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1/2 h-[1.5px] bg-cyan-400 rounded-t-full shadow-[0_0_8px_rgba(0,208,255,0.8)]" />
            )}
        </button>
    );
}
