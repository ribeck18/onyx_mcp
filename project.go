package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type projectUpdate struct {
	ID          int     `json:"id"`
	Number      *string `json:"project_number,omitempty"`
	Name        *string `json:"name,omitempty"`
	Description *string `json:"description,omitempty"`
}

type ListAllProjectsInput struct{}

type GetSingleProjectInput struct {
	ProjectID int `json:"project_id" jsonschema:"the project's internal ID; use list_all_projects to find it"`
}

type CreateProjectInput struct {
	ProjectNumber      string  `json:"project_number" jsonschema:"the project number provided by the user"`
	ProjectName        string  `json:"project_name" jsonschema:"the project name"`
	ProjectDescription *string `json:"project_description,omitempty" jsonschema:"a short project scope summary"`
}

type StageProjectUpdateInput struct {
	ProjectID          int     `json:"project_id" jsonschema:"the project's internal ID"`
	ProjectNumber      *string `json:"project_number,omitempty" jsonschema:"the new project number, only when explicitly requested"`
	ProjectName        *string `json:"project_name,omitempty" jsonschema:"the new project name, only when explicitly requested"`
	ProjectDescription *string `json:"project_description,omitempty" jsonschema:"the new description, only when explicitly requested"`
}

type FinalizeProjectUpdateInput struct {
	StageKey string `json:"stage_key" jsonschema:"the key returned by stage_project_update after the user approves"`
}

func registerProjectTools(server *mcp.Server, client *OnyxClient) {
	mcp.AddTool(server, &mcp.Tool{
		Name:        "list_all_projects",
		Description: "List all projects with their internal ID, name, and project number.",
	}, client.ListAllProjects)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_single_project",
		Description: "Get one project. Use list_all_projects first to find its internal ID.",
	}, client.GetSingleProject)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "create_project",
		Description: "Create a project. Ask the user for the project number if they did not provide one.",
	}, client.CreateProject)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "stage_project_update",
		Description: "Stage explicit project changes. Show the staged changes and get approval before finalizing; do not reveal the stage key.",
	}, client.StageProjectUpdate)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "finalize_project_update",
		Description: "Apply a staged project update only after the user approves it.",
	}, client.FinalizeProjectUpdate)
}

func (c *OnyxClient) ListAllProjects(ctx context.Context, _ *mcp.CallToolRequest, _ ListAllProjectsInput) (*mcp.CallToolResult, any, error) {
	projects, err := c.apiGet(ctx, "projects")
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(projects)
}

func (c *OnyxClient) GetSingleProject(ctx context.Context, _ *mcp.CallToolRequest, input GetSingleProjectInput) (*mcp.CallToolResult, any, error) {
	project, err := c.apiGet(ctx, fmt.Sprintf("projects/%d", input.ProjectID))
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(project)
}

func (c *OnyxClient) CreateProject(ctx context.Context, _ *mcp.CallToolRequest, input CreateProjectInput) (*mcp.CallToolResult, any, error) {
	project, err := c.apiPost(ctx, "projects", struct {
		ProjectNumber string  `json:"project_number"`
		Name          string  `json:"name"`
		Description   *string `json:"description"`
	}{input.ProjectNumber, input.ProjectName, input.ProjectDescription})
	if err != nil {
		return nil, nil, onyxError(err)
	}
	return formattedResult(project)
}

func (c *OnyxClient) StageProjectUpdate(_ context.Context, _ *mcp.CallToolRequest, input StageProjectUpdateInput) (*mcp.CallToolResult, any, error) {
	key, err := stageKey()
	if err != nil {
		return nil, nil, err
	}
	c.stagedProjectsMu.Lock()
	c.stagedProjects[key] = projectUpdate{input.ProjectID, input.ProjectNumber, input.ProjectName, input.ProjectDescription}
	c.stagedProjectsMu.Unlock()
	return nil, fmt.Sprintf("The updates are staged. Show the user the proposed changes, get their approval, then finalize with stage key %s. Do not show the stage key to the user.", key), nil
}

func (c *OnyxClient) FinalizeProjectUpdate(ctx context.Context, _ *mcp.CallToolRequest, input FinalizeProjectUpdateInput) (*mcp.CallToolResult, any, error) {
	c.stagedProjectsMu.Lock()
	update, ok := c.stagedProjects[input.StageKey]
	if ok {
		delete(c.stagedProjects, input.StageKey)
	}
	c.stagedProjectsMu.Unlock()
	if !ok {
		return nil, nil, fmt.Errorf("no staged project is associated with that stage key")
	}

	project, err := c.apiPatch(ctx, fmt.Sprintf("projects/%d", update.ID), update)
	if err != nil {
		return nil, nil, onyxError(err)
	}
	formatted, err := formatJSON(project)
	if err != nil {
		return nil, nil, err
	}
	return nil, fmt.Sprintf("The project has been updated and is now: %s", formatted), nil
}

func stageKey() (string, error) {
	key := make([]byte, 16)
	if _, err := rand.Read(key); err != nil {
		return "", fmt.Errorf("generate stage key: %w", err)
	}
	return hex.EncodeToString(key), nil
}
