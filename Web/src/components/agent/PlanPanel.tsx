import React, { useState } from 'react';
import {
    ListOrdered, ChevronDown, Loader2, Check, CircleAlert, Circle,
} from 'lucide-react';
import type { PlanStep, StepStatus } from '../../lib/api';
import { ROLE_META } from '../../lib/agentMeta';

function StepStatusIcon({ status }: { status: StepStatus }) {
    if (status === 'running') return <Loader2 className="w-3.5 h-3.5 animate-spin text-[#209F84]" />;
    if (status === 'done') return <Check className="w-3.5 h-3.5 text-[#5ba83c]" />;
    if (status === 'error') return <CircleAlert className="w-3.5 h-3.5 text-[#ff5b01]" />;
    return <Circle className="w-3.5 h-3.5 text-[#666666]" />;
}

/** 可折叠执行计划：步骤状态随 tool_call/tool_result 实时刷新（step_id 关联）。 */
export default function PlanPanel({ steps }: { steps: PlanStep[] }) {
    const [open, setOpen] = useState(true);
    if (!steps || steps.length === 0) return null;
    const done = steps.filter((s) => s.status === 'done').length;

    return (
        <div className="glass-panel rounded-xl px-3.5 py-2.5">
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="w-full flex items-center gap-2 text-left"
            >
                <ListOrdered className="w-3.5 h-3.5 text-[#209F84]" />
                <span className="text-[11px] font-medium text-[#333333]">执行计划</span>
                <span className="text-[10px] text-[#666666] tabular-nums">{done}/{steps.length} 步完成</span>
                <ChevronDown
                    className={`w-3.5 h-3.5 ml-auto text-[#666666] transition-transform ${open ? '' : '-rotate-90'}`}
                />
            </button>

            {open && (
                <div className="mt-2 space-y-1.5">
                    {steps.map((step) => {
                        const meta = ROLE_META[step.role] ?? ROLE_META.diagnosis;
                        const RoleIcon = meta.icon;
                        return (
                            <div key={step.step_id} className="flex items-start gap-2">
                                <span className="w-4 flex justify-center pt-0.5 flex-shrink-0">
                                    <StepStatusIcon status={step.status} />
                                </span>
                                <span className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 ${meta.accent.badge}`}>
                                    <RoleIcon className="w-3.5 h-3.5" />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-baseline gap-2">
                                        <span className={`text-xs ${step.status === 'error' ? 'text-[#ff5b01]' : 'text-[#333333]'}`}>
                                            {step.label}
                                        </span>
                                        <span className="text-[10px] font-mono text-[#666666] truncate">{step.tool}</span>
                                    </div>
                                    {step.reason && (
                                        <p className="text-[11px] text-[#666666] leading-snug mt-0.5">{step.reason}</p>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
