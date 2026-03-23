import { cleanupPortFile } from "./support/port-utils";

async function globalTeardown() {
  const g = globalThis as Record<string, unknown>;

  // Stop emulators
  const emulatorProcess = g.__EMULATOR_PROCESS__ as
    | { pid?: number }
    | undefined;
  if (emulatorProcess && emulatorProcess.pid) {
    try {
      process.kill(-emulatorProcess.pid, "SIGTERM");
    } catch {
      // process may already be gone
    }
    console.info("Firebase emulators stopped");
  }

  // Clean up the port allocation file
  cleanupPortFile();
}

export default globalTeardown;
