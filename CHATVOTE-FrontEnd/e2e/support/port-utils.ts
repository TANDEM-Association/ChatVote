import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';

const PORT_FILE = path.resolve(__dirname, '../../.e2e-ports.json');
const BASE_PORT = 10_000;

/** Check if a TCP port is available by attempting to listen on it. */
function isPortAvailable(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '127.0.0.1');
  });
}

/** Find N available ports starting from `base`. */
export async function findAvailablePorts(
  count: number,
  base = BASE_PORT,
): Promise<number[]> {
  const ports: number[] = [];
  let candidate = base;
  while (ports.length < count && candidate < base + 1000) {
    if (await isPortAvailable(candidate)) {
      ports.push(candidate);
    }
    candidate++;
  }
  if (ports.length < count) {
    throw new Error(`Could not find ${count} available ports starting from ${base}`);
  }
  return ports;
}

export interface E2EPorts {
  /** Next.js test server */
  frontend: number;
  /** Mock Socket.IO server */
  mockSocket: number;
}

/** Discover and persist two available ports for the E2E test run. */
export async function allocatePorts(): Promise<E2EPorts> {
  const [frontend, mockSocket] = await findAvailablePorts(2, BASE_PORT);
  const ports: E2EPorts = { frontend, mockSocket };
  fs.writeFileSync(PORT_FILE, JSON.stringify(ports));
  return ports;
}

/** Read previously allocated ports (written by global-setup). */
export function readPorts(): E2EPorts {
  if (!fs.existsSync(PORT_FILE)) {
    // Fallback if port file doesn't exist yet (config evaluation before global-setup)
    return { frontend: BASE_PORT, mockSocket: BASE_PORT + 1 };
  }
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
