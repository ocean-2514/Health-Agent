import React, { useEffect, useMemo, useState } from 'react';
import {
    FileText, CheckCircle2, XCircle, Download, Printer,
    ShieldAlert, Activity, Gauge, TrendingUp, Check, Ban, ArrowRight, Wrench,
} from 'lucide-react';
import { useData } from '../lib/store';
import { advanceWorkorder, submitReviewDecision, type ReviewTask, type Workorder } from '../lib/api';

type ReviewState = 'pending' | 'approved' | 'rejected';

const ORDER_FLOW: Record<string, string> = {
    '待派单': '已派单',
    '已派单': '处理中',
    '处理中': '已闭环',
};

export default function ApprovalWorkspace() {
    const { reviewItems, refreshReviewTasks, workorders, refreshWorkorders, issuedCount, bumpIssued, navigate } = useData();
    const [review, setReview] = useState<Record<string, ReviewState>>({});
    const [issued, setIssued] = useState(false);
    const [note, setNote] = useState<string | null>(null);

    useEffect(() => { refreshReviewTasks(); }, [refreshReviewTasks]);

    const tasks: ReviewTask[] = reviewItems;
    const safeState = (id: string): ReviewState =>
        review[id] ?? tasks.find((t) => t.id === id)?.decision ?? 'pending';

    const setTaskState = async (id: string, state: ReviewState) => {
        setReview((prev) => ({ ...prev, [id]: state }));
        setIssued(false);
        setNote(null);
        if (state === 'pending') return;
        const result = await submitReviewDecision(id, state);
        if (result) {
            await refreshReviewTasks();
            setNote(state === 'approved' ? '已记录核准结论，首页复核统计同步更新。' : '已记录驳回意见，可在历史记录中追溯。');
        } else {
            setNote('结论保存失败，请检查网络后重试。');
        }
    };

    const approvedCount = tasks.filter((t) => safeState(t.id) === 'approved').length;
    const pendingCount = tasks.filter((t) => safeState(t.id) === 'pending').length;
    const rejectedCount = tasks.filter((t) => safeState(t.id) === 'rejected').length;

    const handleIssue = () => {
        if (approvedCount === 0) {
            setNote('请先核准至少一条任务，再签发复核意见。');
            return;
        }
        setIssued(true);
        bumpIssued(approvedCount);
        setNote(`已签发 ${approvedCount} 条核准意见${pendingCount ? `，另有 ${pendingCount} 条待复核未纳入本批签发` : ''}；首页已同步签发统计。`);
    };

    const handleDownload = () => {
        const lines: string[] = [
            '变压器专家复核单',
            `签发时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`,
            `核准意见：${approvedCount} 条 · 驳回：${rejectedCount} 条 · 待复核：${pendingCount} 条`,
            '----------------------------------------',
        ];
        tasks.forEach((t) => {
            const s = safeState(t.id);
            lines.push(`[${s === 'approved' ? '核准' : s === 'rejected' ? '驳回' : '待复核'}] ${t.title}`);
            lines.push(`  设备：${t.device}（${t.station}）｜健康指数 ${t.health}｜风险评分 ${t.risk}`);
            lines.push(`  说明：${t.desc}`);
        });
        const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `专家复核单_${new Date().toISOString().slice(0, 10)}.txt`;
        a.click();
        URL.revokeObjectURL(url);
        setNote('复核单已下载到本地；正式归档版本由检修管理系统统一出具。');
    };

    const handleAdvance = async (order: Workorder) => {
        const next = ORDER_FLOW[order.status];
        if (!next) return;
        await advanceWorkorder(order.order_no, next);
        await refreshWorkorders();
        setNote(`工单 ${order.order_no} 已推进为「${next}」。`);
    };

    const openOrders = useMemo(
        () => workorders.filter((w) => w.status !== '已闭环'),
        [workorders],
    );

    return (
        <div className="flex min-h-full space-x-4">
            {/* Left: task list */}
            <div className="w-96 glass-panel rounded-xl flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-[#dcdfe6] flex items-center justify-between">
                    <div className="font-medium text-[#d99000] flex items-center">
                        <ShieldAlert className="w-4 h-4 mr-2" />
                        待复核任务
                    </div>
                    <span className="text-[10px] text-[#666666]">基于设备健康趋势生成</span>
                </div>
                <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar">
                    {tasks.length === 0 && (
                        <p className="text-xs text-[#666666] p-3">当前暂无待复核任务。</p>
                    )}
                    {tasks.map((task) => {
                        const state = safeState(task.id);
                        return (
                            <div key={task.id} className="rounded-xl border border-[#f0d9a8] bg-[#fdf4e0] p-4">
                                <div className="flex items-start justify-between mb-2">
                                    <div>
                                        <h3 className="text-sm font-bold text-[#333333]">{task.title}</h3>
                                        <p className="text-[10px] text-[#666666] mt-0.5">{task.device} · {task.station}</p>
                                    </div>
                                    <StateBadge state={state} />
                                </div>
                                <p className="text-[11px] text-[#666666] leading-relaxed mb-3">{task.desc}</p>

                                <div className="grid grid-cols-2 gap-2 mb-3">
                                    <div className="rounded-lg bg-[#f8f8fa] px-2.5 py-2 flex items-center">
                                        <Gauge className="w-3.5 h-3.5 text-[#d99000] mr-2" />
                                        <div>
                                            <div className="text-[9px] text-[#666666]">健康指数</div>
                                            <div className="text-xs font-bold text-[#333333] tabular-nums">{task.health}</div>
                                        </div>
                                    </div>
                                    <div className="rounded-lg bg-[#f8f8fa] px-2.5 py-2 flex items-center">
                                        <TrendingUp className="w-3.5 h-3.5 text-[#ff5b01] mr-2" />
                                        <div>
                                            <div className="text-[9px] text-[#666666]">风险评分</div>
                                            <div className="text-xs font-bold text-[#333333] tabular-nums">{task.risk}</div>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setTaskState(task.id, 'approved')}
                                        disabled={state === 'approved'}
                                        className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                                            state === 'approved'
                                                ? 'bg-[#e2f2da] text-[#5ba83c] cursor-default'
                                                : 'bg-[#eef7e8] text-[#5ba83c] border border-[#aed894] hover:bg-[#dcefd0]'
                                        }`}
                                    >
                                        <Check className="w-3 h-3" />
                                        {state === 'approved' ? '已核准' : '核准'}
                                    </button>
                                    <button
                                        onClick={() => setTaskState(task.id, 'rejected')}
                                        disabled={state === 'rejected'}
                                        className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                                            state === 'rejected'
                                                ? 'bg-[#f9d9c6] text-[#ff5b01] cursor-default'
                                                : 'bg-[#f8f8fa] text-[#333333] border border-[#dcdfe6] hover:bg-[#f2f4f6]'
                                        }`}
                                    >
                                        <Ban className="w-3 h-3" />
                                        {state === 'rejected' ? '已驳回' : '驳回'}
                                    </button>
                                </div>
                                <button
                                    onClick={() => navigate('reasoning', { deviceId: task.device_id })}
                                    className="mt-2 w-full flex items-center justify-center gap-1 text-[10px] text-[#209F84] hover:text-[#209F84]"
                                >
                                    查看该设备 AI 分析 <ArrowRight className="w-3 h-3" />
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Right */}
            <div className="flex-1 flex flex-col space-y-4">
                <div className="glass-panel rounded-xl p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-bold text-[#333333] flex items-center">
                            <Activity className="w-4 h-4 mr-2 text-[#d99000]" />
                            复核决策与签发
                        </h2>
                        {issued && (
                            <span className="flex items-center text-[11px] text-[#5ba83c] bg-[#eef7e8] border border-[#aed894] px-2.5 py-1 rounded-lg">
                                <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> 本批意见已签发
                            </span>
                        )}
                    </div>

                    <div className="grid grid-cols-3 gap-3 mb-5">
                        <Summary label="待复核" value={pendingCount} tone="text-[#d99000]" />
                        <Summary label="已核准" value={approvedCount} tone="text-[#5ba83c]" />
                        <Summary label="已驳回" value={rejectedCount} tone="text-[#ff5b01]" />
                    </div>

                    {note && (
                        <div className={`mb-4 rounded-lg px-3 py-2.5 text-[11px] border ${
                            issued || note.startsWith('工单') || note.startsWith('复核单')
                                ? 'text-[#5ba83c] border-[#c4e3b0] bg-[#eef7e8]'
                                : 'text-[#d99000] border-[#f0d9a8] bg-[#fdf4e0]'
                        }`}>
                            {note}
                        </div>
                    )}

                    <div className="flex items-center gap-3 flex-wrap">
                        <button
                            onClick={handleIssue}
                            disabled={issued || approvedCount === 0}
                            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#fcaa00] hover:bg-[#fcaa00] disabled:opacity-40 disabled:cursor-not-allowed text-[#333333] text-xs font-bold transition-colors"
                        >
                            <FileText className="w-4 h-4" />
                            {issued ? '已签发' : '确认签发复核意见'}
                        </button>
                        <button
                            onClick={handleDownload}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-[#333333] text-xs hover:bg-[#f2f4f6] transition-colors"
                        >
                            <Download className="w-4 h-4" /> 下载复核单
                        </button>
                        <button
                            onClick={() => window.print()}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-[#333333] text-xs hover:bg-[#f2f4f6] transition-colors"
                        >
                            <Printer className="w-4 h-4" /> 打印
                        </button>
                        <span className="text-[11px] text-[#666666]">累计签发意见 {issuedCount} 份</span>
                    </div>
                </div>

                <div className="glass-panel rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-semibold text-[#333333] flex items-center gap-2">
                            <Wrench className="w-4 h-4 text-[#8a63e0]" /> 检修工单闭环跟踪
                        </h3>
                        <button onClick={refreshWorkorders} className="text-[11px] text-[#209F84] hover:text-[#209F84]">刷新</button>
                    </div>
                    {openOrders.length === 0 ? (
                        <p className="text-xs text-[#666666] py-3">暂无未闭环工单；生成检修建议工单后在此跟踪流转。</p>
                    ) : (
                        <div className="space-y-2">
                            {openOrders.map((w) => (
                                <div key={w.order_no} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-xs">
                                    <span className="font-mono text-[#666666]">{w.order_no}</span>
                                    <span className="text-[#333333] truncate">{w.equipment_name} · {w.work_type}</span>
                                    <span className="text-[#666666] hidden md:inline">{w.assignee_team}</span>
                                    <span className="ml-auto text-[#d99000]">{w.status}</span>
                                    <button
                                        onClick={() => handleAdvance(w)}
                                        className="px-2.5 py-1 rounded bg-[#e6f4f0] border border-[#9cd2c7] text-[#209F84] hover:bg-[#dceee9] transition-colors"
                                    >
                                        推进至{ORDER_FLOW[w.status] ?? '完成'}
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function StateBadge({ state }: { state: ReviewState }) {
    if (state === 'approved') {
        return (
            <span className="flex items-center text-[10px] text-[#5ba83c] bg-[#eef7e8] border border-[#aed894] px-2 py-0.5 rounded">
                <CheckCircle2 className="w-3 h-3 mr-1" /> 已核准
            </span>
        );
    }
    if (state === 'rejected') {
        return (
            <span className="flex items-center text-[10px] text-[#ff5b01] bg-[#fdeee6] border border-[#f0ac84] px-2 py-0.5 rounded">
                <XCircle className="w-3 h-3 mr-1" /> 已驳回
            </span>
        );
    }
    return (
        <span className="text-[10px] text-[#d99000] bg-[#fdf4e0] border border-[#e8cd92] px-2 py-0.5 rounded">
            待复核
        </span>
    );
}

function Summary({ label, value, tone }: { label: string; value: number; tone: string }) {
    return (
        <div className="rounded-xl border border-[#dcdfe6] bg-[#f8f8fa] px-4 py-3 text-center">
            <div className={`text-2xl font-bold ${tone}`}>{value}</div>
            <div className="text-[10px] text-[#666666] mt-1">{label}</div>
        </div>
    );
}
