import React from 'react';
import type { IntentInfo } from '../../lib/api';
import { INTENT_META } from '../../lib/agentMeta';

/** 本轮问题类型徽章：彩色 chip + 置信度 + 判定来源。 */
export default function IntentBadge({ intent }: { intent?: IntentInfo | null }) {
    if (!intent || !intent.intent) return null;
    const meta = INTENT_META[intent.intent] ?? INTENT_META.chitchat;
    const conf = typeof intent.confidence === 'number' && Number.isFinite(intent.confidence)
        ? Math.round(intent.confidence * 100)
        : null;

    return (
        <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${meta.badge}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                {intent.label || meta.label}
            </span>
            {conf !== null && (
                <span className="text-[11px] text-[#666666] tabular-nums">置信度 {conf}%</span>
            )}
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#f8f8fa] border border-[#dcdfe6] text-[#666666]">
                {intent.source === 'llm' ? '智能判定' : '规程判定'}
            </span>
        </div>
    );
}
