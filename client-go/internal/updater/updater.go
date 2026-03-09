// Package updater checks for a newer client binary from the server and
// replaces the running executable if one is found.
package updater

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"time"
)

// ReleaseInfo is returned by GET /client/release.
type ReleaseInfo struct {
	Version  string `json:"version"`
	URL      string `json:"url"`
	SHA256   string `json:"sha256"`
	Filename string `json:"filename"`
}

// CheckAndUpdate queries the server for a newer client binary.
// currentVersion is the version string embedded at build time (ldflags).
// If a newer version exists, it downloads, verifies, replaces the binary, and
// returns true so the caller can restart.
func CheckAndUpdate(serverAPI, currentVersion string) (bool, error) {
	client := &http.Client{Timeout: 10 * time.Second}
	url := fmt.Sprintf("%s/client/release?os=%s&arch=%s&current=%s",
		serverAPI, runtime.GOOS, runtime.GOARCH, currentVersion)

	resp, err := client.Get(url)
	if err != nil {
		return false, fmt.Errorf("release check: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent {
		// Already up to date.
		return false, nil
	}
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("release check returned %d", resp.StatusCode)
	}

	var info ReleaseInfo
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return false, fmt.Errorf("parse release info: %w", err)
	}
	if info.URL == "" {
		return false, nil
	}

	log.Printf("[updater] new version %s available, downloading…", info.Version)
	newBinary, checksum, err := download(info.URL)
	if err != nil {
		return false, err
	}
	defer os.Remove(newBinary)

	if info.SHA256 != "" && checksum != info.SHA256 {
		return false, fmt.Errorf("checksum mismatch: got %s, want %s", checksum, info.SHA256)
	}

	if err := replace(newBinary); err != nil {
		return false, err
	}
	log.Printf("[updater] updated to %s — please restart", info.Version)
	return true, nil
}

func download(url string) (path, checksum string, err error) {
	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return "", "", fmt.Errorf("download: %w", err)
	}
	defer resp.Body.Close()

	tmp, err := os.CreateTemp("", "drpc-update-*")
	if err != nil {
		return "", "", err
	}

	h := sha256.New()
	if _, err := io.Copy(io.MultiWriter(tmp, h), resp.Body); err != nil {
		tmp.Close()
		os.Remove(tmp.Name())
		return "", "", fmt.Errorf("write download: %w", err)
	}
	tmp.Close()
	return tmp.Name(), hex.EncodeToString(h.Sum(nil)), nil
}

func replace(newBinary string) error {
	self, err := os.Executable()
	if err != nil {
		return err
	}
	self, err = filepath.EvalSymlinks(self)
	if err != nil {
		return err
	}

	// Make the new binary executable.
	if err := os.Chmod(newBinary, 0o755); err != nil {
		return err
	}

	// On Windows we can't replace a running binary; use a .old rename trick.
	old := self + ".old"
	_ = os.Remove(old)
	if err := os.Rename(self, old); err != nil {
		return fmt.Errorf("rename self to .old: %w", err)
	}
	if err := os.Rename(newBinary, self); err != nil {
		// Try to restore.
		_ = os.Rename(old, self)
		return fmt.Errorf("rename new binary: %w", err)
	}
	_ = os.Remove(old)
	return nil
}
