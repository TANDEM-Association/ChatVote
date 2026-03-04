async function integrationTeardown() {
  const backendProcess = (globalThis as any).__BACKEND_PROCESS__;
  if (backendProcess?.pid) {
    try {
      process.kill(-backendProcess.pid, 'SIGTERM');
    } catch {
      // process may already be gone
    }
    console.log('Backend stopped');
  }

  const emulatorProcess = (globalThis as any).__EMULATOR_PROCESS__;
  if (emulatorProcess?.pid) {
    try {
      process.kill(-emulatorProcess.pid, 'SIGTERM');
    } catch {
      // process may already be gone
    }
    console.log('Emulators stopped');
  }
}

export default integrationTeardown;
