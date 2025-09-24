"use client";

import React from "react";
import EventStream from "./event-stream";
import SurferIcon from "@/components/common/icons/SurferIcon";
import { useGetTrajectory } from "@/hooks/useTrajectories";

interface SurferViewProps {
  taskId: string;
  isReplay?: boolean;
}

export const SurferView: React.FC<SurferViewProps> = ({
  taskId,
}) => {
  const { data: trajectory } = useGetTrajectory(taskId);

  return (
    <div className="h-full w-full overflow-hidden scrollbar-hide">
      <div className="border-b border-border flex flex-row items-center justify-between h-13 p-2 pl-4">
        <div className="flex items-center gap-2 text-14-medium-body my-0">
          <SurferIcon className="w-5 h-5 text-gray-8" />
          <h2 className="text-14-medium-body text-gray-8">
            {trajectory?.task || "Loading..."}
          </h2>
        </div>
        <div className="inline-flex items-center gap-2">
          <span className="text-xs text-gray-6">
            ID: {taskId.slice(0, 8)}...
          </span>
        </div>
      </div>

      <div className="bg-canvas-background h-[calc(100%-52px)] overflow-hidden">
        <EventStream trajectoryId={taskId} />
      </div>
    </div>
  );
};

export default SurferView;
