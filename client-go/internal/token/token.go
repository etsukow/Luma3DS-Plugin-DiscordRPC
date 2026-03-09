// Package token handles first-run token provisioning from the server.
package token

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ProvisionResponse is the JSON returned by POST /token.
type ProvisionResponse struct {
	Token   string `json:"token"`
	UDPHost string `json:"udp_host"`
	UDPPort int    `json:"udp_port"`
}

// Provision requests a new unique token from the server.
// serverAPI is the HTTP base URL, e.g. "https://api.etsukow.com".
func Provision(serverAPI string) (ProvisionResponse, error) {
	client := &http.Client{Timeout: 15 * time.Second}
	url := serverAPI + "/token"

	resp, err := client.Post(url, "application/json", bytes.NewBufferString("{}"))
	if err != nil {
		return ProvisionResponse{}, fmt.Errorf("token provision request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if err != nil {
		return ProvisionResponse{}, fmt.Errorf("reading token response: %w", err)
	}

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		return ProvisionResponse{}, fmt.Errorf("server returned %d: %s", resp.StatusCode, string(body))
	}

	var pr ProvisionResponse
	if err := json.Unmarshal(body, &pr); err != nil {
		return ProvisionResponse{}, fmt.Errorf("parsing token response: %w", err)
	}
	if pr.Token == "" {
		return ProvisionResponse{}, fmt.Errorf("server returned empty token")
	}
	return pr, nil
}
