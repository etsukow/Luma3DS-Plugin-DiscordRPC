// drpc — 3DS Discord RPC client
//
// Usage:
//
//	drpc install    — first-run: request token, download plugin, install OS service
//	drpc uninstall  — remove OS service
//	drpc update     — check for client + plugin updates
//	drpc run        — run daemon in foreground (used internally by the service)
//	drpc plugin     — re-download the personalised .3gx plugin
//	drpc status     — print current config and token
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	kservice "github.com/kardianos/service"

	"github.com/etsukow/luma3ds-drpc-client/internal/config"
	"github.com/etsukow/luma3ds-drpc-client/internal/plugin"
	"github.com/etsukow/luma3ds-drpc-client/internal/service"
	"github.com/etsukow/luma3ds-drpc-client/internal/token"
	"github.com/etsukow/luma3ds-drpc-client/internal/updater"
)

// Version is set at build time via -ldflags "-X main.Version=x.y.z".
var Version = "dev"

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[drpc] ")

	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	cmd := os.Args[1]
	args := os.Args[2:]

	switch cmd {
	case "install":
		cmdInstall(args)
	case "uninstall":
		cmdUninstall(args)
	case "update":
		cmdUpdate(args)
	case "run":
		cmdRun(args)
	case "plugin":
		cmdPlugin(args)
	case "status":
		cmdStatus(args)
	case "version", "--version", "-v":
		fmt.Printf("drpc %s\n", Version)
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n\n", cmd)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, `3DS Discord RPC client — v%s

Usage: drpc <command> [flags]

Commands:
  install    Request a token from the server, download the personalised
             .3gx plugin, and install the background service.
  uninstall  Remove the background service.
  update     Check for client and plugin updates.
  run        Run the daemon in the foreground (used by the OS service).
  plugin     Re-download the personalised .3gx plugin.
  status     Print the current configuration and token.
  version    Print the client version.

Environment / .env overrides:
  DRPC_SERVER_WS   WebSocket URL  (default: %s)
  DRPC_SERVER_API  HTTP API URL   (default: %s)
`, Version, config.DefaultServerWS, config.DefaultServerAPI)
}

// ── install ───────────────────────────────────────────────────────────────────

func cmdInstall(args []string) {
	fs := flag.NewFlagSet("install", flag.ExitOnError)
	serverAPI := fs.String("api", config.DefaultServerAPI, "Bridge server HTTP API URL")
	serverWS := fs.String("ws", config.DefaultServerWS, "Bridge server WebSocket URL")
	pluginDir := fs.String("plugin-dir", "", "Directory to save the .3gx plugin (default: config dir)")
	_ = fs.Parse(args)

	cfg, err := config.Load()
	if err != nil {
		log.Printf("warning: could not load existing config: %v", err)
	}

	// Apply flag overrides.
	if *serverAPI != config.DefaultServerAPI {
		cfg.ServerAPI = *serverAPI
	}
	if *serverWS != config.DefaultServerWS {
		cfg.ServerWS = *serverWS
	}

	// ── Step 1: provision token if not already present ─────────────────────
	if cfg.Token == "" {
		log.Printf("requesting token from %s …", cfg.ServerAPI)
		pr, err := token.Provision(cfg.ServerAPI)
		if err != nil {
			log.Fatalf("token provision failed: %v", err)
		}
		cfg.Token = pr.Token
		log.Printf("token received: %s", cfg.Token)
	} else {
		log.Printf("existing token found: %s", cfg.Token)
	}

	if err := config.Save(cfg); err != nil {
		log.Fatalf("save config: %v", err)
	}

	// ── Step 2: download personalised .3gx plugin ─────────────────────────
	pDir := *pluginDir
	if pDir == "" {
		dir, err := config.Dir()
		if err != nil {
			log.Fatalf("config dir: %v", err)
		}
		pDir = filepath.Join(dir, "plugin")
	}
	log.Printf("downloading personalised plugin to %s …", pDir)
	result, err := plugin.Download(plugin.DownloadOptions{
		ServerAPI: cfg.ServerAPI,
		Token:     cfg.Token,
		DestDir:   pDir,
	})
	if err != nil {
		log.Fatalf("plugin download failed: %v", err)
	}
	log.Printf("plugin saved: %s (version %s)", result.Path, result.Version)

	// ── Step 3: install OS service ─────────────────────────────────────────
	svc, err := buildService(cfg)
	if err != nil {
		log.Fatalf("build service: %v", err)
	}
	if err := svc.Install(); err != nil {
		// Already installed is fine.
		log.Printf("service install: %v", err)
	} else {
		log.Println("service installed ✓")
	}
	if err := svc.Start(); err != nil {
		log.Printf("service start: %v", err)
	} else {
		log.Println("service started ✓")
	}

	fmt.Println()
	fmt.Println("✅ Installation complete!")
	fmt.Printf("   Plugin path : %s\n", result.Path)
	fmt.Println("   Copy the .3gx to your 3DS SD card:")
	fmt.Println("   SD:/luma/plugins/<TitleID>/discord-rpc.3gx  (per-game)")
	fmt.Println("   SD:/luma/plugins/default/discord-rpc.3gx    (global fallback)")
}

// ── uninstall ─────────────────────────────────────────────────────────────────

func cmdUninstall(_ []string) {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	svc, err := buildService(cfg)
	if err != nil {
		log.Fatalf("build service: %v", err)
	}
	if err := svc.Stop(); err != nil {
		log.Printf("stop service: %v", err)
	}
	if err := svc.Uninstall(); err != nil {
		log.Fatalf("uninstall service: %v", err)
	}
	log.Println("service uninstalled ✓")
}

// ── update ────────────────────────────────────────────────────────────────────

func cmdUpdate(_ []string) {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	// Client binary update.
	log.Println("checking for client update…")
	updated, err := updater.CheckAndUpdate(cfg.ServerAPI, Version)
	if err != nil {
		log.Printf("client update check failed: %v", err)
	} else if updated {
		log.Println("client updated — please restart the service:")
		log.Println("  drpc uninstall && drpc install")
		return
	} else {
		log.Println("client is up to date ✓")
	}

	// Plugin update.
	if cfg.Token == "" {
		log.Println("no token configured — run 'drpc install' first")
		return
	}
	log.Println("checking for plugin update…")
	dir, err := config.Dir()
	if err != nil {
		log.Fatalf("config dir: %v", err)
	}
	result, err := plugin.Download(plugin.DownloadOptions{
		ServerAPI: cfg.ServerAPI,
		Token:     cfg.Token,
		DestDir:   filepath.Join(dir, "plugin"),
	})
	if err != nil {
		log.Printf("plugin update failed: %v", err)
		return
	}
	log.Printf("plugin updated: %s (version %s) ✓", result.Path, result.Version)
}

// ── run (foreground daemon) ───────────────────────────────────────────────────

func cmdRun(_ []string) {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	if cfg.Token == "" {
		log.Fatalf("no token found — run 'drpc install' first")
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	log.Printf("3DS Discord RPC daemon starting (version %s)", Version)
	log.Printf("server: %s", cfg.ServerWS)
	service.RunDirect(ctx, cfg)
}

// ── plugin ────────────────────────────────────────────────────────────────────

func cmdPlugin(args []string) {
	fs := flag.NewFlagSet("plugin", flag.ExitOnError)
	outDir := fs.String("out", "", "Output directory (default: config dir/plugin)")
	_ = fs.Parse(args)

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}
	if cfg.Token == "" {
		log.Fatalf("no token — run 'drpc install' first")
	}

	dir := *outDir
	if dir == "" {
		cfgDir, err := config.Dir()
		if err != nil {
			log.Fatalf("config dir: %v", err)
		}
		dir = filepath.Join(cfgDir, "plugin")
	}

	result, err := plugin.Download(plugin.DownloadOptions{
		ServerAPI: cfg.ServerAPI,
		Token:     cfg.Token,
		DestDir:   dir,
	})
	if err != nil {
		log.Fatalf("plugin download: %v", err)
	}
	fmt.Printf("plugin saved: %s (version %s)\n", result.Path, result.Version)
}

// ── status ────────────────────────────────────────────────────────────────────

func cmdStatus(_ []string) {
	cfg, err := config.Load()
	if err != nil {
		log.Printf("warning: %v", err)
	}
	path, _ := config.Path()
	fmt.Printf("config file : %s\n", path)
	fmt.Printf("server WS   : %s\n", cfg.ServerWS)
	fmt.Printf("server API  : %s\n", cfg.ServerAPI)
	fmt.Printf("token       : %s\n", maskToken(cfg.Token))
	fmt.Printf("discord app : %s\n", cfg.DiscordAppID)
	fmt.Printf("version     : %s\n", Version)
}

func maskToken(t string) string {
	if len(t) <= 8 {
		return "****"
	}
	return t[:4] + "…" + t[len(t)-4:]
}

// ── service plumbing ──────────────────────────────────────────────────────────

func buildService(cfg config.Config) (kservice.Service, error) {
	self, err := os.Executable()
	if err != nil {
		return nil, err
	}

	daemon := service.New(cfg)
	svcConfig := &kservice.Config{
		Name:        "luma3ds-discord-rpc",
		DisplayName: "3DS Discord RPC",
		Description: "Displays your Nintendo 3DS game on Discord Rich Presence.",
		Executable:  self,
		Arguments:   []string{"run"},
		Option: kservice.KeyValue{
			// macOS: run after login
			"RunAtLoad": true,
		},
	}
	return kservice.New(daemon, svcConfig)
}
