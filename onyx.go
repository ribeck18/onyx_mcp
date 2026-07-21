package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
)

func (c *OnyxClient) apiGet(ctx context.Context, path string, itemId int) (json.RawMessage, error) {
	endpoint, err := url.JoinPath(c.BaseURL + "api" + "vdi" + strconv.Itoa(itemId))
	if err != nil {
		return nil, fmt.Errorf("Build url: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("Build request: %w", err)
	}

	client := c.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("Get item %d: %v", itemId, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("get item %d: %s", itemId, resp.Status)
	}

	var jsonResponse json.RawMessage
	decoder := json.NewDecoder(resp.Body)
	decodeErr := decoder.Decode(&jsonResponse)
	if decodeErr != nil {
		return nil, fmt.Errorf("Decode response %d: %w", itemId, err)
	}

	return jsonResponse, nil
}
