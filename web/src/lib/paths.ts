// Dotted JSON paths shared with the server (e.g. "outputs.3.gain_db").

type Container = Record<string, unknown> | unknown[];

function step(target: Container, key: string): unknown {
  return Array.isArray(target) ? target[Number(key)] : target[key];
}

export function getPath(root: unknown, path: string): unknown {
  let target: unknown = root;
  for (const key of path.split(".")) {
    if (target === null || typeof target !== "object") return undefined;
    target = step(target as Container, key);
  }
  return target;
}

export function setPath(root: unknown, path: string, value: unknown): void {
  const keys = path.split(".");
  const last = keys.pop();
  if (last === undefined) throw new Error("empty path");
  let target: unknown = root;
  for (const key of keys) {
    if (target === null || typeof target !== "object") throw new Error(`bad path ${path}`);
    target = step(target as Container, key);
  }
  if (target === null || typeof target !== "object") throw new Error(`bad path ${path}`);
  if (Array.isArray(target)) target[Number(last)] = value;
  else (target as Record<string, unknown>)[last] = value;
}
