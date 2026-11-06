import React from 'react';
import { Eye, WifiOff, Inbox } from 'lucide-react';
import type { EvidenceRecord } from '../../lib/api';

function confPercent(v: unknown): number | null {
    if (typeof v !== 'number' || !Number.isFinite(v)) return null;
    return v <= 1 ? Math.round(v * 100) : Math.round(v);
}

/** 图像分析依据卡片：逐图展示识别结果；无结果时如实说明，不补充推测目标。 */
export default function EvidenceCard({ records }: { records: EvidenceRecord[] }) {
    if (!records || records.length === 0) return null;

    return (
        <div className="glass-panel rounded-xl px-3.5 py-2.5">
            <div className="flex items-center gap-2">
                <Eye className="w-3.5 h-3.5 text-[#209F84]" />
                <span className="text-[11px] font-medium text-[#333333]">图像分析依据</span>
                <span className="text-[10px] text-[#666666] tabular-nums">{records.length} 张图片</span>
            </div>

            <div className="mt-2 space-y-2">
                {records.map((rec, i) => {
                    const dets = Array.isArray(rec.detections) ? rec.detections : [];
                    return (
                        <div key={i} className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] px-2.5 py-2">
                            <div className="flex items-center gap-2">
                                <span className="text-[11px] text-[#333333]">图片{rec.image_index ?? '-'}</span>
                                {rec.online ? (
                                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[#eef7e8] text-[#5ba83c] border border-[#c4e3b0]">
                                        分析完成
                                    </span>
                                ) : (
                                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[#fbeed2] text-[#d99000] border border-[#f0d9a8]">
                                        暂未完成分析
                                    </span>
                                )}
                            </div>

                            {!rec.online && (
                                <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-[#d99000] leading-snug">
                                    <WifiOff className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                    <span>
                                        本次未获得图像识别结果，相关判断不包含图片依据。
                                        {rec.summary ? ` ${rec.summary}` : ''}
                                    </span>
                                </div>
                            )}

                            {rec.online && dets.length === 0 && (
                                <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-[#666666]">
                                    <Inbox className="w-3 h-3 flex-shrink-0" />
                                    未发现异常目标
                                </div>
                            )}

                            {rec.online && dets.length > 0 && (
                                <div className="mt-1.5 space-y-1">
                                    {dets.map((d, j) => {
                                        const pct = confPercent(d.confidence);
                                        return (
                                            <div key={j} className="flex items-center gap-2">
                                                <span className="text-[11px] text-[#333333] w-24 truncate">{d.class || '未命名类别'}</span>
                                                <span className="flex-1 h-1.5 rounded-full bg-[#f2f4f6] overflow-hidden">
                                                    <span
                                                        className="block h-full rounded-full bg-[#209F84]"
                                                        style={{ width: pct !== null ? `${pct}%` : '0%' }}
                                                    />
                                                </span>
                                                <span className="text-[10px] text-[#666666] tabular-nums w-10 text-right">
                                                    {pct !== null ? `${pct}%` : '—'}
                                                </span>
                                            </div>
                                        );
                                    })}
                                    <p className="text-[10px] text-[#666666] pt-0.5">
                                        共识别 {dets.length} 项
                                    </p>
                                </div>
                            )}

                            {rec.online && rec.summary && (
                                <p className="text-[10px] text-[#666666] leading-snug mt-1 truncate" title={rec.summary}>
                                    {rec.summary}
                                </p>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
