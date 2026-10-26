import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    Send, Bot, User, Wrench, BookOpen, Plus, Loader2, Cpu, Sparkles,
    MessageSquare, Trash2, RefreshCw, Power, X, Cloud, FolderSearch,
    Users, Brain, Activity, Clock, Check, CircleAlert,
} from 'lucide-react';
import {
    agentChatStream, agentCatalogue, agentNewSession, agentSessions, agentHistory,
    agentDeleteSession, agentReloadSkills, agentRegisterRemote, agentReloadRemote,
    agentLoadDir, agentEnableTool, agentDisableTool, agentRemoveTool,
    type CatalogueItem, type SessionInfo, type AgentCatalogue,
    type MutationResult,
} from '../lib/api';

type ToolStep = {
    name: string;
    label: string;
    detail: string;
    status: 'running' | 'done' | 'error';
};

type ChatMsg = {
    role: 'user' | 'assistant';
    text: string;
    toolSteps?: ToolStep[];
    streaming?: boolean;
};

// Map a raw tool name + args to a user-friendly workflow line.
function friendlyTool(name: string, args: Record<string, any>): { label: string; detail: string; icon: React.ReactNode } {
    const a = args || {};
    switch (name) {
        case 'spawn_agent': {
            const tasks = Array.isArray(a.tasks) ? a.tasks : [];
            const kinds = tasks.map((t: any) => t?.type || 'general').join('、');
            return { label: '派生子智能体', detail: `${tasks.length} 个子任务${kinds ? ` (${kinds})` : ''}`, icon: <Users className="w-3.5 h-3.5" /> };
        }
        case 'load_skill':
            return { label: '加载知识技能', detail: a.name || '', icon: <BookOpen className="w-3.5 h-3.5" /> };
        case 'append_skill_memory':
            return { label: '记录技能经验', detail: a.skill_name || '', icon: <Brain className="w-3.5 h-3.5" /> };
        case 'save_memory':
            return { label: '写入跨会话记忆', detail: a.name || '', icon: <Brain className="w-3.5 h-3.5" /> };
        case 'transformer_diagnosis':
            return { label: '运行变压器诊断', detail: a.equipment_id || '', icon: <Activity className="w-3.5 h-3.5" /> };
        case 'history_lookup':
            return { label: '查询诊断历史', detail: a.equipment_id || '', icon: <Clock className="w-3.5 h-3.5" /> };
        default:
            return { label: `调用工具: ${name}`, detail: '', icon: <Wrench className="w-3.5 h-3.5" /> };
    }
}

const WELCOME: ChatMsg = {
    role: 'assistant',
    text:
        '您好，我是变压器健康管控多智能体平台。可以让我对设备做诊断/体检、查历史趋势，' +
        '或问 DGA 判读、检修建议等问题——我会按需调用工具、领域知识与子智能体。试试：「给 tr01 做一次体检」。',
};

