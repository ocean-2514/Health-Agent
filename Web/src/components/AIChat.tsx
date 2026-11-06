import React from 'react';
import { Bot, MessageSquare, ArrowRight, Image as ImageIcon, Wrench, BookOpen } from 'lucide-react';

/**
 * Entry card routing the user to the conversational Q&A page.
 */
export default function AIChat({ onNavigate }: { onNavigate?: () => void }) {
    return (
        <div className="flex flex-col h-full">
            <div className="px-4 py-3 border-b border-[#dcdfe6] font-medium text-[#209F84] flex items-center">
                <Bot className="w-4 h-4 mr-2" />
                AI 管控助手
            </div>
            <div className="flex-1 overflow-y-auto p-4">
                <div className="rounded-xl border border-[#b3ddd5] bg-[#e6f4f0] p-5">
                    <div className="flex items-center mb-3">
                        <div className="w-9 h-9 rounded-full bg-[#e2f2da] text-[#5ba83c] flex items-center justify-center mr-3">
                            <MessageSquare className="w-4 h-4" />
                        </div>
                        <div>
                            <div className="text-sm font-bold text-[#333333]">智能问答助手已就绪</div>
                            <div className="text-[11px] text-[#666666]">结合设备资料与规程，给出可核验的分析结论</div>
                        </div>
                    </div>
                    <p className="text-xs text-[#666666] leading-relaxed mb-4">
                        本页为算法分析视图。需要对话提问、追问或检修建议时，请前往「智能问答」获取带依据来源的分析结论。
                    </p>
                    <ul className="space-y-2 mb-5">
                        {[
                            { icon: <MessageSquare className="w-3.5 h-3.5" />, text: '自然语言问答与 DGA 判读、检修建议' },
                            { icon: <ImageIcon className="w-3.5 h-3.5" />, text: '直接上传图片做缺陷识别' },
                            { icon: <Wrench className="w-3.5 h-3.5" />, text: '结合现场台账、图像与规程开展综合分析' },
                            { icon: <BookOpen className="w-3.5 h-3.5" />, text: '检索电力标准规程并标注来源' },
                        ].map((it, i) => (
                            <li key={i} className="flex items-start text-[11px] text-[#333333]">
                                <span className="text-[#209F84] mr-2 mt-0.5 flex-shrink-0">{it.icon}</span>
                                {it.text}
                            </li>
                        ))}
                    </ul>
                    <button
                        onClick={onNavigate}
                        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#209F84] hover:bg-[#209F84] text-white text-xs font-bold transition-colors"
                    >
                        前往智能问答 <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>
        </div>
    );
}
