// Package config loads and persists client configuration.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
)

const (
	DefaultServerWS  = "wss://api.etsukow.com"
	DefaultServerAPI = "https://api.etsukow.com"
	AppName          = "luma3ds-drpc"
)

// Config holds all runtime settings for the client daemon.
type Config struct {
	// ServerWS is the WebSocket URL of the bridge server.
	ServerWS string `json:"server_ws"`
	// ServerAPI is the HTTP base URL used for token requests and plugin builds.
	ServerAPI string `json:"server_api"`
	// Token is the unique per-user token obtained from the server at first run.
	Token string `json:"token,omitempty"`
	// DiscordAppID is the Discord application ID.
	DiscordAppID string `json:"discord_app_id"`
	// FallbackIcon is used when the game has no icon.
	FallbackIcon string `json:"fallback_icon"`
	// RPCMinInterval is the minimum seconds between Discord RPC updates.
	RPCMinInterval int `json:"rpc_min_interval"`
}

// DefaultConfig returns a config with sane defaults.
func DefaultConfig() Config {
	return Config{
		ServerWS:       DefaultServerWS,
		ServerAPI:      DefaultServerAPI,
		DiscordAppID:   "1480019559606911057",
		FallbackIcon:   "nintendo_3ds",
		RPCMinInterval: 15,
	}
}

// Dir returns the OS-specific config directory for the app.
func Dir() (string, error) {
	var base string
	switch runtime.GOOS {
	case "windows":
		base = os.Getenv("APPDATA")
		if base == "" {
			base = filepath.Join(os.Getenv("USERPROFILE"), "AppData", "Roaming")
		}
	case "darwin":
		base = filepath.Join(os.Getenv("HOME"), "Library", "Application Support")
	default:
		xdg := os.Getenv("XDG_CONFIG_HOME")
		if xdg != "" {
			base = xdg
		} else {
			base = filepath.Join(os.Getenv("HOME"), ".config")
		}
	}
	dir := filepath.Join(base, AppName)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

// Path returns the full path to the config file.
func Path() (string, error) {
	dir, err := Dir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "config.json"), nil
}

// Load reads the config from disk, returning defaults if no file exists yet.
func Load() (Config, error) {
	path, err := Path()
	if err != nil {
		return DefaultConfig(), err
	}
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return DefaultConfig(), nil
	}
	if err != nil {
		return DefaultConfig(), err
	}
	cfg := DefaultConfig()
	if err := json.Unmarshal(data, &cfg); err != nil {
		return DefaultConfig(), err
	}
	return cfg, nil
}

// Save writes the config to disk atomically.
func Save(cfg Config) error {
	path, err := Path()
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
