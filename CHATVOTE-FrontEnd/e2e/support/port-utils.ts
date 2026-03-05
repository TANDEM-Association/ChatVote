import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const PORT_FILE = path.resolve(__dirname, '../../.e2e-ports.json');
const BASE_PORT = 10_000;

export interface E2EPorts {
  /** Next.js test server */
  frontend: number;
  /** Mock Socket.IO server */
  mockSocket: number;
}

/** Check if a TCP port is available synchronously using a subprocess. */
function isPortAvailableSync(port: number): boolean {
  try {
    execSync(
      `node -e "const s=require('net').createServer();s.listen(${port},'127.0.0.1',()=>{s.close(()=>process.exit(0))});s.on('error',()=>process.exit(1))"`,
      { timeout: 3000, stdio: 'ignore' },
    );
    return true;
  } catch {
    return false;
  }
}

/** Find N available ports synchronously starting from `base`. */
function findAvailablePortsSync(count: number, base = BASE_PORT): number[] {
  const ports: number[] = [];
  let candidate = base;
  while (ports.length < count && candidate < base + 1000) {
    if (isPortAvailableSync(candidate)) {
      ports.push(candidate);
    }
    candidate++;
  }
  if (ports.length < count) {
    throw new Error(`Could not find ${count} available ports starting from ${base}`);
  }
  return ports;
}

/**
 * Get E2E ports. Allocates and persists them if not already done.
 * Safe to call from playwright.config.ts (runs synchronously).
 */
export function getOrAllocatePorts(): E2EPorts {
  // If ports were already allocated this run, reuse them
  if (fs.existsSync(PORT_FILE)) {
    return JSON.parse(fs.readFileSync(PORT_FILE, 'utf-8'));
  }

  // Allocate fresh ports
  const [frontend, mockSocket] = findAvailablePortsSync(2, BASE_PORT);
  const ports: E2EPorts = { frontend, mockSocket };
  fs.writeFileSync(PORT_FILE, JSON.stringify(ports));
  return ports;
}

/** Read previously allocated ports (must exist). */
export function readPorts(): E2EPorts {
  return JSON.parse(fs.readFileSync(PORT_FILE, 'utf-8'));
}

/** Clean up the port file. */
export function cleanupPortFile(): void {
  try {
    fs.unlinkSync(PORT_FILE);
  } catch {
    // already gone
  }
}
