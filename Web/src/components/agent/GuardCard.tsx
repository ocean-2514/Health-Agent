import React from 'react';
import { ShieldCheck, ShieldAlert, ShieldX, Check, X } from 'lucide-react';
import type { GuardResult } from '../../lib/api';

const ACTION_META = {
    pass: {
        label: '校核通过',
        icon: ShieldCheck,
        cls: 'bg-[#eef7e8] text-[#5ba83c] border border-[#aed894]',
    },
    corrected: {
        label: '已约束修正',
        icon: ShieldAlert,
        cls: 'bg-[#fbeed2] text-[#d99000] border border-[#e8cd92]',
    },
    blocked: {
        label: '已拦截改写',
        icon: ShieldX,
        cls: 'bg-[#fbe3d4] text-[#ff5b01] border border-[#f5c3a3]',
    },
} as const;

/** 合规校核卡片：确定性 grounding 闸门结果，逐条展示声明是否可溯源。 */
export default function GuardCard({ guard }: { guard?: GuardResult | null }) {
    if (!guard) return null;
    const action = guard.action in ACTION_META ? guard.action : 'pass';
    const meta = ACTION_META[action];
    const ActionIcon = meta.icon;
    const checks = Array.isArray(guard.checks) ? guard.checks : [];

    return (
        <div className="glass-panel rounded-xl px-3.5 py-2.5">
            <div className="flex items-center gap-2">
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${meta.cls}`}>
                    <ActionIcon className="w-3 h-3" />
                    {meta.label}
                </span>
                <span className="text-[10px] text-[#666666]">规程依据校核</span>
            </div>

            {guard.message && (
                <p className="text-[11px] text-[#666666] leading-snug mt-1.5">{guard.message}</p>
            )}

            {checks.length > 0 && (
                <div className="mt-1.5 space-y-1">
                    {checks.map((c, i) => (
                        <div key={i} className="flex items-start gap-2 text-[11px]">
                            {c.grounded ? (
                                <Check className="w-3 h-3 mt-0.5 text-[#5ba83c] flex-shrink-0" />
                            ) : (
                                <X className="w-3 h-3 mt-0.5 text-[#ff5b01] flex-shrink-0" />
                            )}
                            <div className="min-w-0">
                                <span className={c.grounded ? 'text-[#333333]' : 'text-[#ff5b01]'}>
                                    {c.claim}
                                </span>
                                {c.detail && (
                                    <p className="text-[10px] text-[#666666] leading-snug">{c.detail}</p>
                                )}
                            </div>
                            <span className={`ml-auto flex-shrink-0 text-[9px] px-1 py-0.5 rounded ${
                                c.grounded
                                    ? 'bg-[#eef7e8] text-[#5ba83c]'
                                    : 'bg-[#fbe3d4] text-[#ff5b01]'
                            }`}>
                                {c.grounded ? '已溯源' : '无来源'}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
