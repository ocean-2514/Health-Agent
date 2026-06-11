import React, { useState } from 'react';
import Layout from './components/Layout';
import FleetDashboard from './pages/FleetDashboard';
import ReasoningHub from './pages/ReasoningHub';
import ApprovalWorkspace from './pages/ApprovalWorkspace';
import AgentConsole from './pages/AgentConsole';

function App() {
  const [activeTab, setActiveTab] = useState<'fleet' | 'reasoning' | 'approval' | 'agent'>('fleet');
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
      {activeTab === 'agent' && (
        <AgentConsole />
      )}
    </Layout>
  );
}

export default App;
