package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
)

func (c *OnyxClient) apiGet(ctx context.Context, path string, itemId int) (json.RawMessage, error) {
	endpoint, err := url.JoinPath(c.BaseURL, "api", path, strconv.Itoa(itemId))
	if err != nil {
		return nil, fmt.Errorf("Build url: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("Build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.PAT)

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
		return nil, fmt.Errorf("Decode response %d: %w", itemId, decodeErr)
	}

	return jsonResponse, nil
}

func (c *OnyxClient) ApiPost(ctx context.Context, path string, itemId int, payload map[string]string) (json.RawMessage, error) {
	endpoint, err := url.JoinPath(c.BaseURL, "api", path, strconv.Itoa(itemId))
	if err != nil {
		return nil, fmt.Errorf("Build url: %w", err)
	}

	//convert payload to []byte
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("payload to json: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("Build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.PAT)
	req.Header.Add("Content-Type", "application/json")

	client := c.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("post method response: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("get item %d: %s", itemId, resp.Status)
	}

	var jsonResponse json.RawMessage
	decoder := json.NewDecoder(resp.Body)
	decodeErr := decoder.Decode(&jsonResponse)
	if decodeErr != nil {
		return nil, fmt.Errorf("JSON decode: %w", decodeErr)
	}

	return jsonResponse, nil
}
