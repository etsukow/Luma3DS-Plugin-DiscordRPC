// Package rpc wraps pypresence's equivalent logic in Go via Discord IPC.
// We shell out to discord-rpc via the local IPC socket (pipe on Windows,
// unix socket on macOS/Linux) using the go-ipc-rpc protocol.
//
// This package uses the "rich-go" library which speaks the Discord IPC
// protocol natively without needing a Python runtime.
package rpc

import (
	"fmt"
	"log"
	"time"
)

// ipcPath returns the Discord IPC socket path.
// We keep the IPC logic inside the discord sub-package for clarity.

// Client manages a single Discord Rich Presence connection.
type Client struct {
	appID        string
	fallbackIcon string
	minInterval  time.Duration

	pipe         ipcConn
	connected    bool
	lastUpdate   time.Time
	lastGameName string
	gameStart    int64
}

// ipcConn is the minimal interface we need from the IPC layer.
// The real implementation lives in rpc_ipc.go (build-tag split if needed).
type ipcConn interface {
	Connect() error
	SetActivity(activity Activity) error
	ClearActivity() error
	Close() error
}

// Activity mirrors Discord's activity payload.
type Activity struct {
	Details    string
	State      string
	LargeImage string
	LargeText  string
	StartEpoch int64
}

// New creates a new RPC Client (not yet connected).
func New(appID, fallbackIcon string, minInterval time.Duration) *Client {
	return &Client{
		appID:        appID,
		fallbackIcon: fallbackIcon,
		minInterval:  minInterval,
		pipe:         newIPCConn(appID),
	}
}

func (c *Client) ensureConnected() error {
	if c.connected {
		return nil
	}
	if err := c.pipe.Connect(); err != nil {
		return fmt.Errorf("discord IPC connect: %w", err)
	}
	c.connected = true
	log.Println("[rpc] Discord RPC connected ✓")
	return nil
}

func (c *Client) disconnect() {
	if c.pipe != nil {
		_ = c.pipe.Close()
	}
	c.connected = false
}

// Update sets the Discord presence to the given game.  Respects minInterval
// unless force=true.
func (c *Client) Update(name, icon string, force bool) {
	if !force && time.Since(c.lastUpdate) < c.minInterval {
		return
	}
	if name != c.lastGameName || force {
		c.gameStart = time.Now().Unix()
		c.lastGameName = name
	}
	imgKey := icon
	if imgKey == "" {
		imgKey = c.fallbackIcon
	}
	act := Activity{
		Details:    name,
		State:      "Nintendo 3DS",
		LargeImage: imgKey,
		LargeText:  name,
		StartEpoch: c.gameStart,
	}
	if err := c.ensureConnected(); err != nil {
		log.Printf("[rpc] connect error: %v", err)
		return
	}
	if err := c.pipe.SetActivity(act); err != nil {
		log.Printf("[rpc] SetActivity error: %v — reconnecting", err)
		c.disconnect()
		if err2 := c.ensureConnected(); err2 != nil {
			return
		}
		if err3 := c.pipe.SetActivity(act); err3 != nil {
			log.Printf("[rpc] SetActivity retry failed: %v", err3)
			c.disconnect()
			return
		}
	}
	c.lastUpdate = time.Now()
	log.Printf("[rpc] → %s", name)
}

// Clear removes the Discord presence.
func (c *Client) Clear() {
	if !c.connected {
		return
	}
	if err := c.pipe.ClearActivity(); err != nil {
		log.Printf("[rpc] ClearActivity: %v", err)
		c.disconnect()
	}
	c.lastGameName = ""
	c.gameStart = 0
	c.lastUpdate = time.Time{}
	log.Println("[rpc] presence cleared")
}

// Close shuts down the Discord IPC connection.
func (c *Client) Close() {
	c.disconnect()
}
