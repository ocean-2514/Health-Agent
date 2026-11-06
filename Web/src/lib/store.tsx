/** 统一前端数据层（Context）：聚合首页概览、工单台账、复核任务，
 *  并提供跨页导航上下文（设备编号 / 摄像头编号），消除六个页面各自取数、信息孤岛的问题。 */
import React, {
    createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import {
    fleetOverview, listWorkorders, reviewTasks, recordDltResult as apiRecordDlt,
    type FleetOverview, type Workorder, type ReviewTask,
} from "./api";

export type NavTab =
    | "fleet" | "reasoning" | "approval" | "dlt" | "agent" | "monitor"
    | "knowledge" | "admin";

export type NavContextPayload = {
    deviceId?: string;
    cameraId?: string;
};

type DataContextValue = {
    overview: FleetOverview | null;
    overviewLoading: boolean;
    refreshOverview: () => Promise<void>;
    workorders: Workorder[];
    openOrderCount: number;
    refreshWorkorders: () => Promise<void>;
    reviewItems: ReviewTask[];
    refreshReviewTasks: () => Promise<void>;
    issuedCount: number;
    bumpIssued: (n?: number) => void;
    pushDltResult: (payload: {
        equipment_id: string;
        overall_state?: string | null;
        health_index?: number | null;
        total_deduction?: number | null;
        components?: Record<string, any>;
    }) => Promise<void>;
    navigate: (tab: NavTab, ctx?: NavContextPayload) => void;
    navPayload: NavContextPayload;
};

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({
    children,
    navigate,
}: {
    children: React.ReactNode;
    navigate: (tab: NavTab, ctx?: NavContextPayload) => void;
}) {
    const [overview, setOverview] = useState<FleetOverview | null>(null);
    const [overviewLoading, setOverviewLoading] = useState(true);
    const [workorders, setWorkorders] = useState<Workorder[]>([]);
    const [reviewItems, setReviewItems] = useState<ReviewTask[]>([]);
    const [issuedCount, setIssuedCount] = useState<number>(() => {
        const v = Number(localStorage.getItem("issuedReviewCount") || "0");
        return Number.isFinite(v) ? v : 0;
    });
    const [navPayload, setNavPayload] = useState<NavContextPayload>({});
    const mounted = useRef(true);

    const bumpIssued = useCallback((n = 1) => {
        setIssuedCount((c) => {
            const next = c + n;
            localStorage.setItem("issuedReviewCount", String(next));
            return next;
        });
    }, []);

    const refreshOverview = useCallback(async () => {
        setOverviewLoading(true);
        const data = await fleetOverview();
        if (mounted.current) {
            setOverview(data);
            setOverviewLoading(false);
        }
    }, []);

    const pushDltResult = useCallback(async (payload: Parameters<typeof apiRecordDlt>[0]) => {
        await apiRecordDlt(payload);
        await refreshOverview();
    }, [refreshOverview]);

    const refreshWorkorders = useCallback(async () => {
        const data = await listWorkorders();
        if (mounted.current && data) setWorkorders(data.items ?? []);
    }, []);

    const refreshReviewTasks = useCallback(async () => {
        const data = await reviewTasks();
        if (mounted.current && data) setReviewItems(data.items ?? []);
    }, []);

    useEffect(() => {
        mounted.current = true;
        refreshOverview();
        refreshWorkorders();
        refreshReviewTasks();
        return () => { mounted.current = false; };
    }, [refreshOverview, refreshWorkorders, refreshReviewTasks]);

    const go = useCallback((tab: NavTab, ctx?: NavContextPayload) => {
        setNavPayload(ctx ?? {});
        navigate(tab, ctx);
    }, [navigate]);

    const value = useMemo<DataContextValue>(() => ({
        overview,
        overviewLoading,
        refreshOverview,
        workorders,
        openOrderCount: workorders.filter((w) => w.status !== "已闭环").length,
        refreshWorkorders,
        reviewItems,
        refreshReviewTasks,
        issuedCount,
        bumpIssued,
        pushDltResult,
        navigate: go,
        navPayload,
    }), [overview, overviewLoading, refreshOverview, workorders, refreshWorkorders,
        reviewItems, refreshReviewTasks, issuedCount, bumpIssued, pushDltResult, go, navPayload]);

    return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): DataContextValue {
    const ctx = useContext(DataContext);
    if (!ctx) throw new Error("useData 必须在 DataProvider 内使用");
    return ctx;
}
