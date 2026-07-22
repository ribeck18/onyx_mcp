package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"strings"
	"sync"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// OnyxClient calls the Onyx API for one user.
type OnyxClient struct {
	BaseURL    string
	PAT        string
	HTTPClient *http.Client

	stagedProjects   map[string]projectUpdate
	stagedProjectsMu sync.Mutex
}

func NewOnyxClient(baseURL, pat string) *OnyxClient {
	return &OnyxClient{
		BaseURL:        strings.TrimRight(baseURL, "/"),
		PAT:            pat,
		HTTPClient:     &http.Client{Timeout: 10 * time.Second},
		stagedProjects: make(map[string]projectUpdate),
	}
}

type apiError struct {
	StatusCode int
	Status     string
}

func (e *apiError) Error() string { return e.Status }

func (c *OnyxClient) apiGet(ctx context.Context, apiPath string) (json.RawMessage, error) {
	return c.api(ctx, http.MethodGet, apiPath, nil)
}

func (c *OnyxClient) apiPost(ctx context.Context, apiPath string, payload any) (json.RawMessage, error) {
	return c.api(ctx, http.MethodPost, apiPath, payload)
}

func (c *OnyxClient) apiPatch(ctx context.Context, apiPath string, payload any) (json.RawMessage, error) {
	return c.api(ctx, http.MethodPatch, apiPath, payload)
}

func (c *OnyxClient) api(ctx context.Context, method, apiPath string, payload any) (json.RawMessage, error) {
	endpoint, err := c.apiURL(apiPath)
	if err != nil {
		return nil, fmt.Errorf("build Onyx API URL: %w", err)
	}

	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return nil, fmt.Errorf("encode request body: %w", err)
		}
		body = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, endpoint, body)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+c.PAT)
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	client := c.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("reach Onyx: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return nil, &apiError{StatusCode: resp.StatusCode, Status: resp.Status}
	}

	var result json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decode Onyx response: %w", err)
	}
	return result, nil
}

func (c *OnyxClient) apiURL(apiPath string) (string, error) {
	base, err := url.Parse(c.BaseURL)
	if err != nil {
		return "", err
	}
	if base.Scheme == "" || base.Host == "" {
		return "", fmt.Errorf("base URL must be absolute")
	}
	base.Path = path.Join(base.Path, "api") + "/"
	ref, err := url.Parse(apiPath)
	if err != nil {
		return "", err
	}
	return base.ResolveReference(ref).String(), nil
}

func formatJSON(value json.RawMessage) (string, error) {
	var indented bytes.Buffer
	if err := json.Indent(&indented, value, "", "  "); err != nil {
		return "", fmt.Errorf("format Onyx response: %w", err)
	}
	return indented.String(), nil
}

func formattedResult(value json.RawMessage) (*mcp.CallToolResult, any, error) {
	text, err := formatJSON(value)
	return nil, text, err
}

func onyxError(err error) error {
	var apiErr *apiError
	if !errors.As(err, &apiErr) {
		return fmt.Errorf("could not reach Onyx: %w", err)
	}
	if apiErr.StatusCode == http.StatusUnauthorized {
		return fmt.Errorf("authentication to Onyx failed: your Personal Access Token is missing, expired, or revoked")
	}
	return fmt.Errorf("Onyx API request failed: %s", apiErr.Status)
}
