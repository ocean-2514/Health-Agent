import React, { useState } from 'react';
import Layout from './components/Layout';
import FleetDashboard from './pages/FleetDashboard';
import ReasoningHub from './pages/ReasoningHub';
import ApprovalWorkspace from './pages/ApprovalWorkspace';
import AgentConsole from './pages/AgentConsole';
import DltEvaluation from './pages/DltEvaluation';
import MonitorHub from './pages/MonitorHub';
import KnowledgeHub from './pages/KnowledgeHub';
import AdminCenter from './pages/AdminCenter';
import { DataProvider, type NavTab, type NavContextPayload } from './lib/store';

export type TabId = NavTab;

const DEVICE_STATION: Record<string, string> = {
  tr01: 'station1', tr02: 'station1', tr03: 'station2', tr04: 'station2',
};

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('fleet');
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('tr01');
  const [selectedSubstationId, setSelectedSubstationId] = useState<string>('station1');
  const [initialCameraId, setInitialCameraId] = useState<string | null>(null);

  const navigate = (tab: NavTab, ctx?: NavContextPayload) => {
    if (ctx?.deviceId) {
      setSelectedDeviceId(ctx.deviceId);
      const station = DEVICE_STATION[ctx.deviceId];
      if (station) setSelectedSubstationId(station);
    }
    if (ctx?.cameraId) setInitialCameraId(ctx.cameraId);
    setActiveTab(tab);
  };

  return (
    <DataProvider navigate={navigate}>
      <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
        {activeTab === 'fleet' && (
          <FleetDashboard onNavigateToAI={(id) => navigate('reasoning', { deviceId: id })} />
        )}
        {activeTab === 'reasoning' && (
          <ReasoningHub deviceId={selectedDeviceId} onNavigateAgent={() => navigate('agent')} />
        )}
        {activeTab === 'approval' && <ApprovalWorkspace />}
        {activeTab === 'dlt' && (
          <DltEvaluation equipmentId={selectedDeviceId} onEquipmentChange={setSelectedDeviceId} />
        )}
        {activeTab === 'agent' && <AgentConsole />}
        {activeTab === 'monitor' && <MonitorHub initialCameraId={initialCameraId} />}
        {activeTab === 'knowledge' && <KnowledgeHub />}
        {activeTab === 'admin' && <AdminCenter />}
      </Layout>
    </DataProvider>
  );
}

export default App;
