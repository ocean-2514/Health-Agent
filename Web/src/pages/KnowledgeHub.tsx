import React, { useEffect, useMemo, useState } from 'react';
import {
    Database, FileText, Share2, MessageSquareQuote, ExternalLink,
    RefreshCw, FileSpreadsheet, Layers, Unplug, BookOpen,
} from 'lucide-react';
import {
    middleDatasetSummary, middlePdfs, middleGraphOverview, middleQaAsk,
    type MiddleDatasetSummary, type MiddlePdfItem, type MiddleQaResp,
} from '../lib/api';

type SubTab = 'overview' | 'docs' | 'graph' | 'qa';

const SUB_TABS: Array<{ id: SubTab; label: string; icon: React.ReactNode }> = [
    { id: 'overview', label: '数据集概览', icon: <Database className="w-4 h-4" /> },
    { id: 'docs', label: '文档库', icon: <FileText className="w-4 h-4" /> },
    { id: 'graph', label: '知识图谱', icon: <Share2 className="w-4 h-4" /> },
    { id: 'qa', label: '引用问答', icon: <MessageSquareQuote className="w-4 h-4" /> },
];

function Card({ title, icon, children, extra }: {
    title: string; icon: React.ReactNode; children: React.ReactNode; extra?: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#dcdfe6] bg-[#f8f8fa] p-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2 text-[#209F84]">
                    {icon}
                    <h3 className="text-sm font-semibold text-[#333333]">{title}</h3>
                </div>
                {extra}
            </div>
            {children}
        </div>
    );
}

function EmptyState({ text }: { text: string }) {
    return (
        <div className="flex flex-col items-center justify-center py-10 text-[#666666]">
            <Unplug className="w-8 h-8 mb-2 opacity-70" />
            <p className="text-sm">{text}</p>
        </div>
    );
}

