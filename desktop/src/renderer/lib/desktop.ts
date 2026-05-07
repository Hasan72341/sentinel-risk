import { invoke } from '@tauri-apps/api/core';
import { getVersion } from '@tauri-apps/api/app';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { open, save } from '@tauri-apps/plugin-dialog';

export interface FileBuffer {
  buffer: string;
  name: string;
  mimeType: string;
}

// True when running inside the Tauri shell, false in a plain browser
export const isDesktop = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

export async function openFile(): Promise<string | null> {
  return await open({
    multiple: false,
    directory: false,
    filters: [
      { name: 'Financial Statements', extensions: ['csv', 'xlsx', 'xls', 'pdf'] },
      { name: 'Images (OCR)', extensions: ['png', 'jpg', 'jpeg', 'tiff', 'bmp'] },
      { name: 'All Files', extensions: ['*'] },
    ],
  });
}

export async function saveFile(suggestedName: string): Promise<string | null> {
  return await save({
    defaultPath: suggestedName,
    filters: [
      { name: 'PDF Report', extensions: ['pdf'] },
      { name: 'Excel Report', extensions: ['xlsx'] },
    ],
  });
}

export function readFileBuffer(filePath: string): Promise<FileBuffer> {
  return invoke<FileBuffer>('read_file_buffer', { filePath });
}

export async function writeFile(filePath: string, blob: Blob): Promise<void> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
  await invoke('write_file_buffer', { filePath, buffer: dataUrl.slice(dataUrl.indexOf(',') + 1) });
}

export function getAppVersion(): Promise<string> {
  return getVersion();
}

export function windowMinimize(): Promise<void> {
  return getCurrentWindow().minimize();
}

export function windowMaximize(): Promise<void> {
  return getCurrentWindow().toggleMaximize();
}

export function windowClose(): Promise<void> {
  return getCurrentWindow().close();
}

export function windowIsMaximized(): Promise<boolean> {
  return getCurrentWindow().isMaximized();
}
