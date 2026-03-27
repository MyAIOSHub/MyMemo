import { ChildProcess, spawn, execSync } from 'child_process'
import * as http from 'http'
import * as path from 'path'
import * as fs from 'fs'

export interface ServiceStatus {
  surrealdb: 'stopped' | 'starting' | 'running' | 'error'
  api: 'stopped' | 'starting' | 'running' | 'error'
  memoryHub: 'stopped' | 'starting' | 'running' | 'error' | 'external'
  frontend: 'stopped' | 'starting' | 'running' | 'error'
}

/**
 * ServiceManager handles the lifecycle of required services.
 *
 * Port Architecture (user-facing: only 3000):
 * - 3000: Next.js Frontend (sole entry point, Electron loads this)
 *         Proxies /api/* to API backend via rewrites
 * - 5055: FastAPI Backend (localhost-only, proxied by Next.js)
 * - 8000: SurrealDB (database, required)
 * - 1995: Memory Hub Gateway (optional, Docker)
 *         Proxies /local-store/* /cc/* /chat/* /api/v1/* internally
 *
 * Memory Hub: OPTIONAL external service, never auto-launched.
 *   Users start it themselves via `docker compose -f docker-compose.memory-hub.yml up -d`
 *   The app detects it and enables memory features when available.
 */
export class ServiceManager {
  private projectRoot: string
  private processes: Map<string, ChildProcess> = new Map()
  public status: ServiceStatus = {
    surrealdb: 'stopped',
    api: 'stopped',
    memoryHub: 'stopped',
    frontend: 'stopped',
  }

  constructor(projectRoot: string) {
    this.projectRoot = projectRoot
  }

  async startAll(): Promise<void> {
    // Start core services sequentially (each depends on previous)
    await this.startSurrealDB()
    await this.startAPI()
    await this.startFrontend()

    // Memory Hub is external — just detect if it's already running
    await this.detectMemoryHub()
  }

  async stopAll(): Promise<void> {
    // Only stop services we started (never touch Memory Hub)
    this.stopProcess('frontend')
    this.stopProcess('api')
    this.stopProcess('surrealdb')
  }

  private async startSurrealDB(): Promise<void> {
    // Check if SurrealDB is already running (e.g. via Docker)
    const alreadyRunning = await this.pollHealth('http://localhost:8000/health', 2_000)
    if (alreadyRunning) {
      this.status.surrealdb = 'running'
      return
    }

    this.status.surrealdb = 'starting'
    const dataDir = path.join(this.projectRoot, 'data', 'surreal-data')
    fs.mkdirSync(dataDir, { recursive: true })

    // Try to find surreal binary
    const surrealBin = this.findBinary('surreal')
    if (!surrealBin) {
      console.error('SurrealDB binary not found. Please install SurrealDB or start it via Docker.')
      this.status.surrealdb = 'error'
      return
    }

    const proc = spawn(surrealBin, [
      'start',
      '--log', 'info',
      '--user', process.env.SURREAL_USER || 'root',
      '--pass', process.env.SURREAL_PASS || 'root',
      '--bind', '127.0.0.1:8000',
      `rocksdb:${dataDir}`,
    ], {
      cwd: this.projectRoot,
      stdio: 'pipe',
    })

    this.processes.set('surrealdb', proc)
    proc.on('error', (err) => {
      console.error('SurrealDB failed to start:', err.message)
      this.status.surrealdb = 'error'
    })
    proc.on('exit', (code) => {
      if (code !== null && code !== 0) {
        console.error(`SurrealDB exited with code ${code}`)
      }
      this.status.surrealdb = 'stopped'
    })

    const ready = await this.pollHealth('http://localhost:8000/health', 15_000)
    this.status.surrealdb = ready ? 'running' : 'error'
  }

