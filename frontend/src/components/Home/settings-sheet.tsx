"use client";

export const MODELS = {
  GPT4_1: "gpt-4.1",
  HOLO: "h-model",
} as const;

export type ModelType = typeof MODELS[keyof typeof MODELS];

export interface AgentSettings {
  url: string;
  max_n_steps: number;
  max_time_seconds: number;
  navigation_model: ModelType;
  localization_model: ModelType;
  validation_model: ModelType;
  headless_browser: boolean;
  action_timeout: number;
}

export const DEFAULT_SETTINGS: AgentSettings = {
  url: "https://www.hcompany.ai",
  max_n_steps: 30,
  max_time_seconds: 600,
  navigation_model: MODELS.HOLO,
  localization_model: MODELS.HOLO,
  validation_model: MODELS.HOLO,
  headless_browser: true,
  action_timeout: 10,
};

// localStorage utilities
const SETTINGS_STORAGE_KEY = "surferh-agent-settings";

export function saveSettingsToStorage(settings: AgentSettings): void {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.warn("Failed to save settings to localStorage:", error);
  }
}

export function loadSettingsFromStorage(): AgentSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // Validate that all required fields exist and merge with defaults for any missing fields
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
      };
    }
  } catch (error) {
    console.warn("Failed to load settings from localStorage:", error);
  }
  return DEFAULT_SETTINGS;
}

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/common/atoms/sheet";
import { Button } from "@/components/common/atoms/button";
import { Checkbox } from "@/components/common/atoms/checkbox";
import { LabeledInput } from "@/components/common/atoms/labeled-input";
import { LabeledSelect } from "@/components/common/atoms/labeled-select";
import { SettingsSection } from "@/components/common/atoms/settings-section";
import SettingsIcon from "@/components/common/icons/SettingsIcon";

interface SettingsSheetProps {
  settings: AgentSettings;
  onSettingsChange: (settings: AgentSettings) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function SettingsSheetSelect({
  settings,
  onSettingsChange,
  open,
  onOpenChange,
}: SettingsSheetProps) {
  const handleInputChange = (key: keyof AgentSettings, value: string | number | boolean) => {
    onSettingsChange({
      ...settings,
      [key]: value,
    });
  };

  const modelOptions = [
    { value: MODELS.GPT4_1, label: "GPT-4.1" },
    { value: MODELS.HOLO, label: "H-model" },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 text-gray-6 hover:text-gray-8 hover:bg-gray-2"
        >
          <SettingsIcon />
        </Button>
      </SheetTrigger>
      <SheetContent className="w-[480px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="text-16-medium-heading text-gray-8">Settings</SheetTitle>
        </SheetHeader>

        <div className="space-y-6 mt-6">
          {/* Basic Settings */}
          <div className="space-y-4">
            <LabeledInput
              label="Starting URL"
              type="text"
              value={settings.url}
              onChange={(e) => handleInputChange("url", e.target.value)}
              placeholder="https://www.hcompany.ai"
            />

            <LabeledInput
              label="Max Steps"
              type="number"
              value={settings.max_n_steps}
              onChange={(e) => handleInputChange("max_n_steps", parseInt(e.target.value) || 30)}
              min="1"
              max="100"
            />

            <LabeledInput
              label="Max Time (seconds)"
              type="number"
              value={settings.max_time_seconds}
              onChange={(e) => handleInputChange("max_time_seconds", parseInt(e.target.value) || 600)}
              min="60"
              max="3600"
            />

            <LabeledInput
              label="Action Timeout (seconds)"
              type="number"
              value={settings.action_timeout}
              onChange={(e) => handleInputChange("action_timeout", parseInt(e.target.value) || 10)}
              min="1"
              max="60"
            />
          </div>

          {/* Model Selection */}
          <SettingsSection title="Model Selection">
            <div className="space-y-4">
              <LabeledSelect
                label="Navigation Model"
                value={settings.navigation_model}
                onValueChange={(value) => handleInputChange("navigation_model", value as ModelType)}
                options={modelOptions}
              />

              <LabeledSelect
                label="Localization Model"
                value={settings.localization_model}
                onValueChange={(value) => handleInputChange("localization_model", value as ModelType)}
                options={modelOptions}
              />

              <LabeledSelect
                label="Validation Model"
                value={settings.validation_model}
                onValueChange={(value) => handleInputChange("validation_model", value as ModelType)}
                options={modelOptions}
              />
            </div>
          </SettingsSection>

          {/* Browser Settings */}
          <SettingsSection title="Browser Settings">
            <div className="flex items-center gap-2 pl-2">
              <Checkbox
                checked={settings.headless_browser}
                onCheckedChange={(checked) => handleInputChange("headless_browser", checked)}
              />
              <label className="text-14-regular-body text-gray-7">
                Run browser in headless mode
              </label>
            </div>
          </SettingsSection>
        </div>
      </SheetContent>
    </Sheet>
  );
}