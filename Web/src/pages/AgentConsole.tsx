import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    Send, Bot, User, Wrench, BookOpen, Plus, Loader2, Cpu,
    MessageSquare, Trash2, RefreshCw, Power, X, Cloud, FolderSearch,
    ImagePlus, CircleAlert,
} from 'lucide-react';
import {
    agentChatStream, agentCatalogue, agentNewSession, agentSessions, agentHistory,
    agentDeleteSession, agentReloadSkills, agentRegisterRemote, agentReloadRemote,
    agentLoadDir, agentEnableTool, agentDisableTool, agentRemoveTool,
    agentUploadImage,
    type CatalogueItem, type SessionInfo, type AgentCatalogue,
    type MutationResult,
    type IntentInfo, type PlanStep, type EvidenceRecord, type GuardResult,
} from '../lib/api';
import { roleForTool, ROLE_META } from '../lib/agentMeta';
import IntentBadge from '../components/agent/IntentBadge';
import PlanPanel from '../components/agent/PlanPanel';
import CollaborationGraph, { type TraceEntry } from '../components/agent/CollaborationGraph';
import EvidenceCard from '../components/agent/EvidenceCard';
import GuardCard from '../components/agent/GuardCard';

// An image attached to a chat message. `url` is a same-origin URL the browser
// can render; the edge path is kept only on the backend and never typed here.
type ChatImage = { url: string; name: string };

type ChatMsg = {
    role: 'user' | 'assistant';
    text: string;
    images?: ChatImage[];
    streaming?: boolean;
    intent?: IntentInfo | null;
    planSteps?: PlanStep[];
    evidence?: EvidenceRecord[];
    guard?: GuardResult | null;
    trace?: TraceEntry[];
};

// A picked image before it is sent. It uploads immediately so the send path is
// fast and upload errors surface early.
type Attachment = {
    id: string;
    name: string;
    previewUrl: string;
    status: 'uploading' | 'done' | 'error';
    serverPath?: string;
    serverUrl?: string;
    error?: string;
};

const WELCOME: ChatMsg = {
    role: 'assistant',
    text:
        '您好，我是变压器健康智能助手。可以请我对设备做体检诊断、查看历史趋势，' +
        '或咨询油色谱判读、检修建议等问题；回答会附上依据来源与校核结果，便于核对。',
};

const sanitizeDisplay = (text = '') =>
    text
        .replace(/预测剩余寿命（RUL）/g, '预测剩余寿命')
        .replace(/健康指数（HI）/g, '健康指数')
        .replace(/\bRUL\b/g, '剩余寿命')
        .replace(/\bHI\b/g, '健康指数');

