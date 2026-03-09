// Package plugin handles downloading the pre-built .3gx plugin from the server
// or building it on-demand for the current token.
package plugin

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

// DownloadOptions carries the parameters needed to fetch a personalised plugin.
type DownloadOptions struct {
	// ServerAPI is the HTTP base URL of the bridge server.
	ServerAPI string
	// Token is the unique per-user token (embedded in the plugin at build time).
	Token string
	// DestDir is where the downloaded .3gx file will be saved.
	DestDir string
}

// DownloadResult contains the path of the downloaded file and its version string.
type DownloadResult struct {
	Path    string
	Version string
}

// Download requests a personalised .3gx build from the server and saves it to
// DestDir/discord-rpc.3gx.  The server builds (or returns a cached build) for
// the given token, then streams the binary.
func Download(opts DownloadOptions) (DownloadResult, error) {
	client := &http.Client{Timeout: 120 * time.Second}

	params := url.Values{}
	params.Set("token", opts.Token)
	reqURL := opts.ServerAPI + "/plugin/build?" + params.Encode()

	resp, err := client.Get(reqURL)
	if err != nil {
		return DownloadResult{}, fmt.Errorf("plugin download request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return DownloadResult{}, fmt.Errorf("server returned %d: %s", resp.StatusCode, string(body))
	}

	version := resp.Header.Get("X-Plugin-Version")
	if version == "" {
		version = "unknown"
	}

	destPath := filepath.Join(opts.DestDir, "discord-rpc.3gx")
	if err := os.MkdirAll(opts.DestDir, 0o755); err != nil {
		return DownloadResult{}, fmt.Errorf("creating plugin dir: %w", err)
	}

	// Write to a temp file first, then rename atomically.
	tmp := destPath + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return DownloadResult{}, fmt.Errorf("creating temp file: %w", err)
	}

	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(tmp)
		return DownloadResult{}, fmt.Errorf("writing plugin: %w", err)
	}
	f.Close()

	if err := os.Rename(tmp, destPath); err != nil {
		os.Remove(tmp)
		return DownloadResult{}, fmt.Errorf("saving plugin: %w", err)
	}

	return DownloadResult{Path: destPath, Version: version}, nil
}
