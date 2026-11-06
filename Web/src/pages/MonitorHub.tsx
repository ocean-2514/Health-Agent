import React, { useEffect, useRef, useState } from 'react';
import {
    Video, VideoOff, Camera as CameraIcon, Loader2, RefreshCw, Play, Square,
    MapPin, Cpu, CircleAlert, Aperture,
} from 'lucide-react';
import {
    edgeCameras, edgeDemoSources, edgeStreamStart, edgeStreamStop,
    edgeStreamUrl, edgeSnapshotUrl, edgeAlarms,
    type EdgeCamera, type DemoSource, type EdgeAlarm,
} from '../lib/api';

const ALGO_CN: Record<string, string> = {
    algo_1: '可见光缺陷',
    algo_2: '红外热成像',
    algo_3: '安全帽',
    algo_4: '人员闯入',
    algo_5: '烟火',
    algo_6: '油色谱',
    algo_7: '日志异常',
};

export default function MonitorHub({ initialCameraId }: { initialCameraId?: string | null }) {
    const [cameras, setCameras] = useState<EdgeCamera[]>([]);
    const [sources, setSources] = useState<DemoSource[]>([]);
    const [alarms, setAlarms] = useState<EdgeAlarm[]>([]);
    const [selectedCam, setSelectedCam] = useState('');
    const [selectedSource, setSelectedSource] = useState('');
    const [modelType, setModelType] = useState('defect');
    const [streaming, setStreaming] = useState(false);
    const [nonce, setNonce] = useState(0);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [offline, setOffline] = useState(false);
    const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
    const stoppedRef = useRef(false);

    const loadAll = async () => {
        setError(null);
        try {
            const [cams, demo, alarmList] = await Promise.all([
                edgeCameras(),
                edgeDemoSources(),
                edgeAlarms().catch(() => [] as EdgeAlarm[]),
            ]);
            setCameras(cams);
            setSources(demo.sources);
            setAlarms(alarmList.slice(0, 5));
            setOffline(false);
            const target = initialCameraId && cams.some((c) => c.id === initialCameraId)
                ? initialCameraId : cams[0]?.id || '';
            setSelectedCam(target);
            setSelectedSource((prev) => prev || demo.sources[0]?.source || '');
        } catch (e: any) {
            setOffline(true);
            setError(e?.message || '现场服务暂不可达');
        }
    };

    useEffect(() => {
        stoppedRef.current = false;
        loadAll();
        return () => {
            stoppedRef.current = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialCameraId]);

    const current = cameras.find((c) => c.id === selectedCam);
    const selectedSourceIndex = sources.findIndex((s) => s.source === selectedSource);
    const usingSample = selectedSourceIndex >= 0;

    const start = async (camOverride?: string) => {
        const cam = camOverride || selectedCam;
        if (!cam || !selectedSource) return;
        setBusy(true);
        setError(null);
        try {
            await edgeStreamStart(cam, selectedSource, modelType);
            setSnapshotUrl(null);
            setNonce((n) => n + 1);
            setStreaming(true);
        } catch (e: any) {
            setError(e?.message || '视频流启动失败');
        } finally {
            setBusy(false);
        }
    };

    const stop = async () => {
        setBusy(true);
        try {
            await edgeStreamStop(selectedCam);
        } catch (e) {
            /* the edge may already have dropped it — reflect local state anyway */
        }
        if (!stoppedRef.current) setStreaming(false);
        setBusy(false);
    };

    const takeSnapshot = () => {
        if (!selectedCam) return;
        setSnapshotUrl(`${edgeSnapshotUrl(selectedCam)}?t=${Date.now()}`);
    };

    if (offline) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="glass-panel rounded-2xl p-8 max-w-md text-center border border-[#f0d9a8]">
                    <VideoOff className="w-10 h-10 text-[#d99000] mx-auto mb-3" />
                    <h2 className="text-base font-medium text-[#333333] mb-2">现场监控服务暂未连接</h2>
                    <p className="text-xs text-[#666666] leading-relaxed mb-4">
                        请确认现场采集与分析服务运行后点击重新连接；接入现场摄像头前，可先通过视频样例了解识别流程。
                    </p>
                    {error && <p className="text-[11px] text-[#ff5b01] mb-3 font-mono">{error}</p>}
                    <button
                        onClick={loadAll}
                        className="inline-flex items-center px-4 py-2 rounded-lg bg-[#dceee9] text-[#209F84] border border-[#9cd2c7] text-sm hover:bg-[#cde8e1]"
                    >
                        <RefreshCw className="w-4 h-4 mr-2" /> 重新连接
                    </button>
                </div>
            </div>
        );
    }

    const controlsLocked = streaming || busy;

    return (
        <div className="h-full flex gap-4">
            {/* ============ Control panel ============ */}
            <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
                <div className="glass-panel rounded-2xl p-4">
                    <div className="flex items-center font-medium text-[#209F84] mb-3">
                        <CameraIcon className="w-4 h-4" />
                        <span className="ml-2 text-sm">选择摄像头</span>
                    </div>
                    <div className="space-y-2">
                        {cameras.map((c) => (
                            <button
                                key={c.id}
                                onClick={() => !controlsLocked && setSelectedCam(c.id)}
                                disabled={controlsLocked}
                                className={`w-full text-left rounded-lg px-3 py-2 border transition-colors disabled:opacity-50 ${
                                    c.id === selectedCam
                                        ? 'bg-[#e6f4f0] border-[#9cd2c7]'
                                        : 'bg-[#f8f8fa] border-[#dcdfe6] hover:bg-[#f2f4f6]'
                                }`}
                            >
                                <div className="flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-[#6fba47] flex-shrink-0" />
                                    <span className="text-xs text-[#333333] truncate">{c.name}</span>
                                </div>
                                <div className="flex items-center text-[10px] text-[#666666] mt-1 ml-4">
                                    <MapPin className="w-3 h-3 mr-1 flex-shrink-0" />
                                    <span className="truncate">{c.location}</span>
                                </div>
                                <div className="flex flex-wrap gap-1 mt-1.5 ml-4">
                                    {c.algorithms.map((a) => (
                                        <span
                                            key={a}
                                            className="text-[10px] px-1.5 py-0.5 rounded bg-[#f8f8fa] text-[#666666] border border-[#dcdfe6]"
                                        >
                                            {ALGO_CN[a] || a}
                                        </span>
                                    ))}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                <div className="glass-panel rounded-2xl p-4 space-y-3">
                    <div className="flex items-center font-medium text-[#209F84]">
                        <Video className="w-4 h-4" />
                        <span className="ml-2 text-sm">视频样例与识别类型</span>
                    </div>

                    <div>
                        <label className="text-[11px] text-[#666666] block mb-1">视频样例</label>
                        <select
                            value={selectedSourceIndex < 0 ? '' : String(selectedSourceIndex)}
                            disabled={controlsLocked}
                            onChange={(e) => {
                                const idx = Number(e.target.value);
                                setSelectedSource(sources[idx]?.source || '');
                            }}
                            className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded-lg px-2.5 py-2 text-xs text-[#333333] focus:outline-none focus:border-[#6ab8aa] disabled:opacity-50"
                        >
                            {sources.length === 0 && <option value="">（暂无样例视频）</option>}
                            {sources.map((s, idx) => (
                                <option key={s.source} value={idx}>
                                    {s.name}
                                </option>
                            ))}
                        </select>
                        <p className="text-[10px] text-[#666666] mt-1 leading-relaxed">
                            接入现场摄像头后，可直接选择对应实时画面进行分析。
                        </p>
                    </div>

                    <div>
                        <label className="text-[11px] text-[#666666] block mb-1">识别类型</label>
                        <div className="flex gap-2">
                            {[
                                { v: 'defect', t: '缺陷检测' },
                                { v: 'helmet', t: '安全帽检测' },
                            ].map((m) => (
                                <button
                                    key={m.v}
                                    onClick={() => !controlsLocked && setModelType(m.v)}
                                    disabled={controlsLocked}
                                    className={`flex-1 px-2 py-1.5 rounded-lg text-xs border transition-colors disabled:opacity-50 ${
                                        modelType === m.v
                                            ? 'bg-[#e6f4f0] text-[#209F84] border-[#9cd2c7]'
                                            : 'bg-[#f8f8fa] text-[#666666] border-[#dcdfe6] hover:bg-[#f2f4f6]'
                                    }`}
                                >
                                    {m.t}
                                </button>
                            ))}
                        </div>
                    </div>

                    {streaming ? (
                        <button
                            onClick={stop}
                            disabled={busy}
                            className="w-full py-2 rounded-lg bg-[#fbe3d4] text-[#ff5b01] border border-[#f0ac84] text-sm hover:bg-[#f9d9c6] flex items-center justify-center"
                        >
                            {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Square className="w-4 h-4 mr-2" />}
                            停止视频流
                        </button>
                    ) : (
                        <button
                            onClick={() => start()}
                            disabled={busy || !selectedCam || !selectedSource}
                            className="w-full py-2 rounded-lg bg-[#209F84] text-white text-sm hover:bg-[#209F84] flex items-center justify-center disabled:opacity-40"
                        >
                            {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                            启动视频流
                        </button>
                    )}
                </div>

                {alarms.length > 0 && (
                    <div className="glass-panel rounded-2xl p-4">
                        <div className="flex items-center font-medium text-[#d99000] mb-2">
                            <CircleAlert className="w-4 h-4 mr-2" />
                            <span className="text-sm">最近告警</span>
                        </div>
                        <div className="space-y-2">
                            {alarms.map((a) => (
                                <button
                                    key={a.id}
                                    onClick={() => { setSelectedCam(a.camera_id); void start(a.camera_id); }}
                                    className="w-full text-left rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] px-2.5 py-2 hover:border-[#b3ddd5] transition-colors"
                                >
                                    <div className="text-[11px] text-[#333333] truncate">{a.camera_name} · {a.algorithm_name}</div>
                                    <div className="text-[10px] text-[#666666] truncate">{a.result}</div>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* ============ Video stage ============ */}
            <div className="flex-1 flex flex-col gap-4 min-w-0">
                <div className="glass-panel rounded-2xl flex-1 flex flex-col overflow-hidden min-h-0">
                    <div className="flex items-center justify-between px-5 py-3 border-b border-[#dcdfe6] flex-shrink-0">
                        <div className="flex items-center text-[#209F84] font-medium min-w-0">
                            <Aperture className="w-4 h-4 mr-2 flex-shrink-0" />
                            <span className="truncate">{current?.name || '现场画面'}</span>
                            {streaming && (
                                <span className="ml-3 flex items-center text-[11px] text-[#ff5b01]">
                                    <span className="w-1.5 h-1.5 rounded-full bg-[#ff5b01] mr-1.5 animate-pulse" />
                                    {usingSample ? '样例分析中' : '实时'}
                                </span>
                            )}
                        </div>
                        <button
                            onClick={takeSnapshot}
                            disabled={!streaming}
                            className="px-3 py-1.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-xs text-[#333333] hover:text-[#209F84] hover:border-[#9cd2c7] flex items-center disabled:opacity-40"
                        >
                            <CameraIcon className="w-3.5 h-3.5 mr-1.5" /> 单帧抓拍
                        </button>
                    </div>

                    <div className="flex-1 flex items-center justify-center p-5 bg-black/20 min-h-0">
                        {streaming ? (
                            <img
                                key={nonce}
                                src={`${edgeStreamUrl(selectedCam)}?n=${nonce}`}
                                alt="实时视频流"
                                className="max-w-full max-h-full rounded-lg object-contain"
                            />
                        ) : (
                            <div className="text-center text-[#666666]">
                                <Video className="w-12 h-12 mx-auto mb-3 opacity-40" />
                                <p className="text-sm">选择摄像头与视频样例，点击「启动视频流」</p>
                                <p className="text-[11px] text-[#666666] mt-1">
                                    启动后画面将叠加缺陷识别结果，可抓拍留存
                                </p>
                            </div>
                        )}
                    </div>
                </div>

                {error && (
                    <div className="glass-panel rounded-xl p-3 text-xs text-[#ff5b01] border border-[#f5c3a3] flex items-center">
                        <CircleAlert className="w-4 h-4 mr-2 flex-shrink-0" /> {error}
                    </div>
                )}

                {snapshotUrl && (
                    <div className="glass-panel rounded-2xl p-4 flex-shrink-0">
                        <div className="flex items-center text-[#209F84] mb-2">
                            <Cpu className="w-4 h-4 mr-2" />
                            <span className="text-sm">抓拍画面</span>
                        </div>
                        <img
                            src={snapshotUrl}
                            alt="抓拍"
                            className="max-h-64 rounded-lg border border-[#dcdfe6] object-contain"
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
