import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const backendRoot = path.resolve(projectRoot, '../backend');
const venvPython = path.join(backendRoot, '.venv', 'Scripts', 'python.exe');

if (!existsSync(venvPython)) {
  console.error(`Backend venv not found at ${venvPython}`);
  process.exit(1);
}

const child = spawn(venvPython, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
  cwd: backendRoot,
  stdio: 'inherit',
  shell: false,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

child.on('error', (error) => {
  console.error('Backend startup error:', error.message);
  process.exit(1);
});
