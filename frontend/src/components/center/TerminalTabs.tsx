import { useState } from "react";

import { DemandMatrixTab } from "@/components/center/DemandMatrixTab";
import { MarketDynamicsTab } from "@/components/center/MarketDynamicsTab";
import { MarketLeadersTab } from "@/components/center/MarketLeadersTab";
import type { DynamicsTabProps, TerminalTabId } from "@/components/center/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  dynamics: DynamicsTabProps;
  asOfTick: number;
  defaultTab?: TerminalTabId;
  activeTab?: TerminalTabId;
  onTabChange?: (tab: TerminalTabId) => void;
};

export function TerminalTabs({
  dynamics,
  asOfTick,
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
    <Tabs value={activeTab} onValueChange={handleTabChange} className="flex h-full min-h-0 flex-col">
      <TabsList className="mb-2 shrink-0">
        <TabsTrigger value="dynamics">Динамика рынка</TabsTrigger>
        <TabsTrigger value="leaders">Лидеры рынка</TabsTrigger>
        <TabsTrigger value="demand_matrix">Матрица спроса</TabsTrigger>
      </TabsList>

      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "dynamics" ? (
          <TabsContent value="dynamics" className="mt-0 h-full">
            <MarketDynamicsTab {...dynamics} />
          </TabsContent>
        ) : null}

        {activeTab === "leaders" ? (
          <TabsContent value="leaders" className="mt-0 h-full overflow-y-auto">
            <MarketLeadersTab asOfTick={asOfTick} />
          </TabsContent>
        ) : null}

        {activeTab === "demand_matrix" ? (
          <TabsContent value="demand_matrix" className="mt-0 h-full overflow-hidden">
            <DemandMatrixTab asOfTick={asOfTick} />
          </TabsContent>
        ) : null}
      </div>
    </Tabs>
  );
}
