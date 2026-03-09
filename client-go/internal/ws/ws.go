// Package ws implements the WebSocket → Discord RPC bridge.
package ws

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"nhooyr.io/websocket"
	"nhooyr.io/websocket/wsjson"
)

// Presence is a message pushed by the server.
type Presence struct {
	Type    string `json:"type"`
	Event   string `json:"event"`
	TitleID string `json:"titleId"`
	Name    string `json:"name"`
	Icon    string `json:"icon"`
}

// Handler is called with each inbound presence update or clear event.
type Handler interface {
	OnPresence(p Presence)
	OnClear()
}

// Run connects to serverWS, authenticates with token, and dispatches events
// to handler.  It reconnects automatically on error until ctx is cancelled.
func Run(ctx context.Context, serverWS, token string, handler Handler) {
	backoff := 2 * time.Second
	for {
		if err := runOnce(ctx, serverWS, token, handler); err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Printf("[ws] disconnected: %v — reconnecting in %s", err, backoff)
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff):
			}
			if backoff < 60*time.Second {
				backoff *= 2
			}
		} else {
			backoff = 2 * time.Second
		}
	}
}

func runOnce(ctx context.Context, serverWS, token string, handler Handler) error {
	dialCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	conn, _, err := websocket.Dial(dialCtx, serverWS, nil)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.CloseNow()

	// Send auth frame.
	authFrame := map[string]string{"type": "auth", "token": token}
	if err := wsjson.Write(ctx, conn, authFrame); err != nil {
		return fmt.Errorf("auth write: %w", err)
	}

	log.Printf("[ws] connected to %s", serverWS)

	for {
		var raw json.RawMessage
		if err := wsjson.Read(ctx, conn, &raw); err != nil {
			return fmt.Errorf("read: %w", err)
		}

		var envelope struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(raw, &envelope); err != nil {
			continue
		}

		switch envelope.Type {
		case "presence":
			var p Presence
			if err := json.Unmarshal(raw, &p); err == nil {
				handler.OnPresence(p)
			}
		case "clear":
			handler.OnClear()
		}
	}
}
