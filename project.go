package main

import (
	"context"
	"encoding/json"
	"fmt"
)

func (c *OnyxClient) getProject(ctx context.Context, projectId int) (json.RawMessage, error) {
	project, err := c.apiGet(ctx, "project", projectId)
	if err != nil {
		return nil, fmt.Errorf("Error getting project: %w", err)
	}

	return project, nil
}
