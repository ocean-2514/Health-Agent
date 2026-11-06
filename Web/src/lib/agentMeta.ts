// Shared metadata for the agent platform: intent/role/tool labels, accent
// classes and icon references. Both the chat centerpiece and the supporting
// pages import from here so the visual language stays identical.
//
// All Tailwind classes are written as complete static strings (never built by
// string concatenation) so the compiler can detect and keep them.
import {
    Eye, Stethoscope, ShieldCheck, ListChecks, BookMarked,
    type LucideIcon,
} from 'lucide-react';
import type { IntentId, RoleId } from './api';

type Accent = {
    hex: string;
    text: string;
    dot: string;
    badge: string;
    ring: string;
    bar: string;
};

export const ROLE_META: Record<RoleId, {
    label: string;
    tagline: string;
    icon: LucideIcon;
    accent: Accent;
}> = {
    perception: {
        label: '画面查看环节',
        tagline: '图片画面查看与缺陷线索提取',
        icon: Eye,
        accent: {
            hex: '#209F84',
            text: 'text-[#209F84]',
            dot: 'bg-[#209F84]',
            badge: 'bg-[#e6f4f0] text-[#209F84] border border-[#9cd2c7]',
            ring: 'ring-teal-500/40',
            bar: 'bg-[#209F84]',
        },
    },
    diagnosis: {
        label: '综合研判环节',
        tagline: '综合油色谱、温升与运行趋势研判',
        icon: Stethoscope,
        accent: {
            hex: '#38bdf8',
            text: 'text-[#3d8fe8]',
            dot: 'bg-[#439ef9]',
            badge: 'bg-[#dcecfd] text-[#3d8fe8] border border-[#9cc9f4]',
            ring: 'ring-[#439ef9]/40',
            bar: 'bg-[#439ef9]',
        },
    },
    compliance: {
        label: '规程校核环节',
        tagline: '依据现行规程和标准校核结论',
        icon: ShieldCheck,
        accent: {
            hex: '#FCAA00',
            text: 'text-[#d99000]',
            dot: 'bg-[#fcaa00]',
            badge: 'bg-[#fbeed2] text-[#d99000] border border-[#e8cd92]',
            ring: 'ring-[#fcaa00]/40',
            bar: 'bg-[#fcaa00]',
        },
    },
    decision: {
        label: '工单整理环节',
        tagline: '分级建议与检修工单整理',
        icon: ListChecks,
        accent: {
            hex: '#fb7185',
            text: 'text-[#ff5b01]',
            dot: 'bg-[#ff5b01]',
            badge: 'bg-[#fbe3d4] text-[#ff5b01] border border-[#f5c3a3]',
            ring: 'ring-[#ff5b01]/40',
            bar: 'bg-[#ff5b01]',
        },
    },
    knowledge: {
        label: '规程参考环节',
        tagline: '规程检索、历史结论查询与经验参考',
        icon: BookMarked,
        accent: {
            hex: '#34d399',
            text: 'text-[#5ba83c]',
            dot: 'bg-[#6fba47]',
            badge: 'bg-[#eef7e8] text-[#5ba83c] border border-[#aed894]',
            ring: 'ring-[#6fba47]/40',
            bar: 'bg-[#6fba47]',
        },
    },
};

// Map every callable tool (including built-ins) to its owning role.
const TOOL_ROLE: Record<string, RoleId> = {
    edge_visible_detect: 'perception',
    edge_inspect: 'perception',
    edge_stream: 'perception',
    edge_vlm_review: 'diagnosis',
    transformer_diagnosis: 'diagnosis',
    edge_alarm: 'diagnosis',
    load_skill: 'knowledge',
    append_skill_memory: 'knowledge',
    save_memory: 'knowledge',
    middle_rag_ask: 'knowledge',
    history_lookup: 'knowledge',
    compose: 'decision',
    spawn_agent: 'decision',
};

export function roleForTool(tool: string): RoleId {
    return TOOL_ROLE[tool] ?? 'diagnosis';
}

export const INTENT_META: Record<IntentId, {
    label: string;
    badge: string;
    dot: string;
}> = {
    defect_detection: {
        label: '图片/缺陷识别',
        badge: 'bg-[#e6f4f0] text-[#209F84] border border-[#9cd2c7]',
        dot: 'bg-[#209F84]',
    },
    dga_interpretation: {
        label: 'DGA 油色谱判读',
        badge: 'bg-[#dcecfd] text-[#3d8fe8] border border-[#9cc9f4]',
        dot: 'bg-[#439ef9]',
    },
    history_query: {
        label: '历史诊断查询',
        badge: 'bg-[#eef7e8] text-[#5ba83c] border border-[#aed894]',
        dot: 'bg-[#6fba47]',
    },
    knowledge_retrieval: {
        label: '规程/知识检索',
        badge: 'bg-[#eef7e8] text-[#5ba83c] border border-[#aed894]',
        dot: 'bg-[#6fba47]',
    },
    diagnosis: {
        label: '变压器诊断体检',
        badge: 'bg-[#dcecfd] text-[#3d8fe8] border border-[#9cc9f4]',
        dot: 'bg-[#439ef9]',
    },
    report_workorder: {
        label: '报告/工单生成',
        badge: 'bg-[#fbe3d4] text-[#ff5b01] border border-[#f5c3a3]',
        dot: 'bg-[#ff5b01]',
    },
    chitchat: {
        label: '闲聊/概念问答',
        badge: 'bg-[#f2f4f6] text-[#333333] border border-white/15',
        dot: 'bg-gray-400',
    },
};