export default function AgentConsole() {
    const [messages, setMessages] = useState<ChatMsg[]>([WELCOME]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [sessions, setSessions] = useState<SessionInfo[]>([]);
    const [tools, setTools] = useState<CatalogueItem[]>([]);
    const [skills, setSkills] = useState<CatalogueItem[]>([]);
    const [notReady, setNotReady] = useState(false);
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const scrollRef = useRef<HTMLDivElement>(null);
    const fileRef = useRef<HTMLInputElement>(null);

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

    // Patch the last (streaming assistant) message with a plain merge.
    const patchLast = (patch: Partial<ChatMsg>) =>
        setMessages((prev) => {
            if (prev.length === 0) return prev;
            const copy = [...prev];
            copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
            return copy;
        });

    // Patch the last message with a pure updater (used for nested arrays: steps / trace).
    const patchLastMsg = (fn: (msg: ChatMsg) => ChatMsg) =>
        setMessages((prev) => {
            if (prev.length === 0) return prev;
            const copy = [...prev];
            copy[copy.length - 1] = fn(copy[copy.length - 1]);
            return copy;
        });

    const makeId = () =>
        (crypto as Crypto & { randomUUID?: () => string })?.randomUUID?.() ??
        `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    // Pick images, show local previews, and upload each immediately.
    const addFiles = async (fileList: FileList | File[]) => {
        const files = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
        if (!files.length) return;
        const created: Attachment[] = files.map((f) => ({
            id: makeId(),
            name: f.name,
            previewUrl: URL.createObjectURL(f),
            status: 'uploading',
        }));
        setAttachments((prev) => [...prev, ...created]);

        await Promise.all(
            created.map(async (att, idx) => {
                try {
                    const up = await agentUploadImage(files[idx]);
                    setAttachments((prev) =>
                        prev.map((a) =>
                            a.id === att.id
                                ? { ...a, status: 'done', serverPath: up.path, serverUrl: up.url }
                                : a,
                        ),
                    );
                } catch (e: any) {
                    setAttachments((prev) =>
                        prev.map((a) =>
                            a.id === att.id
                                ? { ...a, status: 'error', error: e?.message || '上传失败' }
                                : a,
                        ),
                    );
                }
            }),
        );
    };

    const removeAttachment = (id: string) => {
        setAttachments((prev) => {
            const target = prev.find((a) => a.id === id);
            if (target) URL.revokeObjectURL(target.previewUrl);
            return prev.filter((a) => a.id !== id);
        });
    };

    const handleSend = async () => {
        const text = input.trim();
        const ready = attachments.filter((a) => a.status === 'done');
        const uploading = attachments.some((a) => a.status === 'uploading');
        if (loading || uploading) return;
        if (!text && ready.length === 0) return;

        const imagePaths = ready.map((a) => a.serverPath as string);
        const chatImages: ChatImage[] = ready.map((a) => ({
            url: a.serverUrl as string,
            name: a.name,
        }));
        // Local preview object URLs are no longer needed once the server URLs
        // are available; clear the tray before the request runs.
        attachments.forEach((a) => URL.revokeObjectURL(a.previewUrl));
        setAttachments([]);
        setInput('');
        setLoading(true);
        const wasNew = !sessionId;
        // user message (with thumbnails) + a streaming assistant placeholder
        setMessages((prev) => [
            ...prev,
            { role: 'user', text, images: chatImages.length ? chatImages : undefined },
            { role: 'assistant', text: '', streaming: true },
        ]);

        let acc = '';
        try {
            await agentChatStream(
                text,
                sessionId ?? undefined,
                (ev) => {
                    if (ev.type === 'session') {
                        setSessionId(ev.session_id);
                    } else if (ev.type === 'intent') {
                        patchLast({
                            intent: {
                                intent: ev.intent,
                                label: ev.label,
                                confidence: ev.confidence,
                                source: ev.source,
                                needs_plan: ev.needs_plan,
                            },
                        });
                    } else if (ev.type === 'plan') {
                        patchLast({
                            planSteps: Array.isArray(ev.steps) ? ev.steps.map((s) => ({ ...s })) : [],
                        });
                    } else if (ev.type === 'evidence') {
                        patchLast({
                            evidence: Array.isArray(ev.records) ? ev.records : [],
                        });
                    } else if (ev.type === 'text') {
                        acc += ev.delta;
                        patchLast({ text: acc });
                    } else if (ev.type === 'tool_call') {
                        const role = ev.role ?? roleForTool(ev.name);
                        patchLastMsg((msg) => {
                            const trace = [
                                ...(msg.trace ?? []),
                                { role, name: ev.name, title: ev.title, status: 'running' as const, stepId: ev.step_id },
                            ];
                            let planSteps = msg.planSteps;
                            if (ev.step_id && planSteps && planSteps.length > 0) {
                                planSteps = planSteps.map((s) =>
                                    s.step_id === ev.step_id ? { ...s, status: 'running' as const } : s,
                                );
                            }
                            return { ...msg, trace, planSteps };
                        });
                    } else if (ev.type === 'tool_result') {
                        patchLastMsg((msg) => {
                            const trace = [...(msg.trace ?? [])];
                            for (let i = trace.length - 1; i >= 0; i--) {
                                if (trace[i].status !== 'running') continue;
                                const hit = ev.step_id
                                    ? trace[i].stepId === ev.step_id
                                    : trace[i].name === ev.name;
                                if (hit) {
                                    trace[i] = { ...trace[i], status: ev.ok ? 'done' : 'error' };
                                    break;
                                }
                            }
                            let planSteps = msg.planSteps;
                            if (ev.step_id && planSteps && planSteps.length > 0) {
                                planSteps = planSteps.map((s) =>
                                    s.step_id === ev.step_id
                                        ? { ...s, status: ev.ok ? 'done' : 'error' }
                                        : s,
                                );
                            }
                            return { ...msg, trace, planSteps };
                        });
                    } else if (ev.type === 'final') {
                        acc = ev.answer || acc;
                        patchLast({ text: acc });
                    } else if (ev.type === 'guard') {
                        patchLast({ guard: ev });
                    } else if (ev.type === 'error') {
                        acc += (acc ? '\n\n' : '') + '提示：' + ev.message;
                        patchLast({ text: acc });
                    }
                },
                undefined,
                imagePaths,
            );
        } catch (e: any) {
            patchLastMsg((msg) => ({
                ...msg,
                trace: (msg.trace ?? []).map((t) =>
                    t.status === 'running' ? { ...t, status: 'error' as const } : t,
                ),
                planSteps: (msg.planSteps ?? []).map((s) =>
                    s.status === 'running' ? { ...s, status: 'error' as const } : s,
                ),
            }));
            acc += (acc ? '\n\n' : '') + '提示：' + (e?.message || '请求失败');
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
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#dcdfe6] flex-shrink-0">
                    <span className="text-sm font-medium text-[#333333] flex items-center">
                        <MessageSquare className="w-4 h-4 mr-2 text-[#209F84]" /> 会话
                    </span>
                    <button
                        onClick={handleNewSession}
                        title="新会话"
                        className="w-6 h-6 rounded-md bg-[#f8f8fa] border border-[#dcdfe6] flex items-center justify-center text-[#333333] hover:text-[#209F84] hover:border-[#9cd2c7] transition-colors"
                    >
                        <Plus className="w-3.5 h-3.5" />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                    {sessions.length === 0 && (
                        <p className="text-xs text-[#666666] px-2 py-3">暂无历史会话</p>
                    )}
                    {sessions.map((s) => (
                        <div
                            key={s.session_id}
                            onClick={() => switchSession(s.session_id)}
                            className={`group cursor-pointer rounded-lg px-3 py-2 border transition-colors ${s.session_id === sessionId
                                ? 'bg-[#e6f4f0] border-[#9cd2c7]'
                                : 'bg-[#f8f8fa] border-transparent hover:bg-[#f8f8fa]'}`}
                        >
                            <div className="flex items-center justify-between gap-1">
                                <span className={`text-xs truncate ${s.session_id === sessionId ? 'text-[#209F84]' : 'text-[#333333]'}`}>
                                    {s.title || '新会话'}
                                </span>
                                <button
                                    onClick={(e) => handleDeleteSession(s.session_id, e)}
                                    className="opacity-0 group-hover:opacity-100 text-[#666666] hover:text-[#ff5b01] transition-opacity flex-shrink-0"
                                    title="删除会话"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <div className="text-[10px] text-[#666666] mt-0.5">
                                {s.message_count} 条 · {s.last_active?.slice(5, 16)}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ============ Chat column ============ */}
            <div className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden min-w-0">
                <div className="flex items-center justify-between px-5 py-3 border-b border-[#dcdfe6] flex-shrink-0">
                    <div className="flex items-center text-[#209F84] font-medium min-w-0">
                        <Cpu className="w-4 h-4 mr-2 flex-shrink-0" />
                        智能问答助手
                        <span className="ml-3 text-xs text-[#666666] truncate">
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

                <div className="p-4 border-t border-[#dcdfe6] flex-shrink-0">
                    {/* Pending attachment tray: thumbnails with upload/error state */}
                    {attachments.length > 0 && (
                        <div className="flex flex-wrap gap-2 mb-2.5">
                            {attachments.map((a) => (
                                <div
                                    key={a.id}
                                    className="relative group w-16 h-16 rounded-lg overflow-hidden border border-[#dcdfe6] bg-[#f8f8fa]"
                                >
                                    <img src={a.previewUrl} alt={a.name} className="w-full h-full object-cover" />
                                    {a.status === 'uploading' && (
                                        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                                            <Loader2 className="w-4 h-4 text-[#333333] animate-spin" />
                                        </div>
                                    )}
                                    {a.status === 'error' && (
                                        <div
                                            className="absolute inset-0 bg-[#fbe3d4] flex items-center justify-center"
                                            title={a.error}
                                        >
                                            <CircleAlert className="w-4 h-4 text-[#333333]" />
                                        </div>
                                    )}
                                    <button
                                        onClick={() => removeAttachment(a.id)}
                                        className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                                        title="移除"
                                    >
                                        <X className="w-2.5 h-2.5 text-[#333333]" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="relative">
                        <input
                            type="file"
                            ref={fileRef}
                            className="hidden"
                            accept="image/*"
                            multiple
                            onChange={(e) => {
                                if (e.target.files) addFiles(e.target.files);
                                e.target.value = '';
                            }}
                        />
                        <button
                            onClick={() => fileRef.current?.click()}
                            disabled={loading}
                            title="上传图片"
                            className="absolute left-2.5 top-1.5 w-8 h-8 rounded-full flex items-center justify-center text-[#666666] hover:text-[#209F84] hover:bg-[#f8f8fa] transition-colors disabled:opacity-40"
                        >
                            <ImagePlus className="w-5 h-5" />
                        </button>
                        <input
                            type="text"
                            value={input}
                            disabled={loading}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                            onPaste={(e) => {
                                const pasted = Array.from(e.clipboardData.items)
                                    .filter((it) => it.type.startsWith('image/'))
                                    .map((it) => it.getAsFile())
                                    .filter((f): f is File => !!f);
                                if (pasted.length) addFiles(pasted);
                            }}
                            placeholder={loading ? '正在分析…' : '输入问题，或点击左侧图标上传图片'}
                            className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded-full pl-12 pr-12 py-2.5 text-sm focus:outline-none focus:border-[#6ab8aa] transition-colors disabled:opacity-50"
                        />
                        <button
                            onClick={handleSend}
                            disabled={
                                loading ||
                                attachments.some((a) => a.status === 'uploading') ||
                                (!input.trim() && !attachments.some((a) => a.status === 'done'))
                            }
                            className="absolute right-2 top-1.5 w-8 h-8 rounded-full bg-[#209F84] flex items-center justify-center hover:bg-[#209F84] transition-colors disabled:opacity-40"
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

const TOOL_FRIENDLY: Record<string, string> = {
    edge_visible_detect: '图像缺陷检测',
    edge_inspect: '图像结果复检',
    edge_stream: '监控画面调阅',
    edge_vlm_review: '图像综合复核',
    transformer_diagnosis: '变压器健康诊断',
    edge_alarm: '现场告警查询',
    load_skill: '规程知识调用',
    append_skill_memory: '分析经验积累',
    save_memory: '分析结论保存',
    middle_rag_ask: '规程条款检索',
    history_lookup: '历史结论查询',
    compose: '检修建议单生成',
    spawn_agent: '专项分析调用',
};

const SKILL_FRIENDLY: Record<string, string> = {
    'dga-interpretation': '油色谱判读指引',
    'maintenance-report': '检修报告写作指引',
};

function skillFriendlyName(name: string) {
    return SKILL_FRIENDLY[name] || name;
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

    const businessTools = tools.filter(
        (t) => TOOL_FRIENDLY[t.name] && t.name !== 'spawn_agent' && t.builtin !== false && !t.disabled,
    );
    const businessSkills = skills.filter((s) => SKILL_FRIENDLY[s.name]);

    return (
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
            {notReady && (
                <div className="glass-panel rounded-2xl p-4 text-xs text-[#d99000] border border-[#f0d9a8]">
                    问答服务暂时未就绪，请稍后刷新重试。
                </div>
            )}
            {err && (
                <div className="glass-panel rounded-2xl p-3 text-xs text-[#ff5b01] border border-[#f5c3a3]">
                    {err}
                </div>
            )}
            {msg && (
                <div className="glass-panel rounded-2xl p-3 text-xs text-[#5ba83c] border border-[#c4e3b0]">
                    {msg}
                </div>
            )}

            {/* 业务主视图：可用分析能力 */}
            <div className="glass-panel rounded-2xl p-4">
                <div className="flex items-center font-medium mb-3 text-[#209F84]">
                    <Wrench className="w-4 h-4" />
                    <span className="ml-2 text-sm">可用分析能力</span>
                    <span className="ml-auto text-xs text-[#666666]">{businessTools.length}</span>
                </div>
                <div className="space-y-2">
                    {businessTools.length === 0 && <p className="text-xs text-[#666666]">暂无可展示的能力项。</p>}
                    {businessTools.map((t) => {
                        const role = roleForTool(t.name);
                        return (
                            <div key={t.name} className="bg-[#f8f8fa] rounded-lg px-3 py-2 border border-[#dcdfe6]">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-xs text-[#333333]">{TOOL_FRIENDLY[t.name]}</span>
                                    <span className="text-[9px] text-[#666666]">{ROLE_META[role].tagline}</span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* 业务主视图：规程知识条目 */}
            <div className="glass-panel rounded-2xl p-4">
                <div className="flex items-center font-medium mb-3 text-[#8a63e0]">
                    <BookOpen className="w-4 h-4" />
                    <span className="ml-2 text-sm">规程知识条目</span>
                    <span className="ml-auto text-xs text-[#666666]">{businessSkills.length}</span>
                </div>
                <div className="space-y-2">
                    {businessSkills.length === 0 && (
                        <p className="text-xs text-[#666666]">暂无规程知识条目。</p>
                    )}
                    {businessSkills.map((s) => (
                            <div key={s.name} className="bg-[#f8f8fa] rounded-lg px-3 py-2 border border-[#dcdfe6]">
                                <span className="text-xs text-[#333333]">{skillFriendlyName(s.name)}</span>
                                <p className="text-[11px] text-[#666666] mt-1 line-clamp-2">{s.description}</p>
                            </div>
                        ))}
                </div>
            </div>

            {/* 高级运维（默认折叠，仅系统管理员使用，不进入普通业务流程） */}
            <details className="glass-panel rounded-2xl p-3">
                <summary className="cursor-pointer text-[11px] text-[#666666] select-none hover:text-[#333333]">
                    高级运维（仅系统管理员）
                </summary>
                <div className="mt-3 space-y-3">
                    {tools.filter((t) => !t.builtin).length > 0 && (
                    <div className="space-y-1.5">
                        <div className="text-[11px] text-[#666666]">可选能力维护（管理员）</div>
                        {tools.filter((t) => !t.builtin).map((t) => (
                            <div key={t.name} className="flex items-center gap-2 text-[11px] text-[#666666]">
                                <span className="flex-1 truncate">{TOOL_FRIENDLY[t.name] || t.name}</span>
                                <button
                                    title={t.disabled ? '启用' : '禁用'}
                                    disabled={!!busy}
                                    onClick={() => run(`toggle-${t.name}`, () =>
                                        t.disabled ? agentEnableTool(t.name) : agentDisableTool(t.name))}
                                    className="p-1 rounded hover:bg-[#f2f4f6] text-[#666666]"
                                >
                                    <Power className="w-3.5 h-3.5" />
                                </button>
                                <button
                                    title="移除"
                                    disabled={!!busy}
                                    onClick={() => run(`rm-${t.name}`, () => agentRemoveTool(t.name))}
                                    className="p-1 rounded text-[#666666] hover:text-[#ff5b01] hover:bg-[#f2f4f6]"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        ))}
                    </div>
                    )}

                    <div className="space-y-2 pt-2 border-t border-[#dcdfe6]">
                        <div className="flex items-center text-[11px] text-[#666666]">
                            <Cloud className="w-3.5 h-3.5 mr-1" /> 扩展分析服务接入
                        </div>
                        <input
                            value={remoteUrl}
                            onChange={(e) => setRemoteUrl(e.target.value)}
                            placeholder="扩展服务地址（管理员填写）"
                            className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#6ab8aa]"
                        />
                        <div className="flex gap-1.5">
                            <input
                                value={remoteName}
                                onChange={(e) => setRemoteName(e.target.value)}
                                placeholder="显示名称（可选）"
                                className="flex-1 min-w-0 bg-[#f8f8fa] border border-[#dcdfe6] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#6ab8aa]"
                            />
                            <button
                                disabled={!!busy || !remoteUrl.trim()}
                                onClick={() => run('add-remote', async () => {
                                    const c = await agentRegisterRemote(remoteUrl.trim(), remoteName.trim() || undefined);
                                    setRemoteUrl(''); setRemoteName('');
                                    return c;
                                }, (r) => `已注册：${r.registered ?? 1} 项`)}
                                className="px-3 rounded-lg bg-[#dceee9] text-[#209F84] border border-[#9cd2c7] text-xs hover:bg-[#cde8e1] disabled:opacity-40"
                            >
                                {busy === 'add-remote' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '接入'}
                            </button>
                        </div>
                        <button
                            disabled={!!busy}
                            onClick={() => run('reload-remote', agentReloadRemote,
                                (r) => (r.added?.length ? `更新 ${r.added.length} 项` : '无新增项'))}
                            className="w-full text-[11px] py-1.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-[#666666] hover:text-[#333333] flex items-center justify-center gap-1 disabled:opacity-40"
                        >
                            <RefreshCw className={`w-3 h-3 ${busy === 'reload-remote' ? 'animate-spin' : ''}`} /> 刷新扩展服务清单
                        </button>
                    </div>

                    <div className="space-y-2 pt-2 border-t border-[#dcdfe6]">
                        <div className="flex items-center text-[11px] text-[#666666]">
                            <FolderSearch className="w-3.5 h-3.5 mr-1" /> 本地补充规则目录
                        </div>
                        <div className="flex gap-1.5">
                            <input
                                value={dirPath}
                                onChange={(e) => setDirPath(e.target.value)}
                                placeholder="本地规则目录（管理员填写）"
                                className="flex-1 min-w-0 bg-[#f8f8fa] border border-[#dcdfe6] rounded-lg px-2.5 py-1.5 text-xs focus:outline-none focus:border-[#6ab8aa]"
                            />
                            <button
                                disabled={!!busy || !dirPath.trim()}
                                onClick={() => run('load-dir', async () => {
                                    const c = await agentLoadDir(dirPath.trim());
                                    setDirPath('');
                                    return c;
                                }, (r) => (r.added?.length ? `新增 ${r.added.length} 项` : '未发现可加载能力'))}
                                className="px-2.5 rounded-lg bg-[#dceee9] text-[#209F84] border border-[#9cd2c7] text-xs hover:bg-[#cde8e1] disabled:opacity-40"
                            >
                                {busy === 'load-dir' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '读取'}
                            </button>
                        </div>
                    </div>

                    <button
                        disabled={!!busy}
                        onClick={() => run('reload-skills', agentReloadSkills,
                            (r) => `已刷新知识条目（${r.skills.length} 个）`)}
                        className="w-full text-[11px] py-1.5 rounded-lg bg-[#f3edfd] border border-[#d6c6f5] text-[#8a63e0] hover:bg-[#e6d8fb] flex items-center justify-center gap-1 disabled:opacity-40"
                    >
                        <RefreshCw className={`w-3 h-3 ${busy === 'reload-skills' ? 'animate-spin' : ''}`} /> 刷新规程知识条目
                    </button>
                </div>
            </details>
        </div>
    );
}

function MessageBubble({ msg }: { msg: ChatMsg }) {
    const isUser = msg.role === 'user';
    const hasCards = Boolean(msg.planSteps?.length || msg.trace?.length || msg.evidence?.length);
    const showThinking = msg.streaming && !msg.text && !hasCards;
    const displayText = sanitizeDisplay(msg.text);

    return (
        <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] flex space-x-2 ${isUser ? 'flex-row-reverse space-x-reverse' : 'flex-row'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${isUser ? 'bg-[#dceee9] text-[#209F84]' : 'bg-[#e2f2da] text-[#5ba83c]'}`}>
                    {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
                <div className="space-y-2 min-w-0">
                    {!isUser && (
                        <>
                            {msg.intent && <IntentBadge intent={msg.intent} />}
                            {!!msg.planSteps?.length && <PlanPanel steps={msg.planSteps} />}
                            <CollaborationGraph trace={msg.trace ?? []} plannedCount={msg.planSteps?.length ?? 0} />
                            {!!msg.evidence?.length && <EvidenceCard records={msg.evidence} />}
                            {msg.guard && <GuardCard guard={msg.guard} />}
                        </>
                    )}

                    {showThinking && (
                        <div className="glass-panel px-4 py-2.5 rounded-2xl text-sm text-[#666666] flex items-center">
                            <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> 智能体思考中…
                        </div>
                    )}

                    {isUser && msg.images && msg.images.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 justify-end">
                            {msg.images.map((img, k) => (
                                <img
                                    key={k}
                                    src={img.url}
                                    alt={img.name}
                                    title={img.name}
                                    className="max-h-48 rounded-xl border border-[#dcdfe6] object-cover"
                                />
                            ))}
                        </div>
                    )}

                    {msg.text && (
                        isUser ? (
                            <div className="px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed bg-[#209F84] text-white shadow-sm">
                                {displayText}
                            </div>
                        ) : (
                            <div className="px-4 py-2.5 rounded-2xl glass-panel text-[#333333]">
                                <div className="md-body">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayText}</ReactMarkdown>
                                </div>
                                {msg.streaming && <span className="inline-block w-1.5 h-4 align-middle bg-[#209F84] animate-pulse ml-0.5" />}
                            </div>
                        )
                    )}
                </div>
            </div>
        </div>
    );
}