export default function KnowledgeHub() {
    const [sub, setSub] = useState<SubTab>('overview');
    const [summary, setSummary] = useState<MiddleDatasetSummary | null>(null);
    const [pdfData, setPdfData] = useState<any>(null);
    const [graph, setGraph] = useState<Record<string, any> | null>(null);
    const [loading, setLoading] = useState(false);

    const loadAll = async () => {
        setLoading(true);
        const [s, p, g] = await Promise.all([
            middleDatasetSummary(), middlePdfs(), middleGraphOverview(),
        ]);
        setSummary(s); setPdfData(p); setGraph(g);
        setLoading(false);
    };

    useEffect(() => { loadAll(); }, []);

    const docItems = useMemo<MiddlePdfItem[]>(() => {
        if (!pdfData) return [];
        if (Array.isArray(pdfData)) return pdfData;
        const cats = pdfData.categories ?? [];
        const out: MiddlePdfItem[] = [];
        cats.forEach((c: any) => (c.files ?? []).forEach((f: any) => out.push({
            name: f.name ?? f.file, file_type: f.file_type ?? f.category,
            category: c.name, content_lv1: f.content_lv1,
        })));
        return out;
    }, [pdfData]);

    const kpis = summary?.summary;
    const kpiCards = [
        { label: '资料文件总数', value: kpis?.total_files ?? '—', icon: <FileSpreadsheet className="w-5 h-5 text-[#209F84]" /> },
        { label: 'PDF 文档', value: kpis?.pdf_count ?? '—', icon: <FileText className="w-5 h-5 text-[#3d8fe8]" /> },
        { label: '图像资料', value: kpis?.image_count ?? '—', icon: <Layers className="w-5 h-5 text-[#5ba83c]" /> },
        { label: '知识类别', value: kpis?.category_count ?? '—', icon: <BookOpen className="w-5 h-5 text-[#d99000]" /> },
        { label: '近 7 天新增', value: kpis?.new_files_7d ?? '—', icon: <RefreshCw className="w-5 h-5 text-[#8a63e0]" /> },
    ];

    const graphReady = graph && graph.ok !== false;

    return (
        <div className="space-y-4">
            {/* 页头 */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-bold text-[#333333]">知识管理</h2>
                    <p className="text-xs text-[#666666] mt-0.5">
                        后端知识库构建平台：文档导入、数据集、知识图谱与引用问答，数据经同源网关实时读取
                    </p>
                </div>
                <div className="flex items-center space-x-2">
                    <button
                        onClick={loadAll}
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-xs text-[#333333] hover:bg-[#f2f4f6]"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                        <span>刷新</span>
                    </button>
                    <a
                        href="http://127.0.0.1:5000/"
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-xs text-[#209F84] hover:bg-[#dceee9]"
                    >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>打开知识平台完整界面（独立端口 5000）</span>
                    </a>
                </div>
            </div>

            {/* 子标签 */}
            <div className="flex items-center space-x-1 border-b border-[#dcdfe6] pb-px">
                {SUB_TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setSub(t.id)}
                        className={`flex items-center space-x-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors ${sub === t.id
                            ? 'text-[#209F84] bg-[#e6f4f0] border-b-2 border-[#209F84]'
                            : 'text-[#666666] hover:text-[#333333]'}`}
                    >
                        {t.icon}<span>{t.label}</span>
                    </button>
                ))}
            </div>

            {/* 数据集概览 */}
            {sub === 'overview' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-5 gap-3">
                        {kpiCards.map((k) => (
                            <div key={k.label} className="rounded-xl border border-[#dcdfe6] bg-[#f8f8fa] p-4">
                                <div className="flex items-center justify-between mb-2">{k.icon}</div>
                                <div className="text-2xl font-bold text-[#333333]">{k.value}</div>
                                <div className="text-xs text-[#666666] mt-1">{k.label}</div>
                            </div>
                        ))}
                    </div>
                    <Card title="数据口径说明" icon={<Database className="w-4 h-4" />}>
                        <p className="text-xs text-[#666666] leading-relaxed">
                            本页数字由知识平台后端实时统计，覆盖已导入文档与数据集。当前知识库在数据类型上涵盖
                            机械振动、油色谱、运行台账等不少于 3 类；除公开数据集摘录外，部分资料为固定种子生成的
                            标准样本，现场部署后应以真实导入资料与实测数据替换，演示结果不作为对外实测结论。
                        </p>
                    </Card>
                </div>
            )}

            {/* 文档库 */}
            {sub === 'docs' && (
                <Card title={`文档资料（${docItems.length}）`} icon={<FileText className="w-4 h-4" />}>
                    {docItems.length === 0 ? (
                        <EmptyState text="暂无已导入文档，可在知识平台完整界面中导入资料" />
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-[#666666] text-xs border-b border-[#dcdfe6]">
                                        <th className="text-left py-2 px-2 font-medium">文档名称</th>
                                        <th className="text-left py-2 px-2 font-medium">所属分类</th>
                                        <th className="text-left py-2 px-2 font-medium">知识类型</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {docItems.map((d, i) => (
                                        <tr key={i} className="border-b border-[#dcdfe6] hover:bg-[#f8f8fa]">
                                            <td className="py-2 px-2 text-[#333333]">{d.name}</td>
                                            <td className="py-2 px-2 text-[#666666]">{d.category || '—'}</td>
                                            <td className="py-2 px-2 text-[#666666]">{d.content_lv1 || '—'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Card>
            )}

            {/* 知识图谱 */}
            {sub === 'graph' && (
                <Card title="图谱概览" icon={<Share2 className="w-4 h-4" />}>
                    {!graphReady ? (
                        <EmptyState text="图数据库当前未连接（Neo4j 不可用），连接后将显示实体与关系统计" />
                    ) : (
                        <div className="grid grid-cols-4 gap-3">
                            {Object.entries(graph)
                                .filter(([k]) => ['entity_count', 'document_count', 'fault_mode_count',
                                    'standard_clause_count', 'threshold_rule_count'].includes(k))
                                .map(([k, v]) => (
                                    <div key={k} className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3 text-center">
                                        <div className="text-xl font-bold text-[#209F84]">{String(v)}</div>
                                        <div className="text-xs text-[#666666] mt-1">{k}</div>
                                    </div>
                                ))}
                        </div>
                    )}
                </Card>
            )}

            {/* 引用问答 */}
            {sub === 'qa' && <QaPanel />}
        </div>
    );
}

function QaPanel() {
    const [question, setQuestion] = useState('');
    const [resp, setResp] = useState<MiddleQaResp | null>(null);
    const [asking, setAsking] = useState(false);

    const ask = async () => {
        if (!question.trim()) return;
        setAsking(true);
        const r = await middleQaAsk(question.trim());
        setResp(r); setAsking(false);
    };

    return (
        <Card title="带引用的知识问答" icon={<MessageSquareQuote className="w-4 h-4" />}>
            <div className="flex space-x-2">
                <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && ask()}
                    placeholder="例如：变压器高温过热的判断依据是什么？"
                    className="flex-1 px-3 py-2 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-sm text-[#333333] outline-none focus:border-[#6ab8aa]"
                />
                <button
                    onClick={ask}
                    disabled={asking}
                    className="px-4 py-2 rounded-lg bg-[#dceee9] border border-[#7fc4b8] text-sm text-[#209F84] hover:bg-[#cde8e1] disabled:opacity-60"
                >
                    {asking ? '检索中…' : '提问'}
                </button>
            </div>
            {resp && (
                <div className="mt-4 space-y-3">
                    <div className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3">
                        <p className="text-sm text-[#333333] leading-relaxed">
                            {resp.answer || resp.cited_answer || '（未返回答案）'}
                        </p>
                    </div>
                    {(resp.citation_references?.length ?? 0) > 0 && (
                        <div>
                            <p className="text-xs text-[#666666] mb-1.5">引用来源</p>
                            <div className="flex flex-wrap gap-2">
                                {resp.citation_references?.map((c, i) => (
                                    <span key={i} className="px-2.5 py-1 rounded-md bg-[#e8f3fe] border border-[#b5d8f8] text-xs text-[#3d8fe8]">
                                        {c.title || `来源 ${i + 1}`}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}
