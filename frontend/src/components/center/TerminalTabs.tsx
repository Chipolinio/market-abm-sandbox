import { useState } from "react";

import { DemandMatrixTab } from "@/components/center/DemandMatrixTab";
import { MarketDynamicsTab } from "@/components/center/MarketDynamicsTab";
import { MarketLeadersTab } from "@/components/center/MarketLeadersTab";
import type { DynamicsTabProps, TerminalTabId } from "@/components/center/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  dynamics: DynamicsTabProps;
  defaultTab?: TerminalTabId;
  activeTab?: TerminalTabId;
  onTabChange?: (tab: TerminalTabId) => void;
};

export function TerminalTabs({
  dynamics,
  defaultTab = "dynamics",
  activeTab: controlledTab,
  onTabChange,
}: Props) {
  const [internalTab, setInternalTab] = useState<TerminalTabId>(defaultTab);
  const activeTab = controlledTab ?? internalTab;

  const handleTabChange = (value: string) => {
    const next = value as TerminalTabId;
    if (controlledTab === undefined) {
      setInternalTab(next);
    }
    onTabChange?.(next);
  };

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList>
        <TabsTrigger value="dynamics">Market Dynamics</TabsTrigger>
        <TabsTrigger value="leaders">Market Leaders</TabsTrigger>
        <TabsTrigger value="demand_matrix">Demand Matrix</TabsTrigger>
      </TabsList>

      {activeTab === "dynamics" ? (
        <TabsContent value="dynamics" forceMount>
          <MarketDynamicsTab {...dynamics} />
        </TabsContent>
      ) : null}

      {activeTab === "leaders" ? (
        <TabsContent value="leaders" forceMount>
          <MarketLeadersTab />
        </TabsContent>
      ) : null}

      {activeTab === "demand_matrix" ? (
        <TabsContent value="demand_matrix" forceMount>
          <DemandMatrixTab />
        </TabsContent>
      ) : null}
    </Tabs>
  );
}