  private async startAPI(): Promise<void> {
    // Check if API is already running
    const alreadyRunning = await this.pollHealth('http://localhost:5055/docs', 2_000)
    if (alreadyRunning) {
      this.status.api = 'running'
      return
    }

    this.status.api = 'starting'

    // Try uv first, fall back to python
    const uvBin = this.findBinary('uv')
    let cmd: string
    let args: string[]

    if (uvBin) {
      cmd = uvBin
      args = ['run', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', '5055']
    } else {
      cmd = this.findBinary('python3') || this.findBinary('python') || 'python'
      args = ['-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', '5055']
    }

    const proc = spawn(cmd, args, {
      cwd: this.projectRoot,
      stdio: 'pipe',
      env: {
        ...process.env,
        MEMORY_HUB_URL: process.env.MEMORY_HUB_URL || 'http://localhost:1995',
      },
    })

    this.processes.set('api', proc)
    proc.on('error', (err) => {
      console.error('API failed to start:', err.message)
      this.status.api = 'error'
    })
    proc.on('exit', (code) => {
      if (code !== null && code !== 0) {
        console.error(`API exited with code ${code}`)
      }
      this.status.api = 'stopped'
    })

    const ready = await this.pollHealth('http://localhost:5055/docs', 30_000)
    this.status.api = ready ? 'running' : 'error'
  }

  private async startFrontend(): Promise<void> {
    // Check if frontend is already running
    const alreadyRunning = await this.pollHealth('http://localhost:3000', 2_000)
    if (alreadyRunning) {
      this.status.frontend = 'running'
      return
    }

    this.status.frontend = 'starting'
    const frontendDir = path.join(this.projectRoot, 'frontend')

    const npmBin = this.findBinary('npm') || 'npm'
    const proc = spawn(npmBin, ['run', 'dev'], {
      cwd: frontendDir,
      stdio: 'pipe',
      env: { ...process.env, PORT: '3000' },
    })

    this.processes.set('frontend', proc)
    proc.on('error', (err) => {
      console.error('Frontend failed to start:', err.message)
      this.status.frontend = 'error'
    })
    proc.on('exit', (code) => {
      if (code !== null && code !== 0) {
        console.error(`Frontend exited with code ${code}`)
      }
      this.status.frontend = 'stopped'
    })

    const ready = await this.pollHealth('http://localhost:3000', 30_000)
    this.status.frontend = ready ? 'running' : 'error'
  }

  /**
   * Memory Hub is an OPTIONAL external service.
   * We never start it — only detect if it's already running.
   * Users manage it themselves via docker compose.
   */
  async detectMemoryHub(): Promise<void> {
    const memoryHubUrl = process.env.MEMORY_HUB_URL || 'http://localhost:1995'
    const running = await this.pollHealth(`${memoryHubUrl}/health`, 3_000)
    this.status.memoryHub = running ? 'external' : 'stopped'
    if (running) {
      console.log(`Memory Hub detected at ${memoryHubUrl}`)
    } else {
      console.log('Memory Hub not detected. Memory features will be disabled.')
      console.log('To enable: docker compose -f docker-compose.memory-hub.yml up -d')
    }
  }

  async waitForFrontend(timeoutMs: number): Promise<boolean> {
    return this.pollHealth('http://localhost:3000', timeoutMs)
  }

  private stopProcess(name: string): void {
    const proc = this.processes.get(name)
    if (proc && !proc.killed) {
      proc.kill('SIGTERM')
      // Give process time to clean up, then force kill
      setTimeout(() => {
        if (!proc.killed) proc.kill('SIGKILL')
      }, 5_000)
      this.processes.delete(name)
    }
  }

  private findBinary(name: string): string | null {
    try {
      const result = execSync('which ' + name.replace(/[^a-zA-Z0-9_-]/g, ''), {
        encoding: 'utf-8',
        timeout: 3_000,
      })
      return result.trim() || null
    } catch {
      return null
    }
  }

  private pollHealth(url: string, timeoutMs: number): Promise<boolean> {
    return new Promise((resolve) => {
      const start = Date.now()
      const interval = setInterval(() => {
        if (Date.now() - start > timeoutMs) {
          clearInterval(interval)
          resolve(false)
          return
        }

        const req = http.get(url, (res) => {
          if (res.statusCode && res.statusCode < 500) {
            clearInterval(interval)
            resolve(true)
          }
          res.resume()
        })
        req.on('error', () => { /* retry on next interval */ })
        req.setTimeout(2000, () => req.destroy())
      }, 1500)
    })
  }
}
