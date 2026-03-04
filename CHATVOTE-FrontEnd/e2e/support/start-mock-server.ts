import { startMockServer } from './mock-socket-server';

const PORT = Number(process.env.MOCK_PORT) || 8080;

startMockServer(PORT).then((server) => {
  console.log(`Mock server running on :${PORT}. Press Ctrl+C to stop.`);
  process.on('SIGINT', () => {
    server.close().then(() => process.exit(0));
  });
  process.on('SIGTERM', () => {
    server.close().then(() => process.exit(0));
  });
});