export default function AgentConsole() {
    const [messages, setMessages] = useState<ChatMsg[]>([WELCOME]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<SessionInfo[]>([]);
    const [tools, setTools] = useState<CatalogueItem[]>([]);
    const [skills, setSkills] = useState<CatalogueItem[]>([]);
    const [notReady, setNotReady] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages, loading]);

    // On mount: load catalogue + session list, and resume the most recent session.
    useEffect(() => {
        agentCatalogue()
            .then(applyCatalogue)
            .catch(() => setNotReady(true));
        refreshSessions(true);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const applyCatalogue = (c: AgentCatalogue) => {
        setTools(c.tools || []);
        setSkills(c.skills || []);
        if ((c.tools?.length ?? 0) === 0 && (c.skills?.length ?? 0) === 0) setNotReady(true);
        else setNotReady(false);
    };

    const refreshSessions = async (resumeLatest = false) => {
        const list = await agentSessions();
        setSessions(list);
        if (resumeLatest && !sessionId && list.length > 0) {
            await switchSession(list[0].session_id);
        }
    };

    const historyToMessages = (rows: { role: string; content: string }[]): ChatMsg[] =>
        rows.map((r) => ({ role: r.role === 'user' ? 'user' : 'assistant', text: r.content }));

    const switchSession = async (id: string) => {
        if (id === sessionId) return;
        setSessionId(id);
        const rows = await agentHistory(id);
        setMessages(rows.length ? historyToMessages(rows) : [WELCOME]);
    };

    // Patch the last (streaming assistant) message.
    const patchLast = (patch: Partial<ChatMsg>) =>
        setMessages((prev) => {
            if (prev.length === 0) return prev;
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
            return copy;
        });

    const handleSend = async () => {
        const text = input.trim();
        if (!text || loading) return;
        setInput('');
        setLoading(true);
        const wasNew = !sessionId;
        // user message + a streaming assistant placeholder
        setMessages((prev) => [
            ...prev,
            { role: 'user', text },
            { role: 'assistant', text: '', toolSteps: [], streaming: true },
        ]);

        let acc = '';
        const steps: ToolStep[] = [];
        try {
            await agentChatStream(text, sessionId ?? undefined, (ev) => {
                if (ev.type === 'session') {
                    setSessionId(ev.session_id);
                } else if (ev.type === 'text') {
                    acc += ev.delta;
                    patchLast({ text: acc });
                } else if (ev.type === 'tool_call') {
                    const f = friendlyTool(ev.name, ev.args);
                    steps.push({ name: ev.name, label: f.label, detail: f.detail, status: 'running' });
                    patchLast({ toolSteps: [...steps] });
                } else if (ev.type === 'tool_result') {
                    for (let i = steps.length - 1; i >= 0; i--) {
                        if (steps[i].name === ev.name && steps[i].status === 'running') {
                            steps[i] = { ...steps[i], status: ev.ok ? 'done' : 'error' };
                            break;
                        }
                    }
                    patchLast({ toolSteps: [...steps] });
                } else if (ev.type === 'final') {
                    acc = ev.answer || acc;
                    patchLast({ text: acc });
                } else if (ev.type === 'error') {
                    acc += (acc ? '\n\n' : '') + '⚠️ ' + ev.message;
                    patchLast({ text: acc });
                }
            });
        } catch (e: any) {
            acc += (acc ? '\n\n' : '') + '⚠️ ' + (e?.message || '请求失败');
            patchLast({ text: acc });
        } finally {
            patchLast({ streaming: false });
            setLoading(false);
            if (wasNew) refreshSessions();
        }
    };

    const handleNewSession = async () => {
        try {
            const id = await agentNewSession();
            setSessionId(id);
            setMessages([WELCOME]);
            refreshSessions();
        } catch {
            setSessionId(null);
            setMessages([WELCOME]);
        }
    };

    const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        await agentDeleteSession(id);
        if (id === sessionId) {
            setSessionId(null);
            setMessages([WELCOME]);
        }
        refreshSessions();
    };

    return (
        <div className="h-full flex gap-4">
            {/* ============ Sessions sidebar ============ */}
            <div className="w-56 flex-shrink-0 flex flex-col glass-panel rounded-2xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
                    <span className="text-sm font-medium text-gray-300 flex items-center">
                        <MessageSquare className="w-4 h-4 mr-2 text-cyan-400" /> 会话
                    </span>
                    <button
                        onClick={handleNewSession}
                        title="新会话"
                        className="w-6 h-6 rounded-md bg-white/5 border border-white/10 flex items-center justify-center text-gray-300 hover:text-cyan-300 hover:border-cyan-500/30 transition-colors"
                    >
                        <Plus className="w-3.5 h-3.5" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                    {sessions.length === 0 && (
                        <p className="text-xs text-gray-600 px-2 py-3">暂无历史会话</p>
                    )}
                    {sessions.map((s) => (
                        <div
                            key={s.session_id}
                            onClick={() => switchSession(s.session_id)}
                            className={`group cursor-pointer rounded-lg px-3 py-2 border transition-colors ${s.session_id === sessionId
                                ? 'bg-cyan-500/10 border-cyan-500/30'
                                : 'bg-white/[0.02] border-transparent hover:bg-white/5'}`}
                        >
                            <div className="flex items-center justify-between gap-1">
                                <span className={`text-xs truncate ${s.session_id === sessionId ? 'text-cyan-300' : 'text-gray-200'}`}>
                                    {s.title || '新会话'}
                                </span>
                                <button
                                    onClick={(e) => handleDeleteSession(s.session_id, e)}
                                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-opacity flex-shrink-0"
                                    title="删除会话"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <div className="text-[10px] text-gray-500 mt-0.5">
                                {s.message_count} 条 · {s.last_active?.slice(5, 16)}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ============ Chat column ============ */}
            <div className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden min-w-0">
                <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 flex-shrink-0">
                    <div className="flex items-center text-cyan-400 font-medium min-w-0">
                        <Cpu className="w-4 h-4 mr-2 flex-shrink-0" />
                        多智能体协同平台
                        <span className="ml-3 text-xs text-gray-400 truncate">
                            {(() => {
                                const cur = sessions.find((s) => s.session_id === sessionId);
                                return cur?.title || (sessionId ? '当前会话' : '新会话（未保存）');
                            })()}
                        </span>
                    </div>
                </div>

                <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-5 custom-scrollbar">
                    {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
                </div>

                <div className="p-4 border-t border-white/10 flex-shrink-0">
                    <div className="relative">
                        <input
                            type="text"
                            value={input}
                            disabled={loading}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                            placeholder={loading ? '智能体处理中…' : '输入问题，例如：给 tr01 做一次体检'}
                            className="w-full bg-white/5 border border-white/10 rounded-full pl-5 pr-12 py-2.5 text-sm focus:outline-none focus:border-cyan-500/50 transition-colors disabled:opacity-50"
                        />
                        <button
                            onClick={handleSend}
                            disabled={loading || !input.trim()}
                            className="absolute right-2 top-1.5 w-8 h-8 rounded-full bg-cyan-500 flex items-center justify-center hover:bg-cyan-400 transition-colors disabled:opacity-40"
                        >
                            {loading ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Send className="w-4 h-4 text-white" />}
                        </button>
                    </div>
                </div>
            </div>

            {/* ============ Capability panel ============ */}
            <CapabilityPanel
                tools={tools}
                skills={skills}
                notReady={notReady}
                onCatalogue={applyCatalogue}
            />
        </div>
    );
}

function CapabilityPanel({
    tools, skills, notReady, onCatalogue,
}: {
    tools: CatalogueItem[];
    skills: CatalogueItem[];
    notReady: boolean;
    onCatalogue: (c: AgentCatalogue) => void;
}) {
    const [busy, setBusy] = useState<string | null>(null);
    const [remoteUrl, setRemoteUrl] = useState('');
    const [remoteName, setRemoteName] = useState('');
    const [dirPath, setDirPath] = useState('');
    const [err, setErr] = useState<string | null>(null);
    const [msg, setMsg] = useState<string | null>(null);

    const run = async (
        key: string,
        fn: () => Promise<MutationResult>,
        describe?: (r: MutationResult) => string,
    ) => {
        setBusy(key);
        setErr(null);
        setMsg(null);
        try {
            const r = await fn();
            onCatalogue(r);
            if (describe) setMsg(describe(r));
        } catch (e: any) {
            setErr(e?.message || '操作失败');
        } finally {
            setBusy(null);
        }
    };

    return (
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
            {notReady && (
                <div className="glass-panel rounded-2xl p-4 text-xs text-amber-300/90 border border-amber-500/20">
                    智能体尚未就绪（后端初始化失败或 Ollama 未启动）。
                </div>
            )}
            {err && (
                <div className="glass-panel rounded-2xl p-3 text-xs text-red-300/90 border border-red-500/20">
                    {err}
                </div>
            )}
            {msg && (
                <div className="glass-panel rounded-2xl p-3 text-xs text-emerald-300/90 border border-emerald-500/20">
                    {msg}
                </div>
            )}

            {/* Tools */}
            <div className="glass-panel rounded-2xl p-4">
                <div className="flex items-center font-medium mb-3 text-cyan-400">
                    <Wrench className="w-4 h-4" />
                    <span className="ml-2 text-sm">可调用工具 (Tools)</span>
                    <span className="ml-auto text-xs text-gray-500">{tools.length}</span>
                </div>

                <div className="space-y-2">
                    {tools.length === 0 && <p className="text-xs text-gray-600">（无）</p>}
                    {tools.map((t) => (
                        <div key={t.name} className={`bg-white/5 rounded-lg px-3 py-2 border ${t.disabled ? 'border-white/5 opacity-60' : 'border-white/5'}`}>
                            <div className="flex items-center">
                                <span className="text-xs font-mono text-gray-200">{t.name}</span>
                                {t.builtin && <span className="ml-2 text-[10px] px-1.5 rounded bg-cyan-500/15 text-cyan-300/80 border border-cyan-500/20">内置</span>}
                                {t.disabled && <span className="ml-2 text-[10px] px-1.5 rounded bg-gray-500/20 text-gray-400">disabled</span>}
                                <div className="ml-auto flex items-center gap-1">
                                    <button
                                        title={t.disabled ? '启用' : '禁用'}
                                        disabled={!!busy}
                                        onClick={() => run(`toggle-${t.name}`, () =>
                                            t.disabled ? agentEnableTool(t.name) : agentDisableTool(t.name))}
                                        className={`p-1 rounded hover:bg-white/10 ${t.disabled ? 'text-gray-500' : 'text-cyan-400'}`}
                                    >
                                        <Power className="w-3.5 h-3.5" />
                                    </button>
                                    {/* built-in tools are core capabilities — not removable */}
                                    {!t.builtin && (
                                        <button
                                            title="移除"
                                            disabled={!!busy}
                                            onClick={() => run(`rm-${t.name}`, () => agentRemoveTool(t.name))}
                                            className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-white/10"
                                        >
                                            <X className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </div>
                            </div>
                            <p className="text-[11px] text-gray-500 mt-1 line-clamp-2">{t.description}</p>
                        </div>
                    ))}
                </div>

                {/* add remote tool */}
                <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
                    <div className="flex items-center text-[11px] text-gray-500">
                        <Cloud className="w-3.5 h-3.5 mr-1" /> 热加载远程 A2A 工具
                    </div>
                    <input
                        value={remoteUrl}
                        onChange={(e) => setRemoteUrl(e.target.value)}
                        placeholder="http://host:port"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-cyan-500/50"
                    />
                    <div className="flex gap-1.5">
                        <input
                            value={remoteName}
                            onChange={(e) => setRemoteName(e.target.value)}
                            placeholder="名称(可选, 探活失败时必填)"
                            className="flex-1 min-w-0 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-cyan-500/50"
                        />
                        <button
                            disabled={!!busy || !remoteUrl.trim()}
                            onClick={() => run('add-remote', async () => {
                                const c = await agentRegisterRemote(remoteUrl.trim(), remoteName.trim() || undefined);
                                setRemoteUrl(''); setRemoteName('');
                                return c;
                            }, (r) => `已注册远程工具: ${r.registered}`)}
                            className="px-3 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs hover:bg-cyan-500/30 disabled:opacity-40"
                        >
                            {busy === 'add-remote' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '加'}
                        </button>
                    </div>
                    <button
                        disabled={!!busy}
                        onClick={() => run('reload-remote', agentReloadRemote,
                            (r) => (r.added?.length ? `新增远程: ${r.added.join(', ')}` : '无新增(全部已注册或无 enabled 项)'))}
                        className="w-full text-[11px] py-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-400 hover:text-gray-200 flex items-center justify-center gap-1 disabled:opacity-40"
                    >
                        <RefreshCw className={`w-3 h-3 ${busy === 'reload-remote' ? 'animate-spin' : ''}`} /> 重载 remote_tools.yaml
                    </button>
                </div>

                {/* scan a directory for local tools */}
                <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
                    <div className="flex items-center text-[11px] text-gray-500">
                        <FolderSearch className="w-3.5 h-3.5 mr-1" /> 扫描目录加载本地工具
                    </div>
                    <div className="flex gap-1.5">
                        <input
                            value={dirPath}
                            onChange={(e) => setDirPath(e.target.value)}
                            placeholder="examples/hot_tools"
                            className="flex-1 min-w-0 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-cyan-500/50"
                        />
                        <button
                            disabled={!!busy || !dirPath.trim()}
                            onClick={() => run('load-dir', async () => {
                                const c = await agentLoadDir(dirPath.trim());
                                setDirPath('');
                                return c;
                            }, (r) => (r.added?.length
                                ? `新增工具: ${r.added.join(', ')}`
                                : '未发现可加载工具(该目录 .py 需在模块级写 TOOL=... 或 TOOLS=[...])'))}
                            className="px-2.5 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs hover:bg-cyan-500/30 disabled:opacity-40"
                        >
                            {busy === 'load-dir' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '扫描'}
                        </button>
                    </div>
                    <p className="text-[10px] text-gray-600">
                        相对路径以仓库根为基准。内置工具(tools/ 下)是类形式 + 在 tools.yaml 声明,
                        不经此扫描;示例可填 <span className="text-gray-500">examples/hot_tools</span>。
                    </p>
                </div>
            </div>

            {/* Skills */}
            <div className="glass-panel rounded-2xl p-4">
                <div className="flex items-center font-medium mb-1 text-violet-400">
                    <BookOpen className="w-4 h-4" />
                    <span className="ml-2 text-sm">领域知识技能 (Skills)</span>
                    <span className="ml-auto text-xs text-gray-500">{skills.length}</span>
                </div>
                <p className="text-[11px] text-gray-500 mb-3">经 load_skill 按需加载</p>
                <div className="space-y-2">
                    {skills.length === 0 && <p className="text-xs text-gray-600">（无）</p>}
                    {skills.map((s) => (
                        <div key={s.name} className="bg-white/5 rounded-lg px-3 py-2 border border-white/5">
                            <span className="text-xs font-mono text-gray-200">{s.name}</span>
                            <p className="text-[11px] text-gray-500 mt-1 line-clamp-2">{s.description}</p>
                        </div>
                    ))}
                </div>
                <button
                    disabled={!!busy}
                    onClick={() => run('reload-skills', agentReloadSkills,
                        (r) => `已重载知识技能 (${r.skills.length} 个)`)}
                    className="mt-3 w-full text-[11px] py-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-300 hover:bg-violet-500/20 flex items-center justify-center gap-1 disabled:opacity-40"
                >
                    <RefreshCw className={`w-3 h-3 ${busy === 'reload-skills' ? 'animate-spin' : ''}`} /> 重载知识技能 (扫描 SKILL.md)
                </button>
            </div>
        </div>
    );
}

function StepIcon({ status }: { status: ToolStep['status'] }) {
    if (status === 'running') return <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />;
    if (status === 'done') return <Check className="w-3.5 h-3.5 text-emerald-400" />;
    return <CircleAlert className="w-3.5 h-3.5 text-red-400" />;
}

function Workflow({ steps }: { steps: (ToolStep & { icon?: React.ReactNode })[] }) {
    return (
        <div className="glass-panel rounded-xl px-3 py-2 space-y-1.5 border border-white/5">
            <div className="text-[10px] uppercase tracking-wider text-gray-500 flex items-center">
                <Sparkles className="w-3 h-3 mr-1" /> 工作流
            </div>
            {steps.map((s, i) => (
                <div key={i} className="flex items-center text-xs">
                    <span className="w-4 flex justify-center mr-1.5 text-gray-400">{s.icon ?? <Wrench className="w-3.5 h-3.5" />}</span>
                    <span className={s.status === 'error' ? 'text-red-300' : 'text-gray-200'}>{s.label}</span>
                    {s.detail && <span className="ml-1.5 text-gray-500 font-mono text-[11px]">{s.detail}</span>}
                    <span className="ml-auto pl-2"><StepIcon status={s.status} /></span>
                </div>
            ))}
        </div>
    );
}

// friendlyTool returns an icon; attach it onto steps for rendering.
function withIcons(steps: ToolStep[]): (ToolStep & { icon?: React.ReactNode })[] {
    return steps.map((s) => ({ ...s, icon: friendlyTool(s.name, {}).icon }));
}

function MessageBubble({ msg }: { msg: ChatMsg }) {
    const isUser = msg.role === 'user';
    const steps = msg.toolSteps && msg.toolSteps.length > 0 ? withIcons(msg.toolSteps) : [];
    const showThinking = msg.streaming && !msg.text && steps.length === 0;
    return (
        <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] flex space-x-2 ${isUser ? 'flex-row-reverse space-x-reverse' : 'flex-row'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-cyan-500/20 text-cyan-400' : 'bg-blue-500/20 text-blue-400'}`}>
                    {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
                <div className="space-y-1.5 min-w-0">
                    {!isUser && steps.length > 0 && <Workflow steps={steps} />}

                    {showThinking && (
                        <div className="glass-panel px-4 py-2.5 rounded-2xl text-sm text-gray-400 flex items-center">
                            <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> 智能体思考中…
                        </div>
                    )}

                    {msg.text && (
                        isUser ? (
                            <div className="px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed bg-cyan-500 text-white shadow-[0_4px_12px_rgba(0,208,255,0.2)]">
                                {msg.text}
                            </div>
                        ) : (
                            <div className="px-4 py-2.5 rounded-2xl glass-panel text-gray-200">
                                <div className="md-body">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
                                </div>
                                {msg.streaming && <span className="inline-block w-1.5 h-4 align-middle bg-cyan-400/70 animate-pulse ml-0.5" />}
                            </div>
                        )
                    )}
                </div>
            </div>
        </div>
    );
}
