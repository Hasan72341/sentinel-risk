import { useState, useEffect } from 'react';
import { Minus, Square, X, Copy } from 'lucide-react';
import { isDesktop, windowMinimize, windowMaximize, windowClose, windowIsMaximized } from '../lib/desktop';

export default function Titlebar() {
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    const checkMaximized = async () => {
      if (isDesktop) {
        const max = await windowIsMaximized();
        setIsMaximized(max);
      }
    };
    checkMaximized();

    // Poll for maximize state changes
    const interval = setInterval(checkMaximized, 500);
    return () => clearInterval(interval);
  }, []);

  const handleMinimize = () => windowMinimize();
  const handleMaximize = () => {
    windowMaximize();
    setIsMaximized(!isMaximized);
  };
  const handleClose = () => windowClose();

  // Only show custom titlebar in the desktop shell
  if (!isDesktop) return null;

  return (
    <div data-tauri-drag-region className="h-9 bg-cascade-charcoal flex items-center justify-between select-none shrink-0">
      {/* Left: App title */}
      <div className="flex items-center gap-2 pl-3">
        <div className="w-4 h-4 bg-cascade-gold rounded flex items-center justify-center">
          <span className="text-white font-bold text-[9px]">S</span>
        </div>
        <span className="text-white/70 text-xs font-medium">Sentinel Risk</span>
      </div>

      {/* Center: Spacer for drag region */}
      <div data-tauri-drag-region className="flex-1 self-stretch" />

      {/* Right: Window controls */}
      <div className="flex items-center">
        <button
          onClick={handleMinimize}
          className="w-11 h-9 flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors"
        >
          <Minus size={14} />
        </button>
        <button
          onClick={handleMaximize}
          className="w-11 h-9 flex items-center justify-center text-white/60 hover:text-white hover:bg-white/10 transition-colors"
        >
          {isMaximized ? <Copy size={12} /> : <Square size={12} />}
        </button>
        <button
          onClick={handleClose}
          className="w-11 h-9 flex items-center justify-center text-white/60 hover:text-white hover:bg-red-600 transition-colors rounded-tr"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}