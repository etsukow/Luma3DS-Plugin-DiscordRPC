package rpc

import (
	"fmt"
	"time"

	richgo "github.com/hugolgst/rich-go/client"
)

// richGoConn wraps hugolgst/rich-go to satisfy ipcConn.
type richGoConn struct {
	appID string
}

func newIPCConn(appID string) ipcConn {
	return &richGoConn{appID: appID}
}

func (r *richGoConn) Connect() error {
	if err := richgo.Login(r.appID); err != nil {
		return fmt.Errorf("rich-go login: %w", err)
	}
	return nil
}

func (r *richGoConn) SetActivity(act Activity) error {
	start := time.Unix(act.StartEpoch, 0)
	return richgo.SetActivity(richgo.Activity{
		Details:    act.Details,
		State:      act.State,
		LargeImage: act.LargeImage,
		LargeText:  act.LargeText,
		Timestamps: &richgo.Timestamps{Start: &start},
	})
}

func (r *richGoConn) ClearActivity() error {
	// rich-go has no explicit clear; set an empty activity.
	return richgo.SetActivity(richgo.Activity{})
}

func (r *richGoConn) Close() error {
	richgo.Logout()
	return nil
}
