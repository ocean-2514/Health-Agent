import React, { useMemo } from 'react';
import {
    Network, Loader2, Check, CircleAlert, History,
} from 'lucide-react';
import type { RoleId } from '../../lib/api';
import { ROLE_META } from '../../lib/agentMeta';

export type TraceEntry = {
    role: RoleId;
    name: string;
    title?: string;
    status: 'running' | 'done' | 'error';
    stepId?: string;
};

const NODE_POS: Record<RoleId, { x: number; y: number }> = {
    knowledge: { x: 11, y: 72 },
    perception: { x: 31, y: 22 },
    diagnosis: { x: 51, y: 72 },
    compliance: { x: 72, y: 22 },
    decision: { x: 90, y: 72 },
};

// 静态协同骨架：表示角色之间可能的交接关系（未激活时置淡灰）。
const BASE_EDGES: Array<[RoleId, RoleId]> = [
    ['knowledge', 'perception'],
    ['knowledge', 'diagnosis'],
    ['perception', 'diagnosis'],
    ['diagnosis', 'compliance'],
    ['diagnosis', 'decision'],
    ['compliance', 'decision'],
];

const TOOL_LABEL: Record<string, string> = {
    edge_visible_detect: '图像缺陷检测',
    edge_inspect: '巡检图像复检',
    edge_vlm_review: '图像综合复核',
    transformer_diagnosis: '健康融合诊断',
    edge_alarm: '现场告警研判',
    load_skill: '规程知识调用',
    append_skill_memory: '分析经验记录',
    save_memory: '分析结论保存',
    middle_rag_ask: '规程条款检索',
    history_lookup: '历史诊断查询',
    compose: '汇总生成报告',
    spawn_agent: '专项分析调用',
};

function TraceStatusIcon({ status }: { status: TraceEntry['status'] }) {
    if (status === 'running') return <Loader2 className="w-3 h-3 animate-spin text-[#209F84]" />;
    if (status === 'done') return <Check className="w-3 h-3 text-[#5ba83c]" />;
    return <CircleAlert className="w-3 h-3 text-[#ff5b01]" />;
}

/**
 * 分析过程图：5 类分析环节节点 + 静态骨架连线；本轮经过的环节高亮，
 * 相邻调用之间的流转边用流动虚线动画指示方向；下方附按时间顺序的处理时序。
 */
export default function CollaborationGraph({
    trace,
    plannedCount,
}: {
    trace: TraceEntry[];
    plannedCount?: number;
}) {
    const visited = useMemo(() => {
        const set = new Set<RoleId>();
        trace.forEach((t) => set.add(t.role));
        return set;
    }, [trace]);

    const activeRole = useMemo(() => {
        for (let i = trace.length - 1; i >= 0; i--) {
            if (trace[i].status === 'running') return trace[i].role;
        }
        return trace.length ? trace[trace.length - 1].role : null;
    }, [trace]);

    // 相邻调用（角色去重）构成本轮真实流转路径。
    const flowEdges = useMemo(() => {
        const edges: Array<[RoleId, RoleId]> = [];
        let prev: RoleId | null = null;
        trace.forEach((t) => {
            if (prev && prev !== t.role) edges.push([prev, t.role]);
            prev = t.role;
        });
        return edges;
    }, [trace]);

    if (trace.length === 0 && !plannedCount) return null;

    const hasFlow = flowEdges.length > 0;

    return (
        <div className="glass-panel rounded-xl px-3.5 py-2.5">
            <div className="flex items-center gap-2">
                <Network className="w-3.5 h-3.5 text-[#209F84]" />
                <span className="text-[11px] font-medium text-[#333333]">分析处理过程</span>
                <span className="text-[10px] text-[#666666] tabular-nums">
                    已由 {visited.size}/5 类环节处理
                </span>
            </div>

            <style>{`
                @keyframes agentDashFlow { to { stroke-dashoffset: -14; } }
                .agent-flow-dash { animation: agentDashFlow 1s linear infinite; }
            `}</style>

            <div className="relative h-[150px] mt-1">
                <svg
                    className="absolute inset-0 w-full h-full"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                >
                    {BASE_EDGES.map(([a, b]) => {
                        const pa = NODE_POS[a];
                        const pb = NODE_POS[b];
                        const active = flowEdges.some(([x, y]) => x === a && y === b);
                        return (
                            <line
                                key={`${a}-${b}`}
                                x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
                                stroke={active ? '#209F84' : '#dcdfe6'}
                                strokeWidth={active ? 1.6 : 1}
                                strokeDasharray={active ? '5 4' : '2 4'}
                                className={active ? 'agent-flow-dash' : undefined}
                                vectorEffect="non-scaling-stroke"
                                opacity={active ? 0.85 : 1}
                            />
                        );
                    })}
                </svg>

                {(Object.keys(NODE_POS) as RoleId[]).map((id) => {
                    const meta = ROLE_META[id];
                    const Icon = meta.icon;
                    const p = NODE_POS[id];
                    const on = visited.has(id);
                    const active = activeRole === id;
                    return (
                        <div
                            key={id}
                            className="absolute flex flex-col items-center"
                            style={{ left: `${p.x}%`, top: `${p.y}%`, transform: 'translate(-50%, -50%)' }}
                        >
                            <div
                                title={meta.tagline}
                                className={`relative w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 ${
                                    on ? meta.accent.badge : 'bg-[#f8f8fa] border border-[#dcdfe6] text-[#666666]'
                                }`}
                            >
                                <Icon className="w-4.5 h-4.5" />
                                {active && (
                                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-[#209F84] animate-pulse" />
                                )}
                            </div>
                            <span className={`mt-1 text-[10px] whitespace-nowrap ${on ? meta.accent.text : 'text-[#666666]'}`}>
                                {meta.label}
                            </span>
                        </div>
                    );
                })}
            </div>

            {trace.length > 0 && (
                <div className="mt-2 pt-2 border-t border-[#dcdfe6]">
                    <div className="flex items-center gap-1.5 text-[10px] text-[#666666] mb-1.5">
                        <History className="w-3 h-3" /> 调用时序
                    </div>
                    <div className="space-y-1 max-h-36 overflow-y-auto custom-scrollbar pr-1">
                        {trace.map((entry, i) => {
                            const meta = ROLE_META[entry.role] ?? ROLE_META.diagnosis;
                            const Icon = meta.icon;
                            return (
                                <div key={i} className="flex items-center gap-2">
                                    <span className="text-[10px] text-[#666666] tabular-nums w-3.5 flex-shrink-0">
                                        {i + 1}
                                    </span>
                                    <span className={`w-5 h-5 rounded flex items-center justify-center flex-shrink-0 ${meta.accent.badge}`}>
                                        <Icon className="w-3 h-3" />
                                    </span>
                                    <span className="text-[11px] text-[#333333] truncate">
                                        {entry.title || TOOL_LABEL[entry.name] || entry.name}
                                    </span>
                                    <span className="text-[10px] font-mono text-[#666666] truncate hidden sm:inline">
                                        {entry.name}
                                    </span>
                                    <span className="ml-auto flex-shrink-0">
                                        <TraceStatusIcon status={entry.status} />
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {!hasFlow && trace.length > 0 && (
                <p className="text-[10px] text-[#666666] mt-1">本轮单角色调用，无跨角色交接</p>
            )}
        </div>
    );
}
