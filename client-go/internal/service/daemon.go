// Package service implements the long-running daemon logic that:
//   - reads config
//   - authenticates with token over WebSocket
//   - updates Discord Rich Presence
//
// It satisfies kardianos/service.Interface so it can run as a native OS service.
package service

import (
	"context"
	"log"
	"time"

	kservice "github.com/kardianos/service"

	"github.com/etsukow/luma3ds-drpc-client/internal/config"
	"github.com/etsukow/luma3ds-drpc-client/internal/rpc"
	"github.com/etsukow/luma3ds-drpc-client/internal/ws"
)

// Daemon is the kardianos/service compatible daemon.
type Daemon struct {
	cfg    config.Config
	cancel context.CancelFunc
}

// New creates a Daemon from cfg.
func New(cfg config.Config) *Daemon {
	return &Daemon{cfg: cfg}
}

// Start implements kardianos/service.Interface.
func (d *Daemon) Start(s kservice.Service) error {
	ctx, cancel := context.WithCancel(context.Background())
	d.cancel = cancel
	go d.run(ctx)
	return nil
}

// Stop implements kardianos/service.Interface.
func (d *Daemon) Stop(s kservice.Service) error {
	if d.cancel != nil {
		d.cancel()
	}
	return nil
}

func (d *Daemon) run(ctx context.Context) {
	rpcClient := rpc.New(
		d.cfg.DiscordAppID,
		d.cfg.FallbackIcon,
		time.Duration(d.cfg.RPCMinInterval)*time.Second,
	)
	defer rpcClient.Close()

	handler := &presenceHandler{rpc: rpcClient}
	log.Printf("[service] connecting to %s", d.cfg.ServerWS)
	ws.Run(ctx, d.cfg.ServerWS, d.cfg.Token, handler)
}

type presenceHandler struct {
	rpc       *rpc.Client
	lastName  string
	gameStart int64
}

func (h *presenceHandler) OnPresence(p ws.Presence) {
	isStart := p.Event == "plugin_start"
	h.rpc.Update(p.Name, p.Icon, isStart)
}

func (h *presenceHandler) OnClear() {
	h.rpc.Clear()
}

// RunDirect runs the daemon in the foreground (no OS service wrapper).
func RunDirect(ctx context.Context, cfg config.Config) {
	d := New(cfg)
	d.run(ctx)
}
