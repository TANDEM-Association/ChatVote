import { cleanupPortFile } from './support/port-utils';

async function globalTeardown() {
  // Stop mock server
  const mockServer = (globalThis as any).__MOCK_SERVER__;
  if (mockServer) {
    await mockServer.close();
    console.log('Mock server stopped');
  }

  // Stop emulators
  const emulatorProcess = (globalThis as any).__EMULATOR_PROCESS__;
  if (emulatorProcess && emulatorProcess.pid) {
    try {
      process.kill(-emulatorProcess.pid, 'SIGTERM');
    } catch {
      // process may already be gone
    }
    console.log('Firebase emulators stopped');
  }

  // Clean up the port allocation file
  cleanupPortFile();
}

export default globalTeardown;
