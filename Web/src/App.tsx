import React, { useState } from 'react';
import Layout from './components/Layout';
import FleetDashboard from './pages/FleetDashboard';
import ReasoningHub from './pages/ReasoningHub';
import ApprovalWorkspace from './pages/ApprovalWorkspace';
import AgentConsole from './pages/AgentConsole';
import DltEvaluation from './pages/DltEvaluation';

export type TabId = 'fleet' | 'reasoning' | 'approval' | 'dlt' | 'agent';

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('fleet');
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('tr01');
  const [selectedSubstationId, setSelectedSubstationId] = useState<string>('station1');

  const handleNavigateToAI = (deviceId: string) => {
    setSelectedDeviceId(deviceId);
    // Find substation for this device if needed, but for now we'll just switch tab
    setActiveTab('reasoning');
  };

  return (
    <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
      {activeTab === 'fleet' && (
        <FleetDashboard
          onNavigateToAI={handleNavigateToAI}
          selectedSubstationId={selectedSubstationId}
          onSelectSubstation={setSelectedSubstationId}
        />
      )}
      {activeTab === 'reasoning' && (
        <ReasoningHub deviceId={selectedDeviceId} />
      )}
      {activeTab === 'approval' && (
        <ApprovalWorkspace />
      )}
      {activeTab === 'dlt' && (
        <DltEvaluation
          equipmentId={selectedDeviceId}
          onEquipmentChange={setSelectedDeviceId}
        />
      )}
      {activeTab === 'agent' && (
        <AgentConsole />
      )}
    </Layout>
  );
}

export default App;
