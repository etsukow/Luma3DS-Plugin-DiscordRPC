<script>
  import { onMount, onDestroy } from 'svelte'
  import { invoke } from '@tauri-apps/api/core'
  import { listen } from '@tauri-apps/api/event'

  // ── State ──────────────────────────────────────────────────────────────────
  let status = $state({ installed: false, token: null, server_ws: '', server_api: '', plugin_path: null })
  let wsStatus = $state({ connected: false, message: 'Not started' })
  let rpcStatus = $state({ connected: false, message: 'Waiting…' })
  let pollInterval = null
  let currentGame = $state(null)
  let logs = $state([])
  let logId = 0
  let busy = $state(false)
  let activeTab = $state('dashboard')
  let copied = $state(false)

  const MAX_LOGS = 200

  // ── Listeners ──────────────────────────────────────────────────────────────
  let unlisten = []

  onMount(async () => {
    status = await invoke('get_status')

    unlisten.push(await listen('log', ({ payload }) => {
      addLog(payload.level, payload.message)
    }))

    unlisten.push(await listen('ws_status', ({ payload }) => {
      wsStatus = payload
      if (payload.connected) addLog('info', payload.message)
      else addLog('warn', payload.message)
    }))

    unlisten.push(await listen('rpc_status', ({ payload }) => {
      rpcStatus = payload
      addLog(payload.connected ? 'success' : 'warn', `Discord: ${payload.message}`)
    }))

    unlisten.push(await listen('presence_event', ({ payload }) => {
      if (payload.type === 'presence') {
        currentGame = { name: payload.name, icon: payload.icon, titleId: payload.title_id }
        addLog('info', `▶ ${payload.name} (${payload.title_id})`)
      } else if (payload.type === 'clear') {
        currentGame = null
        addLog('info', 'Presence cleared')
      }
    }))

    unlisten.push(await listen('install_complete', ({ payload }) => {
      status = { ...status, installed: true, plugin_path: payload }
      busy = false
    }))

    unlisten.push(await listen('uninstall_complete', () => {
      status = { ...status, installed: false, token: null, plugin_path: null }
      currentGame = null
      busy = false
    }))

    // Poll live status every 3s to sync state missed before listeners were ready
    async function pollLiveStatus() {
      try {
        const live = await invoke('get_live_status')
        wsStatus = { connected: live.ws_connected, message: live.ws_message }
        rpcStatus = { connected: live.rpc_connected, message: live.rpc_message }
        if (live.current_game) {
          currentGame = { name: live.current_game.name, icon: live.current_game.icon, titleId: live.current_game.title_id }
        } else if (!live.ws_connected) {
          currentGame = null
        }
      } catch (_) {}
    }
    await pollLiveStatus()
    pollInterval = setInterval(pollLiveStatus, 3000)
  })

  onDestroy(() => {
    unlisten.forEach(fn => fn())
    if (pollInterval) clearInterval(pollInterval)
  })

  // ── Actions ────────────────────────────────────────────────────────────────
  async function doInstall() {
    busy = true
    logs = []
    activeTab = 'logs'
    try {
      await invoke('install')
      status = await invoke('get_status')
    } catch (e) {
      addLog('error', `Install failed: ${e}`)
    } finally {
      busy = false
    }
  }

  async function doUninstall() {
    if (!confirm('Remove the service and your token? You will need to re-install.')) return
    busy = true
    try {
      await invoke('uninstall')
    } catch (e) {
      addLog('error', `Uninstall failed: ${e}`)
      busy = false
    }
  }

  async function doUpdatePlugin() {
    busy = true
    addLog('info', 'Updating plugin…')
    try {
      await invoke('update_plugin')
      addLog('success', 'Plugin updated ✓')
    } catch (e) {
      addLog('error', `Update failed: ${e}`)
    } finally {
      busy = false
    }
  }

  async function copyPluginPath() {
    if (status.plugin_path) {
      await navigator.clipboard.writeText(status.plugin_path)
      copied = true
      setTimeout(() => copied = false, 2000)
    }
  }

  function addLog(level, message) {
    const ts = new Date().toLocaleTimeString()
    logs = [{ id: ++logId, ts, level, message }, ...logs].slice(0, MAX_LOGS)
  }

  function clearLogs() { logs = [] }
