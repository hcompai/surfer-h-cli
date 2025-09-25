"use client";
import { useState, useEffect } from "react";
import CreateTrajectoryInputArea from "./create-trajectory-input-area";
import { AgentSettings, DEFAULT_SETTINGS, loadSettingsFromStorage, saveSettingsToStorage } from "./settings-sheet";
import SettingsSheet from "./settings-sheet";

const examples = [
  "Explore H Company's website to discover their recent blog posts, click on the latest post and read to the bottom of the page. Summarize the interesting findings and explain why they're significant for the AI and automation industry.",
  "On Google flights. Find a one-way business class flight from Buenos Aires to Amsterdam on the 10th of next month, and provide the details of the flight with the shortest duration.",
];

const exampleUrlMappings: Record<string, string> = {
"Explore H Company's website to discover their recent blog posts, click on the latest post and read to the bottom of the page. Summarize the interesting findings and explain why they're significant for the AI and automation industry.": "https://www.hcompany.ai",
  "On Google flights. Find a one-way business class flight from Buenos Aires to Amsterdam on the 10th of next month, and provide the details of the flight with the shortest duration.": "https://www.google.com/travel/flights"
};

function ExamplePrompts({ onSelectExample }: { onSelectExample: (example: string) => void }) {
  const [visibleCount, setVisibleCount] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setVisibleCount((prev) => {
        if (prev < examples.length) {
          return prev + 1;
        }
        clearInterval(timer);
        return prev;
      });
    }, 100); // Reveal one every 100ms

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="w-full max-w-[680px] mt-8 pl-4">
      <div className="space-y-4">
        {examples.slice(0, visibleCount).map((example, index) => (
          <button
            key={index}
            onClick={() => onSelectExample(example)}
            className="w-full text-left text-14-regular-body text-gray-6 hover:text-gray-8 transition-colors duration-200 animate-in fade-in slide-in-from-bottom-1 duration-500 ease-out"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function HomepageContainer() {
  const [message, setMessage] = useState<string>("");
  const [settings, setSettings] = useState<AgentSettings>(DEFAULT_SETTINGS);
  const [isSettingsLoaded, setIsSettingsLoaded] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Load settings from localStorage on mount
  useEffect(() => {
    const loadedSettings = loadSettingsFromStorage();
    setSettings(loadedSettings);
    setIsSettingsLoaded(true);
  }, []);

  // Save settings to localStorage whenever they change (but not on initial load)
  useEffect(() => {
    if (isSettingsLoaded) {
      saveSettingsToStorage(settings);
    }
  }, [settings, isSettingsLoaded]);

  const handleSelectExample = (example: string) => {
    setMessage(example);

    // Update the URL in settings if there's a mapping for this example
    const mappedUrl = exampleUrlMappings[example];
    if (mappedUrl) {
      setSettings(prev => ({
        ...prev,
        url: mappedUrl
      }));
    }
  };

  const handleSettingsChange = (newSettings: AgentSettings) => {
    setSettings(newSettings);
  };

  const handleOpenSettings = () => {
    setIsSettingsOpen(true);
  };

  return (
    <div className="relative h-full w-full">
      {/* Settings Button - Top Right */}
      <div className="absolute top-0 right-0 z-10">
        <SettingsSheet
          settings={settings}
          onSettingsChange={handleSettingsChange}
          open={isSettingsOpen}
          onOpenChange={setIsSettingsOpen}
        />
      </div>

      {/* Main Content */}
      <div className="flex flex-col pt-10 md:pt-40 items-center pb-10">
        <div className="flex flex-col md:flex-row items-center text-center mb-4 md:mb-0 md:text-left gap-y-0 md:gap-x-3.5">
          <h1 className="text-36-light-heading">Open Surfer-H</h1>
        </div>

        <CreateTrajectoryInputArea
          message={message}
          setMessage={setMessage}
          settings={settings}
          onOpenSettings={handleOpenSettings}
        />

        <ExamplePrompts onSelectExample={handleSelectExample} />
      </div>
    </div>
  );
}