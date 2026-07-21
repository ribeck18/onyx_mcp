package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
)

// GetVDI returns the JSON representation of one vendor data item.
func (c *OnyxClient) GetVDI(ctx context.Context, vdiID int) (json.RawMessage, error) {
	endpoint, err := url.JoinPath(c.BaseURL, "api", "vdi", strconv.Itoa(vdiID))
	if err != nil {
		return nil, fmt.Errorf("build VDI URL: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("create VDI request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.PAT)

	client := c.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("get VDI %d: %w", vdiID, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("get VDI %d: %s", vdiID, resp.Status)
	}

	var vdi json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&vdi); err != nil {
		return nil, fmt.Errorf("decode VDI %d: %w", vdiID, err)
	}
	return vdi, nil
}
