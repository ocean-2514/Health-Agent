import React from 'react';
import {
    Gauge, Microscope, Cctv, ClipboardCheck, Bot, Database, Settings,
} from 'lucide-react';

type TabId =
    | 'fleet' | 'reasoning' | 'approval' | 'dlt' | 'agent' | 'monitor'
    | 'knowledge' | 'admin';

type LayoutProps = {
    children: React.ReactNode;
    activeTab: TabId;
    setActiveTab: (tab: TabId) => void;
};

const FRONT_TABS: Array<{ id: TabId; label: string; icon: React.ReactNode; activeOn?: TabId[] }> = [
    { id: 'fleet', label: '综合概览', icon: <Gauge className="w-4 h-4" /> },
    { id: 'reasoning', label: '设备分析', icon: <Microscope className="w-4 h-4" />, activeOn: ['reasoning', 'dlt'] },
    { id: 'monitor', label: '现场监控', icon: <Cctv className="w-4 h-4" /> },
    { id: 'approval', label: '专家复核与工单', icon: <ClipboardCheck className="w-4 h-4" /> },
    { id: 'agent', label: '智能助手', icon: <Bot className="w-4 h-4" /> },
];

const BACK_TABS: Array<{ id: TabId; label: string; icon: React.ReactNode }> = [
    { id: 'knowledge', label: '知识管理', icon: <Database className="w-4 h-4" /> },
    { id: 'admin', label: '系统管理', icon: <Settings className="w-4 h-4" /> },
];

export default function Layout({ children, activeTab, setActiveTab }: LayoutProps) {
    const isDeviceAnalysis = activeTab === 'reasoning' || activeTab === 'dlt';

    return (
        <div className="bg-tech-container font-sans selection:bg-[#cde8e1] h-screen flex flex-col">
            <div className="bg-grid"></div>
            <div className="bg-glow-1"></div>

            {/* Header */}
            <header className="relative z-50 flex items-center justify-between h-16 px-6 border-b border-[#dcdfe6] bg-white flex-shrink-0 overflow-hidden">
                <div className="flex items-center space-x-6 min-w-0 flex-1">
                    <div className="flex items-center space-x-3 flex-shrink-0">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#209F84] to-[#177a66] flex items-center justify-center shadow-sm">
                            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                            </svg>
                        </div>
                        <h1 className="hidden lg:block text-lg font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-[#209F84] to-[#177a66]">
                            变压器健康管控平台
                        </h1>
                    </div>

                    <nav className="flex items-center space-x-1 min-w-0 flex-1 overflow-x-auto custom-scrollbar">
                        {/* 前端 · 用户业务 */}
                        {FRONT_TABS.map((t) => {
                            const active = t.activeOn
                                ? t.activeOn.includes(activeTab)
                                : activeTab === t.id;
                            return (
                                <TabButton key={t.id} active={active} onClick={() => setActiveTab(t.id)}>
                                    <span className="flex items-center space-x-1.5">
                                        {t.icon}<span>{t.label}</span>
                                    </span>
                                </TabButton>
                            );
                        })}

                        {/* 前后端分隔 */}
                        <div className="w-px h-6 bg-[#f0f2f5] mx-2 flex-shrink-0"></div>

                        {/* 后端 · 系统管理（管理员） */}
                        {BACK_TABS.map((t) => (
                            <TabButton key={t.id} active={activeTab === t.id} onClick={() => setActiveTab(t.id)} admin>
                                <span className="flex items-center space-x-1.5">
                                    {t.icon}<span>{t.label}</span>
                                </span>
                            </TabButton>
                        ))}
                    </nav>
                </div>

                <div className="flex items-center space-x-3 text-sm flex-shrink-0">
                    <div className="flex items-center px-3 py-1.5 rounded-full bg-[#f8f8fa] border border-[#dcdfe6]">
                        <div className="w-2 h-2 rounded-full bg-[#6fba47] mr-2 led-pulse-green"></div>
                        <span className="text-[#333333] whitespace-nowrap">服务运行中</span>
                    </div>
                    <div className="hidden md:block px-3 py-1.5 rounded-full bg-[#fdf4e0] text-[#d99000] border border-[#f0d9a8]">
                        当前为标准样本数据，非现场实时采集
                    </div>
                </div>
            </header>

            {/* 设备分析子标签（AI分析 / 标准评价） */}
            {isDeviceAnalysis && (
                <div className="relative z-40 flex items-center px-6 h-10 bg-white border-b border-[#dcdfe6] flex-shrink-0">
                    <span className="text-xs text-[#666666] mr-3">设备分析</span>
                    <SubTabButton active={activeTab === 'reasoning'} onClick={() => setActiveTab('reasoning')}>
                        AI 证据与趋势分析
                    </SubTabButton>
                    <SubTabButton active={activeTab === 'dlt'} onClick={() => setActiveTab('dlt')}>
                        DL/T 1685 标准评价
                    </SubTabButton>
                </div>
            )}

            {/* Main Content Area */}
            <main className="relative z-10 flex-1 p-4 overflow-y-auto custom-scrollbar">
                {children}
            </main>
        </div>
    );
}

function TabButton({ active, onClick, children, admin }: {
    active: boolean; onClick: () => void; children: React.ReactNode; admin?: boolean;
}) {
    return (
        <button
            onClick={onClick}
            className={`relative flex-shrink-0 whitespace-nowrap px-3.5 py-2 text-sm font-medium transition-all duration-300 rounded-lg ${active
                ? 'text-[#209F84] bg-[#e6f4f0] border border-[#9cd2c7]'
                : admin
                    ? 'text-[#666666] hover:text-[#333333] hover:bg-[#f8f8fa] border border-transparent'
                    : 'text-[#666666] hover:text-[#333333] hover:bg-[#f8f8fa] border border-transparent'
                }`}
        >
            {children}
            {active && (
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1/2 h-[1.5px] bg-[#209F84] rounded-t-full shadow-none" />
            )}
        </button>
    );
}

function SubTabButton({ active, onClick, children }: {
    active: boolean; onClick: () => void; children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            className={`flex-shrink-0 whitespace-nowrap px-3 py-1 text-xs rounded-md transition-colors mr-2 ${active
                ? 'text-[#209F84] bg-[#e6f4f0] border border-[#9cd2c7]'
                : 'text-[#666666] hover:text-[#333333] border border-transparent'}`}
        >
            {children}
        </button>
    );
}