</script>

<main>
  <header>
    <div class="brand">
      <svg class="logo-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="6" width="20" height="13" rx="2" stroke="#7289da" stroke-width="1.5"/>
        <circle cx="7" cy="12" r="2" fill="#7289da" opacity="0.7"/>
        <rect x="10.5" y="10.5" width="3" height="3" rx="0.5" fill="#7289da" opacity="0.7"/>
        <circle cx="17" cy="12" r="1.5" fill="#7289da" opacity="0.4"/>
        <path d="M5 6V4.5A1.5 1.5 0 0 1 6.5 3h11A1.5 1.5 0 0 1 19 4.5V6" stroke="#7289da" stroke-width="1.5"/>
      </svg>
      <span class="title">3DS Discord RPC</span>
    </div>
    <div class="badges">
      <div class="status-pill" class:on={wsStatus.connected} title={wsStatus.message}>
        <span class="pip"></span><span>Server</span>
      </div>
      <div class="status-pill" class:on={rpcStatus.connected} title={rpcStatus.message}>
        <svg class="discord-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057c.002.022.015.043.032.054a19.9 19.9 0 0 0 5.993 3.03.077.077 0 0 0 .084-.028 13.895 13.895 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z"/></svg>
        <span>Discord</span>
      </div>
    </div>
  </header>

  <nav>
    <button class:active={activeTab === 'dashboard'} onclick={() => activeTab = 'dashboard'}>
      <svg viewBox="0 0 20 20" fill="currentColor"><path d="M10.707 2.293a1 1 0 0 0-1.414 0l-7 7a1 1 0 0 0 1.414 1.414L4 10.414V17a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-6.586l.293.293a1 1 0 0 0 1.414-1.414l-7-7z"/></svg>
      Dashboard
    </button>
    <button class:active={activeTab === 'logs'} onclick={() => activeTab = 'logs'}>
      <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M3 5a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1zm0 5a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1zm1 4a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2H4z" clip-rule="evenodd"/></svg>
      Logs {#if logs.length > 0}<span class="log-count">{logs.length}</span>{/if}
    </button>
    <button class:active={activeTab === 'settings'} onclick={() => activeTab = 'settings'}>
      <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 0 1-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 0 1 .947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 0 1 2.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 0 1 2.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 0 1 .947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 0 1-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 0 1-2.287-.947zM10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" clip-rule="evenodd"/></svg>
      Settings
    </button>
  </nav>

  <!-- ── Dashboard ─────────────────────────────────────────────────────────── -->
  {#if activeTab === 'dashboard'}
  <section class="tab">

    <!-- Now playing -->
    {#if currentGame}
    <div class="now-playing">
      <div class="now-playing-glow"></div>
      <div class="now-playing-content">
        <div class="game-art">
          {#if currentGame.icon}
            <img src={currentGame.icon} alt={currentGame.name} />
          {:else}
            <div class="game-art-placeholder">🎮</div>
          {/if}
          <span class="playing-dot"></span>
        </div>
        <div class="game-meta">
          <div class="now-label">Now Playing</div>
          <div class="game-name">{currentGame.name}</div>
          <div class="game-sub">
            <span class="console-tag">
              <svg viewBox="0 0 20 20" fill="currentColor" class="console-icon"><rect x="2" y="5" width="16" height="10" rx="2"/></svg>
              Nintendo 3DS
            </span>
            <span class="game-tid">{currentGame.titleId}</span>
          </div>
        </div>
      </div>
    </div>
    {:else}
    <div class="idle-card">
      <div class="idle-icon">
        <svg viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="20" stroke="#7289da" stroke-width="1.5" opacity="0.3"/><path d="M16 24h4m8 0h4M24 16v4m0 8v4" stroke="#7289da" stroke-width="2" stroke-linecap="round" opacity="0.5"/></svg>
      </div>
      <div class="idle-text">No game detected</div>
      <div class="idle-sub">Launch a game on your 3DS with the plugin enabled</div>
    </div>
    {/if}

    <!-- Status grid -->
    <div class="status-grid">
      <div class="stat-card" class:stat-ok={status.installed}>
        <div class="stat-icon">{status.installed ? '✓' : '✗'}</div>
        <div class="stat-label">Service</div>
        <div class="stat-value">{status.installed ? 'Installed' : 'Not installed'}</div>
      </div>
      <div class="stat-card" class:stat-ok={wsStatus.connected}>
        <div class="stat-icon">{wsStatus.connected ? '✓' : '✗'}</div>
        <div class="stat-label">Server</div>
        <div class="stat-value">{wsStatus.connected ? 'Connected' : 'Offline'}</div>
      </div>
      <div class="stat-card" class:stat-ok={rpcStatus.connected}>
        <div class="stat-icon">{rpcStatus.connected ? '✓' : '✗'}</div>
        <div class="stat-label">Discord</div>
        <div class="stat-value">{rpcStatus.connected ? 'Connected' : 'Not open'}</div>
      </div>
    </div>

    <!-- Plugin path -->
    {#if status.plugin_path && status.installed}
    <div class="card">
      <div class="card-header">
        <h3>Plugin file</h3>
        <span class="card-hint">Copy to your 3DS SD card</span>
      </div>
      <div class="path-row">
        <code class="path">{status.plugin_path}</code>
        <button class="copy-btn" class:copied onclick={copyPluginPath}>
          {copied ? '✓ Copied' : '📋 Copy'}
        </button>
      </div>
      <div class="sd-hint">→ <code>SD:/luma/plugins/default/discord-rpc.3gx</code></div>
    </div>
    {/if}

    <!-- Actions -->
    <div class="actions">
      {#if !status.installed}
        <button class="btn primary" onclick={doInstall} disabled={busy}>
          {#if busy}
            <span class="spinner"></span> Installing…
          {:else}
            <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0 1 12 2v5h4a1 1 0 0 1 .82 1.573l-7 10A1 1 0 0 1 8 18v-5H4a1 1 0 0 1-.82-1.573l7-10a1 1 0 0 1 1.12-.38z" clip-rule="evenodd"/></svg>
            Install
          {/if}
        </button>
      {:else}
        <button class="btn secondary" onclick={doUpdatePlugin} disabled={busy}>
          {#if busy}
            <span class="spinner"></span> Updating…
          {:else}
            <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4 2a1 1 0 0 1 1 1v2.101a7.002 7.002 0 0 1 11.601 2.566 1 1 0 1 1-1.885.666A5.002 5.002 0 0 0 5.999 7H9a1 1 0 0 1 0 2H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zm.008 9.057a1 1 0 0 1 1.276.61A5.002 5.002 0 0 0 14.001 13H11a1 1 0 1 1 0-2h5a1 1 0 0 1 1 1v5a1 1 0 1 1-2 0v-2.101a7.002 7.002 0 0 1-11.601-2.566 1 1 0 0 1 .61-1.276z" clip-rule="evenodd"/></svg>
            Update plugin
          {/if}
        </button>
        <button class="btn ghost-danger" onclick={doUninstall} disabled={busy}>
          <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M9 2a1 1 0 0 0-.894.553L7.382 4H4a1 1 0 0 0 0 2v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6a1 1 0 1 0 0-2h-3.382l-.724-1.447A1 1 0 0 0 11 2H9zM7 8a1 1 0 0 1 2 0v6a1 1 0 1 1-2 0V8zm4 0a1 1 0 0 1 2 0v6a1 1 0 1 1-2 0V8z" clip-rule="evenodd"/></svg>
          Uninstall
        </button>
      {/if}
    </div>

  </section>
  {/if}

  <!-- ── Logs ───────────────────────────────────────────────────────────────── -->
  {#if activeTab === 'logs'}
  <section class="tab logs-tab">
    <div class="logs-toolbar">
      <span class="logs-count">{logs.length} entries</span>
      <button class="btn-sm" onclick={clearLogs}>Clear</button>
    </div>
    <div class="logs">
      {#each logs as entry (entry.id)}
        <div class="log-line {entry.level}">
          <span class="log-ts">{entry.ts}</span>
          <span class="log-level-dot"></span>
          <span class="log-msg">{entry.message}</span>
        </div>
      {:else}
        <div class="log-empty">
          <svg viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="20" stroke="#333" stroke-width="1.5"/><path d="M16 24h16M24 16v16" stroke="#333" stroke-width="2" stroke-linecap="round" opacity="0.4"/></svg>
          <p>No logs yet</p>
        </div>
      {/each}
    </div>
  </section>
  {/if}

  <!-- ── Settings ───────────────────────────────────────────────────────────── -->
  {#if activeTab === 'settings'}
  <section class="tab settings-tab">
    <div class="card">
      <div class="card-header"><h3>Server</h3></div>
      <label>
        <span class="label-text">WebSocket URL</span>
        <input type="text" value={status.server_ws} disabled />
      </label>
      <label>
        <span class="label-text">API URL</span>
        <input type="text" value={status.server_api} disabled />
      </label>
      {#if status.token}
      <label>
        <span class="label-text">Your token</span>
        <input type="text" value={status.token} disabled />
      </label>
      {/if}
      <p class="settings-hint">Server settings are managed by your token provisioning.</p>
    </div>
    <div class="card">
      <div class="card-header"><h3>About</h3></div>
      <div class="about-row">
        <span>3DS Discord RPC</span>
        <a href="https://github.com/etsukow/Luma3DS-Plugin-DiscordRPC" target="_blank" class="gh-link">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577v-2.165c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
          GitHub
        </a>
      </div>
    </div>
  </section>
  {/if}
</main>

<style>
  :global(*) { box-sizing: border-box; margin: 0; padding: 0; }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', sans-serif;
    background: #0d0f14;
    color: #c8cdd4;
    height: 100vh;
    overflow: hidden;
  }

  main { display: flex; flex-direction: column; height: 100vh; }

  /* ── Header ───────────────────────────────────────────────────────────────── */
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px;
    background: #13151c;
    border-bottom: 1px solid #1e2130;
    user-select: none;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .logo-icon { width: 28px; height: 28px; }
  .title { font-size: 15px; font-weight: 700; color: #e0e3ea; letter-spacing: -.02em; }

  .badges { display: flex; gap: 6px; }
  .status-pill {
    display: flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 500;
    background: #1a1d26; color: #555;
    border: 1px solid #1e2130;
    transition: all .2s;
  }
  .status-pill.on { background: #1a2b1e; color: #3ba55d; border-color: #2d4a33; }
  .pip {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor; opacity: .6;
  }
  .discord-icon { width: 12px; height: 12px; }

  /* ── Nav ──────────────────────────────────────────────────────────────────── */
  nav {
    display: flex; gap: 0;
    background: #13151c;
    padding: 0 16px;
    border-bottom: 1px solid #1e2130;
  }
  nav button {
    display: flex; align-items: center; gap: 6px;
    padding: 11px 16px; border: none; background: none;
    color: #555; cursor: pointer; font-size: 13px; font-weight: 500;
    border-bottom: 2px solid transparent;
    transition: color .15s;
    position: relative;
  }
  nav button svg { width: 14px; height: 14px; }
  nav button:hover { color: #c8cdd4; }
  nav button.active { color: #7289da; border-bottom-color: #7289da; }
  .log-count {
    font-size: 10px; background: #7289da22; color: #7289da;
    padding: 1px 6px; border-radius: 10px; margin-left: 2px;
  }

  /* ── Tabs ─────────────────────────────────────────────────────────────────── */
  .tab { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; min-height: 0; }

  /* ── Now playing ──────────────────────────────────────────────────────────── */
  .now-playing {
    position: relative; overflow: hidden;
    border-radius: 14px; padding: 20px;
    background: linear-gradient(135deg, #1a1d26 0%, #13151c 100%);
    border: 1px solid #2a2f42;
  }
  .now-playing-glow {
    position: absolute; inset: 0; opacity: .15;
    background: radial-gradient(circle at 20% 50%, #7289da 0%, transparent 60%);
    pointer-events: none;
  }
  .now-playing-content { position: relative; display: flex; align-items: center; gap: 18px; }
  .game-art {
    position: relative; flex-shrink: 0;
    width: 72px; height: 72px; border-radius: 12px; overflow: hidden;
    border: 2px solid #2a2f42;
    background: #1e2130;
  }
  .game-art img { width: 100%; height: 100%; object-fit: cover; }
  .game-art-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; font-size: 32px; }
  .playing-dot {
    position: absolute; bottom: 4px; right: 4px;
    width: 10px; height: 10px; border-radius: 50%;
    background: #3ba55d; border: 2px solid #13151c;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: .5; }
  }
  .game-meta { flex: 1; min-width: 0; }
  .now-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: #7289da; margin-bottom: 4px; }
  .game-name { font-size: 20px; font-weight: 700; color: #e0e3ea; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .game-sub { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
  .console-tag {
    display: flex; align-items: center; gap: 4px;
    font-size: 11px; color: #7289da; background: #7289da18;
    padding: 3px 8px; border-radius: 6px;
  }
  .console-icon { width: 12px; height: 12px; }
  .game-tid { font-size: 11px; color: #444; font-family: 'SF Mono', 'Fira Code', monospace; }

  /* ── Idle ─────────────────────────────────────────────────────────────────── */
  .idle-card {
    border-radius: 14px; padding: 32px 20px;
    background: #13151c; border: 1px dashed #1e2130;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    text-align: center;
  }
  .idle-icon svg { width: 48px; height: 48px; }
  .idle-text { font-size: 15px; font-weight: 600; color: #3a3f52; }
  .idle-sub { font-size: 12px; color: #2a2f42; }

  /* ── Status grid ──────────────────────────────────────────────────────────── */
  .status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .stat-card {
    background: #13151c; border: 1px solid #1e2130;
    border-radius: 12px; padding: 14px 12px;
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    transition: border-color .2s;
  }
  .stat-card.stat-ok { border-color: #2d4a33; }
  .stat-icon { font-size: 16px; color: #444; }
  .stat-card.stat-ok .stat-icon { color: #3ba55d; }
  .stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: #444; }
  .stat-value { font-size: 12px; font-weight: 600; color: #666; }
  .stat-card.stat-ok .stat-value { color: #3ba55d; }

  /* ── Cards ────────────────────────────────────────────────────────────────── */
  .card {
    background: #13151c; border-radius: 12px;
    border: 1px solid #1e2130; padding: 16px;
  }
  .card-header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12px; }
  .card-header h3 { font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: #555; }
  .card-hint { font-size: 11px; color: #333; }

  /* ── Plugin path ──────────────────────────────────────────────────────────── */
  .path-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .path {
    flex: 1; background: #0d0f14; padding: 8px 10px; border-radius: 8px;
    font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; color: #888;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    border: 1px solid #1e2130;
  }
  .copy-btn {
    padding: 7px 12px; border-radius: 8px; border: 1px solid #1e2130;
    background: #1a1d26; color: #888; font-size: 12px; cursor: pointer;
    white-space: nowrap; transition: all .15s;
  }
  .copy-btn:hover { background: #7289da22; color: #7289da; border-color: #7289da44; }
  .copy-btn.copied { background: #1a2b1e; color: #3ba55d; border-color: #2d4a33; }
  .sd-hint { font-size: 11px; color: #333; }
  .sd-hint code { color: #7289da88; font-family: 'SF Mono', 'Fira Code', monospace; }

  /* ── Actions ──────────────────────────────────────────────────────────────── */
  .actions { display: flex; gap: 10px; flex-wrap: wrap; }
  .btn {
    display: flex; align-items: center; gap: 7px;
    padding: 10px 20px; border: none; border-radius: 10px;
    font-size: 13px; cursor: pointer; font-weight: 600;
    transition: all .15s; letter-spacing: -.01em;
  }
  .btn svg { width: 15px; height: 15px; }
  .btn:disabled { opacity: .4; cursor: not-allowed; }
  .btn.primary { background: linear-gradient(135deg, #7289da, #5b6fc7); color: #fff; box-shadow: 0 2px 12px #7289da33; }
  .btn.primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 20px #7289da44; }
  .btn.secondary { background: #1a1d26; color: #7289da; border: 1px solid #7289da44; }
  .btn.secondary:hover:not(:disabled) { background: #7289da18; }
  .btn.ghost-danger { background: transparent; color: #666; border: 1px solid #1e2130; }
  .btn.ghost-danger:hover:not(:disabled) { color: #f04747; border-color: #f0474744; background: #f0474710; }
  .spinner {
    width: 13px; height: 13px; border: 2px solid #ffffff44;
    border-top-color: #fff; border-radius: 50%;
    animation: spin .7s linear infinite; display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Tabs ─────────────────────────────────────────────────────────────────── */
  .tab { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 14px; min-height: 0; overflow-y: auto; }
  .logs-tab { padding: 0; gap: 0; overflow: hidden; }

  /* ── Logs toolbar ────────────────────────────────────────────────────────── */
  .logs-toolbar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 16px; background: #13151c;
    border-bottom: 1px solid #1e2130;
    flex-shrink: 0;
  }
  .logs-count { font-size: 12px; color: #444; }
  .btn-sm {
    padding: 5px 12px; font-size: 11px; background: #1a1d26;
    border: 1px solid #1e2130; border-radius: 6px; color: #555; cursor: pointer;
    transition: all .15s;
  }
  .btn-sm:hover { color: #c8cdd4; border-color: #2a2f42; }
  .logs { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 0; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11.5px; }
  .log-line {
    display: flex; align-items: center; gap: 10px;
    padding: 4px 16px; border-bottom: 1px solid #0d0f1488;
    transition: background .1s;
  }
  .log-line:hover { background: #13151c; }
  .log-ts { color: #333; flex-shrink: 0; font-size: 10.5px; }
  .log-level-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; background: #444; }
  .log-line.info .log-level-dot { background: #4a4f6a; }
  .log-line.success .log-level-dot { background: #3ba55d; }
  .log-line.warn .log-level-dot { background: #faa61a; }
  .log-line.error .log-level-dot { background: #f04747; }
  .log-msg { color: #888; }
  .log-line.success .log-msg { color: #3ba55d; }
  .log-line.warn .log-msg { color: #faa61a; }
  .log-line.error .log-msg { color: #f04747; }
  .log-empty {
    display: flex; flex-direction: column; align-items: center; gap: 12px;
    padding: 60px 20px; color: #333;
  }
  .log-empty svg { width: 48px; height: 48px; }
  .log-empty p { font-size: 13px; font-family: -apple-system, sans-serif; }

  /* ── Settings ─────────────────────────────────────────────────────────────── */
  .settings-tab { gap: 14px; }
  .settings-tab label { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
  .label-text { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: .05em; }
  .settings-tab input {
    background: #0d0f14; border: 1px solid #1e2130; border-radius: 8px;
    padding: 9px 12px; color: #555; font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }
  .settings-hint { font-size: 11px; color: #333; margin-top: 4px; }
  .about-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: #888; }
  .gh-link {
    display: flex; align-items: center; gap: 6px;
    color: #7289da; text-decoration: none; font-size: 12px; font-weight: 500;
    padding: 6px 12px; border-radius: 8px; background: #7289da18;
    transition: background .15s;
  }
  .gh-link:hover { background: #7289da30; }
  .gh-link svg { width: 14px; height: 14px; }
</style>
