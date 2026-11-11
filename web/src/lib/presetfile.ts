// Preset files (.prs) of the official t.racks editor: a 16-byte header ("***DSP408V010***"),
// the preset name (14 bytes) and the config. The server checks everything; this only reads
// what the import dialog shows (docs/PROTOCOL.md §7.1).

export const PRESET_FILE_MAX_BYTES = 16 * 1024;

export interface PresetFileInfo {
  model: string; // "408", "206", "204"
  name: string;
}

/** Model and preset name of a preset file, or an error message. */
export function readPresetFile(bytes: Uint8Array): PresetFileInfo | string {
  if (bytes.length > PRESET_FILE_MAX_BYTES) return "this file is too large for a preset file";
  const header = latin1(bytes.subarray(0, 16));
  const match = /^\*\*\*DSP(\d{3})\S*\s*\*\*\*$/.exec(header);
  if (bytes.length < 30 || !match) return "this is not a t.racks preset file (.prs)";
  return {
    model: match[1] ?? "",
    name: latin1(bytes.subarray(16, 30)).replace(/\0.*$/s, "").trimEnd(),
  };
}

/** A preset name the DSP accepts: printable ASCII, accents dropped ("é" → "e"), 14 at most. */
export function asciiName(name: string, length = 14): string {
  const plain = [...name.normalize("NFC")]
    .map((c) => c.normalize("NFKD").replace(/[^\x20-\x7e]/g, "") || "?")
    .join("");
  return plain.slice(0, length).trimEnd();
}

export function toBase64(bytes: Uint8Array): string {
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text);
}

export function fromBase64(data: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
}

/** Let the browser save ``bytes`` as ``filename``. */
export function download(bytes: Uint8Array<ArrayBuffer>, filename: string): void {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function latin1(bytes: Uint8Array): string {
  return String.fromCharCode(...bytes);
}
