"use client";

import { Button } from "@/components/common/atoms/button";
import Play3Icon from "../common/icons/Play3";
import { useCreateTrajectory } from "@/hooks/useTrajectories";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AgentSettings } from "./settings-sheet";

interface CreateTrajectoryInputAreaProps {
  message: string;
  setMessage: (message: string) => void;
  settings: AgentSettings;
  onOpenSettings: () => void;
}

export default function CreateTrajectoryInputArea({
  message,
  setMessage,
  settings,
  onOpenSettings,
}: CreateTrajectoryInputAreaProps) {
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const createTrajectory = useCreateTrajectory({
    onSuccess: (trajectory) => {
      console.log('Trajectory created:', trajectory.trajectory_id);
      // Navigate to the surfer view with the new trajectory
      router.push(`/surfer-view/${trajectory.trajectory_id}`);
    },
    onError: (error) => {
      console.error('Failed to create trajectory:', error.message);
      setIsSubmitting(false);
    },
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (message.trim().length === 0 || isSubmitting) {
      return;
    }

    setIsSubmitting(true);

    try {
      await createTrajectory.mutateAsync({
        task: message.trim(),
        url: settings.url,
        max_n_steps: settings.max_n_steps,
        max_time_seconds: settings.max_time_seconds,
        model_name_navigation: settings.navigation_model,
        temperature_navigation: 0.7,
        n_navigation_screenshots: 3,
        model_name_localization: settings.localization_model,
        temperature_localization: 0.7,
        use_validator: true,
        model_name_validation: settings.validation_model,
        temperature_validation: 0.0,
        headless_browser: settings.headless_browser,
        action_timeout: settings.action_timeout,
      });
    } catch (error) {
      // Error is already handled in onError callback
      console.error('Submit error:', error);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Check for Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux)
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      // Create a synthetic form event to trigger submission
      const syntheticEvent = {
        preventDefault: () => { },
      } as React.FormEvent;
      handleSubmit(syntheticEvent);
    }
    // Let normal Enter key work for new lines
  };

  return (
    <>
      <div className="pt-8 w-full max-w-[680px]">
      </div>
      <form
        onSubmit={handleSubmit}
        className="p-4 border border-gray-3 bg-gray-1 h-[220px] rounded-lg w-full max-w-[680px] floating-shadow-1 flex flex-col relative text-14-regular-body focus-within:border-gray-4 transition-border duration-200"
        style={{ marginTop: "-10px" }}
      >
        <div className="relative w-full flex-grow min-h-0">
          <textarea
            className="w-full h-full rounded-lg p-2 focus:ring-0 focus:outline-none resize-none bg-transparent caret-black dark:caret-white text-14-regular-body overflow-auto"
            value={message}
            placeholder="Describe your task here..."
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck="false"
            inputMode="text"
            style={{
              fontFamily: "inherit",
              fontSize: window.innerWidth <= 768 ? "16px" : "14px",
              lineHeight: "inherit",
              overflowY: "auto",
              whiteSpace: "pre-wrap",
              paddingBottom: "3px",
              transform: "translateZ(0)",
            }}
          />
        </div>

        <div className="w-full flex flex-row justify-between items-center pt-0 mb-0">
          <div className="flex flex-row gap-x-2 items-center">
            <button
              type="button"
              onClick={onOpenSettings}
              className="text-12-regular-body text-gray-5 hover:text-gray-7 transition-colors duration-200 cursor-pointer"
            >
              Starting at: <span className="underline decoration-dotted underline-offset-2">{settings.url}</span>
            </button>
          </div>

          <div className="flex flex-row gap-x-2 items-center">
            <div className="rounded-sm bg-gray-2 text-gray-5">
              <Button
                type="submit"
                disabled={message.trim().length === 0 || isSubmitting}
                variant={message.trim().length === 0 || isSubmitting ? "ghost" : "default"}
                size="icon"
                className={
                  message.trim().length === 0 || isSubmitting
                    ? "bg-gray-2"
                    : "bg-gray-8 rounded-sm shadow-none hover:bg-gray-7"
                }
              >
                {isSubmitting ? (
                  <div className="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full" />
                ) : (
                  <Play3Icon fill="currentColor" height={18} width={18} />
                )}
              </Button>
            </div>
          </div>
        </div>
      </form>
    </>
  );
}